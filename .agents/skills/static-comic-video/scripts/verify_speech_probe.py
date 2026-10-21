"""Run actual local speech integration probes; all projects are technical fixtures."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from static_comic.contracts import bytes_digest,canonical


def negative_fixture(source, target, kind):
    if target.exists():
        raise ValueError("Negative fixture target must be new")
    for name in ("input","assets","review"):
        shutil.copytree(source/name,target/name)
    with wave.open(str(source/'input/voice.wav'),'rb') as audio:
        params=audio.getparams(); frames=audio.readframes(audio.getnframes())
    unit=params.nchannels*params.sampwidth; rate=params.framerate
    if kind=='missing':
        frames=frames[:6*rate*unit]+frames[int(12.8*rate)*unit:]
    else:
        frames=frames[:int(15.8*rate)*unit]
    with wave.open(str(target/'input/voice.wav'),'wb') as audio:
        audio.setparams(params); audio.writeframes(frames)
    board=json.loads((target/'input/storyboard.json').read_text(encoding='utf-8'))
    board['audio']['sha256']=bytes_digest((target/'input/voice.wav').read_bytes())
    # Input duration is only a placeholder: real align obtains it from decoded PCM.
    (target/'input/storyboard.json').write_bytes(canonical(board))
    overrides=json.loads((target/'input/overrides.json').read_text(encoding='utf-8'))
    overrides['audio_sha256']=board['audio']['sha256']
    overrides['storyboard_sha256']=bytes_digest((target/'input/storyboard.json').read_bytes())
    (target/'input/overrides.json').write_bytes(canonical(overrides))


def main():
    reports=ROOT/'reports/sc-p3'
    for name in ('missing','truncated'):
        negative_fixture(reports/'normal',reports/name,name)
    checks=[]
    for name in ('normal','missing','truncated'):
        for operation in ('align','compile'):
            command=[sys.executable,'-m','static_comic',operation,'--project',str(reports/name),'--technical-fixture']
            start=time.perf_counter()
            run=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=2100,check=False)
            (reports/f'{name}-{operation}.stdout').write_bytes(run.stdout)
            (reports/f'{name}-{operation}.stderr').write_bytes(run.stderr)
            expected=0 if name=='normal' else (3 if operation=='align' else 2)
            checks.append({'command':command,'exit_code':run.returncode,'expected_exit':expected,
                           'seconds':round(time.perf_counter()-start,3),'status':'PASS' if run.returncode==expected else 'FAIL'})
            (reports/'integration.json').write_bytes(canonical(checks))
            print(name,operation,checks[-1]['status'],flush=True)
    return 0 if all(c['status']=='PASS' for c in checks) else 1


if __name__=='__main__': raise SystemExit(main())
