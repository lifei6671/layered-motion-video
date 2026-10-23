"""Finite layouts checked against every motion frame and the template envelope."""
from io import BytesIO

from PIL import ImageFont

from .emphasis_vision import POSITIONS


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def glyph_coverage(data, text):
    # The installed fontTools is used only for reading the font cmap, never to
    # fetch a font. Missing dependency is explicit, not a fallback font.
    try:
        from fontTools.ttLib import TTFont
    except ImportError as error:
        raise ValueError('UNAVAILABLE: fontTools is required for glyph coverage') from error
    try:
        with TTFont(BytesIO(data)) as font:
            cmap = font.getBestCmap() or {}
            missing = sorted({ord(c) for c in text if not c.isspace() and ord(c) not in cmap})
    except Exception as error:
        raise ValueError('Invalid font cmap: '+str(error)) from error
    if missing:
        raise ValueError('Font lacks code points: '+', '.join(f'U+{c:04X}' for c in missing))


def choose_layout(event, font_data, observation, geometry, policy):
    if observation['emotion'] == 'quiet':
        return None, {'reason_code':'QUIET_NARRATIVE'}
    if not observation['subjects']:
        return None, {'reason_code':'UNVERIFIED', 'detail':'No subject geometry'}
    glyph_coverage(font_data, event['text'])
    size = event.get('font_size', 72)
    from fontTools.ttLib import TTFont
    with TTFont(BytesIO(font_data)) as parsed:
        upm = parsed['head'].unitsPerEm
        hhea = parsed['hhea']
        em_height = (hhea.ascent-hhea.descent+hhea.lineGap)/upm
        if 'OS/2' in parsed:
            os2 = parsed['OS/2']
            em_height = max(em_height,(os2.usWinAscent+os2.usWinDescent)/upm,
                            (os2.sTypoAscender-os2.sTypoDescender+os2.sTypoLineGap)/upm)
        if parsed.flavor:
            parsed.flavor = None
            sfnt = BytesIO(); parsed.save(sfnt); font_data = sfnt.getvalue()
    font = ImageFont.truetype(BytesIO(font_data), size=size)
    # lineHeight=1.2 in the renderer; include long glyph bearings in width.
    bbox = font.getbbox(event['text'])
    advance = (sum(font.getlength(c) for c in event['text']) if event['preset']=='stagger_group'
               else font.getlength(event['text']))
    if event['preset']=='number_tick':
        digit = max(font.getlength(c) for c in '0123456789')
        advance = sum(digit if c in '0123456789' else font.getlength(c) for c in event['text'])
    width = max(advance, bbox[2]-min(0,bbox[0])) + 4
    # Chromium SVG getBBox includes the font's Windows line metrics, which
    # exceed 1.2em for real CJK fonts such as LXGW WenKai.
    height = max(size*1.2, size*em_height+4, bbox[3]-bbox[1])
    request = event.get('layout', {})
    if width > request.get('max_width', .4)*1920:
        return None, {'reason_code':'NO_SAFE_REGION', 'detail':'Text exceeds max_width'}
    stroke = event.get('stroke_width', 3)
    shadow = event.get('shadow_px', 4)
    # Shared upper bound with emphasis-presets.tsx: 1.18x, <=12px motion.
    pad = (stroke + shadow*3)*1.18 + 12 + 8
    extra_x, extra_y = (width*.18/2+pad)/1920, (height*.18/2+pad)/1080
    top,right,bottom,left = policy['safe_insets']
    if policy.get('selection') == 'manual':
        if not event.get('pinned') or not all(k in request for k in ('x','y')):
            return None, {'reason_code':'MANUAL_SELECTION_REQUIRED'}
        candidates = [('fixed', (request['x'],request['y']))]
    elif event.get('pinned') and 'x' in request and 'y' in request:
        candidates = [('fixed', (request['x'],request['y']))]
    else:
        preferred = request.get('preset')
        names = ([preferred] if preferred in POSITIONS else []) + [p for p in POSITIONS if p != preferred]
        candidates = [(p, POSITIONS[p]) for p in names]
    failures = []
    for name, (x,y) in candidates:
        outer = [x-extra_x,y-extra_y,x+width/1920+extra_x,y+height/1080+extra_y]
        if not (left <= outer[0] and top <= outer[1] and outer[2] <= 1-right and outer[3] <= 1-bottom):
            failures.append({'position':name,'reason':'SAFE_INSETS'}); continue
        stats = observation['regions'].get(name, [])
        if stats and max(m['edge'] for m in stats) > 26:
            failures.append({'position':name,'reason':'VISUAL_BUSY'}); continue
        collision = None
        w,h = geometry['prepared_size']
        for frame in geometry['frames']:
            cx,cy,cw,ch = frame['crop']
            for box in observation['subjects']+observation['embedded_text']+observation['unusable']:
                projected = [(box[0]*w-cx)/cw,(box[1]*h-cy)/ch,(box[2]*w-cx)/cw,(box[3]*h-cy)/ch]
                if overlap(outer, projected):
                    collision = frame['global_frame']; break
            if collision is not None:
                break
        if collision is not None:
            failures.append({'position':name,'reason':'COLLISION','global_frame':collision}); continue
        luma = sum(m['luma'] for m in stats)/max(1,len(stats))
        return {'x':x,'y':y,'width':width/1920,'height':height/1080,'font_size':size}, {
            'reason_code':'SAFE_REGION', 'position':name, 'envelope':outer,
            'frames_checked':len(geometry['frames']), 'color':'#171717' if luma > 140 else '#ffffff',
            'stroke_color':'#ffffff' if luma > 140 else '#171717'}
    return None, {'reason_code':'NO_SAFE_REGION','attempts':failures}
