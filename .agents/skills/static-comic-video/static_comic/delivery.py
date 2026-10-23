"""SC-P5 sequential preview, explicit review, visual render and complete-audio mux."""
from html import escape
from functools import wraps
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from PIL import Image

from .contracts import canonical, digest, read_json, validate
from .image_supply import policy_options, requests, verify as verify_images, write_docs
from .media import file_hash, mux_command, run, verify_media
from .paths import read_bytes, resolve_path, process_args, process_path
from .project import SMALL_FILE, check_human, check_human_metadata, check_source_policy, compile_project
from .speech_audio import prepare_audio
from .cache import cached, operation, publish, versions
from .human_review import require_newer

BASE = Path(__file__).resolve().parents[1]
RENDERER = BASE / 'renderer/static-comic'
BROWSER = RENDERER / 'node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe'
PROFILES = {'preview': {'scale': .5, 'crf': 28, 'width': 960, 'height': 540},
            'final': {'scale': 1, 'crf': 18, 'width': 1920, 'height': 1080}}


def locations(technical):
    suffix = '/technical' if technical else ''
    return {'remotion': 'work/remotion'+suffix, 'timeline': 'work/timeline'+suffix,
            'preview': 'preview'+suffix, 'review': 'review'+suffix,
            'output': 'output'+suffix, 'reports': 'reports'+suffix}


def initialize(root):
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError('init requires a new or empty episode directory')
    root.mkdir(parents=True, exist_ok=True)
    write_docs(root, {'input/image_source_policy.json': {'schema_version': '1.0', 'mode': 'mixed',
        'status': 'SOURCE_POLICY_PENDING', 'default_channel': None, 'allowed_channels': [],
        'shots': {}, 'supersedes': None, 'confirmation': None}, 'assets/images/manifest.json': {'schema_version': '1.0', 'assets': []},
        'review/image_approvals.json': {'schema_version': '1.0', 'receipts': []},
        'input/render.yaml': b"width: 1920\nheight: 1080\nfps_num: 30\nfps_den: 1\nalpha_background: '#ffffff'\n"})
    return {**policy_options(root), 'next': 'Provide input/script.txt, voice.wav or voice.mp3, and storyboard.json; confirm the image channel before acquisition.'}


def runtime():
    cli = RENDERER/'node_modules/@remotion/cli/remotion-cli.js'
    if not cli.is_file() or not BROWSER.is_file():
        raise ValueError('Locked local Remotion/browser missing; follow runtime.md, no implicit download')
    installed = {}
    declared = read_json((RENDERER/'package.json').read_bytes())['dependencies']
    for name, version in declared.items():
        actual = read_json((RENDERER/'node_modules'/name/'package.json').read_bytes())['version']
        if actual != version:
            raise ValueError(f'Installed renderer dependency differs from pinned version: {name}')
        installed[name] = actual
    tools = {}
    for name in ('node', 'ffmpeg', 'ffprobe'):
        executable = shutil.which(name)
        if not executable:
            raise ValueError(f'Required executable unavailable: {name}')
        tools[name] = {'path': executable, 'sha256': file_hash(executable),
                       'version': run([executable, '--version' if name == 'node' else '-version']).decode('utf-8').splitlines()[0]}
    tools['browser'] = {'path': process_path(BROWSER), 'sha256': file_hash(BROWSER)}
    sources = [*sorted((BASE/'static_comic').glob('*.py')), *sorted((RENDERER/'src').glob('*')),
               RENDERER/'package-lock.json', RENDERER/'package.json', RENDERER/'remotion.config.ts', RENDERER/'tsconfig.json',
               BASE/'schemas/contracts.json', BASE/'uv.lock']
    return {'tools': tools, 'python': sys.version, 'installed': installed,
            'sources': {p.relative_to(BASE).as_posix(): file_hash(p) for p in sources if p.is_file()},
            'profiles': PROFILES, 'mux': {'video': 'copy', 'audio': 'aac', 'bitrate': '192k', 'sample_rate': 48000}}


def snapshot(root, technical=False, *, write=False):
    compiled = compile_project(root, technical_fixture=technical, write=write)
    loc = locations(technical)
    for name, value in (('props.json', compiled['props']), ('staging-manifest.json', compiled['staging'])):
        if read_json(read_bytes(root, f"{loc['remotion']}/{name}", SMALL_FILE)) != value:
            raise ValueError('Staged execution differs from current inputs; compile again')
    if read_json(read_bytes(root, f"{loc['timeline']}/timeline.lock.json", SMALL_FILE)) != compiled['timeline']:
        raise ValueError('Locked timeline differs from current inputs; compile again')
    if compiled['motion_cards']['present']:
        # 已选定字卡计划是当前视觉批准对象的一部分，独立锁不可被旧事件冒充。
        from .motion_cards import selected_plan
        original = selected_plan(root, read_bytes(root, 'input/script.txt', SMALL_FILE))
        locked = read_json(read_bytes(root, f"{loc['timeline']}/motion_cards.lock.json", SMALL_FILE))
        if (original is None or locked.get('events') != compiled['motion_cards']['events']
                or locked.get('plan_sha256') != digest(original)
                or locked.get('script_sha256') != original['script_sha256']):
            raise ValueError('Motion-card lock is stale or changed; compile and preview again')
    for image in compiled['staging']['images']:
        if file_hash(resolve_path(root, loc['remotion']+'/public/'+image['staged_image'])) != image['staged_sha256']:
            raise ValueError('Staged image differs from the locked image snapshot')
    for resource in compiled['staging'].get('resources', []):
        if file_hash(resolve_path(root, loc['remotion']+'/public/'+resource['path'])) != resource['sha256']:
            raise ValueError('Staged emphasis resource differs from the locked snapshot')
    value = {'artifact_kind': compiled['artifact_kind'], 'timeline': digest(compiled['timeline']),
             'props': digest(compiled['props']), 'staging': digest(compiled['staging']),
             'inputs': compiled['timeline']['input_hashes'], 'runtime': runtime(),
             'master_sha256': file_hash(resolve_path(root, 'work/audio/master_48k.wav')),
             'total_frames': compiled['total_frames']}
    if compiled['emphasis']['sfx']:
        from .sfx_mix import mix
        audio = mix(root, compiled['emphasis']['sfx'], compiled['emphasis_policy']['audio'], write=write)
        value['audio_reference'] = {'path':audio['mix_path'], 'sha256':audio['mix_sha256'],
                                    'stem_sha256':audio['stem_sha256'], 'samples':audio['samples']}
    return value, compiled


def read_record(root, path):
    return read_json(read_bytes(root, path, 16 * 1024 * 1024))


def checked_record(root, name, snap, technical):
    value = read_record(root, f"{locations(technical)['reports']}/{name}.json")
    if value.get('snapshot') != snap:
        raise ValueError(f'{name}: inputs, renderer version or configuration changed; preview/review again')
    for path, sha in value['files'].items():
        if file_hash(resolve_path(root, path)) != sha:
            raise ValueError(f'{name}: media hash changed: {path}')
    return value


def review_binding(record):
    return digest({'snapshot': record['snapshot'], 'files': record['files']})


def check_delivery_human(decision, technical):
    if technical:
        check_human_metadata(decision['human'])
    else:
        check_human(decision['human'], scope=decision['stage'],
                    expected={k: v for k, v in decision.items() if k != 'human'})


def require_approval(root, preview, technical):
    decision = validate('deliveryDecision', read_record(root, f"{locations(technical)['review']}/approval.json"))
    check_delivery_human(decision, technical)
    if (decision['stage'] != 'preview' or decision['binding_sha256'] != review_binding(preview)
            or decision['decision'] != 'APPROVED' or not decision['checks']['semantics']
            or not decision['checks']['full_listening']):
        raise ValueError('Current audible preview requires explicit semantic and complete-listening approval')
    return decision


def render_command(root, loc, target, profile, technical):
    entry = 'src/technical.tsx' if technical else 'src/index.tsx'
    return ['node', str(RENDERER/'node_modules/@remotion/cli/remotion-cli.js'), 'render', entry,
            'ComicVideo', str(target), f"--props={resolve_path(root, loc['remotion']+'/props.json')}",
            f"--public-dir={resolve_path(root, loc['remotion']+'/public')}", '--muted', '--codec=h264',
            '--pixel-format=yuv420p', '--color-space=bt709', '--image-format=png',
            f"--scale={profile['scale']}", f"--crf={profile['crf']}", '--concurrency=2',
            f'--browser-executable={BROWSER}', '--log=error']


def contact_sheet(root, compiled, loc):
    shots = compiled['props']['shots']
    sheet = Image.new('RGB', (960, ((len(shots)+2)//3)*180), 'white')
    for index, shot in enumerate(shots):
        with Image.open(resolve_path(root, f"{loc['timeline']}/cover/{shot['id']}.png")) as image:
            thumb = image.convert('RGB').resize((320, 180), Image.Resampling.LANCZOS)
            sheet.paste(thumb, ((index%3)*320, (index//3)*180))
    buffer = BytesIO(); sheet.save(buffer, format='JPEG', quality=90)
    return buffer.getvalue()


def tracked(function):
    @wraps(function)
    def execute(root, technical=False):
        root = Path(root).resolve(strict=True)
        with operation(root, function.__name__, locations(technical)['reports']):
            return function(root, technical)
    return execute


def visual_product(root, snap, compiled, loc, profile_name, technical):
    profile = PROFILES[profile_name]
    rt = snap['runtime']
    build_key = {'sources': {k:v for k,v in rt['sources'].items()
                            if k.startswith('renderer/') or k == 'schemas/contracts.json'},
                 'installed': rt['installed'], 'node': rt['tools']['node'], 'technical': technical,
                 'images': {i['staged_image']: i['staged_sha256'] for i in compiled['staging']['images']},
                 'version': versions('static_comic/delivery.py')}
    if compiled['staging'].get('resources'):
        build_key['resources'] = {r['path']:r['sha256'] for r in compiled['staging']['resources']}
    def build_bundle(temp):
        command = ['node', str(RENDERER/'node_modules/@remotion/cli/remotion-cli.js'), 'bundle',
                   'src/technical.tsx' if technical else 'src/index.tsx', f'--out-dir={temp / "bundle"}',
                   f"--public-dir={resolve_path(root, loc['remotion']+'/public')}", '--log=error']
        run(command, cwd=RENDERER)
        if not (temp/'bundle/index.html').is_file():
            raise ValueError('Remotion bundle has no entry')
        return {'command': command}
    bundle, _ = cached(root, 'remotion-build', build_key, build_bundle)
    bundle_hashes = read_record(root, bundle.relative_to(Path(root)).as_posix()+'/manifest.json')['files']
    key = {'build': digest(build_key), 'bundle': bundle_hashes, 'props': compiled['props'], 'profile': profile,
           'browser': rt['tools']['browser'], 'node': rt['tools']['node'],
           'validation': versions('static_comic/media.py', packages=('numpy',))}
    master = resolve_path(root, 'work/audio/master_48k.wav')
    def build_visual(temp):
        command = render_command(root, loc, temp/'visual.mp4', profile, technical)
        command[3] = str(bundle/'bundle')
        run(command, cwd=RENDERER)
        validation = verify_media(temp/'visual.mp4', master, frames=snap['total_frames'],
                                 width=profile['width'], height=profile['height'])
        return {'validation': validation, 'command': command}
    record_name = 'preview' if profile_name == 'preview' else 'visual'
    exported = loc['preview']+'/preview_visual.mp4' if profile_name == 'preview' else loc['remotion']+'/visual.mp4'
    reason = None
    if resolve_path(root, loc['reports']+'/'+record_name+'.json').exists():
        previous = read_record(root, loc['reports']+'/'+record_name+'.json')
        path = resolve_path(root, exported)
        if not path.is_file() or file_hash(path) != previous.get('files', {}).get(exported):
            reason = 'published_visual_missing_or_corrupt'
    folder, result = cached(root, 'visual-'+profile_name, key, build_visual, rebuild_reason=reason)
    # Hash validation protects hits; media validation also checks the current PCM clock.
    validation = verify_media(folder/'visual.mp4', master, frames=snap['total_frames'],
                             width=profile['width'], height=profile['height'])
    return folder/'visual.mp4', {**result, 'validation': validation}


def mux_product(root, visual, master, snap, profile_name):
    profile = PROFILES[profile_name]
    key = {'visual': file_hash(visual), 'audio': file_hash(master), 'profile': profile,
           'frames': snap['total_frames'], 'ffmpeg': snap['runtime']['tools']['ffmpeg'],
           'version': versions('static_comic/media.py', packages=('numpy',))}
    def build(temp):
        command = mux_command(visual, master, temp/'audible.mp4')
        run(command)
        validation = verify_media(visual, master, frames=snap['total_frames'], width=profile['width'],
                                  height=profile['height'], audible=temp/'audible.mp4')
        return {'validation': validation, 'command': command}
    folder, result = cached(root, 'mux-'+profile_name, key, build)
    validation = verify_media(visual, master, frames=snap['total_frames'], width=profile['width'],
                              height=profile['height'], audible=folder/'audible.mp4')
    return folder/'audible.mp4', {**result, 'validation': validation}


@tracked
def preview(root, technical=False):
    if technical:
        compile_project(root, technical_fixture=True, write=False)
        board = read_record(root, 'input/storyboard.json')
        prepare_audio(root, board['audio']['source'])
    snap, compiled = snapshot(root, technical, write=True)
    loc = locations(technical); profile = PROFILES['preview']
    names = [loc['preview']+'/'+n for n in ('preview_visual.mp4', 'preview.mp4', 'contact_sheet.jpg')]
    master = resolve_path(root, snap.get('audio_reference',{}).get('path','work/audio/master_48k.wav'))
    started = time.monotonic()
    visual, vr = visual_product(root, snap, compiled, loc, 'preview', technical)
    audible, mr = mux_product(root, visual, master, snap, 'preview')
    sheet = contact_sheet(root, compiled, loc)
    extra = {}
    if compiled['emphasis']['visual'] or compiled['emphasis']['sfx']:
        from .emphasis_preview import preview_evidence
        extra = preview_evidence(visual, compiled, loc)
        if compiled['emphasis']['sfx']:
            extra[loc['preview']+'/mix.json'] = read_bytes(root,'reports/mix.json',16*1024*1024)
    if compiled['motion_cards']['events']:
        # 动态镜头抽帧取自本次真正渲出的视觉视频，摘要进入试听批准绑定。
        from .motion_card_preview import motion_card_evidence
        extra.update(motion_card_evidence(visual, compiled, loc))
    if snapshot(root, technical)[0] != snap:
        raise ValueError('Inputs changed while rendering; preview cannot be approved')
    from .contracts import bytes_digest
    record = {'snapshot': snap, 'files': {names[0]: file_hash(visual), names[1]: file_hash(audible),
                                        names[2]: bytes_digest(sheet)},
              'validation': mr['validation'], 'commands': [vr['command'], mr['command']],
              'elapsed_seconds': time.monotonic()-started}
    record['files'].update({name:bytes_digest(data) for name,data in extra.items()})
    publish(root, {names[0]: visual, names[1]: audible, names[2]: sheet, **extra,
                   loc['reports']+'/preview.json': canonical(record)})
    return {'status': 'PREVIEW_AUDIO_MUXED', 'artifact_kind': snap['artifact_kind'], 'preview': names[1],
            'contact_sheet': names[2], 'binding_sha256': review_binding(record), 'human_acceptance': 'NOT_RUN'}


def approve(root, decision, technical=False):
    validate('deliveryDecision', decision); check_delivery_human(decision, technical)
    if not decision['reason'].strip():
        raise ValueError('Human decision reason is required')
    snap, _ = snapshot(root, technical)
    stage = decision['stage']; loc = locations(technical)
    record = checked_record(root, 'preview' if stage == 'preview' else 'render', snap, technical)
    if decision['binding_sha256'] != review_binding(record):
        raise ValueError('Human decision targets a stale media binding')
    name = 'approval.json' if stage == 'preview' else 'quality.json'
    previous_path = resolve_path(root, loc['review']+'/'+name)
    if not technical and previous_path.exists():
        try:
            previous_decision = validate('deliveryDecision', read_record(root, loc['review']+'/'+name))
            check_delivery_human(previous_decision, False)
        except (ValueError, OSError):
            pass  # Permit explicit recovery from legacy/invalid pointers.
        else:
            if (previous_decision['stage'] == stage
                    and previous_decision['binding_sha256'] == decision['binding_sha256']):
                require_newer(decision['human'], previous_decision['human'])
    if decision['decision'] == 'APPROVED':
        required = ('semantics', 'full_listening') if stage == 'preview' else ('formal_quality',)
        if not all(decision['checks'][k] for k in required):
            raise ValueError('Approval requires all stage-specific human checks')
        if stage == 'final':
            verify(root, technical)
        else:
            verify_media(resolve_path(root, loc['preview']+'/preview_visual.mp4'),
                         resolve_path(root, snap.get('audio_reference',{}).get('path','work/audio/master_48k.wav')), frames=snap['total_frames'],
                         width=960, height=540, audible=resolve_path(root, loc['preview']+'/preview.mp4'))
    outputs = {loc['review']+'/'+name: decision,
               loc['review']+f'/delivery-events/{digest(decision)}.json': decision}
    if previous_path.exists():
        previous = read_bytes(root, loc['review']+'/'+name, 16 * 1024 * 1024)
        outputs[loc['review']+f'/delivery-history/{file_hash(previous_path)}.json'] = previous
    write_docs(root, outputs)
    return {'status': ('TECHNICAL_REVIEW_RECORDED' if technical else
                      ('REVIEW_APPROVED' if stage == 'preview' else 'QUALITY_APPROVED'))
                      if decision['decision'] == 'APPROVED' else 'REVIEW_REQUIRED', 'stage': stage}


@tracked
def render_visual(root, technical=False):
    snap, compiled = snapshot(root, technical, write=True); loc = locations(technical)
    candidate = checked_record(root, 'preview', snap, technical)
    approval = require_approval(root, candidate, technical)
    name = loc['remotion']+'/visual.mp4'
    started = time.monotonic()
    target, product = visual_product(root, snap, compiled, loc, 'final', technical)
    if snapshot(root, technical)[0] != snap or require_approval(root, candidate, technical) != approval:
        raise ValueError('Inputs or approval changed during formal render')
    publish(root, {name: target, loc['reports']+'/visual.json': canonical({'snapshot': snap,
        'files': {name: file_hash(target)}, 'approval_sha256': digest(approval),
        **product, 'elapsed_seconds': time.monotonic()-started})})
    return {'status': 'FINAL_VISUAL_RENDERED', 'visual': name}


@tracked
def mux(root, technical=False):
    snap, _ = snapshot(root, technical); loc = locations(technical)
    candidate = checked_record(root, 'preview', snap, technical)
    approval = require_approval(root, candidate, technical)
    visual = checked_record(root, 'visual', snap, technical)
    if visual['approval_sha256'] != digest(approval):
        raise ValueError('Formal visual was rendered under a different approval')
    visual_path = resolve_path(root, loc['remotion']+'/visual.mp4')
    master = resolve_path(root, snap.get('audio_reference',{}).get('path','work/audio/master_48k.wav'))
    name = loc['output']+'/final.mp4'
    started = time.monotonic()
    target, product = mux_product(root, visual_path, master, snap, 'final')
    if snapshot(root, technical)[0] != snap or require_approval(root, candidate, technical) != approval:
        raise ValueError('Inputs or approval changed during mux')
    final = {'snapshot': snap,
        'files': {**visual['files'], name: file_hash(target)}, 'approval_sha256': digest(approval),
        **product, 'elapsed_seconds': time.monotonic()-started}
    report, response = verification_record(root, snap, final, product['validation'], technical)
    publish(root, {name: target, loc['reports']+'/render.json': canonical(final),
                   loc['reports']+'/validation.json': canonical(report)})
    return response


def verify(root, technical=False):
    snap, _ = snapshot(root, technical); loc = locations(technical)
    candidate = checked_record(root, 'preview', snap, technical)
    approval = require_approval(root, candidate, technical)
    final = checked_record(root, 'render', snap, technical)
    if final['approval_sha256'] != digest(approval):
        raise ValueError('Final media approval is stale')
    result = verify_media(resolve_path(root, loc['remotion']+'/visual.mp4'),
        resolve_path(root, snap.get('audio_reference',{}).get('path','work/audio/master_48k.wav')), frames=snap['total_frames'], width=1920, height=1080,
        audible=resolve_path(root, loc['output']+'/final.mp4'))
    report, response = verification_record(root, snap, final, result, technical)
    publish(root, {loc['reports']+'/validation.json': canonical(report)})
    return response


def verification_record(root, snap, final, result, technical):
    loc = locations(technical)
    quality, quality_error = 'NOT_RUN', None
    quality_path = loc['review']+'/quality.json'
    if resolve_path(root, quality_path).exists():
        try:
            decision = validate('deliveryDecision', read_record(root, quality_path))
            check_delivery_human(decision, technical)
            if decision['stage'] != 'final' or decision['binding_sha256'] != review_binding(final):
                raise ValueError('Formal quality approval is stale')
            quality = 'PASS' if decision['decision'] == 'APPROVED' and decision['checks']['formal_quality'] else 'FAIL'
        except (ValueError, OSError) as error:
            # Invalid quality records remain replaceable through a new confirmation.
            quality, quality_error = 'REVIEW_REQUIRED', str(error)
    acceptance = {'technical': 'PASS', 'semantics': 'TEST_ONLY' if technical else 'PASS',
                  'complete_listening': 'TEST_ONLY' if technical else 'PASS',
                  'formal_quality': 'TEST_ONLY' if technical and quality == 'PASS' else quality}
    report = {'artifact_kind': snap['artifact_kind'],
              'binding_sha256': review_binding(final), 'acceptance': acceptance, 'media': result,
              'formal_quality_error': quality_error}
    response = {'status': 'OUTPUT_VERIFIED', 'artifact_kind': snap['artifact_kind'], 'acceptance': acceptance,
            'production_accepted': not technical and all(v == 'PASS' for v in acceptance.values()),
            'final': loc['output']+'/final.mp4', 'binding_sha256': review_binding(final)}
    return report, response


def inspect(root, technical=False):
    snap, _ = snapshot(root, technical); loc = locations(technical)
    candidate = checked_record(root, 'preview', snap, technical)
    status = 'PREVIEW_AUDIO_MUXED'
    try:
        require_approval(root, candidate, technical)
        status = 'TECHNICAL_REVIEW_RECORDED' if technical else 'REVIEW_APPROVED'
    except (ValueError, OSError):
        pass  # Only the optional human receipt is absent/rejected/stale; media was checked above.
    binding = review_binding(candidate)
    emphasis_html = ''
    if loc['preview']+'/emphasis.json' in candidate['files']:
        evidence = read_record(root,loc['preview']+'/emphasis.json')
        rows = ''.join('<tr>'+''.join('<td>'+escape(str(e[k]))+'</td>' for k in
                       ('id','kind','start_sample','play_samples','gain_db'))+'</tr>' for e in evidence['sfx_events'])
        emphasis_html = ('<h2>文字关键帧与音效</h2><p>静音决定仅关闭新增音效，完整旁白保留。</p>'
            + ('<img width="960" src="emphasis_sheet.jpg">' if loc['preview']+'/emphasis_sheet.jpg' in candidate['files'] else '')
            + '<table border="1"><tr><th>事件</th><th>类别</th><th>起点采样</th><th>长度采样</th><th>增益 dB</th></tr>'
            + rows+'</table><p><a href="emphasis.json">事件与跳过原因</a></p>')
    html = (f'<!doctype html><meta charset="utf-8"><title>有声预览审核</title><h1>{escape(snap["artifact_kind"])}</h1>'
            '<p>请完整试听并核对语义；技术检查通过不代表批准。正式画质需另审。</p>'
            '<video controls width="960" src="preview.mp4"></video><p><img width="960" src="contact_sheet.jpg"></p>'
            f'<p>状态：{status}</p><pre>binding_sha256: {binding}</pre>'+emphasis_html)
    write_docs(root, {loc['preview']+'/index.html': html.encode('utf-8')})
    return {'status': status, 'binding_sha256': binding, 'report': loc['preview']+'/index.html',
            'technical': candidate['validation']['status'], 'formal_quality': 'NOT_RUN'}


def status(root, technical=False):
    attempt = resolve_path(root, locations(technical)['reports']+'/attempt.json')
    if attempt.exists():
        last = read_record(root, locations(technical)['reports']+'/attempt.json')
        if last['status'] in ('FAILED', 'RUNNING'):
            return {**last, 'status': 'FAILED' if last['status'] == 'FAILED' else 'INTERRUPTED_OR_RUNNING',
                    'current_success': False}
    if technical:
        return inspect(root, True)
    gates = []
    try:
        policy = validate('policy', read_record(root, 'input/image_source_policy.json'))
        if policy.get('status') != 'APPROVED':
            return {'status': 'SOURCE_POLICY_PENDING', 'passed': gates}
        board = validate('storyboard', read_record(root, 'input/storyboard.json'))
        check_source_policy(policy, board['shots']); gates.append('SOURCE_POLICY_APPROVED')
        requests(root); gates.append('IMAGE_PLAN_APPROVED')
        verify_images(root); gates.append('IMAGE_REVIEW_APPROVED')
        compile_project(root, write=False); gates.append('TIMING_CONFIRMED')
        result = {**inspect(root), 'passed': gates}
        if result['status'] == 'REVIEW_APPROVED':
            snap, _ = snapshot(root)
            preview_record = checked_record(root, 'preview', snap, False)
            approval = require_approval(root, preview_record, False)
            for name, state in (('visual', 'FINAL_VISUAL_RENDERED'), ('render', 'FINAL_AUDIO_MUXED')):
                if not resolve_path(root, f'reports/{name}.json').exists():
                    break
                record = checked_record(root, name, snap, False)
                if record['approval_sha256'] != digest(approval):
                    raise ValueError('Formal output approval is stale')
                result['status'] = state
                if name == 'render' and resolve_path(root, 'reports/validation.json').exists():
                    validation = read_record(root, 'reports/validation.json')
                    if validation['binding_sha256'] == review_binding(record):
                        result['status'] = 'OUTPUT_VERIFIED'
        return result
    except (ValueError, OSError) as error:
        return {'status': 'REVIEW_REQUIRED', 'passed': gates, 'error': str(error)}


def studio(root, technical=False):
    snapshot(root, technical, write=True); loc = locations(technical)
    entry = 'src/technical.tsx' if technical else 'src/index.tsx'
    command = ['node', str(RENDERER/'node_modules/@remotion/cli/remotion-cli.js'), 'studio', entry,
        f"--props={resolve_path(root, loc['remotion']+'/props.json')}",
        f"--public-dir={resolve_path(root, loc['remotion']+'/public')}", '--no-open']
    log = resolve_path(root, loc['reports']+'/studio.log', output=True); log.parent.mkdir(parents=True, exist_ok=True)
    command, cwd = process_args(command, RENDERER)
    with log.open('ab') as stream:
        process = subprocess.Popen(command, cwd=cwd, stdout=stream, stderr=stream,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return {'status': 'STUDIO_STARTING', 'pid': process.pid, 'log': str(log),
            'note': 'Silent visual inspection only; does not approve audible preview'}


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description='SC-P5 audible preview and explicit approval workflow')
    parser.add_argument('action', choices=('init', 'status', 'studio', 'preview', 'inspect', 'approve', 'render-visual', 'mux', 'verify'))
    parser.add_argument('--project', required=True)
    parser.add_argument('--technical-fixture', action='store_true')
    parser.add_argument('--input', help='Episode-relative explicit human decision JSON for approve')
    args = parser.parse_args(argv)
    if args.action == 'init':
        if args.technical_fixture:
            raise ValueError('init always starts with undecided production source policy')
        return initialize(args.project)
    root = Path(args.project).resolve(strict=True)
    if args.action == 'approve':
        if not args.input:
            raise ValueError('--input is required; approval is never inferred')
        return approve(root, read_record(root, args.input), args.technical_fixture)
    return {'status': status, 'studio': studio, 'preview': preview, 'inspect': inspect,
            'render-visual': render_visual, 'mux': mux, 'verify': verify}[args.action](root, args.technical_fixture)
