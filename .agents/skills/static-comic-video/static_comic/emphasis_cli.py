"""Candidate planning never changes selected plans or supplies human approval."""
import argparse
import copy
import re

from .cache import publish
from .contracts import canonical, digest, read_json, validate
from .emphasis import empty_plan, load_manifest, load_policy, validate_plan
from .paths import read_bytes, resolve_path



def resource_workflow(root, action, *, kind=None, asset_id=None, signed_file=None):
    """Prepare a reviewable decision or apply a separately signed human receipt.

    A manifest APPROVED flag alone never authorizes a production resource.
    """
    from .emphasis import verify_asset
    from .project import check_human
    suffix = {'font': 'fonts', 'sfx': 'sfx'}
    if action == 'prepare-resource':
        if kind not in suffix or not asset_id:
            raise ValueError('prepare-resource requires --asset-kind and --asset-id')
        source = f"assets/{suffix[kind]}/manifest.json"
        manifest = validate('fontManifest' if kind == 'font' else 'sfxManifest',
                            read_json(read_bytes(root, source, 4*1024*1024)))
        entries = [item for item in manifest['assets'] if item['asset_id'] == asset_id]
        if len(entries) != 1 or entries[0]['review_status'] != 'APPROVED':
            raise ValueError('Resource must have a unique reviewed manifest entry')
        asset = verify_asset(root, entries[0], kind=suffix[kind], technical=True)
        proposal = {'schema_version':'1.0', 'asset_kind':kind, 'asset_id':asset_id,
                    'asset_sha256':asset['sha256'], 'asset_manifest_sha256':digest(asset),
                    'decision':'APPROVED'}
        path = f"review/resource-proposals/{kind}-{asset_id}.json"
        publish(root, {path:canonical(proposal)+b'\n'})
        return {'status':'REVIEW_REQUIRED', 'path':path,
                'next':'Review the resource and license, then human-confirm --scope resources; apply the signed receipt with emphasis approve-resource'}
    if action != 'approve-resource' or not signed_file:
        raise ValueError('approve-resource requires --file with a signed receipt')
    decision = validate('emphasisResourceDecision',
                        read_json(read_bytes(root, signed_file, 4*1024*1024)))
    check_human(decision['human'], scope='resources',
                expected={k:v for k,v in decision.items() if k != 'human'})
    kind = decision['asset_kind']
    manifest_name = f"assets/{suffix[kind]}/manifest.json"
    manifest = validate('fontManifest' if kind == 'font' else 'sfxManifest',
                        read_json(read_bytes(root, manifest_name, 4*1024*1024)))
    entries = [item for item in manifest['assets'] if item['asset_id'] == decision['asset_id']]
    if len(entries) != 1:
        raise ValueError('Signed approval refers to an unknown/ambiguous resource')
    asset = verify_asset(root, entries[0], kind=suffix[kind], technical=True)
    if (asset['review_status'] != 'APPROVED' or decision['asset_sha256'] != asset['sha256']
            or decision['asset_manifest_sha256'] != digest(asset)):
        raise ValueError('Resource review is stale, rejected or not current')
    path='review/emphasis_resource_approvals.json'
    target=resolve_path(root,path)
    current=validate('emphasisResourceApprovals',read_json(read_bytes(root,path,4*1024*1024))) if target.exists() else {'schema_version':'1.0','decisions':[]}
    others=[item for item in current['decisions'] if (item['asset_kind'],item['asset_id']) != (kind,decision['asset_id'])]
    updated=validate('emphasisResourceApprovals',{'schema_version':'1.0','decisions':others+[decision]})
    publish(root,{path:canonical(updated)+b'\n'})
    return {'status':'RESOURCE_REVIEW_APPLIED','asset_kind':kind,'asset_id':decision['asset_id'],'path':path}


def merge_candidates(current, candidate):
    """Explicit manual exclusions and fixed events survive candidate import."""
    merged=copy.deepcopy(candidate)
    for row in merged['shot_decisions']:
        previous=next(s for s in current['shot_decisions'] if s['shot_id']==row['shot_id'])
        for key,value in (('text_decision','skip'),('sfx_decision','silence')):
            if previous[key]==value:
                row[key]=value
                row['reason_code']='MANUAL_SKIP'; row['reason']=previous['reason']
    for key in ('visual_events','audio_events'):
        fixed=[e for e in current[key] if e['pinned']]
        ids={e['id'] for e in fixed}
        merged[key]=fixed+[e for e in merged[key] if e['id'] not in ids]
    merged['excluded']=current['excluded']+ [e for e in merged['excluded'] if e not in current['excluded']]
    return merged


def propose(root, compiled, *, provider, technical, candidate_file=None):
    """Make a non-authoritative plan. Agent proposals require actual supplied evidence."""
    board = read_json(read_bytes(root, 'input/storyboard.json', 4*1024*1024))
    script = read_bytes(root, 'input/script.txt', 4*1024*1024)
    ids = [shot['id'] for shot in board['shots']]
    policy = load_policy(root)
    observations = compiled['emphasis']['observations']
    if observations is None:
        return {'status':'DISABLED', 'reason':'Enable visual/audio before proposing'}
    if provider == 'agent':
        if not candidate_file:
            return {'status':'UNAVAILABLE', 'reason':'No visual Agent runtime is configured in this CLI',
                    'next':'Have an authorized Agent actually inspect current work/emphasis/frames PNGs and observations, produce a checked episode-relative JSON plan and input/emphasis_observations.json; then run emphasis propose --provider agent --file <plan-path> followed by emphasis import',
                    'evidence_frames':{s['shot_id']:[v['path'] for v in s['samples']]
                                       for s in observations['shots']}}
        if not all(item['provider']=='agent' and item['status']=='DECLARED_OBSERVATION'
                   for item in observations['shots']):
            raise ValueError('Agent proposal requires current agent-declared observations for every shot; inspect real frames first')
        candidate = validate_plan(
            read_json(read_bytes(root,candidate_file,4*1024*1024)),
            script_bytes=script,shot_ids=ids)
        if any(event['source']!='agent' and not event['pinned']
               for event in candidate['visual_events']+candidate['audio_events']):
            raise ValueError('Agent candidates must declare their true source; manual fixed items are preserved at import')
        path=('work/emphasis/technical' if technical else 'work/emphasis')+'/proposals.json'
        publish(root,{path:canonical(candidate)+b'\n'})
        return {'status':'PROPOSED','path':path,'visual_candidates':len(candidate['visual_events']),
                'sfx_candidates':len(candidate['audio_events']),
                'model_observation':'DECLARED_VIEWED',
                'provider':'external_agent_submission',
                'note':'Declared agent observation is a provenance claim; it does not authenticate execution',
                'selected_plan_changed':False}

    text = script.decode('utf-8-sig')
    plan = empty_plan(script,ids)
    assets = {}
    if policy['audio']['enabled'] and resolve_path(root,'assets/sfx/manifest.json').exists():
        assets = load_manifest(root,'sfx',technical=technical)

    def sound_for(kind):
        candidates=[a for a in assets.values() if kind in a['tags']]
        return min(candidates,key=lambda a:a['asset_id']) if candidates else None

    def sound_event(shot, kind, anchor):
        if not policy['audio']['enabled'] or kind not in policy['audio']['uses']:
            return
        asset = sound_for(kind)
        if asset is None:
            return
        index = sum(e['id'].startswith('SE-'+shot['id']+'-') for e in plan['audio_events'])
        plan['audio_events'].append({
            'id':f'SE-{shot["id"]}-{kind}-{index}', 'kind':kind,
            'sfx_asset_id':asset['asset_id'], 'anchor':anchor,
            'gain_db':policy['audio']['default_sfx_gain_db'],
            'fade_in_samples':240,'fade_out_samples':960,
            'pinned':False,'source':'rules'})

    for index,(shot,row,observation) in enumerate(zip(board['shots'],plan['shot_decisions'],observations['shots'])):
        lo,hi=shot['script_range']
        passage=text[lo:hi]
        quiet=(observation['emotion']=='quiet'
               or any(word in passage for word in ('沉思','哀悼','安静','默哀')))
        if quiet:
            row.update(text_decision='skip',sfx_decision='silence',
                       reason_code='QUIET_NARRATIVE',reason='旁白或实际观察标注为克制情绪')
            continue
        busy=all(values and max(m['edge'] for m in values)>26
                 for values in observation['regions'].values())
        if busy:
            row.update(text_decision='skip',reason_code='VISUAL_BUSY',
                       reason='当前候选区均为高边缘复杂度，跳过视觉强调')
        match=re.search(r'[0-9]+(?:\.[0-9]+)?(?:%|％|元|倍|万|亿)',passage)
        if (match and not busy and policy['visual']['enabled']
                and policy['visual']['selection']=='adaptive'):
            event_id='VE-'+shot['id']
            plan['visual_events'].append({
                'id':event_id,'shot_id':shot['id'],
                'script_range':[lo+match.start(),lo+match.end()],'text':match[0],
                'semantic_type':'number','importance':'high','preset':'number_tick',
                'tier':1,'layout':{'preset':'upper_right'},
                'pinned':False,'source':'rules'})
            row.update(reason_code='KEY_NUMBER',
                       reason='原文数值候选，仍需声学和动态布局检查')
            sound_event(shot,'keyword',{
                'type':'visual_marker','visual_event_id':event_id,
                'marker':'impact','offset_samples':0})

        # Narration punctuation/verbs are evidence of an explicit rhetorical beat.
        for word in ('突然','发现','原来','转折'):
            at=passage.find(word)
            if at>=0:
                sound_event(shot,'narrative',{
                    'type':'speech_start','shot_id':shot['id'],
                    'script_range':[lo+at,lo+at+len(word)],'offset_samples':0})
                break

        # Real pictured actions require matching inspected evidence, not just
        # a script guess. A declared visual observation can still be rejected
        # by the user's final audible preview review.
        scene_words=('敲门','关门','脚步','打字','雨声','铃声')
        if (observation.get('provider') in ('agent','human')
                and observation.get('status')=='DECLARED_OBSERVATION'):
            for word in scene_words:
                at=passage.find(word)
                if at>=0 and word in observation['reason']:
                    sound_event(shot,'scene',{
                        'type':'speech_start','shot_id':shot['id'],
                        'script_range':[lo+at,lo+at+len(word)],'offset_samples':0})
                    break
            transition=shot['transition_out']
            if transition and transition['type']!='cut' and observation['emotion']=='energetic':
                sound_event(shot,'transition',{
                    'type':'transition_frame','from_shot_id':shot['id'],
                    'point':'mid','offset_samples':0})

    validate_plan(plan,script_bytes=script,shot_ids=ids)
    path=('work/emphasis/technical' if technical else 'work/emphasis')+'/proposals.json'
    publish(root,{path:canonical(plan)+b'\n'})
    return {'status':'PROPOSED','path':path,
            'visual_candidates':len(plan['visual_events']),
            'sfx_candidates':len(plan['audio_events']),
            'model_observation':'NOT_RUN','selected_plan_changed':False}


def main(argv):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('group',choices=('emphasis','sfx'))
    parser.add_argument('command',choices=('propose','import','inspect','verify','mix','prepare-resource','approve-resource'))
    parser.add_argument('--asset-kind',choices=('font','sfx'))
    parser.add_argument('--asset-id')
    parser.add_argument('--project',required=True)
    parser.add_argument('--technical-fixture',action='store_true')
    parser.add_argument('--provider',choices=('rules','agent'),default='rules')
    parser.add_argument('--file')
    args=parser.parse_args(argv)
    from .project import compile_project, load_project
    if args.group=='emphasis' and args.command in ('prepare-resource','approve-resource'):
        return resource_workflow(args.project,args.command,kind=args.asset_kind,
                                 asset_id=args.asset_id,signed_file=args.file)
    if args.group=='emphasis' and args.command=='import':
        if not args.file:
            raise ValueError('import requires --file with an episode-relative proposal path')
        docs,_,_=load_project(args.project)
        ids=[s['id'] for s in docs['storyboard']['shots']]
        script=read_bytes(args.project,'input/script.txt',4*1024*1024)
        candidate=validate_plan(read_json(read_bytes(args.project,args.file,4*1024*1024)),script_bytes=script,shot_ids=ids)
        existing=resolve_path(args.project,'input/emphasis_plan.json')
        if existing.exists():
            current=validate_plan(read_json(existing.read_bytes()),script_bytes=script,shot_ids=ids)
            candidate=merge_candidates(current,candidate)
            validate_plan(candidate,script_bytes=script,shot_ids=ids)
        publish(args.project,{'input/emphasis_plan.json':canonical(candidate)+b'\n'})
        return {'status':'IMPORTED','path':'input/emphasis_plan.json','requires_compile':True}
    allowed={'emphasis':('propose','inspect','verify'),'sfx':('inspect','mix')}
    if args.command not in allowed[args.group]:
        raise ValueError('Unsupported command for '+args.group)
    compiled=compile_project(args.project,technical_fixture=args.technical_fixture,write=args.command in ('propose','mix','verify'))
    if args.command=='propose':
        return propose(args.project,compiled,provider=args.provider,
                       technical=args.technical_fixture,candidate_file=args.file)
    if args.command=='mix':
        from .sfx_mix import mix
        return mix(args.project,compiled['emphasis']['sfx'],compiled['emphasis_policy']['audio'])
    return {'status':'PASS','artifact_kind':compiled['artifact_kind'],
            'visual':compiled['emphasis']['visual'],'sfx':compiled['emphasis']['sfx'],
            'diagnostics':compiled['emphasis']['diagnostics'],'human_review':'NOT_RUN'}
