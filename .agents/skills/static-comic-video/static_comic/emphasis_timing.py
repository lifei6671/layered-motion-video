"""Compile independent visual and sound events on the existing integer clock."""
from pathlib import Path
import re

from .contracts import canonical, digest, read_json, validate
from .emphasis_layout import choose_layout
from .emphasis_vision import observe
from .paths import read_bytes, resolve_path
from .timeline import frame_at


def speech_samples(aligned, source_range):
    """Consume every reading character intersecting this exact source range.

    The caller has already run speech.apply_alignment's evidence replay. A
    partial number token (e.g. one digit of 300%) must never become a timestamp.
    """
    if aligned is None:
        raise ValueError('TIMING_UNCERTAIN: no replayed character alignment')
    lo, hi = source_range
    ranges = aligned['reading_map']['source_ranges']
    chars = aligned['characters']
    selected = [i for i,(a,b) in enumerate(ranges) if a < hi and lo < b]
    if not selected or any(not lo <= ranges[i][0] < ranges[i][1] <= hi for i in selected):
        raise ValueError('TIMING_UNCERTAIN: partial or missing reading token')
    if any(chars[i]['source'] != 'acoustic_aligned' or chars[i]['samples'] is None for i in selected):
        raise ValueError('TIMING_UNCERTAIN: low-score, interpolated or manual/coarse evidence')
    pairs = [chars[i]['samples'] for i in selected]
    if any(not 0 <= a < b for a,b in pairs) or any(a[1] > b[0] for a,b in zip(pairs,pairs[1:])):
        raise ValueError('TIMING_UNCERTAIN: non-monotonic character evidence')
    return [pairs[0][0], pairs[-1][1]]


def stable_window(index, timing):
    shot = timing[index]
    incoming = timing[index-1]['transition_out'] if index else None
    outgoing = shot['transition_out']
    return (shot['start_frame']+(incoming['post_frames'] if incoming else 0),
            shot['end_frame']-(outgoing['pre_frames'] if outgoing else 0))


def compile_events(root, extension, board, execution, geometry, prepared, *, motion_cards=None, technical=False, write=True):
    policy, plan = extension['policy'], extension['plan']
    enabled = policy['visual']['enabled'] or policy['audio']['enabled']
    if not enabled:
        return {'visual':[], 'sfx':[], 'diagnostics':[], 'outputs':{}, 'resources':[], 'observations':None}
    aligned = None
    if resolve_path(root, 'work/alignment/aligned.json').exists():
        aligned = read_json(read_bytes(root,'work/alignment/aligned.json',32*1024*1024))
    shot_map = {s['id']: (i,s) for i,s in enumerate(board['shots'])}
    # 这些动作帧由 MotionCardTrack 中受控的 3 个配方约定，不从外部注入。
    cards = {c['id']: c for c in (motion_cards or [])}
    card_markers = {'talkcraft-number-slab': {'enter': 8, 'impact': 24},
                    'talkcraft-ink-underline': {'enter': 6, 'impact': 28},
                    'talkcraft-chapter-card': {'enter': 5, 'impact': 28}}
    decisions = {s['shot_id']:s for s in plan['shot_decisions']}
    samples = board['audio']['duration_samples']
    candidate_frames = {}
    for event in plan['visual_events']:
        try:
            interval = speech_samples(aligned,event['script_range'])
            candidate_frames.setdefault(event['shot_id'],[]).extend([frame_at(s) for s in interval])
        except ValueError:
            pass  # Per-event diagnostic below preserves this reason.
    observations, outputs = observe(root, execution, geometry, prepared, technical=technical,
                                    candidate_frames=candidate_frames)
    obs = {s['shot_id']:s for s in observations['shots']}
    visual, sfx, diagnostics, resources = [], [], [], []
    blocking = []
    excluded = {e['id']:e for e in plan['excluded']}

    def reject(event, reason, detail=None):
        status = 'REVIEW_REQUIRED' if event['pinned'] else 'SKIPPED'
        record = {'id':event['id'], 'status':status, 'reason_code':reason, 'detail':detail}
        diagnostics.append(record)
        if event['pinned']:
            blocking.append(record)

    # Human-fixed events reserve capacity. For the remaining candidates semantic
    # importance wins before script order; IDs only break otherwise equal ties.
    rank = {'high': 0, 'medium': 1, 'low': 2}
    visual_order = sorted(plan['visual_events'], key=lambda e: (
        not e['pinned'], rank[e['importance']], e['script_range'][0],
        e['script_range'][1], e['id']))
    sound_order = sorted(plan['audio_events'], key=lambda e: (not e['pinned'], e['id']))
    for event in visual_order:
        sid = event['shot_id']; index, shot = shot_map[sid]
        if event['id'] in excluded:
            reject(event,'MANUAL_SKIP',excluded[event['id']]); continue
        if not policy['visual']['enabled'] or decisions[sid]['text_decision'] == 'skip':
            reject(event,'MANUAL_SKIP' if policy['visual']['enabled'] else 'DISABLED'); continue
        if policy['visual']['selection'] == 'manual' and (
                not event['pinned'] or not all(k in event['layout'] for k in ('x', 'y'))):
            reject(event, 'MANUAL_SELECTION_REQUIRED',
                   'Manual selection requires a pinned event with explicit x/y; no auto-position fallback')
            continue
        lo,hi = event['script_range']; a,b = shot['script_range']
        if not a <= lo < hi <= b:
            raise ValueError(event['id']+': script_range crosses its declared shot')
        if event['preset'] in ('fragment_disperse','particle_assemble'):
            reject(event,'UNAVAILABLE','Template not implemented'); continue
        if event['tier'] == 2 and not policy['visual']['allow_advanced']:
            reject(event,'DISABLED','Advanced effects disabled'); continue
        if any(c in event['text'] for c in '\r\n\t'):
            reject(event,'UNSUPPORTED_MULTILINE'); continue
        if event['preset']=='number_tick':
            numeric = re.fullmatch(r'([+-]?[0-9]+(?:\.[0-9]{1,6})?)(?:%|％|元|倍|万|亿|人|次|个)?',event['text'])
            if numeric is None or abs(float(numeric[1])) > 9007199254740991:
                reject(event,'UNPARSEABLE_NUMBER'); continue
        try:
            interval = speech_samples(aligned,event['script_range'])
        except ValueError as error:
            reject(event,'TIMING_UNCERTAIN',str(error)); continue
        anchor = frame_at(interval[0]); enter = event.get('enter_frames',12); exit_frames=event.get('exit_frames',10)
        start = anchor-max(1,enter//2)
        hold = event.get('hold_frames',max(18,frame_at(interval[1])-(start+enter)+1))
        end = start+enter+hold+exit_frames
        lower,upper = stable_window(index,execution)
        if enter < 2 or exit_frames < 2 or hold > 300 or not lower <= start < end <= upper or end > upper:
            reject(event,'TIMING_WINDOW',{'proposed':[start,end],'stable':[lower,upper]}); continue
        if frame_at(interval[1]) > start+enter+hold or (event['tier']==2 and end-start>90):
            reject(event,'TIMING_WINDOW','Speech or advanced duration exceeds budget'); continue
        vp = policy['visual']
        same_shot=[e for e in visual if e['shot_id']==sid]
        neighbors=[e for e in visual if abs(e['start_frame']-start)<1800]
        if (len(same_shot)>=vp['max_events_per_shot'] or len(neighbors)>=vp['max_events_per_minute']
                or any(start < e['end_frame']+vp['min_gap_frames'] and e['start_frame'] < end+vp['min_gap_frames'] for e in visual)
                or (event['preset']=='comic_burst' and any(e['preset']=='comic_burst' for e in same_shot))):
            reject(event,'DENSITY_BUDGET'); continue
        asset = extension['fonts'][event.get('font_asset_id',next(iter(extension['fonts'])))]
        data = read_bytes(root,asset['path'],64*1024*1024)
        layout, detail = choose_layout(event,data,obs[sid],geometry[index],vp)
        if layout is None:
            reject(event,detail['reason_code'],detail); continue
        font_path = f"fonts/{asset['sha256']}{Path(asset['path']).suffix.lower()}"
        prepared[font_path] = data
        if not any(r['path']==font_path for r in resources):
            resources.append({'path':font_path,'sha256':asset['sha256'],'asset_id':asset['asset_id'],'kind':'font'})
        markers = {'enter_start':start,'impact':anchor,'settle':start+enter,'exit_start':start+enter+hold}
        theme = policy['visual']['theme']
        theme_colors = {'comic_bright':('#ffcf33','#171717'), 'comic_ink':('#171717','#ffffff'),
                        'minimal':(detail['color'],detail['stroke_color']), 'cinematic':('#fff2d5','#171717')}
        color,outline = theme_colors.get(theme,(detail['color'],detail['stroke_color']))
        locked = {'id':event['id'],'shot_id':sid,'text':event['text'],'preset':event['preset'],'tier':event['tier'],
            'start_frame':start,'end_frame':end,'anchor_frame':anchor,'enter_frames':enter,'hold_frames':hold,
            'exit_frames':exit_frames,'markers':markers,'layout':layout,'font_asset_id':asset['asset_id'],
            'font_path':font_path,'font_sha256':asset['sha256'],'color':event.get('color',color),
            'stroke_color':event.get('stroke_color',outline), 'stroke_width':event.get('stroke_width',3),
            'shadow_px':event.get('shadow_px',4),'seed':int(digest([event['id'],asset['sha256']])[:8],16),
            'script_range':event['script_range'],'speech_samples':interval}
        visual.append(validate('compiledVisualEmphasis',locked))
        diagnostics.append({'id':event['id'],'status':'ACCEPTED','layout':detail,'precision':'acoustic_aligned'})
    normalized = {}
    for event in sound_order:
        if event['id'] in excluded:
            reject(event,'MANUAL_SKIP',excluded[event['id']]); continue
        if not policy['audio']['enabled'] or event['kind'] not in policy['audio']['uses']:
            reject(event,'DISABLED'); continue
        anchor = event['anchor']; origin = anchor['type']; sid = anchor.get('shot_id',anchor.get('from_shot_id'))
        marker_frame = None
        if origin == 'motion_marker':
            linked = cards.get(anchor['motion_card_id'])
            if linked is None:
                reject(event, 'MOTION_CARD_UNAVAILABLE')
                continue
            sid = linked['shot_id']
            local = card_markers[linked['recipe']]
            marker_frame = (linked['end_frame'] - 6 if anchor['marker'] == 'exit'
                            else linked['start_frame'] + local[anchor['marker']])
            start = marker_frame * 1600
        elif origin == 'visual_marker':
            linked = next((e for e in visual if e['id']==anchor['visual_event_id']),None)
            if linked is None:
                reject(event,'VISUAL_EVENT_UNAVAILABLE'); continue
            sid=linked['shot_id']; start=linked['markers'][anchor['marker']]*1600
        elif origin == 'speech_start':
            shot=shot_map[sid][1]; a,b=shot['script_range']; lo,hi=anchor['script_range']
            if not a<=lo<hi<=b:
                raise ValueError(event['id']+': speech anchor crosses declared shot')
            try:
                start=speech_samples(aligned,anchor['script_range'])[0]
            except ValueError as error:
                reject(event,'TIMING_UNCERTAIN',str(error)); continue
        elif origin == 'shot_start':
            start=execution[shot_map[sid][0]]['start_frame']*1600
        else:
            tr=execution[shot_map[sid][0]]['transition_out']
            if tr is None:
                reject(event,'NO_TRANSITION'); continue
            first,last=tr['transition_start_frame'],tr['transition_end_frame']
            start={'start':first,'mid':(first+last)//2,'end':last}[anchor['point']]*1600
        start+=anchor['offset_samples']
        if decisions[sid]['sfx_decision']=='silence' or obs[sid]['emotion']=='quiet':
            reject(event,'MANUAL_SILENCE' if decisions[sid]['sfx_decision']=='silence' else 'QUIET_NARRATIVE'); continue
        asset=extension['sfx'][event['sfx_asset_id']]
        from .sfx_library import normalize_asset
        if asset['asset_id'] not in normalized:
            normalized[asset['asset_id']]=normalize_asset(root,asset,write=write,technical=technical)
        sound=normalized[asset['asset_id']]
        trim=event.get('trim_start_sample',0); trim_end=event.get('trim_end_sample',sound['samples'])
        length=trim_end-trim
        # 可对齐音效的实际声学峰值，而非仅将文件开头放到事件帧。
        sync = event.get('sync_to')
        cue = asset.get('cue_points')
        if sync is not None and cue is None:
            reject(event, 'SYNC_POINT_UNAVAILABLE'); continue
        # 原有事件没有 sync_to 时，始终以裁剪后音效文件开头对齐，保持兼容。
        relative_sync = cue[sync + '_samples'] - trim if sync is not None else 0
        if not 0 <= trim < trim_end <= sound['samples'] or not 0 <= relative_sync < length:
            reject(event,'AUDIO_SYNC_TRIM_CONFLICT'); continue
        start -= relative_sync
        if start < 0 or start >= samples:
            reject(event,'AUDIO_BOUNDS'); continue
        silence=[s for s in execution if decisions[s['id']]['sfx_decision']=='silence' or obs[s['id']]['emotion']=='quiet']
        # The sound must never play inside a silent logical shot. Trim only when
        # explicitly opted in, and taper the truncated tail to avoid a hard cut.
        cutoff = samples
        for quiet_shot in silence:
            begin, finish = quiet_shot['start_frame']*1600, min(samples, quiet_shot['end_frame']*1600)
            if begin <= start < finish:
                cutoff = start
                break
            if start < begin:
                cutoff = min(cutoff, begin)
        clipped = start + length > cutoff
        if clipped:
            if not event.get('allow_tail_trim', False):
                reject(event, 'SILENCE_TAIL_CONFLICT' if cutoff < samples else 'AUDIO_BOUNDS')
                continue
            length = cutoff-start
        if length < 1 or event['fade_in_samples'] >= length:
            reject(event, 'AUDIO_BOUNDS' if length < 1 else 'FADE_BOUNDS')
            continue
        fade_out = event['fade_out_samples']
        if clipped:
            fade_out = max(fade_out, min(960, max(1,length//4)))
            fade_out = min(fade_out, length-event['fade_in_samples'])
        if event['fade_in_samples'] + fade_out > length:
            reject(event,'FADE_BOUNDS'); continue
        ap=policy['audio']
        if sum(abs(e['start_sample']-start)<2880000 for e in sfx)>=ap['max_events_per_minute']:
            reject(event,'DENSITY_BUDGET'); continue
        boundaries=sorted({start,*[e['start_sample'] for e in sfx if start<=e['start_sample']<start+length]})
        if any(1+sum(e['start_sample']<=t<e['start_sample']+e['play_samples'] for e in sfx)>ap['max_concurrent'] for t in boundaries):
            reject(event,'CONCURRENT_BUDGET'); continue
        locked={'id':event['id'],'kind':event['kind'],'asset_id':asset['asset_id'],'asset_sha256':asset['sha256'],
            'start_sample':start,'source_trim_samples':trim,'play_samples':length,'gain_db':event['gain_db'],
            'fade_in_samples':event['fade_in_samples'],'fade_out_samples':fade_out,
            'normalized_path':sound['normalized_path'],'normalized_sha256':sound['normalized_sha256'],
            'anchor':anchor}
        if sync is not None:
            locked['sync_to'] = sync
        if marker_frame is not None:
            locked['motion_frame'] = marker_frame
        sfx.append(validate('compiledSfxEvent',locked))
        diagnostics.append({'id':event['id'],'status':'ACCEPTED','anchor_origin':anchor,'shot_id':sid,
                            'source':asset,'start_sample':start,'synced_sample':start+relative_sync,
                             'expected_frame':marker_frame,'sync_to':sync})
    visual.sort(key=lambda e:(e['start_frame'],e['id'])); sfx.sort(key=lambda e:(e['start_sample'],e['id']))
    base='work/emphasis/technical' if technical else 'work/emphasis'
    report={'status':'REVIEW_REQUIRED' if blocking else 'PASS','events':diagnostics,'shot_decisions':plan['shot_decisions'],
            'input_hashes':extension['input_hashes'],'observations_sha256':digest(observations),'human_review':'NOT_RUN'}
    visual_lock={'artifact_kind':observations['artifact_kind'],'events':visual,
                 'input_hashes':extension['input_hashes'],'observations_sha256':digest(observations)}
    sfx_lock={'artifact_kind':observations['artifact_kind'],'events':sfx,'input_hashes':extension['input_hashes']}
    for name,value in [('observations',observations),('visual.lock',visual_lock),('sfx.lock',sfx_lock),('diagnostics',report)]:
        outputs[f'{base}/{name}.json']=canonical(value)+b'\n'
    if blocking:
        if write:
            from .cache import publish
            publish(root,outputs)
        raise ValueError('REVIEW_REQUIRED: fixed emphasis conflict: '+', '.join(e['id']+'/'+e['reason_code'] for e in blocking))
    return {'visual':visual,'sfx':sfx,'diagnostics':diagnostics,'outputs':outputs,'resources':resources,
            'observations':observations}
