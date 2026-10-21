import {AbsoluteFill} from 'remotion';
import {TransitionSeries} from '@remotion/transitions';
import type {Props} from './contracts.generated.js';
import {StaticShot} from './StaticShot.js';
import {transitionElement} from './transitions.js';

export function ComicVideo({shots}: {[K in keyof Props]: Props[K]}) {
  return <AbsoluteFill style={{backgroundColor: '#000', overflow: 'hidden'}}>
    <TransitionSeries>{shots.flatMap((shot) => {
      const sequence = <TransitionSeries.Sequence key={shot.id} name={shot.id} durationInFrames={shot.physical_frames}>
        <StaticShot shot={shot} />
      </TransitionSeries.Sequence>;
      const transition = shot.transition_out;
      if (!transition || transition.type === 'cut') return [sequence];
      return [sequence, transitionElement(transition.type, transition.duration_frames, shot.id + '-transition')];
    })}</TransitionSeries>
  </AbsoluteFill>;
}
