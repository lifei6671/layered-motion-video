import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {contractValidator, validateProps} from './dist/contracts.js';
import {motionCardOpacity, motionRecipe, MOTION_CARD_RECIPE_IDS} from './dist/motion-card-registry.js';
import {MotionCardTrack} from './dist/MotionCardTrack.js';
import {inkRibbonPath} from './dist/talkcraft-recipes.js';

const read = name => JSON.parse(readFileSync(new URL(name, import.meta.url), 'utf8'));
const validate = contractValidator(read('../../schemas/contracts.json'));
const original = read('../../fixtures/visual/clock-360/props.json');
const card = {
  id: 'MC-001', shot_id: 'SHOT-001', recipe: 'talkcraft-number-slab',
  script_range: [0, 4], text: '166元', style: 'paper', source: 'manual',
  start_frame: 34, end_frame: 96,
};
const withCards = (...cards) => validateProps(validate, {...structuredClone(original), motion_cards: cards}, true);

test('SC-M: old props and zero cards preserve the old composition', () => {
  assert.doesNotThrow(() => validateProps(validate, original, true));
  assert.equal(renderToStaticMarkup(createElement(MotionCardTrack, {cards: []})), '');
  assert.equal(original.video.total_frames, 360);
});

test('SC-M: trusted recipe registry contains no dynamic eval or unregistered code', () => {
  assert.deepEqual(MOTION_CARD_RECIPE_IDS.sort(), [
    'talkcraft-chapter-card', 'talkcraft-ink-underline', 'talkcraft-number-slab']);
  assert.equal(motionRecipe(card.recipe).scope, 'full');
  assert.throws(() => motionRecipe('evil-js'), /Unregistered/);
});

test('SC-M: accepted card stays in its original stable shot and does not change video duration', () => {
  const props = withCards(card);
  assert.equal(props.motion_cards.length, 1);
  assert.equal(props.video.total_frames, original.video.total_frames);
});

test('SC-M: transition spill, invalid schedule, duplicate and unknown recipes reject', () => {
  for (const patch of [
    {start_frame: 110, end_frame: 172},
    {start_frame: -1, end_frame: 60},
    {start_frame: 34, end_frame: 35},
    {recipe: 'eval("__attack")'},
    {text: '16<script>'},
    {text: '123456789012345元'},
    {style: 'url(https://malicious)'},
    {extra: 'untrusted'},
  ]) {
    assert.throws(() => withCards({...card, ...patch}));
  }
  assert.throws(() => withCards(card, {...card, id: 'MC-002', start_frame: 50, end_frame: 100}), /overlap|density/);
});

test('SC-M: second card in another stable shot is permitted with frame-safe timing', () => {
  const second = {...card, id: 'MC-002', shot_id: 'SHOT-002',
    recipe: 'talkcraft-ink-underline', text: '冲动消费',
    script_range: [5, 9], start_frame: 132, end_frame: 194};
  assert.equal(withCards(card, second).motion_cards.length, 2);
});

test('SC-M: frame envelope fades only at boundaries and is deterministic', () => {
  assert.equal(motionCardOpacity(-1, 62), 0);
  assert.equal(motionCardOpacity(0, 62), 0);
  assert.equal(motionCardOpacity(5, 62), 1);
  assert.equal(motionCardOpacity(30, 62), 1);
  assert.equal(motionCardOpacity(61, 62), 0);
  assert.equal(motionCardOpacity(62, 62), 0);
  assert.equal(motionCardOpacity(1, 62), motionCardOpacity(1, 62));
});

test('SC-M: stroke algorithm stays finite, deterministic and rejects invalid geometry', () => {
  const path = inkRibbonPath(800, 32, 14, .75, 11);
  assert.equal(path, inkRibbonPath(800, 32, 14, .75, 11));
  assert.match(path, /^M /);
  assert.match(path, / Z$/);
  assert.doesNotMatch(path, /NaN|Infinity/);
  assert.throws(() => inkRibbonPath(0, 32, 14, .75), /Invalid/);
});
