import {AbsoluteFill} from 'remotion';
import {TransitionSeries} from '@remotion/transitions';
import type {Props} from './contracts.generated.js';
import {StaticShot} from './StaticShot.js';
import {transitionElement} from './transitions.js';
import {VisualEmphasisOverlay} from './VisualEmphasisOverlay.js';
import {MotionCardTrack} from './MotionCardTrack.js';

export function ComicVideo({shots, visual_emphasis, motion_cards}: {[K in keyof Props]: Props[K]}) {
  return <AbsoluteFill style={{backgroundColor: '#000', overflow: 'hidden'}}>
    <TransitionSeries>{shots.flatMap((shot) => {
      const sequence = <TransitionSeries.Sequence key={shot.id} name={shot.id} durationInFrames={shot.physical_frames}>
        <StaticShot shot={shot} />
      </TransitionSeries.Sequence>;
      const transition = shot.transition_out;
      if (!transition || transition.type === 'cut') return [sequence];
      return [sequence, transitionElement(transition.type, transition.duration_frames, shot.id + '-transition')];
    })}</TransitionSeries>
    {/* SC-M2：字卡覆盖原漫画稳定窗口，不能改变镜头或原始声音的长度。 */}
    <MotionCardTrack cards={motion_cards ?? []} />
    <VisualEmphasisOverlay events={visual_emphasis ?? []} />
  </AbsoluteFill>;
}
