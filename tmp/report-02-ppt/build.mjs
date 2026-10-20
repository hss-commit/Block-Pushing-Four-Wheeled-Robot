import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {Presentation,PresentationFile} from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const require=createRequire(import.meta.url),{chromium}=require('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=process.cwd(),dir=path.join(root,'tmp/report-02-ppt'),skill='C:/Users/Admin/.codex/plugins/cache/openai-primary-runtime/presentations/26.1015.12040/skills/presentations';
const b=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
const page=await b.newPage({viewport:{width:1600,height:900}});await page.goto(pathToFileURL(path.join(root,'机器人推块比赛_第二次汇报.html')).href);
const data=[];
for(let i=0;i<8;i++){
 await page.evaluate(i=>show(i),i);
 data.push(await page.evaluate(()=>{
 const s=document.querySelector('.slide.active'),base=s.getBoundingClientRect();
 const rect=e=>{const r=e.getBoundingClientRect();return{left:r.left-base.left,top:r.top-base.top,width:r.width,height:r.height}};
 const hex=c=>'#'+c.match(/[\d.]+/g).slice(0,3).map(v=>(+v).toString(16).padStart(2,'0')).join('');
 const style=e=>{const c=getComputedStyle(e);return{size:parseFloat(c.fontSize),bold:+c.fontWeight>=600,color:hex(c.color),lineHeight:parseFloat(c.lineHeight)||parseFloat(c.fontSize)*1.2}};
 const lines=e=>{const w=document.createTreeWalker(e,NodeFilter.SHOW_TEXT),ls=[];let n;while(n=w.nextNode()){const st=style(n.parentElement);for(let j=0;j<n.length;j++){const r=document.createRange();r.setStart(n,j);r.setEnd(n,j+1);const q=r.getBoundingClientRect();if(!q.width||!q.height)continue;let l=ls.find(l=>Math.abs(l.y-(q.y-base.y))<2&&l.st.size===st.size);if(!l){l={x:q.x-base.x,y:q.y-base.y,width:0,text:'',st};ls.push(l);}l.text+=n.textContent[j];l.width=q.right-base.x-l.x;}}return ls;};
 const text=[];for(const e of s.querySelectorAll('h1,h2,h3,p,.number,.arrow,.checks>div,.outcome'))if(!e.closest('table'))text.push(...lines(e));
 const rules=[];for(const e of s.querySelectorAll('*')){const c=getComputedStyle(e),r=rect(e);if(+parseFloat(c.borderTopWidth)>0)rules.push({...r,height:parseFloat(c.borderTopWidth),color:hex(c.borderTopColor)});}
 const tables=[...s.querySelectorAll('table')].map(t=>({box:rect(t),rows:[...t.rows].map(r=>({height:rect(r).height,cells:[...r.cells].map(c=>({box:rect(c),text:c.innerText,st:style(c.querySelector('.status')||c),padding:parseFloat(getComputedStyle(c).paddingRight)}))}))}));
 return{text,rules,tables,notes:notes[current]};
 }));
}
await b.close();await fs.writeFile(path.join(dir,'source.json'),JSON.stringify(data,null,2));
const p=Presentation.create({slideSize:{width:1600,height:900}});
for(const [i,d] of data.entries()){
 const s=p.slides.add();s.background.fill='#f5f4ee';
 if(i>=5)s.shapes.add({geometry:'rect',name:'Blank template background',position:{left:0,top:0,width:1600,height:900},fill:'#f5f4ee',line:{fill:'none',width:0}});
 for(const r of d.rules)s.shapes.add({geometry:'rect',name:'Template divider',position:{left:r.left,top:r.top,width:r.width,height:r.height},fill:r.color,line:{fill:'none',width:0}});
 for(const l of d.text){const t=s.shapes.add({geometry:'textbox',name:l.text.slice(0,55),position:{left:l.x,top:l.y,width:Math.min(1535-l.x,l.width+18),height:l.st.size*1.34},fill:'none',line:{fill:'none',width:0}});t.text=l.text;t.text.style={fontSize:l.st.size,typeface:'Segoe UI',bold:l.st.bold,color:l.st.color,alignment:'left',verticalAlignment:'top',autoFit:'none',wrap:'none',insets:{left:0,right:0,top:0,bottom:0}};}
 for(const tb of d.tables){const t=s.tables.add({rows:tb.rows.length,columns:3,left:tb.box.left,top:tb.box.top,width:tb.box.width,height:tb.box.height,columnWidths:tb.rows[0].cells.map(c=>c.box.width),values:tb.rows.map(r=>r.cells.map(c=>c.text))});t.styleOptions={headerRow:false,firstColumn:false,bandedRows:false,bandedColumns:false};t.borders.assign({fill:'none',width:0});tb.rows.forEach((r,ri)=>{t.rows[ri].height=r.height;r.cells.forEach((c,ci)=>{const cell=t.getCell(ri,ci);cell.fill='#f5f4ee';cell.text.style={typeface:'Segoe UI',fontSize:c.st.size,bold:c.st.bold,color:c.st.color,alignment:'left',verticalAlignment:'middle',autoFit:'none',wrap:'square',lineSpacing:1.35,insets:{left:0,right:c.padding,top:0,bottom:0}};t.cells.block({row:ri,column:ci,rowCount:1,columnCount:1}).assign({margins:{left:0,right:c.padding,top:0,bottom:0},anchor:'center'});});});}
 s.speakerNotes.textFrame.setText(d.notes||'');
 console.log('Built slide '+(i+1));
}
const candidatePath=path.join(dir,'candidate.pptx');await(await PresentationFile.exportPptx(p)).save(candidatePath);
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const result=await finalizePresentation({workspaceDir:root,candidatePath,finalPath:path.join(root,'输出/机器人推块比赛_第二次汇报_可编辑版.pptx'),explicitTotalSlideCount:8,requiredNativeTableOwnerSlides:[2],requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'design',families:['Segoe UI']},pythonExecutable:'C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','15240000,8572500','--validate-heading-fit','--require-native-table-slide','2'],verifyArtifactToolImport:true,receiptPath:path.join(dir,'validation.json')});
console.log(JSON.stringify({finalPath:result.finalPath,slides:result.packageIntegrity.slide_count}));
