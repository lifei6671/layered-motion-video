"""Real TEST_ONLY media/cache probe; no production approval, models or downloads."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time


BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from static_comic.contracts import canonical, read_json
from static_comic.cache import publish
from static_comic import delivery
from static_comic.media import file_hash


def measure(root, label):
    reports=root/'reports'; reports.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,'-m','static_comic','preview','--project',str(root),'--technical-fixture']
    command_file=reports/f'{label}-command.json'
    command_file.write_bytes(canonical({'argv':command,'cwd':str(BASE),'label':label,
        'cache_expectation':'cold' if label=='cold' else 'warm'}))
    output=reports/f'measure-{label}'
    result=subprocess.run(['pwsh','-NoProfile','-File',str(BASE/'scripts/measure_performance.ps1'),
        '-CommandFile',str(command_file),'-OutputDirectory',str(output),'-TimeoutSeconds','1800'],
        cwd=BASE,capture_output=True,text=True,timeout=1860)
    if result.returncode:
        raise ValueError(f'{label}: preview failed; inspect {output}: '+result.stderr[-2000:])
    measured=read_json((output/'measurement.json').read_bytes())
    caches={p.stem:read_json(p.read_bytes()) for p in (root/'reports/cache').glob('*.json')}
    return {'command':command,'exit_code':result.returncode,'elapsed_seconds':measured['wall_seconds'],
            'peak_aggregate_rss_bytes':measured['sampled_peak_tree_working_set_bytes'],
            'measurement_status':measured['measurement_status'],'cache':caches,'measurement':str(output/'measurement.json')}



def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--performance',action='store_true')
    args=parser.parse_args()
    root=Path(args.project).resolve(strict=True); out=Path(args.output).resolve()
    if out.exists() and any(out.iterdir()): raise ValueError('Probe output must be new or empty')
    out.mkdir(parents=True,exist_ok=True)
    report={'artifact_kind':'technical_fixture','human_review':'NOT_RUN','production_accepted':False,
            'source_fixture':str(root),'performance':{},'tests':{}}
    # Low-level products are intentional test entrypoints, never human receipts.
    snap,compiled=delivery.snapshot(root,True,write=True); loc=delivery.locations(True)
    start=time.monotonic()
    visual,vr=delivery.visual_product(root,snap,compiled,loc,'final',True)
    master=root/snap.get('audio_reference',{}).get('path','work/audio/master_48k.wav')
    audible,mr=delivery.mux_product(root,visual,master,snap,'final')
    publish(root,{'output/technical/emphasis_1080.mp4':audible})
    report['formal_resolution']={'elapsed_seconds':time.monotonic()-start,'video':str(root/'output/technical/emphasis_1080.mp4'),
        'sha256':file_hash(audible),'visual':vr,'mux':mr}
    from static_comic.emphasis_preview import preview_evidence
    frames=preview_evidence(visual,compiled,{'preview':'reports/emphasis-1080'})
    publish(root,frames)
    report['tests']['eight_templates_rendered']=len(compiled['emphasis']['visual'])==8
    report['tests']['four_sfx_kinds']=len({e['kind'] for e in compiled['emphasis']['sfx']})==4
    from static_comic.sfx_mix import pcm
    stem=pcm(root/'work/audio/sfx_stem_48k.wav')
    report['tests']['silence_tail_zero']=not stem[48*48000:].any()
    report['tests']['zero_text_shots']=not any(e['shot_id'] in ('SHOT-009','SHOT-010') for e in compiled['emphasis']['visual'])
    if not all(report['tests'].values()): raise ValueError('Fixture acceptance failed')
    (out/'probe.json').write_bytes(canonical(report))
    if args.performance:
        for variant in ('baseline','basic','advanced','mixed'):
            target=out/variant
            for path in ('input','assets','work/alignment'):
                shutil.copytree(root/path,target/path)
            (target/'review').mkdir(parents=True)
            (target/'review/image_approvals.json').write_bytes(canonical({'schema_version':'1.0','receipts':[]}))
            (target/'work/audio').mkdir(parents=True)
            for name in ('master_48k.wav','align_16k.wav','audio.json'):
                if (root/'work/audio'/name).exists(): shutil.copy2(root/'work/audio'/name,target/'work/audio'/name)
            policy=read_json((target/'input/emphasis_policy.json').read_bytes())
            plan=read_json((target/'input/emphasis_plan.json').read_bytes())
            if variant=='baseline':
                policy.update(mode='disabled'); policy['visual']['enabled']=False
            if variant!='mixed': policy['audio']['enabled']=False
            if variant=='basic': plan['visual_events']=[e for e in plan['visual_events'] if e['tier']==1]
            (target/'input/emphasis_policy.json').write_bytes(canonical(policy))
            (target/'input/emphasis_plan.json').write_bytes(canonical(plan))
            cold=measure(target,'cold'); warm=measure(target,'warm')
            report['performance'][variant]={'cold':cold,'warm':warm}
            report['tests'][variant+'_cold_rebuilt']=all(cold['cache'][stage]['status']=='REBUILT'
                for stage in ('remotion-build','visual-preview','mux-preview'))
            report['tests'][variant+'_warm_hit']=all(warm['cache'][stage]['status']=='HIT'
                for stage in ('remotion-build','visual-preview','mux-preview'))
            report['tests'][variant+'_memory_measured']=all(r['measurement_status']=='PASS' for r in (cold,warm))
            (out/'probe.json').write_bytes(canonical(report))
            print(variant,round(cold['elapsed_seconds'],2),round(warm['elapsed_seconds'],2),flush=True)
        target=out/'mixed'
        before=read_json((target/'reports/technical/preview.json').read_bytes())
        plan=read_json((target/'input/emphasis_plan.json').read_bytes())
        plan['audio_events'][0]['gain_db']-=2
        (target/'input/emphasis_plan.json').write_bytes(canonical(plan))
        changed=measure(target,'gain-change')
        after=read_json((target/'reports/technical/preview.json').read_bytes())
        key='preview/technical/preview_visual.mp4'
        report['tests']['gain_only_visual_identical']=before['files'][key]==after['files'][key]
        report['tests']['gain_only_binding_changes']=delivery.review_binding(before)!=delivery.review_binding(after)
        report['gain_change']=changed
        report['tests']['gain_only_visual_cache_hit']=all(changed['cache'][stage]['status']=='HIT'
            for stage in ('remotion-build','visual-preview'))
        report['tests']['gain_only_audio_rebuilt']=all(changed['cache'][stage]['status']=='REBUILT'
            for stage in ('sfx-mix','mux-preview'))
        if not all(report['tests'].values()): raise ValueError('Real cache acceptance failed')
    (out/'probe.json').write_bytes(canonical(report))
    print(json.dumps({'status':'PASS','report':str(out/'probe.json'),'tests':report['tests']}))


if __name__=='__main__': main()
