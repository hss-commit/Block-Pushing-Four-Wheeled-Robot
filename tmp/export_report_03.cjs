const fs=require('fs');
const path=require('path');
const {pathToFileURL}=require('url');
const {chromium}=require('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const root=path.resolve(__dirname,'..'),out=path.join(root,'tmp','report-03');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1600,height:900}});
 await page.goto(pathToFileURL(path.join(root,'机器人推块比赛_第三次汇报_成果与计划版.html')).href);
 const data=[];
 for(let i=0;i<11;i++){
  await page.evaluate(i=>show(i),i);
  const d=await page.evaluate(i=>{
   const s=document.querySelectorAll('.slide')[i];
   const items=[...s.querySelectorAll('h1,h2,p')].map(el=>{
    const st=getComputedStyle(el),box=el.getBoundingClientRect(),range=document.createRange();range.selectNodeContents(el);
    const r=range.getBoundingClientRect();
    return {text:el.innerText,x:box.x,y:r.y,w:box.width,h:r.height,size:parseFloat(st.fontSize),line:parseFloat(st.lineHeight)||parseFloat(st.fontSize)*1.2,bold:parseInt(st.fontWeight)>=600,color:st.color,kicker:el.classList.contains('kicker')};
   });
   const rules=[...s.querySelectorAll('.report-copy p,.cover-rule')].map(el=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:el.classList.contains('cover-rule')?4:1,cover:el.classList.contains('cover-rule')};});
   return {items,rules,notes:notes[i]};
  },i);data.push(d);
  await page.locator('nav').evaluate(el=>el.style.visibility='hidden');
  await page.screenshot({path:path.join(out,`source-${i+1}.png`)});
 }
 fs.writeFileSync(path.join(out,'geometry.json'),JSON.stringify(data,null,2));
 await browser.close();console.log('Extracted 11 pages and source previews.');
})().catch(e=>{console.error(e);process.exit(1)});
