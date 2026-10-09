import fs from 'node:fs';
process.on('exit',code=>fs.appendFileSync('tmp/render-debug.log',`EXIT ${code}\n`));
process.on('uncaughtException',error=>fs.appendFileSync('tmp/render-debug.log',`UNCAUGHT ${error.stack}\n`));
process.on('unhandledRejection',error=>fs.appendFileSync('tmp/render-debug.log',`REJECT ${error?.stack||error}\n`));
const oldExit=process.exit;process.exit=(code)=>{fs.appendFileSync('tmp/render-debug.log',`EXIT CALL ${code} ${new Error().stack}\n`);return oldExit(code);};
fs.writeFileSync('tmp/render-debug.log','START\n');
const {Presentation,PresentationFile,FileBlob}=await import('file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs');
fs.appendFileSync('tmp/render-debug.log','IMPORTED\n');
const p=await PresentationFile.importPptx(await FileBlob.load('tmp/ppt-build/probe.pptx'));
fs.appendFileSync('tmp/render-debug.log','LOADED\n');
try {const image=await p.export({slide:p.slides.items[0],format:'png',scale:0.5});fs.writeFileSync('tmp/editable-probe.png',new Uint8Array(await image.arrayBuffer()));}catch(e){fs.appendFileSync('tmp/render-debug.log',`CAUGHT ${e.stack}\n`)}
