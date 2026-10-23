import {clamp, EmphasisText, emphasisState, type VisualEvent} from './emphasis-presets.js';

export const ADVANCED_PRESETS = ['ink_reveal', 'light_sweep'] as const;
export const PARTICLE_BUDGET = {maxParticles: 120, maxFrames: 90, implemented: false} as const;

export function assertSupportedPreset(event: VisualEvent) {
  if (event.preset === 'fragment_disperse' || event.preset === 'particle_assemble') {
    throw new Error(event.id + ': particle template UNAVAILABLE; no particle implementation');
  }
  if (event.tier === 3) throw new Error(event.id + ': prerendered alpha effects UNAVAILABLE');
  if (event.tier === 2 && (!ADVANCED_PRESETS.includes(event.preset as typeof ADVANCED_PRESETS[number]) ||
      event.end_frame - event.start_frame > 90)) {
    throw new Error(event.id + ': advanced template or 90-frame budget invalid');
  }
}

export function AdvancedEmphasis({event, localFrame}: {event: VisualEvent; localFrame: number}) {
  const {reveal} = emphasisState(event, localFrame);
  // Hex-encode IDs to make deterministic SVG references safe for every schema ID.
  const id = 'emphasis-' + Array.from(event.id, c => c.codePointAt(0)!.toString(16)).join('-');
  const width = event.layout.width * 1920;
  const height = event.layout.height * 1080;
  if (event.preset === 'ink_reveal') {
    const edge = width * reveal;
    // Fixed, seed-derived ragged edge: no random calls or per-frame particle allocation.
    const offset = (event.seed % 7) + 3;
    return <>
      <defs><clipPath id={id}><path d={`M0 0 H${edge} L${Math.max(0, edge-offset)} ${height*.25} L${edge} ${height*.5} L${Math.max(0, edge-offset)} ${height*.75} L${edge} ${height} H0 Z`} /></clipPath></defs>
      <g clipPath={reveal === 1 ? undefined : `url(#${id})`}><EmphasisText event={event} /></g>
    </>;
  }
  const center = reveal * 140 - 20;
  return <>
    <defs><linearGradient id={id}>
      <stop offset={`${clamp((center - 12) / 100) * 100}%`} stopColor={event.color} />
      <stop offset={`${clamp(center / 100) * 100}%`} stopColor="#ffffff" />
      <stop offset={`${clamp((center + 12) / 100) * 100}%`} stopColor={event.color} />
    </linearGradient></defs>
    <EmphasisText event={event} fill={reveal >= 1 ? event.color : `url(#${id})`} />
  </>;
}
