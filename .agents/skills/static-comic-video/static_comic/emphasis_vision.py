"""Observe the approved, normalized snapshot; heuristics never claim model vision."""
from io import BytesIO

from jsonschema import Draft202012Validator
from PIL import Image, ImageFilter, ImageStat

from .contracts import bytes_digest, canonical, digest, read_json
from .paths import read_bytes, resolve_path

POSITIONS = {'upper_left': (.20, .14), 'upper_right': (.60, .14),
             'left_center': (.20, .43), 'right_center': (.60, .43), 'lower_side': (.32, .73)}
BOX = {'type': 'array', 'items': {'type': 'number', 'minimum': 0, 'maximum': 1},
       'minItems': 4, 'maxItems': 4}
OBSERVATION_SCHEMA = {'type': 'object', 'additionalProperties': False,
    'required': ['schema_version', 'provider', 'shots'], 'properties': {
    'schema_version': {'const': '1.0'}, 'provider': {'enum': ['agent', 'human']},
    'shots': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
        'required': ['shot_id', 'evidence_sha256', 'viewed_frames', 'subjects', 'embedded_text',
                     'unusable', 'emotion', 'reason'], 'properties': {
        'shot_id': {'type': 'string'}, 'evidence_sha256': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
        'viewed_frames': {'type': 'array', 'items': {'type': 'integer', 'minimum': 0}, 'uniqueItems': True},
        'subjects': {'type': 'array', 'items': BOX}, 'embedded_text': {'type': 'array', 'items': BOX},
        'unusable': {'type': 'array', 'items': BOX},
        'emotion': {'enum': ['neutral', 'quiet', 'energetic']}, 'reason': {'type': 'string', 'minLength': 1}}}}}}


def observe(root, execution, geometry, prepared, *, technical=False, candidate_frames=None):
    """Return observations and image bytes for atomic publication by compile_project.

    Supplied boxes are in normalized *snapshot* coordinates, transformed on every
    execution frame by layout.py. Source subject boxes are always retained.
    """
    supplied = None
    path = 'input/emphasis_observations.json'
    if resolve_path(root, path).exists():
        supplied = read_json(read_bytes(root, path, 4 * 1024 * 1024))
        canonical(supplied)
        errors = list(Draft202012Validator(OBSERVATION_SCHEMA).iter_errors(supplied))
        if errors:
            raise ValueError('emphasis observations: '+errors[0].message)
        ids = [s['shot_id'] for s in supplied['shots']]
        if len(ids) != len(set(ids)) or set(ids) != {s['id'] for s in execution}:
            raise ValueError('Observation inventory must cover every shot exactly once')
    result, outputs = [], {}
    base = 'work/emphasis/technical' if technical else 'work/emphasis'
    for shot, geom in zip(execution, geometry):
        frames = geom['frames']
        logical = [f for f in frames if shot['start_frame'] <= f['global_frame'] < shot['end_frame']]
        selected = {logical[(len(logical)-1)*i//4]['global_frame'] for i in range(5)}
        selected.update(f for f in (candidate_frames or {}).get(shot['id'], [])
                        if shot['start_frame'] <= f < shot['end_frame'])
        binding = digest({'image': shot['image_sha256'], 'motion': shot['motion'],
                          'geometry': geom, 'sample_frames': sorted(selected), 'technical': technical})
        with Image.open(BytesIO(prepared[shot['staged_image']])) as image:
            samples, metrics = [], {p: [] for p in POSITIONS}
            for frame in frames:
                if frame['global_frame'] not in selected:
                    continue
                x, y, w, h = frame['crop']
                view = image.convert('RGB').resize((480, 270), Image.Resampling.LANCZOS, box=(x,y,x+w,y+h))
                output = BytesIO(); view.save(output, format='PNG')
                name = f"{base}/frames/{shot['id']}-{frame['global_frame']:06}.png"
                outputs[name] = output.getvalue()
                samples.append({'global_frame': frame['global_frame'], 'path': name,
                                'sha256': bytes_digest(output.getvalue())})
                for position, (px, py) in POSITIONS.items():
                    region = view.crop((int(px*480), int(py*270), int(min(.99,px+.32)*480), int(min(.99,py+.13)*270))).convert('L')
                    # Exclude filter boundary: a flat patch must have zero edge energy.
                    edge = region.filter(ImageFilter.FIND_EDGES)
                    metrics[position].append({'luma': ImageStat.Stat(region).mean[0],
                        'contrast': ImageStat.Stat(region).stddev[0],
                        'edge': ImageStat.Stat(edge.crop((1,1,edge.width-1,edge.height-1))).mean[0]})
        w,h = geom['prepared_size']
        subject = geom['subject_bbox_prepared']
        entry = {'shot_id': shot['id'], 'evidence_sha256': binding, 'samples': samples,
            'provider': 'rules', 'status': 'HEURISTIC', 'model_status': 'UNAVAILABLE',
            'subjects': [] if subject is None else [[subject[0]/w,subject[1]/h,subject[2]/w,subject[3]/h]],
            'embedded_text': [], 'unusable': [], 'emotion': 'neutral', 'regions': metrics,
            'reason': 'Pixel contrast/edge heuristic and authored subject only; embedded text detection and aesthetics UNVERIFIED'}
        if supplied:
            authored = next(s for s in supplied['shots'] if s['shot_id'] == shot['id'])
            if authored['evidence_sha256'] != binding or set(authored['viewed_frames']) != selected:
                raise ValueError(shot['id']+': stale/unviewed observation frames; inspect current snapshots')
            for key in ('subjects','embedded_text','unusable'):
                if any(not b[0] < b[2] or not b[1] < b[3] for b in authored[key]):
                    raise ValueError(shot['id']+': invalid observation box')
            entry.update({k: authored[k] for k in ('embedded_text','unusable','emotion','reason')})
            entry['subjects'] += authored['subjects']
            entry.update(provider=supplied['provider'], status='DECLARED_OBSERVATION',
                         model_status='DECLARED_VIEWED' if supplied['provider']=='agent' else 'NOT_RUN')
        result.append(entry)
    return {'schema_version':'1.0', 'artifact_kind':'technical_fixture' if technical else 'production',
            'shots':result}, outputs
