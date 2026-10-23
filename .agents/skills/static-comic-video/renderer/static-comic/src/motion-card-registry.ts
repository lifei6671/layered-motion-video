/** SC-M 受控动效注册表：仅开放明确审查过的配方，无任意脚本入口。
 * Talkcraft 两个基础动画已在 talkcraft-recipes.tsx 中按非商业协议适配。
 */
export const MOTION_CARD_RECIPES = {
  'talkcraft-number-slab': {minFrames: 42, maxFrames: 150, scope: 'full', energy: 'medium', source: 'video-talkcraft'},
  'talkcraft-ink-underline': {minFrames: 32, maxFrames: 150, scope: 'full', energy: 'low', source: 'video-talkcraft'},
  'talkcraft-chapter-card': {minFrames: 48, maxFrames: 180, scope: 'full', energy: 'medium', source: 'video-talkcraft'},
} as const;

export type MotionCardRecipeId = keyof typeof MOTION_CARD_RECIPES;
export const MOTION_CARD_RECIPE_IDS = Object.keys(MOTION_CARD_RECIPES) as MotionCardRecipeId[];
export const MOTION_CARD_RECIPE_VERSION = 'sc-m1.0';

export function motionRecipe(id: string) {
  if (!Object.prototype.hasOwnProperty.call(MOTION_CARD_RECIPES, id)) {
    throw new Error('Unregistered motion-card recipe: ' + id);
  }
  return MOTION_CARD_RECIPES[id as MotionCardRecipeId];
}

/** 每一帧由纯函数确定；离场前后画面透明，原漫画可自然接管。 */
export function motionCardOpacity(frame: number, duration: number) {
  if (!Number.isInteger(frame) || !Number.isInteger(duration) || duration <= 0) throw new Error('Invalid card frame');
  if (frame < 0 || frame >= duration) return 0;
  return Math.min(1, frame / 5, (duration - 1 - frame) / 5);
}
