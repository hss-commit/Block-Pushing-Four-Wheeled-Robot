import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {Presentation,PresentationFile} from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const require=createRequire(import.meta.url);
const {chromium}=require('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
process.env.RUNTIME_NODE_MODULES='C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const build=path.join(root,'tmp','ppt-build-en'),output=path.join(root,'输出');
const skill='C:/Users/Admin/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations';
await fs.mkdir(build,{recursive:true});await fs.mkdir(output,{recursive:true});
const finalPath=path.join(output,'机器人推块比赛_阶段汇报_英文版.pptx');
const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:2});
await page.goto(pathToFileURL(path.join(root,'机器人推块比赛_阶段汇报_英文版.html')).href);
await page.addStyleTag({content:'.deck-controls,.notes-panel,.hint,.progress{display:none!important}*{animation:none!important;transition:none!important}'});
await page.evaluate(()=>document.fonts.ready);
const count=await page.locator('.slide').count();if(count!==11)throw Error(`Unexpected page count ${count}`);
const manifest=[];
for(let i=0;i<count;i++){
 await page.evaluate(i=>deck.show(i),i);
 const data=await page.locator('.slide.active').evaluate(e=>({title:e.querySelector('h2').textContent,notes:e.querySelector('.speaker-notes').textContent,visibleText:[...e.querySelectorAll('h2,h3,p,td,th,svg text')].map(x=>x.textContent).join('\n')}));
 const png=path.join(build,`page-${String(i+1).padStart(2,'0')}.png`);
 await page.screenshot({path:png});manifest.push({...data,png});
}
await browser.close();await fs.writeFile(path.join(build,'manifest.json'),JSON.stringify(manifest,null,2));
console.log(`Captured ${count} pages at 3840 × 2160, with speaker notes.`);
const presentation=Presentation.create({slideSize:{width:1920,height:1080}});
for(const item of manifest){
 const s=presentation.slides.add();s.background.fill='#f7f8f3';
 s.images.add({blob:new Uint8Array(await fs.readFile(item.png)),contentType:'image/png',alt:item.visibleText,fit:'contain',position:{left:0,top:0,width:1920,height:1080}});
 s.speakerNotes.textFrame.setText(item.notes);
}
const candidatePath=path.join(build,'candidate.pptx');
await(await PresentationFile.exportPptx(presentation)).save(candidatePath);
console.log('PPTX exported. Validating package and slide dimensions.');
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const result=await finalizePresentation({
 workspaceDir:root,candidatePath,finalPath,
 explicitTotalSlideCount:11,
 requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
 pythonExecutable:'C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','18288000,10287000'],
 verifyArtifactToolImport:true,
 receiptPath:path.join(build,'validation.json')
});
console.log(JSON.stringify({finalPath,result},null,2));

