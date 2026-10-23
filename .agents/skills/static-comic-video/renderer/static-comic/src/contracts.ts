import {Ajv2020} from 'ajv/dist/2020.js';
import type {StaticComicContracts} from './contracts.generated.js';
import {BASIC_PRESETS, EMPHASIS_ENVELOPE, numberAt} from './emphasis-presets.js';
import {ADVANCED_PRESETS, assertSupportedPreset} from './emphasis-advanced.js';
import {motionRecipe} from './motion-card-registry.js';

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
  const eventIds = new Set<string>();
  for (const event of props.visual_emphasis ?? []) {
    const shotIndex = props.shots.findIndex(shot => shot.id === event.shot_id);
    const shot = props.shots[shotIndex];
    const previous = props.shots[shotIndex - 1]?.transition_out;
    const {enter_start, impact, settle, exit_start} = event.markers;
    if (!shot || eventIds.has(event.id) || event.start_frame < shot.start_frame + (previous?.post_frames ?? 0) ||
        event.end_frame > shot.end_frame - (shot.transition_out?.pre_frames ?? 0) ||
        event.enter_frames < 2 || event.exit_frames < 2 || event.hold_frames < 1 ||
        event.end_frame - event.start_frame !== event.enter_frames + event.hold_frames + event.exit_frames ||
        enter_start !== event.start_frame || impact !== event.anchor_frame ||
        impact <= enter_start || impact >= settle || settle !== event.start_frame + event.enter_frames ||
        exit_start !== settle + event.hold_frames ||
        !new RegExp('^fonts/' + event.font_sha256 + '\\.(ttf|otf|woff|woff2)$').test(event.font_path)) {
      throw new Error('Invalid emphasis execution budget: ' + event.id);
    }
    assertSupportedPreset(event);
    if (/[\r\n\t]/.test(event.text)) throw new Error('Emphasis requires single-line source text: ' + event.id);
    if ((event.tier === 1 && !BASIC_PRESETS.includes(event.preset as typeof BASIC_PRESETS[number])) ||
        (event.tier === 2 && !ADVANCED_PRESETS.includes(event.preset as typeof ADVANCED_PRESETS[number]))) {
      throw new Error('Invalid emphasis preset tier: ' + event.id);
    }
    if (event.preset === 'number_tick') numberAt(event.text, 0);
    const {x, y, width, height} = event.layout;
    const padding = (event.stroke_width + event.shadow_px * 3) * EMPHASIS_ENVELOPE.maxScale + EMPHASIS_ENVELOPE.maxTranslation;
    const extraX = width * (EMPHASIS_ENVELOPE.maxScale - 1) / 2 + padding / 1920;
    const extraY = height * (EMPHASIS_ENVELOPE.maxScale - 1) / 2 + padding / 1080;
    if (x - extraX < 0 || y - extraY < 0 || x + width + extraX > 1 || y + height + extraY > 1) {
      throw new Error('Emphasis dynamic envelope leaves canvas: ' + event.id);
    }
    eventIds.add(event.id);
  }
  // 全屏动态镜头只可占用不含转场的静态漫画稳定窗口。
  // 此处独立复核 Python 事件锁，不信任手工改动的 props.json。
  const cards = [...(props.motion_cards ?? [])].sort((a, b) => a.start_frame - b.start_frame || a.id.localeCompare(b.id));
  const seenCards = new Set<string>();
  for (let i = 0; i < cards.length; i++) {
    const card = cards[i];
    const shotIndex = props.shots.findIndex(shot => shot.id === card.shot_id);
    const shot = props.shots[shotIndex];
    if (!shot || seenCards.has(card.id)) throw new Error('Duplicate/unknown motion card: ' + card.id);
    seenCards.add(card.id);
    const previous = props.shots[shotIndex - 1]?.transition_out;
    const minFrame = shot.start_frame + (previous?.post_frames ?? 0);
    const maxFrame = shot.end_frame - (shot.transition_out?.pre_frames ?? 0);
    const recipe = motionRecipe(card.recipe);
    if (card.start_frame < minFrame || card.end_frame > maxFrame ||
        card.end_frame - card.start_frame < recipe.minFrames ||
        card.end_frame - card.start_frame > recipe.maxFrames ||
        card.script_range[0] >= card.script_range[1] ||
        /[\\r\\n\\t<>]/.test(card.text + (card.label ?? ''))) {
      throw new Error('Invalid motion-card timing/content: ' + card.id);
    }
    const maxChars = card.recipe === 'talkcraft-number-slab' ? 12 : 14;
    if (Array.from(card.text).length > maxChars || Array.from(card.label ?? '').length > 20) {
      throw new Error('Motion-card text exceeds readable width budget: ' + card.id);
    }
    if (card.recipe === 'talkcraft-number-slab' &&
        !/^[+-]?[0-9]+(?:\\.[0-9]{1,6})?(?:%|％|元|倍|万|亿|人|次|个)?$/.test(card.text)) {
      throw new Error('Unverifiable number card: ' + card.id);
    }
    if (cards.some(other => other !== card && other.shot_id === card.shot_id) ||
        cards.slice(0, i).some(other => card.start_frame < other.end_frame) ||
        (props.visual_emphasis ?? []).some(e => card.start_frame < e.end_frame && e.start_frame < card.end_frame) ||
        cards.slice(0, i).filter(other => Math.abs(card.start_frame - other.start_frame) < 1800).length >= 2) {
      throw new Error('Motion-card overlap/density conflict: ' + card.id);
    }
  }
  return props;
}

export function sliceCodepoints(text: string, start: number, end: number): string {
  const points = Array.from(text.startsWith('\uFEFF') ? text.slice(1) : text);
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start || end > points.length) {
    throw new Error('Invalid Unicode code-point range');
  }
  return points.slice(start, end).join('');
}
