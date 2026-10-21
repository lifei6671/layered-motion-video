import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import type {ExecutionShot} from './contracts.generated.js';
import {motionAt} from './motion.js';

export function StaticShot({shot}: {shot: ExecutionShot}) {
  const state = motionAt(shot, useCurrentFrame());
  return <AbsoluteFill style={{overflow: 'hidden'}} data-shot={shot.id} data-logical-frame={state.logicalFrame}>
    <Img src={staticFile(shot.staged_image)} style={{
      width: '100%', height: '100%', position: 'absolute',
      transform: `scale(${state.scale})`,
      transformOrigin: `${state.anchor[0] * 100}% ${state.anchor[1] * 100}%`,
    }} />
  </AbsoluteFill>;
}
