const {chromium}=require('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),{pathToFileURL}=require('url');
const content=require('./report_en_content.cjs');
(async()=>{
 const root=path.resolve(__dirname,'..');
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1920,height:1080}});
 await page.goto(pathToFileURL(path.join(root,'机器人推块比赛_阶段汇报.html')).href);
 await page.evaluate(({slides,notes})=>{
  document.documentElement.lang='en';document.title='Block-Pushing Robot Competition | Progress Report';
  document.querySelectorAll('.slide').forEach((s,i)=>{
   const walker=document.createTreeWalker(s,NodeFilter.SHOW_TEXT);let n, nodes=[];
   while(n=walker.nextNode())if(n.textContent.trim()&&!n.parentElement.closest('.speaker-notes'))nodes.push(n);
   if(nodes.length!==slides[i].length)throw Error(`Slide ${i+1}: ${nodes.length} vs ${slides[i].length}`);
   nodes.forEach((n,j)=>n.textContent=slides[i][j]);
   s.querySelector('.speaker-notes').textContent=notes[i];s.setAttribute('aria-label',`Slide ${i+1}: ${slides[i][0]}`);
   s.querySelectorAll('svg').forEach(svg=>svg.setAttribute('aria-label',slides[i][0]));
  });
  const style=document.createElement('style');style.textContent=`
body{font-family:Arial,"Microsoft YaHei",sans-serif}h2{font-size:58px;letter-spacing:-1px}.cover h2{font-size:78px;letter-spacing:-1.5px}.cover-meta{font-size:30px}.cover-position{font-size:35px;line-height:1.7}.cover-topics{font-size:27px;gap:29px}.lead{font-size:37px;line-height:1.45;margin-bottom:32px}.point{padding:21px 0}.point h3{font-size:31px}.point p{font-size:28px;line-height:1.55}.intro{font-size:32px}.framework-lead{font-size:35px;line-height:1.6}.comparison strong{font-size:38px}.comparison p{font-size:26px}.team-table thead th{font-size:29px}.team-table tbody td{font-size:28px}.shared-line{gap:45px}.shared-line p{font-size:28px}.delivery-lead{font-size:42px;line-height:1.6}.delivery-metrics{font-size:29px}.delivery-rows h3{font-size:38px}.delivery-rows p{font-size:30px;line-height:1.6}
`;document.head.appendChild(style);
  document.querySelector('#fullscreen').textContent='Fullscreen F';document.querySelector('#notesButton').textContent='Notes N';document.querySelector('#editButton').textContent='Edit text';document.querySelector('#saveButton').textContent='Save HTML';
  document.querySelector('#prev').title='Previous slide';document.querySelector('#next').title='Next slide';
  document.querySelector('.deck-controls').setAttribute('aria-label','Presentation controls');
  document.querySelector('#notes').setAttribute('aria-label','Speaker notes');document.querySelector('#closeNotes').setAttribute('aria-label','Close notes');
 },content);
 await page.evaluate(()=>{
  const texts=[...document.querySelectorAll('.slide:nth-child(3) svg text')];
  const command=texts.find(t=>t.textContent==='Wireless commands');
  command.setAttribute('x','100');command.innerHTML='<tspan x="100" y="375">Wireless speed</tspan><tspan x="100" y="412">commands</tspan>';
  const speed=texts.find(t=>t.textContent==='Wheel speed');
  speed.setAttribute('x','803');speed.setAttribute('font-size','24');speed.innerHTML='<tspan x="803" y="565">Wheel</tspan><tspan x="803" y="597">speed</tspan>';
 });
 // Fit English diagram labels within the existing technical drawing geometry.
 for(let i=0;i<11;i++){
  await page.evaluate(i=>deck.show(i),i);
  await page.evaluate(()=>{
   document.querySelectorAll('.slide.active svg text').forEach(t=>{
    if(t.children.length)return; const svg=t.ownerSVGElement, vb=svg.viewBox.baseVal, x=Number(t.getAttribute('x'));
    const anchor=t.getAttribute('text-anchor')||t.parentElement.getAttribute('text-anchor')||'start';
    let available=vb.width-x-20;
    if(anchor==='middle')available=Math.min(x,vb.width-x)*2-40;
    if(vb.width===1740){const widths={126:216,578:326,1087:307,1540:356};available=widths[x]||available;}
    if(vb.width===1000&&x===450)available=620;
    if(vb.width===1000&&x===143)available=295;
    if(vb.width===1000&&x===685)available=150;
    const width=t.getComputedTextLength();
    if(width>available){const size=parseFloat(getComputedStyle(t).fontSize);t.style.fontSize=`${Math.max(21,size*available/width)}px`;}
   });
  });
 }
 await page.evaluate(()=>{deck.show(0);document.body.classList.remove('controls-show');document.querySelector('#hint').classList.remove('show');});
 let html=await page.content();html=html.replaceAll('robot-report-20260928-engineering-a','robot-report-20260929-english');
 fs.writeFileSync(path.join(root,'机器人推块比赛_阶段汇报_英文版.html'),html);
 await browser.close();console.log('English HTML: 11 slides and English speaker notes.');
})();

