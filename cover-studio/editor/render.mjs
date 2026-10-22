/** CLI: npm run render -- input.json output.png http://127.0.0.1:8765 [png|jpeg] */
import {selectComposition,renderStill} from '@remotion/renderer';
import {readFile,access} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const [input,output,assetBase,format='png']=process.argv.slice(2);
if(!input||!output||!assetBase||!['png','jpeg'].includes(format))throw Error('需要 input.json output.png assetBase [png|jpeg]');
const document=JSON.parse(await readFile(input,'utf8'));
const serveUrl=path.join(root,'../static/remotion-cover');
await access(path.join(serveUrl,'index.html'));
const inputProps={document,assetBase};
const edge=path.join(process.env['PROGRAMFILES(X86)']||'C:/Program Files (x86)','Microsoft/Edge/Application/msedge.exe');
const browserExecutable=process.env.COVER_STUDIO_BROWSER||(existsSync(edge)?edge:undefined);
const composition=await selectComposition({serveUrl,id:'CoverArtwork',inputProps,browserExecutable,timeoutInMilliseconds:60000});
await renderStill({serveUrl,composition,inputProps,output:path.resolve(output),imageFormat:format,
  browserExecutable,timeoutInMilliseconds:60000,logLevel:'error',
  ...(format==='jpeg'?{jpegQuality:95}:{})});
console.log(JSON.stringify({output:path.resolve(output),width:document.width,height:document.height,format}));
