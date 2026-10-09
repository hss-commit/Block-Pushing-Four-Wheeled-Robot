const {chromium}=require('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),{pathToFileURL}=require('url');
(async()=>{
 const root=path.resolve(__dirname,'..'),dir=path.join(__dirname,'report-qa');fs.mkdirSync(dir,{recursive:true});
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1280,height:720},deviceScaleFactor:1});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(pathToFileURL(path.join(root,'机器人推块比赛_阶段汇报.html')).href);await page.waitForTimeout(400);
 const bounds=[];
 for(let i=0;i<12;i++){
  await page.evaluate(i=>{deck.show(i);document.body.classList.remove('controls-show');document.querySelector('#hint').classList.remove('show');},i);await page.waitForTimeout(300);
  bounds.push(await page.evaluate(()=>{const s=document.querySelector('.slide.active'),r=s.getBoundingClientRect(),f=s.querySelector('footer').getBoundingClientRect();return{slide:deck.current+1,overflow:[...s.querySelectorAll('h2,h3,p,li,td,.bottom-line,.shared,.budget,.action-loop,.roadmap b')].filter(e=>{const b=e.getBoundingClientRect();return b.width&&b.height&&(b.bottom>f.top-7||b.right>r.right-30||b.left<r.left);}).map(e=>({text:e.textContent.slice(0,60),bottom:Math.round(e.getBoundingClientRect().bottom),footer:Math.round(f.top)}))};}));
  await page.screenshot({path:path.join(dir,`slide-${String(i+1).padStart(2,'0')}.png`)});
 }
 await page.keyboard.press('Home');if(await page.evaluate(()=>deck.current)!==0)throw Error('Home failed');
 await page.keyboard.press('ArrowRight');if(await page.evaluate(()=>deck.current)!==1)throw Error('Navigation failed');
 await page.keyboard.press('n');if(await page.locator('#notes').isHidden())throw Error('Notes failed');await page.keyboard.press('n');
 await page.keyboard.press('e');if(!await page.evaluate(()=>deck.editing))throw Error('Edit failed');
 await page.keyboard.press('Escape');if(await page.evaluate(()=>deck.editing))throw Error('Exit edit failed');
 await page.setViewportSize({width:390,height:844});await page.keyboard.press('Home');
 await page.evaluate(()=>{document.querySelector('#hint').classList.remove('show');document.body.classList.remove('controls-show');});
 await page.waitForTimeout(300);await page.screenshot({path:path.join(dir,'phone.png')});
 const ratio=await page.locator('.deck-stage').evaluate(e=>{const r=e.getBoundingClientRect();return r.width/r.height;});
 if(Math.abs(ratio-16/9)>.001)throw Error('Stage ratio failed');
 fs.writeFileSync(path.join(dir,'verification.json'),JSON.stringify({errors,bounds,phoneRatio:ratio,checks:['keyboard navigation','notes toggle','editing toggle','phone 16:9 stage']},null,2));
 console.log(JSON.stringify({errors,bounds,phoneRatio:ratio},null,2));await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
