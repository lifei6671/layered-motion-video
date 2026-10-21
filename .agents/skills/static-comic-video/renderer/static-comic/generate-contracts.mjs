import {readFileSync, writeFileSync} from 'node:fs';
import {compile} from 'json-schema-to-typescript';
const schema = JSON.parse(readFileSync(new URL('../../schemas/contracts.json', import.meta.url), 'utf8'));
const output = await compile(schema, 'StaticComicContracts', {
  bannerComment: '/* Generated from ../../schemas/contracts.json. Do not edit. */',
  style: {singleQuote: true},
});
const target = new URL('./src/contracts.generated.ts', import.meta.url);
if (process.argv.includes('--check')) {
  if (readFileSync(target, 'utf8') !== output) throw new Error('Generated TypeScript contracts are stale');
} else writeFileSync(target, output);
