const {chromium}=require('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const path=require('path'),fs=require('fs'),{pathToFileURL}=require('url');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1280,height:720}});const errs=[];page.on('pageerror',e=>errs.push(e.message));
 const p=path.join(__dirname,'style-review'),result=[];
 for(const name of ['a','b','c']){await page.goto(pathToFileURL(path.join(p,name+'.html')).href);await page.screenshot({path:path.join(p,name+'.png')});result.push(await page.evaluate(()=>({title:document.title,overflow:[...document.querySelectorAll('h1,h2,h3,p')].filter(e=>{let r=e.getBoundingClientRect();return r.right>innerWidth||r.bottom>innerHeight||r.left<0||r.top<0;}).map(e=>e.textContent)})));}
 await page.goto(pathToFileURL(path.resolve(__dirname,'..','汇报风格对比.html')).href);
 for(let i=0;i<3;i++){await page.locator('button').nth(i).click();if(await page.locator('iframe.active').getAttribute('title')!=='视觉方向 '+String.fromCharCode(65+i))throw Error('Picker failed');}
 console.log(JSON.stringify({result,errors:errs,picker:'passed'},null,2));await browser.close();
 if(errs.length||result.some(r=>r.overflow.length))process.exit(1);
})().catch(e=>{console.error(e);process.exit(1);});
