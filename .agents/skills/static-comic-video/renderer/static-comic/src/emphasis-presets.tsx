import type {Props} from './contracts.generated.js';

export type VisualEvent = NonNullable<Props['visual_emphasis']>[number];
export const BASIC_PRESETS = ['soft_rise', 'comic_pop', 'comic_burst', 'number_tick', 'underline_reveal', 'stagger_group'] as const;
// Keep in sync with Python layout's conservative dynamic envelope.
export const EMPHASIS_ENVELOPE = {maxScale: 1.18, maxTranslation: 12} as const;
export const clamp = (value: number) => Math.max(0, Math.min(1, value));
const progress = (frame: number, start: number, end: number) => clamp((frame - start) / Math.max(1, end - start));

export function numberAt(text: string, progress: number): string {
  const match = /^([+-]?)(\d+)(\.\d+)?(%|％|元|倍|万|亿|人|次|个)?$/.exec(text);
  if (!match || !Number.isFinite(Number(match[1] + match[2] + (match[3] ?? ''))) ||
      Math.abs(Number(match[2])) > Number.MAX_SAFE_INTEGER) {
    throw new Error('number_tick requires an exact Arabic number and supported unit: ' + text);
  }
  const decimals = (match[3]?.length ?? 1) - 1;
  if (decimals > 6) throw new Error('number_tick supports at most six decimal places');
  if (progress >= 1) return text; // Preserve original spelling, trailing decimals and unit.
  const target = Number(match[2] + (match[3] ?? ''));
  const value = (target * clamp(progress)).toFixed(decimals);
  return match[1] + value + (match[4] ?? '');
}

export function emphasisState(event: VisualEvent, localFrame: number) {
  const frame = event.start_frame + localFrame;
  const {enter_start, impact, settle, exit_start} = event.markers;
  const entering = progress(frame, enter_start, settle);
  const exiting = progress(frame, exit_start, event.end_frame - 1);
  const active = localFrame >= 0 && frame < event.end_frame;
  let scale = 1;
  let dx = 0;
  let dy = 0;
  if (event.preset === 'comic_pop' || event.preset === 'comic_burst') {
    scale = frame <= impact ? .72 + .46 * progress(frame, enter_start, impact) :
      1.18 - .18 * progress(frame, impact, settle);
    if (event.preset === 'comic_burst' && frame >= impact && frame < settle) {
      dx = (localFrame % 2 === 0 ? 1 : -1) * 6 * (1 - progress(frame, impact, settle));
    }
  } else if (event.preset === 'soft_rise') {
    dy = 12 * (1 - entering);
  }
  return {scale, dx, dy, entering, exiting, opacity: active ? Math.min(1, entering * 3) * (1 - exiting) : 0,
    reveal: entering, countProgress: progress(frame, enter_start, settle)};
}

export function EmphasisText({event, text = event.text, fill = event.color}: {event: VisualEvent; text?: string; fill?: string}) {
  return <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" xmlSpace="preserve"
    fontFamily={'emphasis-' + event.font_sha256} fontSize={event.layout.font_size}
    fill={fill} stroke={event.stroke_color} strokeWidth={event.stroke_width}
    paintOrder="stroke" strokeLinejoin="round" style={{fontSynthesis: 'none'}}>{text}</text>;
}

export function BasicEmphasis({event, localFrame}: {event: VisualEvent; localFrame: number}) {
  const state = emphasisState(event, localFrame);
  const width = event.layout.width * 1920;
  const height = event.layout.height * 1080;
  const text = event.preset === 'number_tick' ? numberAt(event.text, state.countProgress) : event.text;
  return <>
    {event.preset === 'comic_burst' && <g stroke={event.color} strokeWidth={2} opacity={1 - state.entering}>
      {Array.from({length: 8}, (_, i) => {
        const angle = i * Math.PI / 4;
        return <line key={i} x1={width / 2 + Math.cos(angle) * width * .42}
          y1={height / 2 + Math.sin(angle) * height * .34}
          x2={width / 2 + Math.cos(angle) * width * .49}
          y2={height / 2 + Math.sin(angle) * height * .47} />;
      })}
    </g>}
    {event.preset === 'stagger_group' ?
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" xmlSpace="preserve"
        fontFamily={'emphasis-' + event.font_sha256} fontSize={event.layout.font_size}
        style={{fontKerning: 'none', fontVariantLigatures: 'none', fontSynthesis: 'none'}}
        fill={event.color} stroke={event.stroke_color} strokeWidth={event.stroke_width} paintOrder="stroke" strokeLinejoin="round">
        {Array.from(text).map((character, i, points) => <tspan key={i}
          opacity={clamp(state.entering * (points.length + 1) - i)}>{character}</tspan>)}
      </text> : <EmphasisText event={event} text={text} />}
    {event.preset === 'underline_reveal' && <line x1={width * .05} x2={width * (.05 + .9 * state.reveal)}
      y1={height * .9} y2={height * .9} stroke={event.color} strokeWidth={Math.max(2, event.stroke_width)} />}
  </>;
}
