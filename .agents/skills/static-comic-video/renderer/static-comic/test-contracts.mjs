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
