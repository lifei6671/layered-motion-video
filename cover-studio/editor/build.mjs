import {build} from 'esbuild';
import {bundle} from '@remotion/bundler';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root = path.dirname(fileURLToPath(import.meta.url));
await build({entryPoints:[path.join(root,'src/main.tsx')], bundle:true, minify:true,
  format:'iife', target:'es2022', outfile:path.join(root,'../static/editor.bundle.js'),
  define:{'process.env.NODE_ENV':'"production"'}});
await bundle({entryPoint:path.join(root,'src/remotion.tsx'),
  outDir:path.join(root,'../static/remotion-cover'), publicDir:null});
console.log('React editor and shared Remotion still composition built.');
