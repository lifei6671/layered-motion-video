import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {contractValidator, validateProps} from './dist/contracts.js';
import {BASIC_PRESETS, BasicEmphasis, emphasisState, numberAt, EMPHASIS_ENVELOPE} from './dist/emphasis-presets.js';
import {ADVANCED_PRESETS, AdvancedEmphasis, assertSupportedPreset} from './dist/emphasis-advanced.js';
import {VisualEmphasisOverlay} from './dist/VisualEmphasisOverlay.js';

const read = name => JSON.parse(readFileSync(new URL(name, import.meta.url)));
const validate = contractValidator(read('../../schemas/contracts.json'));
const baseline = read('../../fixtures/visual/clock-360/props.json');
const event = {id: 'VE-001', shot_id: 'SHOT-001', text: '300%', preset: 'comic_pop', tier: 1,
  start_frame: 30, end_frame: 70, anchor_frame: 36, enter_frames: 12, hold_frames: 18, exit_frames: 10,
  markers: {enter_start: 30, impact: 36, settle: 42, exit_start: 60},
  layout: {x: .1, y: .1, width: .25, height: .1, font_size: 60}, font_asset_id: 'font-001',
  font_path: 'fonts/' + 'a'.repeat(64) + '.ttf', font_sha256: 'a'.repeat(64),
  color: '#ffffff', stroke_color: '#000000', stroke_width: 2, shadow_px: 2, seed: 123,
  script_range: [0, 4], speech_samples: [57600, 80000]};
const checked = (...events) => validateProps(validate, {...structuredClone(baseline), visual_emphasis: events}, true);

test('zero-event overlay emits no element and old props need no fonts', () => {
  assert.equal(renderToStaticMarkup(createElement(VisualEmphasisOverlay, {events: []})), '');
  assert.doesNotThrow(() => validateProps(validate, baseline, true));
});

for (const preset of [...BASIC_PRESETS, ...ADVANCED_PRESETS]) {
  test(preset + ': locked global markers bound deterministic animation envelope and lifetime', () => {
    const value = {...event, preset, tier: ADVANCED_PRESETS.includes(preset) ? 2 : 1};
    checked(value);
    assert.equal(emphasisState(value, -1).opacity, 0);
    assert.equal(emphasisState(value, 0).opacity, 0);
    assert.equal(emphasisState(value, 39).opacity, 0);
    assert.equal(emphasisState(value, 40).opacity, 0);
    assert.equal(emphasisState(value, 12).opacity, 1);
    for (let frame = 0; frame < 40; frame++) {
      const state = emphasisState(value, frame);
      assert.deepEqual(state, emphasisState(value, frame));
      assert.ok(state.scale <= EMPHASIS_ENVELOPE.maxScale);
      assert.ok(Math.abs(state.dx) <= EMPHASIS_ENVELOPE.maxTranslation);
      assert.ok(Math.abs(state.dy) <= EMPHASIS_ENVELOPE.maxTranslation);
      assert.ok(state.opacity >= 0 && state.opacity <= 1);
    }
    // SSR verifies markup determinism only; real browser frames are separate acceptance.
    const Component = value.tier === 1 ? BasicEmphasis : AdvancedEmphasis;
    const markup = () => renderToStaticMarkup(createElement('svg', null, createElement(Component, {event: value, localFrame: 6})));
    assert.equal(markup(), markup());
    assert.match(markup(), /emphasis-/);
  });
}

test('impact is the exact pop maximum and settle returns to the lock size', () => {
  assert.equal(emphasisState(event, event.markers.impact - event.start_frame).scale, 1.18);
  assert.equal(emphasisState(event, event.markers.settle - event.start_frame).scale, 1);
  const later = structuredClone(event);
  later.start_frame += 100; later.end_frame += 100; later.anchor_frame += 100;
  for (const marker of Object.keys(later.markers)) later.markers[marker] += 100;
  assert.deepEqual(emphasisState(event, 6), emphasisState(later, 6));
});

test('numeric values stop at the exact source spelling and reject ambiguous source', () => {
  for (const value of ['300%', '-12.50元', '+004倍', '0.001％', '7亿']) assert.equal(numberAt(value, 1), value);
  assert.equal(numberAt('300%', .5), '150%');
  assert.equal(numberAt('-12.50元', .5), '-6.25元');
  for (const value of ['三百', '约300%', '1,200元', '3e2', '1/3', '9007199254740992', '0.1234567', '¥300']) {
    assert.throws(() => numberAt(value, .5), /number_tick/);
    assert.throws(() => checked({...event, preset: 'number_tick', text: value}), /number_tick/);
  }
});

test('unsafe layout, untrusted font, transition spill and inconsistent marker locks fail closed', () => {
  for (const mutate of [
    value => {value.layout.x = 0;},
    value => {value.markers.impact++;},
    value => {value.end_frame++;},
    value => {value.font_path = 'fonts/' + 'b'.repeat(64) + '.ttf';},
    value => {value.start_frame = 100; value.end_frame = 140;},
    value => {value.tier = 2;},
    value => {value.text = '第一行\r\n第二行';},
  ]) {
    const value = structuredClone(event); mutate(value);
    assert.throws(() => checked(value));
  }
  assert.throws(() => checked(event, event), /execution budget/);
});

test('particles and alpha prereenders remain explicitly unavailable; advanced work stays within budget', () => {
  for (const preset of ['fragment_disperse', 'particle_assemble']) {
    assert.throws(() => assertSupportedPreset({...event, preset, tier: 2}), /UNAVAILABLE/);
    assert.throws(() => checked({...event, preset, tier: 2}), /UNAVAILABLE/);
  }
  assert.throws(() => assertSupportedPreset({...event, tier: 3}), /UNAVAILABLE/);
  assert.throws(() => assertSupportedPreset({...event, preset: 'ink_reveal', tier: 2, end_frame: 121}), /90-frame/);
});
