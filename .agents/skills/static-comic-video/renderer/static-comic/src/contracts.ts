import {Ajv2020} from 'ajv/dist/2020.js';
import type {StaticComicContracts} from './contracts.generated.js';

export function contractValidator(schema: object) {
  const ajv = new Ajv2020({strict: true, allErrors: true});
  ajv.addSchema(schema, 'contracts');
  return <K extends keyof StaticComicContracts>(kind: K, input: unknown): StaticComicContracts[K] => {
    const check = ajv.compile({$ref: 'contracts#/$defs/' + kind});
    if (!check(input)) throw new Error(ajv.errorsText(check.errors));
    return input as StaticComicContracts[K];
  };
}

export function validateProps(
  validate: ReturnType<typeof contractValidator>, input: unknown, allowTechnicalFixture = false,
): StaticComicContracts['props'] {
  const props = validate('props', input);
  if (!allowTechnicalFixture && props.artifact_kind !== 'production') {
    throw new Error('Technical fixture is not production input');
  }
  let boundary = 0;
  const ids = new Set<string>();
  for (let i = 0; i < props.shots.length; i++) {
    const shot = props.shots[i];
    const previous = props.shots[i - 1]?.transition_out;
    const next = shot.transition_out;
    const head = previous?.pre_frames ?? 0;
    const tail = next?.post_frames ?? 0;
    if (ids.has(shot.id) || shot.start_frame !== boundary ||
        shot.end_frame - shot.start_frame !== shot.logical_frames ||
        shot.head_hold_frames !== head || shot.tail_hold_frames !== tail ||
        shot.sequence_start_frame !== boundary - head ||
        shot.physical_frames !== head + shot.logical_frames + tail ||
        (previous?.post_frames ?? 0) + (next?.pre_frames ?? 0) >= shot.logical_frames ||
        shot.staged_image !== 'images/' + shot.image_sha256 + '.png') {
      throw new Error('Invalid execution budget: ' + shot.id);
    }
    if ((i === props.shots.length - 1) !== (next === null)) throw new Error('Invalid transition chain');
    if (next) {
      const pre = next.placement === 'start_at_anchor' ? 0 :
        next.placement === 'end_at_anchor' ? next.duration_frames : Math.floor(next.duration_frames / 2);
      if ((next.type === 'cut') !== (next.duration_frames === 0) ||
          next.pre_frames !== pre || next.post_frames !== next.duration_frames - pre ||
          next.transition_start_frame !== shot.end_frame - pre ||
          next.transition_end_frame !== shot.end_frame + next.post_frames ||
          next.transition_start_frame < 0 || next.transition_end_frame > props.video.total_frames) {
        throw new Error('Invalid transition window: ' + shot.id);
      }
    }
    ids.add(shot.id);
    boundary = shot.end_frame;
  }
  if (boundary !== props.video.total_frames) throw new Error('Incomplete frame coverage');
  return props;
}

export function sliceCodepoints(text: string, start: number, end: number): string {
  const points = Array.from(text.startsWith('\uFEFF') ? text.slice(1) : text);
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start || end > points.length) {
    throw new Error('Invalid Unicode code-point range');
  }
  return points.slice(start, end).join('');
}
