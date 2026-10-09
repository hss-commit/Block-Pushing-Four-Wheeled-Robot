const {chromium}=require('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),{pathToFileURL}=require('url');
(async()=>{
 const root=path.resolve(__dirname,'..'),dir=path.join(__dirname,'report-qa-en');fs.mkdirSync(dir,{recursive:true});
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1280,height:720},deviceScaleFactor:1});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(pathToFileURL(path.join(root,'机器人推块比赛_阶段汇报_英文版.html')).href);
 const duplicateIds=await page.evaluate(()=>{const a=[...document.querySelectorAll('[id]')].map(e=>e.id);return a.filter((id,i)=>a.indexOf(id)!==i);});if(duplicateIds.length)throw Error('Duplicate IDs: '+duplicateIds);const count=await page.locator('.slide').count();if(count!==11)throw Error('Expected 11 slides');
 const bounds=[];
 for(let i=0;i<count;i++){
  await page.evaluate(i=>{deck.show(i);document.body.classList.remove('controls-show');document.querySelector('#hint').classList.remove('show');},i);await page.waitForTimeout(750);
  bounds.push(await page.evaluate(()=>{const s=document.querySelector('.slide.active'),r=s.getBoundingClientRect();return{slide:deck.current+1,title:s.querySelector('h2').textContent,overflow:[...s.querySelectorAll('h2,h3,p,li,.stage-state,.deliverables span')].filter(e=>{const b=e.getBoundingClientRect();return b.width&&b.height&&(b.bottom>r.bottom-25||b.right>r.right-25||b.left<r.left+25);}).map(e=>e.textContent.slice(0,60))};}));
  await page.screenshot({path:path.join(dir,`slide-${String(i+1).padStart(2,'0')}.png`)});
 }
 await page.keyboard.press('Home');if(await page.evaluate(()=>deck.current)!==0)throw Error('Home failed');
 await page.keyboard.press('ArrowRight');if(await page.evaluate(()=>deck.current)!==1)throw Error('Navigation failed');
 await page.keyboard.press('n');if(await page.locator('#notes').isHidden())throw Error('Notes failed');await page.keyboard.press('n');
 await page.keyboard.press('e');if(!await page.evaluate(()=>deck.editing))throw Error('Edit failed');
 const title=page.locator('.slide.active h2');const original=await title.innerHTML();await title.fill('测试编辑');await page.keyboard.press('Escape');
 if(await page.evaluate(()=>deck.editing))throw Error('Exit edit failed');
 await page.reload();if(await page.locator('.slide.active h2').textContent()!=='测试编辑')throw Error('Persistence failed');
 await page.evaluate(original=>{document.querySelector('.slide.active h2').innerHTML=original;persist();},original);
 await page.evaluate(()=>download());
 await page.setViewportSize({width:390,height:844});await page.keyboard.press('Home');
 await page.evaluate(()=>{document.querySelector('#hint').classList.remove('show');document.body.classList.remove('controls-show');});
 await page.waitForTimeout(750);await page.screenshot({path:path.join(dir,'phone.png')});
 const ratio=await page.locator('.deck-stage').evaluate(e=>{const r=e.getBoundingClientRect();return r.width/r.height;});
 if(Math.abs(ratio-16/9)>.001)throw Error('Stage ratio failed');
 const result={count,errors,bounds,phoneRatio:ratio,checks:['keyboard navigation','notes toggle','editing and persistence','export invoked','phone 16:9 stage']};
 fs.writeFileSync(path.join(dir,'verification.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));await browser.close();
 if(errors.length||bounds.some(b=>b.overflow.length))process.exit(1);
})().catch(e=>{console.error(e);process.exit(1);});

