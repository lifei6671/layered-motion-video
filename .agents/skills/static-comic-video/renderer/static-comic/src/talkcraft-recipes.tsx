/**
 * Noncommercial motion primitives adapted from video-talkcraft:
 * https://github.com/Vincentwei1021/video-talkcraft
 * Upstream: template/cards/number-slab-pop.tsx and template/cards/ink-underline.tsx
 * Required Notice: Copyright (c) 2026 Vincent Wei
 * License: PolyForm Noncommercial 1.0.0
 * https://polyformproject.org/licenses/noncommercial/1.0.0
 * Changes: isolated content-independent deterministic motion components,
 * dropped host footage and all demo assets/text. No audio is generated here.
 */
import type {CSSProperties} from 'react';
import {useCurrentFrame} from 'remotion';

const clamp = (n: number) => Math.max(0, Math.min(1, n));
const smooth = (p: number) => 1 - Math.pow(1 - clamp(p), 4);
const overshoot = (p: number) => {
  const t = clamp(p) - 1;
  return 1 + 2.70158 * t * t * t + 1.70158 * t * t;
};
const between = (frame: number, start: number, frames: number, curve: (n: number) => number) =>
  curve((frame - start) / Math.max(1, frames));

export const TALKCRAFT_RECIPE_IDS = ['talkcraft-number-slab', 'talkcraft-ink-underline'] as const;

type NumberSlabProps = {
  number: string;
  label?: string;
  accent?: string;
  ink?: string;
  background?: string;
  startFrame?: number;
  fontFamily?: string;
};

/** Full-frame insert; keeps its duration in the caller's fixed global timeline. */
export function TalkcraftNumberSlab({
  number, label = '', accent = '#d73d37', ink = '#181818',
  background = '#fbf8f2', startFrame = 0, fontFamily = 'sans-serif',
}: NumberSlabProps) {
  const frame = useCurrentFrame() - startFrame;
  const slab = between(frame, 8, 7, smooth);
  const numeral = between(frame, 15, 9, overshoot);
  const details = between(frame, 21, 7, smooth);
  const caption = between(frame, 27, 8, smooth);
  const center: CSSProperties = {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    position: 'absolute', inset: 0,
  };
  return <div style={{...center, background, fontFamily, overflow: 'hidden'}}>
    <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', maxWidth: '90%'}}>
      <div style={{background: accent, borderRadius: 24, padding: '30px 56px',
        opacity: slab, transform: `translateY(${(slab - 1) * 20}px) scale(${.94 + .06 * slab})`}}>
        <div style={{fontVariantNumeric: 'tabular-nums', fontWeight: 800, fontSize: 140,
          lineHeight: 1.15, color: '#ffffff', whiteSpace: 'nowrap',
          opacity: Math.min(1, Math.max(0, numeral)), transform: `scale(${.72 + .28 * numeral})`}}>
          {number}
        </div>
      </div>
      {label && <div style={{marginTop: 34, fontSize: 40, fontWeight: 600, color: ink,
        opacity: caption, transform: `translateY(${6 * (1 - caption)}px)`}}>{label}</div>}
      <div style={{position: 'absolute', width: 0, height: 0, opacity: details}} />
    </div>
  </div>;
}

type InkUnderlineProps = {
  width: number;
  y: number;
  color?: string;
  thickness?: number;
  startFrame?: number;
  durationFrames?: number;
  seed?: number;
};

type Point = [number, number];
const cubicPoint = (t: number, a: Point, b: Point, c: Point, d: Point): Point => {
  const u = 1 - t;
  return [u ** 3 * a[0] + 3 * u * u * t * b[0] + 3 * u * t * t * c[0] + t ** 3 * d[0],
          u ** 3 * a[1] + 3 * u * u * t * b[1] + 3 * u * t * t * c[1] + t ** 3 * d[1]];
};

/** Returns a deterministic, tapered fill path; unit-testable without a browser. */
export function inkRibbonPath(width: number, y: number, thickness: number, progress: number, seed = 7): string {
  if (![width, y, thickness, progress, seed].every(Number.isFinite) || width <= 0 || thickness <= 0)
    throw new Error('Invalid ink underline geometry');
  const wobble = ((seed % 7) - 3) * .5;
  const a: Point = [0, y];
  const b: Point = [width * .3, y + wobble];
  const c: Point = [width * .7, y - wobble];
  const d: Point = [width, y + wobble * .6];
  const count = Math.max(2, Math.floor(40 * clamp(progress)));
  const left: Point[] = [], right: Point[] = [];
  for (let i = 0; i < count; i++) {
    const t = i / 39;
    const here = cubicPoint(t, a, b, c, d);
    const prev = cubicPoint(Math.max(0, t - .01), a, b, c, d);
    const next = cubicPoint(Math.min(1, t + .01), a, b, c, d);
    const dx = next[0] - prev[0], dy = next[1] - prev[1];
    const norm = Math.hypot(dx, dy) || 1;
    const half = thickness * (.5 - .38 * t);
    const nx = -dy / norm * half, ny = dx / norm * half;
    left.push([here[0] + nx, here[1] + ny]);
    right.push([here[0] - nx, here[1] - ny]);
  }
  const points = [...left, ...right.reverse()];
  return points.map(([x, py], i) => `${i ? 'L' : 'M'} ${x.toFixed(2)} ${py.toFixed(2)}`).join(' ') + ' Z';
}

/** Render this inside the already approved keyword layout box. */
export function TalkcraftInkUnderline({
  width, y, color = '#b54b24', thickness = 14,
  startFrame = 0, durationFrames = 12, seed = 7,
}: InkUnderlineProps) {
  const frame = useCurrentFrame();
  const progress = smooth((frame - startFrame) / Math.max(1, durationFrames));
  return <svg viewBox={`0 0 ${width} ${Math.max(32, y + thickness * 2)}`}
    style={{width, height: Math.max(32, y + thickness * 2), overflow: 'visible', pointerEvents: 'none'}}>
    <path d={inkRibbonPath(width, y, thickness, progress, seed)} fill={color} />
  </svg>;
}
