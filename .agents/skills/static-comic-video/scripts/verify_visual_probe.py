"""Decode every frame and compare the Remotion visual track with SC-P1 geometry.

FFmpeg is used only for decoding/inspection, never to synthesize motion/transitions.
"""
import argparse
import copy
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageChops, ImageStat
from static_comic.contracts import bytes_digest, read_json
from static_comic.images import motion_at

SIZE=(320,180)


def expected_frame(props, sources, frame):
    shots=props["shots"]
    active=[s for s in shots if s["sequence_start_frame"]<=frame<s["sequence_start_frame"]+s["physical_frames"]]
    def shot_image(s):
        source=sources[s["id"]]
        state=motion_at(s["motion"],frame-s["sequence_start_frame"],s,*source.size)
        x,y,w,h=state["crop"]
        return source.resize(SIZE,Image.Resampling.BICUBIC,box=(x,y,x+w,y+h))
    if len(active)==1: return shot_image(active[0]),False
    if len(active)!=2: raise AssertionError(f"Unexpected active shot count at {frame}: {len(active)}")
    old,new=active
    tr=old["transition_out"]; k=frame-tr["transition_start_frame"]; length=tr["duration_frames"]
    a,b=shot_image(old),shot_image(new); progress=k/length
    if tr["type"]=="fade": return Image.blend(a,b,progress),False
    if tr["type"].startswith("wipe"):
        mask=Image.new("L",SIZE,0)
        count=round(SIZE[0]*progress)
        if count:
            from PIL import ImageDraw
            box=(0,0,count-1,SIZE[1]-1) if tr["type"]=="wipe_from_left" else (SIZE[0]-count,0,SIZE[0]-1,SIZE[1]-1)
            ImageDraw.Draw(mask).rectangle(box,fill=255)
        return Image.composite(b,a,mask),False
    if tr["type"]=="fade_black":
        middle=(length-1)//2
        black=Image.new("RGB",SIZE)
        if k<=middle: return Image.blend(a,black,k/middle),k==middle
        return Image.blend(black,b,(k-middle)/(length-1-middle)),False
    raise AssertionError(tr["type"])


def verify(video, project, output):
    video,project,output=Path(video),Path(project),Path(output)
    output.mkdir(parents=True,exist_ok=True)
    props_path=project/"work/remotion/technical/props.json"
    props=read_json(props_path.read_bytes())
    assert props["artifact_kind"]=="technical_fixture"
    sources={}
    source_hashes={}
    for shot in props["shots"]:
        path=project/"work/remotion/technical/public"/shot["staged_image"]
        raw=path.read_bytes(); assert bytes_digest(raw)==shot["image_sha256"]
        sources[shot["id"]]=Image.open(path).convert("RGB")
        source_hashes[shot["staged_image"]]=bytes_digest(raw)
    probe=subprocess.run(["ffprobe","-v","error","-show_streams","-show_format","-show_frames",
                          "-show_entries","frame=best_effort_timestamp,pkt_duration","-of","json",str(video)],
                         capture_output=True,check=True,timeout=120)
    metadata=json.loads(probe.stdout)
    streams=metadata["streams"];assert len(streams)==1 and streams[0]["codec_type"]=="video"
    stream=streams[0]; total=props["video"]["total_frames"]
    for key,value in {"codec_name":"h264","width":1920,"height":1080,"pix_fmt":"yuv420p",
                      "sample_aspect_ratio":"1:1","r_frame_rate":"30/1","avg_frame_rate":"30/1",
                      "color_space":"bt709"}.items():
        assert stream.get(key)==value,(key,stream.get(key),value)
    assert int(stream["nb_frames"])==total
    pts=[Fraction(f["best_effort_timestamp"])*Fraction(stream["time_base"]) for f in metadata["frames"]]
    assert pts==[Fraction(i,30) for i in range(total)],"Non-contiguous presentation timestamps"
    (output/"ffprobe.json").write_bytes(probe.stdout)
    keys={0,total-1}
    for shot in props["shots"]:
        keys.update((shot["start_frame"],shot["end_frame"]-1))
        if shot["transition_out"] and shot["transition_out"]["duration_frames"]:
            tr=shot["transition_out"];start=tr["transition_start_frame"];end=tr["transition_end_frame"]
            keys.update((start-1,start,start+(end-start-1)//2,end-1,end))
    comparisons=[]; black_frames=[]; expected_black=[]; direction_checks=[]
    error_file=(output/"decode.log").open("wb")
    command=["ffmpeg","-v","error","-xerror","-i",str(video),"-map","0:v:0","-f","rawvideo","-pix_fmt","rgb24","pipe:1"]
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=error_file)
    try:
        for frame in range(total):
            raw=process.stdout.read(1920*1080*3)
            assert len(raw)==1920*1080*3,f"Truncated decode at {frame}"
            actual=Image.frombytes("RGB",(1920,1080),raw)
            small=actual.resize(SIZE,Image.Resampling.BICUBIC)
            expected,is_black=expected_frame(props,sources,frame)
            mae=sum(ImageStat.Stat(ImageChops.difference(small,expected)).mean)/3
            if max(small.getextrema()[c][1] for c in range(3))<=3: black_frames.append(frame)
            if is_black: expected_black.append(frame)
            comparisons.append({"frame":frame,"mae_rgb":round(mae,4)})
            for index,shot in enumerate(props["shots"]):
                tr=shot["transition_out"]
                if (tr and tr["type"].startswith("wipe") and
                        frame==tr["transition_start_frame"]+(tr["duration_frames"]-1)//2):
                    reversed_props=copy.deepcopy(props)
                    reversed_props["shots"][index]["transition_out"]["type"]=(
                        "wipe_from_right" if tr["type"]=="wipe_from_left" else "wipe_from_left")
                    wrong,_=expected_frame(reversed_props,sources,frame)
                    reversed_mae=sum(ImageStat.Stat(ImageChops.difference(small,wrong)).mean)/3
                    direction_checks.append({"frame":frame,"type":tr["type"],"correct_mae":mae,
                                             "reversed_mae":reversed_mae,"passed":mae+5<reversed_mae})
            if frame in keys: actual.save(output/f"frame-{frame:04}.png")
        assert not process.stdout.read(1),"Unexpected extra decoded frame"
        assert process.wait(timeout=30)==0,"FFmpeg full decode failed"
    finally:
        process.stdout.close()
        if process.poll() is None: process.kill();process.wait()
        error_file.close()
    worst=max(comparisons,key=lambda x:x["mae_rgb"])
    # Allows H.264 chroma subsampling and browser-vs-Pillow filter differences.
    failures=[]
    if worst["mae_rgb"]>5: failures.append(f"Visual oracle mismatch: {worst}")
    if black_frames!=expected_black: failures.append(f"Black frames {black_frames} != expected {expected_black}")
    if any(not check["passed"] for check in direction_checks): failures.append("Wipe direction did not match fixture")
    report={"status":"FAIL" if failures else "PASS","video_sha256":bytes_digest(video.read_bytes()),
            "props_sha256":bytes_digest(props_path.read_bytes()),"snapshot_hashes":source_hashes,
            "frames":total,"fps":"30/1","width":1920,"height":1080,"audio_streams":0,
            "pts_contiguous":True,"full_decode":True,"worst_frame":worst,
            "black_frames":black_frames,"expected_black_frames":expected_black,
            "direction_checks":direction_checks,
            "comparisons":comparisons,"failures":failures}
    (output/"verification.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    assert not failures,"; ".join(failures)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video",required=True);parser.add_argument("--project",required=True);parser.add_argument("--output",required=True)
    args=parser.parse_args()
    result=verify(args.video,args.project,args.output)
    print(json.dumps({k:result[k] for k in ("status","frames","worst_frame","black_frames")}))
