"""Inspect decoded technical frames; missing renders stay NOT_RUN, never PASS."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, ImageChops, ImageStat

BASE = Path(__file__).resolve().parents[1]


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def dimensions(video, expected):
    command = [shutil.which('ffprobe'), '-v', 'error', '-select_streams', 'v:0',
               '-show_entries', 'stream=width,height,avg_frame_rate,nb_frames', '-of', 'json', str(video)]
    result = subprocess.run(command, capture_output=True, timeout=60, check=True)
    stream = json.loads(result.stdout)['streams'][0]
    if (stream['width'], stream['height']) != expected or stream['avg_frame_rate'] != '30/1':
        raise ValueError('Unexpected frame geometry or fps: '+str(stream))
    return stream


def extract(video, indices, destination, expected):
    destination.mkdir(parents=True, exist_ok=True)
    indices = sorted(set(indices))
    select = '+'.join(f'eq(n\\,{frame})' for frame in indices)
    command = [shutil.which('ffmpeg'), '-v', 'error', '-nostdin', '-y', '-i', str(video),
               '-map', '0:v:0', '-vf', 'select='+select, '-fps_mode', 'passthrough', '-frames:v', str(len(indices)),
               '-threads', '1', str(destination/'selected-%06d.png')]
    result = subprocess.run(command, capture_output=True, timeout=180, check=False)
    (destination/'ffmpeg.log').write_bytes(result.stdout+result.stderr)
    if result.returncode:
        raise ValueError('Frame extraction failed: '+result.stderr.decode(errors='replace'))
    files = {}
    for ordinal, frame in enumerate(indices, 1):
        source = destination/f'selected-{ordinal:06}.png'
        if not source.is_file(): raise ValueError(f'Missing decoded global frame {frame}')
        with Image.open(source) as image:
            if image.size != expected: raise ValueError('Extracted frame size mismatch')
        target = destination/f'frame-{frame:06}.png'; source.replace(target)
        files[frame] = target
    return files, command


def difference(first, second):
    if first.size != second.size: raise ValueError('Pixel comparison requires equal dimensions')
    delta = ImageChops.difference(first.convert('RGB'),second.convert('RGB'))
    histogram = delta.histogram()
    channels = first.width*first.height*3
    return {'mae_8bit':sum(ImageStat.Stat(delta).mean)/3,
            'channel_fraction_gt_8':sum(histogram[channel*256+value] for channel in range(3) for value in range(9,256))/channels,
            'max_difference':max(upper for _,upper in delta.getextrema())}


def verify_marker_indices(props, low, high):
    expected=set()
    for event in props.get('visual_emphasis',[]):
        points={'before':max(0,event['start_frame']-1),**event['markers'],
                'exit':event['end_frame']-1,'after':min(props['video']['total_frames']-1,event['end_frame'])}
        expected.update((event['id'],marker,frame) for marker,frame in points.items())
    key=lambda row:(row['id'],row['marker'],row['global_frame'])
    lo={key(row):row for row in low}; hi={key(row):row for row in high}
    if len(lo)!=len(low) or len(hi)!=len(high) or set(lo)!=expected or set(hi)!=expected:
        raise ValueError('Event marker/global frame inventories differ from current props or contain duplicates')
    return lo,hi


def check(root, baseline):
    props_path = root/'work/remotion/technical/props.json'
    props = read(props_path)
    if props['artifact_kind'] != 'technical_fixture':
        raise ValueError('This script only accepts explicit technical fixtures')
    output = root/'reports/emphasis-1080'; output.mkdir(parents=True, exist_ok=True)
    report = {'artifact_kind':'technical_fixture','props_sha256':digest(props_path),
              'human_visual_review':'NOT_RUN','checks':{}, 'thresholds':{
                  'scale_comparison_full_mae':3,'scale_comparison_event_roi_mae':15,
                  'zero_text_mae':1,'zero_text_channel_fraction_gt_8':.005},
              'limits':'Sparse decoded-frame regression; not a complete subjective viewing or listening approval.'}
    video = root/'output/technical/emphasis_1080.mp4'
    preview = root/'preview/technical/preview_visual.mp4'
    transition_rows = []
    for shot in props['shots']:
        tr = shot['transition_out']
        if not tr: continue
        selected = {'before':tr['transition_start_frame']-1,'start':tr['transition_start_frame'],
                    'anchor':shot['end_frame'],'last':tr['transition_end_frame']-1,
                    'after':tr['transition_end_frame']}
        transition_rows += [{'shot_id':shot['id'],'type':tr['type'],'marker':marker,'global_frame':frame}
                            for marker,frame in selected.items() if 0<=frame<props['video']['total_frames']]
    if not video.is_file():
        report['checks']['transitions']={'status':'NOT_RUN','reason':'1080 render missing','path':str(video)}
    else:
        try:
            stream = dimensions(video,(1920,1080))
            files,command = extract(video,[r['global_frame'] for r in transition_rows],output/'transitions',(1920,1080))
            for row in transition_rows:
                file=files[row['global_frame']]; row.update(path=str(file.relative_to(root)),sha256=digest(file),size=[1920,1080])
            report['checks']['transitions']={'status':'PASS','stream':stream,'video_sha256':digest(video),
                'command':command,'frames':transition_rows}
            (output/'transitions/index.json').write_text(json.dumps(transition_rows,ensure_ascii=False,indent=2),encoding='utf-8')
        except (ValueError,subprocess.SubprocessError,KeyError,IndexError) as error:
            report['checks']['transitions']={'status':'FAIL','reason':str(error)}
    preview_index = root/'preview/technical/emphasis.json'
    final_index = output/'emphasis.json'
    if not preview_index.is_file() or not final_index.is_file():
        report['checks']['preview_final_semantics']={'status':'NOT_RUN','reason':'One event frame index is missing'}
    else:
        try:
            low = read(preview_index)['visual_frames']; high = read(final_index)['visual_frames']
            lo,hi=verify_marker_indices(props,low,high)
            events={event['id']:event for event in props.get('visual_emphasis',[])}
            pairs=[]
            for identity,row in lo.items():
                first=root/row['path']; second=root/hi[identity]['path']
                with Image.open(first) as a, Image.open(second) as b:
                    if a.size!=(960,540) or b.size!=(1920,1080): raise ValueError('Event frame dimensions differ from profiles')
                    scaled=b.resize(a.size,Image.Resampling.LANCZOS)
                    metric=difference(a,scaled)
                    layout=events[identity[0]]['layout']
                    box=(max(0,int(layout['x']*960)-30),max(0,int(layout['y']*540)-30),
                         min(960,int((layout['x']+layout['width'])*960)+30),
                         min(540,int((layout['y']+layout['height'])*540)+30))
                    roi=difference(a.crop(box),scaled.crop(box))
                passed=metric['mae_8bit']<=3 and roi['mae_8bit']<=15
                pairs.append({'id':identity[0],'marker':identity[1],'global_frame':identity[2],
                    'status':'PASS' if passed else 'FAIL','full_frame':metric,'event_roi':roi,
                    'preview':row['path'],'preview_sha256':digest(first),'final':hi[identity]['path'],'final_sha256':digest(second)})
            report['checks']['preview_final_semantics']={'status':'PASS' if pairs and all(p['status']=='PASS' for p in pairs) else 'FAIL',
                'meaning':'Both inventories equal markers derived from current props; actual decoded image pairs at both sizes meet fixed pixel-distance limits.',
                'pairs':pairs}
        except (ValueError,KeyError,OSError) as error:
            report['checks']['preview_final_semantics']={'status':'FAIL','reason':str(error)}
    baseline_video=baseline/'preview/technical/preview_visual.mp4'
    baseline_props=baseline/'work/remotion/technical/props.json'
    if not baseline_video.is_file() or not baseline_props.is_file() or not preview.is_file():
        report['checks']['zero_text_baseline']={'status':'NOT_RUN','reason':'Baseline or mixed preview missing'}
    else:
        try:
            base_props=read(baseline_props)
            if base_props['video']!=props['video'] or base_props['shots']!=props['shots'] or base_props.get('visual_emphasis'):
                raise ValueError('Baseline geometry/timing/images differ or baseline contains text events')
            dimensions(preview,(960,540)); dimensions(baseline_video,(960,540))
            events=props.get('visual_emphasis',[]); rows=[]
            for index,shot in enumerate(props['shots']):
                if any(event['shot_id']==shot['id'] for event in events): continue
                incoming=props['shots'][index-1]['transition_out'] if index else None
                lo=shot['start_frame']+(incoming['post_frames'] if incoming else 0)
                hi=shot['end_frame']-(shot['transition_out']['pre_frames'] if shot['transition_out'] else 0)-1
                rows += [{'shot_id':shot['id'],'global_frame':lo+(hi-lo)*part//4} for part in range(5)]
            indices=[row['global_frame'] for row in rows]
            if not indices: raise ValueError('No zero-text shot available for comparison')
            current,_=extract(preview,indices,output/'zero-text/mixed',(960,540))
            original,_=extract(baseline_video,indices,output/'zero-text/baseline',(960,540))
            for row in rows:
                frame=row['global_frame']
                with Image.open(current[frame]) as a, Image.open(original[frame]) as b: metric=difference(a,b)
                row.update(metric, status='PASS' if metric['mae_8bit']<=1 and metric['channel_fraction_gt_8']<=.005 else 'FAIL',
                    mixed=str(current[frame].relative_to(root)),baseline=str(original[frame].relative_to(root)))
            report['checks']['zero_text_baseline']={'status':'PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL',
                'mixed_video_sha256':digest(preview),'baseline_video_sha256':digest(baseline_video),
                'meaning':'Matched geometry and decoded pixels in five stable-window frames per zero-text shot; allows bounded H.264 quantization.',
                'frames':rows}
        except (ValueError,subprocess.SubprocessError,KeyError,OSError) as error:
            report['checks']['zero_text_baseline']={'status':'FAIL','reason':str(error)}
    states=[check['status'] for check in report['checks'].values()]
    report['status']='FAIL' if 'FAIL' in states else 'NOT_RUN' if 'NOT_RUN' in states else 'PASS'
    target=output/'frame-verification.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(target),
                      'checks':{key:value['status'] for key,value in report['checks'].items()}},ensure_ascii=False))
    return 1 if report['status']=='FAIL' else 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,default=BASE/'reports/sc-k5/fixture/validated')
    parser.add_argument('--baseline',type=Path,default=BASE/'reports/sc-k5/probe-complete/baseline')
    args=parser.parse_args()
    sys.exit(check(args.project.resolve(),args.baseline.resolve()))
