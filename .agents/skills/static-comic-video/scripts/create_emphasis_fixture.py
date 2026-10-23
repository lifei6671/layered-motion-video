"""Build a 60-second TEST_ONLY emphasis fixture; no model, approval or rendering.

The soundtrack is a synthetic low-level tone, not speech. Character timestamps
are deliberately synthetic unit-test evidence, never a WhisperX quality claim.
"""
import argparse
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import sys
import wave

BASE = Path(__file__).resolve().parents[1]
REPO = BASE.parents[2]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / 'tests'))

import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw
from scripts.create_fixture import create_fixture
from speech_support import seed_alignment
from static_comic.contracts import bytes_digest, canonical, read_json
from static_comic.emphasis import DEFAULT_POLICY, empty_plan
from static_comic.project import compile_project
from static_comic.speech import read_evidence, store_evidence
from static_comic.speech_audio import prepare_audio


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else canonical(value) + b'\n')


def pcm_wav(values, rate=48000):
    data = BytesIO()
    with wave.open(data, 'wb') as output:
        output.setnchannels(values.shape[1])
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(np.asarray(values, dtype='<i2').tobytes())
    return data.getvalue()


def build(root, font_path):
    root = Path(root).resolve()
    board = create_fixture(root)  # Refuses a nonempty destination.
    original = read_json((root / 'assets/images/manifest.json').read_bytes())['assets'][0]
    original_shot = deepcopy(board['shots'][0])
    presets = ['soft_rise', 'comic_pop', 'comic_burst', 'number_tick', 'underline_reveal',
               'stagger_group', 'ink_reveal', 'light_sweep']
    words = ['轻轻浮现', '关键概念', '突破', '300%', '核心原理', '观察思考行动', '水墨', '光芒', '安静', '留白']
    parts = [f'这是合成测试画面，现在展示{word}，并保留完整时间。' for word in words]
    script = ''.join(parts).encode('utf-8')
    write(root, 'input/script.txt', script)
    samples = 60 * 48000
    t = np.arange(samples) / 48000
    tone = np.rint(450 * np.sin(2 * np.pi * 180 * t)).astype('<i2')
    source = pcm_wav(np.column_stack([tone, tone]))
    write(root, 'input/voice.wav', source)
    board.update(episode_id='TEST-ONLY-emphasis-60s', script_sha256=bytes_digest(script),
                 audio={'source':'input/voice.wav', 'sha256':bytes_digest(source),
                        'sample_rate':48000, 'duration_samples':samples})
    shots, assets, cursor, word_ranges = [], [], 0, []
    for index, (part, word) in enumerate(zip(parts, words)):
        sid = f'SHOT-{index+1:03}'
        name = f'assets/images/shot_{index+1:04}.png'
        image = Image.new('RGB', (1920, 1080), '#f4efdf')
        draw = ImageDraw.Draw(image)
        # Deliberately sparse geometry with the same authored subject box used
        # by collision checks; no unverified claim of AI image observation.
        draw.ellipse((850, 480, 1010, 640), fill='#d59966', outline='#292522', width=7)
        draw.rounded_rectangle((825, 630, 1035, 830), 35, fill='#5b9294', outline='#292522', width=7)
        draw.line((835, 815, 790, 930), fill='#292522', width=9)
        draw.line((1025, 815, 1080, 930), fill='#292522', width=9)
        draw.text((50, 32), f'TEST ONLY / {index+1:02} / {presets[index] if index<8 else "NO TEXT / NO SFX"}', fill='#66615a')
        output = BytesIO(); image.save(output, format='PNG'); data = output.getvalue()
        write(root, name, data)
        asset = deepcopy(original)
        asset.update(shot_id=sid, path=name, sha256=bytes_digest(data),
                     prompt='TEST_ONLY deterministic authored geometric figure; not a reviewed production comic')
        assets.append(asset)
        shot = deepcopy(original_shot)
        shot.update(id=sid, image=name, script_range=[cursor,cursor+len(part)],
                    narrative='TEST_ONLY synthetic timing and geometric figure, no production review',
                    start_samples=index*6*48000, speech_interval_samples=[index*6*48000,(index*6+5.8)*48000],
                    subject_bbox=[.40,.43,.58,.88], transition_out=None)
        shot['speech_interval_samples'] = [int(v) for v in shot['speech_interval_samples']]
        shot['motion']['scale_to'] = 1.04
        shots.append(shot)
        word_start = cursor+part.index(word)
        word_ranges.append([word_start,word_start+len(word)])
        cursor += len(part)
    for i, shot in enumerate(shots[:-1]):
        shot['transition_out'] = {'to_shot_id':shots[i+1]['id'], 'relation':'technical_test',
            'evidence':'TEST_ONLY authored geometry', 'visual_evidence':'Same central figure on quiet background',
            'intent':'Exercise real overlap rendering; not user-approved semantics',
            'type':['fade','wipe_from_left','fade_black'][i%3], 'duration_frames':12,
            'placement':'center_on_anchor', 'semantic_anchor_samples':shots[i+1]['start_samples'],
            'planning_source':'technical_fixture', 'image_hashes':[assets[i]['sha256'],assets[i+1]['sha256']]}
    board['shots'] = shots
    write(root, 'input/storyboard.json', board)
    write(root, 'assets/images/manifest.json', {'schema_version':'1.0','assets':assets})
    font_data = Path(font_path).read_bytes()
    with TTFont(BytesIO(font_data)) as font:
        names = {str(key):list(dict.fromkeys(n.toUnicode() for n in font['name'].names if n.nameID==key))
                 for key in (0,1,13,14)}
    if not any('SIL OPEN FONT LICENSE' in text.upper() for text in names['13']):
        raise ValueError('Expected embedded SIL OFL license evidence in the local font')
    license_data = canonical({'TEST_ONLY':True,'embedded_name_records':names,'source_sha256':bytes_digest(font_data)})
    write(root, 'assets/fonts/font.ttf', font_data)
    write(root, 'assets/fonts/license-evidence.json', license_data)
    font_asset = {'asset_id':'local-wenkai','path':'assets/fonts/font.ttf','sha256':bytes_digest(font_data),
        'family':names['1'][0],'source_kind':'user_provided','source_uri':Path(font_path).resolve().as_uri(),
        'author':names['0'][0],'license':'SIL-OFL-1.1','usage_scope':'TECHNICAL_ONLY local fixture',
        'license_evidence':{'path':'assets/fonts/license-evidence.json','sha256':bytes_digest(license_data)},
        'review_status':'TECHNICAL_ONLY'}
    write(root, 'assets/fonts/manifest.json', {'schema_version':'1.0','assets':[font_asset]})
    sfx_assets = []
    sound_license = b'TEST_ONLY. Locally synthesized by create_emphasis_fixture.py; original oscillator/pulse samples. CC0-1.0.'
    write(root, 'assets/sfx/LICENSE.txt', sound_license)
    for index, kind in enumerate(['keyword','scene','transition','narrative']):
        length = 9600
        st = np.arange(length)/48000
        values = np.rint(7000*np.sin(2*np.pi*(500+index*170)*st)*np.linspace(1,0,length)).astype('<i2')
        if kind == 'keyword': values[:2] = [10000,-10000]
        data = pcm_wav(np.column_stack([values,values]))
        path = f'assets/sfx/{kind}.wav'; write(root,path,data)
        sfx_assets.append({'asset_id':kind,'path':path,'sha256':bytes_digest(data),
            'source_kind':'local_created','source_uri':'local:scripts/create_emphasis_fixture.py','author':'fixture generator',
            'license':'CC0-1.0','usage_scope':'TECHNICAL_ONLY','license_evidence':{'path':'assets/sfx/LICENSE.txt',
            'sha256':bytes_digest(sound_license)},'review_status':'TECHNICAL_ONLY',
            'sample_rate':48000,'channels':2,'duration_samples':length,'tags':[kind]})
    write(root, 'assets/sfx/manifest.json', {'schema_version':'1.0','assets':sfx_assets})
    policy = deepcopy(DEFAULT_POLICY); policy['mode']='mixed'
    policy['visual'].update(enabled=True, max_events_per_minute=12, safe_insets=[.06,.06,.06,.06])
    policy['audio']['enabled']=True
    plan = empty_plan(script,[shot['id'] for shot in shots])
    for index, decision in enumerate(plan['shot_decisions']):
        decision.update(text_decision='auto' if index<8 else 'skip',sfx_decision='allow' if index<8 else 'silence',
                        reason='TEST_ONLY prescribed coverage; final two shots exercise explicit skip and silence')
    for index,preset in enumerate(presets):
        plan['visual_events'].append({'id':f'VE-{index+1:03}','shot_id':shots[index]['id'],
            'script_range':word_ranges[index],'text':words[index], 'semantic_type':'number' if preset=='number_tick' else 'concept',
            'importance':'high','preset':preset,'tier':1 if index<6 else 2,
            'layout':{'preset':['upper_left','upper_right','left_center'][index%3],'max_width':.4},
            'font_asset_id':'local-wenkai','font_size':68, 'stroke_width':2,'shadow_px':2,
            'pinned':False,'source':'rules'})
    anchors = [{'type':'visual_marker','visual_event_id':'VE-002','marker':'impact','offset_samples':0},
               {'type':'shot_start','shot_id':'SHOT-003','offset_samples':48000},
               {'type':'transition_frame','from_shot_id':'SHOT-004','point':'start','offset_samples':0},
               {'type':'speech_start','shot_id':'SHOT-006','script_range':word_ranges[5],'offset_samples':0}]
    for kind,anchor in zip(['keyword','scene','transition','narrative'],anchors):
        plan['audio_events'].append({'id':'SFX-'+kind,'kind':kind,'sfx_asset_id':kind,'anchor':anchor,
            'gain_db':-12,'fade_in_samples':0 if kind=='keyword' else 240,'fade_out_samples':960,
            'pinned':False,'source':'rules'})
    write(root, 'input/emphasis_policy.json', policy)
    write(root, 'input/emphasis_plan.json', plan)
    # Run actual FFmpeg preparation first. seed_alignment writes silent test WAVs;
    # restore prepared source PCM and rebind the explicitly synthetic evidence.
    actual_audio = prepare_audio(root, 'input/voice.wav')
    preserved = {name:(root/name).read_bytes() for name in ('work/audio/master_48k.wav','work/audio/align_16k.wav')}
    aligned = seed_alignment(root, technical_fixture=True)
    raw = read_evidence(root, aligned['raw_ref'])
    raw['audio'] = actual_audio
    raw['TEST_ONLY'] = 'Synthetic character timestamps over a generated tone; no speech model was run.'
    aligned['raw_ref'] = store_evidence(root, raw)
    aligned['TEST_ONLY'] = raw['TEST_ONLY']
    for name,data in preserved.items(): write(root,name,data)
    write(root, 'work/alignment/aligned.json', aligned)
    result = compile_project(root, technical_fixture=True)
    events = result['emphasis']
    summary = {'artifact_kind':'technical_fixture','TEST_ONLY':raw['TEST_ONLY'],
        'production_speech':'NOT_RUN','human_review':'NOT_RUN','render':'NOT_RUN',
        'total_frames':result['props']['video']['total_frames'], 'duration_samples':samples,
        'visual_count':len(events['visual']),'sfx_count':len(events['sfx']),
        'presets':[e['preset'] for e in events['visual']], 'sfx_kinds':[e['kind'] for e in events['sfx']],
        'layout_positions':[e['layout']['position'] for e in events['diagnostics'] if e.get('layout')],
        'diagnostics':events['diagnostics'],'master_sha256':bytes_digest(preserved['work/audio/master_48k.wav'])}
    write(root, 'reports/fixture-build.json', summary)
    if summary['visual_count'] != 8 or summary['sfx_count'] != 4 or summary['total_frames'] != 1800:
        raise ValueError('Fixture coverage failed; inspect reports/fixture-build.json')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,help='Empty destination; existing work is never overwritten')
    parser.add_argument('--font',default=str(REPO/'cover-studio/fonts/LXGWWenKai/LXGWWenKai-Regular.ttf'))
    arguments = parser.parse_args()
    build(arguments.output,arguments.font)
