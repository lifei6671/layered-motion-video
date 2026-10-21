import type {ExecutionShot} from './contracts.generated.js';

export function motionAt(shot: ExecutionShot, localFrame: number) {
  const j = Math.max(0, Math.min(shot.logical_frames - 1, localFrame - shot.head_hold_frames));
  const u = j / Math.max(1, shot.logical_frames - 1);
  const e = u * u * (3 - 2 * u);
  const motion = shot.motion;
  return {
    logicalFrame: j,
    scale: motion.scale_from + (motion.scale_to - motion.scale_from) * e,
    anchor: motion.crop_anchor_from.map((a, i) => a + (motion.crop_anchor_to[i] - a) * e),
  };
}

// linearTiming supplies frame/L; choose a real discrete black frame for odd AND even L.
export function fadeBlackOpacity(direction: 'entering' | 'exiting', progress: number, duration: number) {
  if (!Number.isInteger(duration) || duration < 3) throw new Error('fade_black requires at least 3 frames');
  const k = Math.max(0, Math.min(duration - 1, Math.round(progress * duration)));
  const middle = Math.floor((duration - 1) / 2);
  return direction === 'exiting' ? Math.max(0, 1 - k / middle) :
    Math.max(0, (k - middle) / (duration - 1 - middle));
}
