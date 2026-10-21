import {Composition, getInputProps} from 'remotion';
import schema from '../../../schemas/contracts.json' with {type: 'json'};
import {contractValidator, validateProps} from './contracts.js';
import {ComicVideo} from './ComicVideo.js';

const validate = contractValidator(schema);
export function checkedProps(input: unknown, allowTechnicalFixture: boolean) {
  const props = validateProps(validate, input, allowTechnicalFixture);
  for (const shot of props.shots) {
    if (shot.transition_out?.type === 'fade_black' && shot.transition_out.duration_frames < 3) {
      throw new Error(shot.id + ': fade_black requires at least 3 frames');
    }
  }
  return {...props};
}

export function RemotionRoot({technical = false}: {technical?: boolean}) {
  const initial = checkedProps(getInputProps(), technical);
  return <Composition id="ComicVideo" component={ComicVideo} defaultProps={initial}
    durationInFrames={initial.video.total_frames} width={initial.video.width} height={initial.video.height}
    fps={initial.video.fps_num / initial.video.fps_den}
    calculateMetadata={({props}) => {
      const locked = checkedProps(props, technical);
      return {durationInFrames: locked.video.total_frames, width: locked.video.width,
        height: locked.video.height, fps: locked.video.fps_num / locked.video.fps_den, props: locked};
    }} />;
}
