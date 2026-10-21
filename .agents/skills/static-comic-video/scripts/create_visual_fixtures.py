"""Generate deterministic comic-style rendering fixtures."""
import argparse
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from create_fixture import create_fixture
from static_comic.contracts import canonical, bytes_digest, read_json
from static_comic.project import compile_project


def make_project(root, cuts_only=False):
    board = create_fixture(root)
    root = Path(root)
    template = board["shots"][0]
    asset_template = read_json((root/"assets/images/manifest.json").read_bytes())["assets"][0]
    motions = ["static","zoom_in","zoom_out","pan_x","pan_y","static","static","static","static"]
    labels = ["STATIC", "ZOOM IN", "ZOOM OUT", "PAN X", "PAN Y", "FADE BLACK / EVEN", "FADE BLACK / ODD", "CUT", "ONE FRAME"]
    effects = ["cut","fade","cut","wipe_from_left","wipe_from_right","fade_black","fade_black","cut"]
    lengths = [60]*8+[1]
    if cuts_only:
        motions, labels, effects, lengths = ["static"]*3, ["CUT A","CUT B","CUT C"], ["cut"]*2, [20]*3
    palette = ["#f4d8b2","#c8dfdb","#e7c9c2","#c7d9e8","#d9d3e7","#f4dfb0","#bdd9bf","#d3d9de","#f4d8b2"]
    # Known system font for readable labels inside the static technical artwork.
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 56)
    small = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 30)
    shots, assets = [], []
    start = 0
    for i,(motion,n,label) in enumerate(zip(motions,lengths,labels)):
        shot=copy.deepcopy(template); asset=copy.deepcopy(asset_template)
        sid=f"SHOT-{i+1:03}"; name=f"assets/images/shot_{i+1:04}.png"
        shot.update(id=sid,image=name,script_range=[i,i+1],start_samples=start*1600,
                    speech_interval_samples=[start*1600,(start+n)*1600],transition_out=None,
                    subject_bbox=[.35,.30,.65,.75])
        m=shot["motion"]
        m.update(type=motion,scale_from=1,scale_to=1,crop_anchor_from=[.5,.5],crop_anchor_to=[.5,.5])
        if motion=="zoom_in": m["scale_to"]=1.18
        if motion=="zoom_out": m["scale_from"]=1.18
        if motion.startswith("pan"):
            m.update(scale_from=1.2,scale_to=1.2)
            axis=0 if motion=="pan_x" else 1
            m["crop_anchor_from"][axis]=.15; m["crop_anchor_to"][axis]=.85
        art=Image.new("RGB",(2560,1440),palette[i])
        d=ImageDraw.Draw(art)
        ink="#202c39"
        d.rounded_rectangle((180,150,2380,1280),radius=34,fill="#fff8e9",outline=ink,width=8)
        d.text((280,220),f"{i+1:02}  /  {label}",font=font,fill=ink)
        d.text((280,310),"SC-P2  /  1080p 30fps  /  TECHNICAL FIXTURE",font=small,fill=ink)
        # Comic panel: horizon, windows, desk, person, cup and speech balloon.
        for x in (400,1800):
            d.rectangle((x,480,x+360,840),outline=ink,width=6)
            d.line((x+180,480,x+180,840),fill=ink,width=4)
            d.line((x,660,x+360,660),fill=ink,width=4)
        d.ellipse((1090,450,1370,730),fill=palette[i],outline=ink,width=9)
        d.arc((1100,450,1360,690),180,350,fill=ink,width=15)
        d.ellipse((1170,570,1185,590),fill=ink)
        d.ellipse((1270,570,1285,590),fill=ink)
        d.arc((1180,610,1280,655),5,175,fill=ink,width=4)
        d.rounded_rectangle((1020,730,1440,1080),radius=60,fill=palette[i],outline=ink,width=9)
        d.line((840,980,1640,980),fill=ink,width=14)
        d.line((930,980,900,1190),fill=ink,width=9)
        d.line((1550,980,1580,1190),fill=ink,width=9)
        d.rectangle((1400,875,1490,970),fill="#fff8e9",outline=ink,width=6)
        d.arc((1470,890,1530,950),270,90,fill=ink,width=6)
        d.ellipse((1450,405,1660,555),fill="#fff8e9",outline=ink,width=5)
        d.text((1500,445),"Hi!",font=font,fill=ink)
        # High-contrast spatial-frequency target at native source resolution.
        for x in range(350,750,5): d.line((x,1040,x,1160),fill=ink,width=1)
        d.text((350,1180),"FINE-LINE TARGET",font=small,fill=ink)
        art.save(root/name,format="PNG")
        raw=(root/name).read_bytes()
        asset.update(shot_id=sid,path=name,sha256=bytes_digest(raw),prompt="Deterministic comic geometry test panel")
        assets.append(asset); shots.append(shot); start+=n
    for i,effect in enumerate(effects):
        length=0 if effect=="cut" else (11 if i in (3,6) else 12)
        placements=["end_at_anchor","start_at_anchor","center_on_anchor"]
        shots[i]["transition_out"]={
            "to_shot_id":shots[i+1]["id"],"relation":"technical","evidence":"Known fixture boundary",
            "visual_evidence":"Two generated geometric panels","intent":labels[i]+" to "+labels[i+1],
            "type":effect,"duration_frames":length,"placement":placements[i%3],
            "semantic_anchor_samples":shots[i+1]["start_samples"],"planning_source":"technical_fixture",
            "image_hashes":[assets[i]["sha256"],assets[i+1]["sha256"]]}
    script=("测"*len(shots)).encode("utf-8")
    (root/"input/script.txt").write_bytes(script)
    # These fixtures use the SC-P1 known-clock contract. Keep a matching silence WAV.
    import wave
    with wave.open(str(root/"input/voice.wav"),"wb") as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(48000)
        audio.writeframes(b"\0\0"*(start*1600))
    board.update(episode_id="all-cuts" if cuts_only else "motion-transitions",
                 script_sha256=bytes_digest(script),shots=shots)
    board["audio"].update(duration_samples=start*1600,sha256=bytes_digest((root/"input/voice.wav").read_bytes()))
    (root/"input/storyboard.json").write_bytes(canonical(board)+b"\n")
    (root/"assets/images/manifest.json").write_bytes(canonical({"schema_version":"1.0","assets":assets})+b"\n")
    return compile_project(root,technical_fixture=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    output=Path(args.output)
    for name,cuts in (("showcase",False),("all-cuts",True)):
        result=make_project(output/name,cuts)
        print(name,result["total_frames"])
