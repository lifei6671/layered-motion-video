import {build} from 'esbuild';
import {execFileSync} from 'node:child_process';
for(const name of ['model','migration','controller'])await build({entryPoints:[`src/${name}.ts`],bundle:true,platform:'node',format:'esm',outfile:`.test-build/${name}.mjs`});
execFileSync(process.execPath,['--test','tests/model.test.mjs'],{stdio:'inherit'});
