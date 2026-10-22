import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import test from 'node:test';
import {contractValidator, validateProps, sliceCodepoints} from './dist/contracts.js';
const schema = JSON.parse(readFileSync(new URL('../../schemas/contracts.json', import.meta.url)));
const validate = contractValidator(schema);
const cases = ['contracts-cases.json', 'image-contract-cases.json', 'transition-contract-cases.json', 'delivery-contract-cases.json', 'human-confirmation-contract-cases.json'].flatMap(name =>
  JSON.parse(readFileSync(new URL('../../fixtures/' + name, import.meta.url))));
for (const item of cases) {
  test('shared schema: ' + item.name, () => {
    if (item.valid) assert.doesNotThrow(() => validate(item.kind, item.value));
    else assert.throws(() => validate(item.kind, item.value));
  });
}
const props = cases.find(item => item.kind === 'props' && item.valid).value;

test('local creation does not require commercial or publication declarations', () => {
  for (const [kind, fields] of [
    ['imageBrief', ['publication_scope']], ['imageSubmission', ['license', 'license_evidence']],
  ]) {
    const value = structuredClone(cases.find(item => item.kind === kind && item.valid).value);
    for (const field of fields) delete value[field];
    assert.doesNotThrow(() => validate(kind, value));
  }
  const asset = structuredClone(cases.find(item => item.kind === 'manifest' && item.valid).value.assets[0]);
  delete asset.license;
  assert.doesNotThrow(() => validate('asset', asset));
  const checks = {comic_style: true, character_identity: true, narrative: true,
    composition: true, motion_safe: true, resolution_accepted: true};
  assert.doesNotThrow(() => validate('imageChecks', checks));
  assert.doesNotThrow(() => validate('imageChecks', {...checks, publication_rights: false, attribution_ready: false}));
  assert.doesNotThrow(() => validate('license', {publication_allowed: false}));
  assert.doesNotThrow(() => validate('imageReference', {source_uri: 'test-only', sha256: 'a'.repeat(64), version: '1'}));
  delete checks.motion_safe;
  assert.throws(() => validate('imageChecks', checks));
});

test('chat confirmation schema binds evidence shape without requiring a terminal source', () => {
  const human = {
    actor: 'conversation_user', actor_role: 'human', at: '2026-10-22T00:00:00Z',
    evidence: 'SYNTHETIC TEST ONLY',
    confirmation: {
      source: 'conversation', scope: 'policy', payload: {payload_sha256: 'a'.repeat(64)},
      signature: 'b'.repeat(64),
      conversation: {thread_id: 'TEST-ONLY', user_message: '确认来源', scope: 'policy', decision_sha256: 'c'.repeat(64)},
    },
  };
  assert.doesNotThrow(() => validate('human', human)); // Shape only, not approval verification.
  const missing = structuredClone(human);
  delete missing.confirmation.conversation;
  assert.throws(() => validate('human', missing));
  const blank = structuredClone(human);
  blank.confirmation.conversation.user_message = ' ';
  assert.throws(() => validate('human', blank));
  const terminal = structuredClone(human);
  terminal.confirmation.source = 'local_terminal';
  assert.throws(() => validate('human', terminal));
  delete terminal.confirmation.conversation;
  assert.doesNotThrow(() => validate('human', terminal));
});
test('technical props require explicit fixture admission', () => {
  assert.throws(() => validateProps(validate, props), /Technical fixture/);
  assert.equal(validateProps(validate, props, true).video.total_frames, 360);
});
test('edited execution budgets fail at the consumer boundary', () => {
  for (const field of ['physical_frames', 'sequence_start_frame', 'head_hold_frames', 'start_frame']) {
    const edited = structuredClone(props);
    edited.shots[1][field] += 1;
    assert.throws(() => validateProps(validate, edited, true), /budget/);
  }
  const edited = structuredClone(props);
  edited.shots[0].transition_out.transition_start_frame++;
  assert.throws(() => validateProps(validate, edited, true), /window/);
});
test('Unicode code points preserve BOM policy, CRLF, repeats and non-BMP', () => {
  const text = '\uFEFF重复句。\r\n重复句。𠮷🙂\r\n结尾。';
  assert.equal(sliceCodepoints(text, 6, 14), '重复句。𠮷🙂\r\n');
  assert.throws(() => sliceCodepoints(text, 0, 100), /range/);
});
