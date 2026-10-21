// SC-P0 runtime probe only: no production composition or image acquisition.
import {createRequire} from 'node:module';
import {readFileSync, existsSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {openBrowser} from '@remotion/renderer';
import {TransitionSeries} from '@remotion/transitions';

const require = createRequire(import.meta.url);
const manifest = JSON.parse(readFileSync(new URL('./package.json', import.meta.url)));
const lock = JSON.parse(readFileSync(new URL('./package-lock.json', import.meta.url)));
const versions = {};
for (const [name, expected] of Object.entries(manifest.dependencies)) {
  const actual = require(`${name}/package.json`).version;
  if (actual !== expected || lock.packages[`node_modules/${name}`]?.version !== expected) {
    throw new Error(`Dependency mismatch: ${name}: ${actual} != ${expected}`);
  }
  versions[name] = actual;
}
for (const [path, pkg] of Object.entries(lock.packages)) {
  if (/node_modules\/@remotion\/[^/]+$/.test(path) && pkg.version !== manifest.dependencies.remotion) {
    throw new Error(`Remotion lock mismatch: ${path}: ${pkg.version}`);
  }
}
if (!TransitionSeries) throw new Error('TransitionSeries export unavailable');
const browserExecutable = process.argv[2];
if (!browserExecutable || !existsSync(browserExecutable)) throw new Error('Existing browser executable required');
const browser = await openBrowser('chrome', {browserExecutable});
try {
  const markup = renderToStaticMarkup(React.createElement('main', null, '静态漫画 runtime'));
  if (markup !== '<main>静态漫画 runtime</main>') throw new Error(`React content mismatch: ${markup}`);
  const browserVersion = execFileSync(browserExecutable, ['--version'], {encoding: 'utf8', windowsHide: true, timeout: 10000}).trim();
  console.log(JSON.stringify({status: 'PASS', versions, browserVersion, browserExecutable, markup, scope: 'Browser launch + React SSR; no video render'}));
} finally {
  await browser.close({silent: true});
}
