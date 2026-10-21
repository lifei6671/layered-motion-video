import {AbsoluteFill} from 'remotion';
import {TransitionSeries, linearTiming, type TransitionPresentationComponentProps} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {wipe} from '@remotion/transitions/wipe';
import type {TransitionType} from './contracts.generated.js';
import {fadeBlackOpacity} from './motion.js';

function FadeBlack({children, presentationDirection, presentationProgress, presentationDurationInFrames}:
  TransitionPresentationComponentProps<Record<string, never>>) {
  return <AbsoluteFill style={{opacity: fadeBlackOpacity(
    presentationDirection, presentationProgress, presentationDurationInFrames,
  )}}>{children}</AbsoluteFill>;
}

export function transitionElement(type: Exclude<TransitionType, 'cut'>, duration: number, key: string) {
  const timing = linearTiming({durationInFrames: duration});
  switch (type) {
    case 'fade': return <TransitionSeries.Transition key={key} timing={timing} presentation={fade()} />;
    case 'wipe_from_left': return <TransitionSeries.Transition key={key} timing={timing} presentation={wipe({direction: 'from-left'})} />;
    case 'wipe_from_right': return <TransitionSeries.Transition key={key} timing={timing} presentation={wipe({direction: 'from-right'})} />;
    case 'fade_black': return <TransitionSeries.Transition key={key} timing={timing} presentation={{component: FadeBlack, props: {}}} />;
  }
}
