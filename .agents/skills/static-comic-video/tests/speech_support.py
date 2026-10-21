"""Synthetic model evidence for unit tests ONLY. Never actual speech approval."""
from io import BytesIO
import wave

from static_comic.contracts import canonical
from static_comic.paths import write_bytes
from static_comic.project import load_project
from static_comic.speech import VERSION, binding, evaluate, store_evidence
from static_comic.speech_audio import wav_info
from static_comic.speech_text import make_plan


def synthetic_windows(plan):
    windows = []
    for w in plan["windows"]:
        length = (w["input_16k"][1]-w["input_16k"][0])/16000
        step = length / (len(w["text"])+1)
        chars = [{"char":c,"start":round(i*step,3),"end":round((i+0.8)*step,3),"score":0.9}
                 for i,c in enumerate(w["text"])]
        windows.append({"window":w,"result":{"segments":[{"chars":chars}]},"dictionary_characters":list(set(w["text"]))})
    return windows


def seed_alignment(root, technical_fixture=False):
    docs,hashes,_ = load_project(root); board=docs["storyboard"]
    script=(root/"input/script.txt").read_bytes().decode("utf-8-sig")
    samples=board["audio"]["duration_samples"]
    coarse={"backend_matches":True,"response":{"segments":[
        {"start":s["speech_interval_samples"][0]/48000,"end":s["speech_interval_samples"][1]/48000,
         "text":script[s["script_range"][0]:s["script_range"][1]]} for s in board["shots"]]}}
    plan=make_plan(script,board,coarse,[],samples); windows=synthetic_windows(plan)
    audio={}
    for key,rate,channels,name in (("master",48000,2,"master_48k.wav"),("align",16000,1,"align_16k.wav")):
        out=BytesIO()
        with wave.open(out,"wb") as w:
            w.setnchannels(channels); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(b"\0\0"*((samples if rate==48000 else (samples+2)//3)*channels))
        data=out.getvalue(); write_bytes(root,"work/audio/"+name,data); audio[key]=wav_info(data)
    bind=binding(board,hashes,technical_fixture)
    raw={"binding":bind,"audio":audio,"coarse_ref":store_evidence(root,coarse),"plan":plan,"windows":windows}
    result=evaluate(board,plan,windows,[],samples)
    assert result["status"]=="PASS",result
    aligned={"version":VERSION,"binding":bind,"raw_ref":store_evidence(root,raw),**result}
    write_bytes(root,"work/alignment/aligned.json",canonical(aligned))
    return aligned
