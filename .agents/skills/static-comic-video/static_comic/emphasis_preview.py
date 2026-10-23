"""Batch-decode unique visual emphasis markers and bind them to preview review."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from .contracts import bytes_digest, canonical
from .media import file_hash, run

# Bound FFmpeg select-filter length while keeping the number of full decodes
# proportional to the number of distinct frames, not to all event markers.
FRAMES_PER_BATCH = 128


def extract_markers(visual, frames):
    """Return {absolute_frame: PNG bytes}, with exact ordering and image checks."""
    if not frames:
        return {}, None, 0
    ordered = sorted(set(frames))
    if any(type(f) is not int or f < 0 for f in ordered):
        raise ValueError('Invalid emphasis marker frame')
    video_hash = file_hash(visual)
    images = {}
    batches = 0
    with TemporaryDirectory(prefix='sc-emphasis-frames-') as directory:
        folder = Path(directory)
        for offset in range(0, len(ordered), FRAMES_PER_BATCH):
            chunk = ordered[offset:offset + FRAMES_PER_BATCH]
            # Literal, integer-only frame indices; FFmpeg will emit exactly the
            # selected frames in source order, without duplicates or timestamp shifts.
            expression = '+'.join(f'eq(n\\,{frame})' for frame in chunk)
            pattern = folder / 'frame-%05d.png'
            run(['ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-y',
                 '-i', visual, '-map', '0:v:0', '-an', '-vf', 'select=' + expression,
                 '-fps_mode', 'passthrough', '-frames:v', str(len(chunk)), '-start_number', '0',
                 '-f', 'image2', '-c:v', 'png', pattern])
            actual = sorted(folder.glob('frame-*.png'))
            if len(actual) != len(chunk):
                raise ValueError('Emphasis marker extraction missed or duplicated a video frame')
            for frame, path in zip(chunk, actual):
                data = path.read_bytes()
                with Image.open(BytesIO(data)) as image:
                    if image.format != 'PNG':
                        raise ValueError('Emphasis marker is not a PNG')
                    image.verify()
                images[frame] = data
                path.unlink()
            batches += 1
    if file_hash(visual) != video_hash:
        raise ValueError('Visual video changed while extracting emphasis markers')
    return images, video_hash, batches


def preview_evidence(visual, compiled, loc):
    outputs, entries, tiles = {}, [], []
    events = compiled['emphasis']['visual']
    markers = []
    total = compiled['total_frames']
    for event in events:
        points = {'before': max(0, event['start_frame'] - 1), **event['markers'],
                  'exit': event['end_frame'] - 1,
                  'after': min(total - 1, event['end_frame'])}
        for label, frame in points.items():
            if not 0 <= frame < total:
                raise ValueError('Emphasis frame leaves the locked video budget')
            markers.append((event, label, frame))
    frames, video_hash, batches = extract_markers(visual, [row[2] for row in markers])
    for event, label, frame in markers:
        data = frames[frame]
        name = f"{loc['preview']}/emphasis/{event['id']}-{label}-{frame:06}.png"
        outputs[name] = data
        entries.append({'id': event['id'], 'marker': label, 'global_frame': frame,
                        'path': name, 'sha256': bytes_digest(data)})
        with Image.open(BytesIO(data)) as image:
            tile = Image.new('RGB', (320, 204), '#ffffff')
            tile.paste(image.convert('RGB').resize((320, 180)), (0, 24))
            ImageDraw.Draw(tile).text((4, 4), f"{event['id']} {label} f={frame}", fill='black')
            tiles.append(tile)
    if tiles:
        sheet = Image.new('RGB', (320 * 4, 204 * ((len(tiles) + 3) // 4)), '#dddddd')
        for i, tile in enumerate(tiles):
            sheet.paste(tile, ((i % 4) * 320, (i // 4) * 204))
        buffer = BytesIO()
        sheet.save(buffer, format='JPEG', quality=92)
        outputs[loc['preview'] + '/emphasis_sheet.jpg'] = buffer.getvalue()
    outputs[loc['preview'] + '/emphasis.json'] = canonical({
        'visual_frames': entries, 'visual_sha256': video_hash,
        'unique_decoded_frames': len(frames), 'decode_batches': batches,
        'sfx_events': compiled['emphasis']['sfx'],
        'diagnostics': compiled['emphasis']['diagnostics'],
        'human_full_listening': 'NOT_RUN'})
    return outputs
