const {chromium}=require('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),{pathToFileURL}=require('url');
(async()=>{
 const root=path.resolve(__dirname,'..'),dir=path.join(__dirname,'editable-en');fs.mkdirSync(dir,{recursive:true});
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1920,height:1080}});
 await page.goto(pathToFileURL(path.join(root,'机器人推块比赛_阶段汇报_英文版.html')).href);
 await page.addStyleTag({content:'*{transition:none!important;animation:none!important}.deck-controls,.hint,.notes-panel{display:none!important}'});
 const data=[];
 for(let index=0;index<11;index++){
  await page.evaluate(i=>deck.show(i),index);
  data.push(await page.evaluate(()=>{
   const slide=document.querySelector('.slide.active'),base=slide.getBoundingClientRect(),items=[];
   const rect=e=>{const b=e.getBoundingClientRect();return {left:b.left-base.left,top:b.top-base.top,width:b.width,height:b.height}};
   const color=(c,opacity=1)=>{if(c==='none'||c==='transparent'||c.startsWith('url('))return 'none';const m=c.match(/[\d.]+/g);if(!m)return c;return '#'+m.slice(0,3).map(n=>Math.round(+n).toString(16).padStart(2,'0')).join('')+(opacity*(m[3]??1)<1?'/'+(opacity*(m[3]??1)*100):'')};
   const textStyle=e=>{const c=getComputedStyle(e);return {fontSize:parseFloat(c.fontSize),bold:parseFloat(c.fontWeight)>=600,color:color(c.color),fontFamily:'Arial',lineHeight:parseFloat(c.lineHeight)||parseFloat(c.fontSize)*1.2,align:c.textAlign}};
   // HTML rules/backgrounds, excluding native tables and diagrams.
   for(const e of slide.querySelectorAll('h2,.point,.cover-topics,.comparison strong,.plan-checks,.delivery-rows>div')){
    const c=getComputedStyle(e),b=rect(e);
    for(const side of ['Top','Bottom'])if(parseFloat(c['border'+side+'Width'])>0){const y=side==='Top'?b.top:b.top+b.height;items.push({type:'path',name:'Section rule',points:[{x:b.left,y},{x:b.left+b.width,y}],stroke:color(c['border'+side+'Color']),lineWidth:parseFloat(c['border'+side+'Width']),fill:'none'});}
   }
   // Text remains editable as logical text blocks, retaining line breaks.
   for(const e of slide.querySelectorAll('h2,h3,p,.cover-topics>span,.comparison>span,.comparison>strong')){
    if(e.closest('svg,table,.speaker-notes'))continue;
    const b=rect(e);if(!b.width||!b.height)continue;
    const walker=document.createTreeWalker(e,NodeFilter.SHOW_TEXT);let node,chars=[];
    while(node=walker.nextNode()){
     const st=textStyle(node.parentElement);
     for(let i=0;i<node.textContent.length;i++){
      const r=document.createRange();r.setStart(node,i);r.setEnd(node,i+1);const q=r.getBoundingClientRect();
      if(q.width&&q.height)chars.push({char:node.textContent[i],x:q.x-base.x,y:q.y-base.y,width:q.width,height:q.height,style:st});
     }
    }
    const lines=[];
    for(const ch of chars){let line=lines.find(l=>Math.abs(l.y-ch.y)<3);if(!line){line={y:ch.y,x:ch.x,height:ch.height,runs:[]};lines.push(line)}let run=line.runs.at(-1);if(!run||JSON.stringify(run.style)!==JSON.stringify(ch.style)){run={text:'',style:ch.style};line.runs.push(run)}run.text+=ch.char;}
    if(lines.length)items.push({type:'text',name:e.tagName==='H2'?'Slide title':e.textContent.slice(0,65),box:b,style:textStyle(e),lines});
   }
   // Tables stay real PowerPoint tables.
   const tables=[...slide.querySelectorAll('table')].map(t=>({box:rect(t),rows:[...t.rows].map(row=>({height:rect(row).height,cells:[...row.cells].map(cell=>{const c=getComputedStyle(cell);return {value:cell.innerText,box:rect(cell),style:textStyle(cell),fill:color(c.backgroundColor),margins:{top:parseFloat(c.paddingTop),bottom:parseFloat(c.paddingBottom),left:parseFloat(c.paddingLeft),right:parseFloat(c.paddingRight)}}})}))}));
   // Convert each SVG primitive to an editable native shape or freeform.
   for(const svg of slide.querySelectorAll('svg'))for(const e of svg.querySelectorAll('rect,circle,ellipse,line,path,polyline,polygon,text')){
    if(e.closest('defs'))continue;
    const tag=e.tagName.toLowerCase(),c=getComputedStyle(e),m=e.getScreenCTM();if(!m)continue;
    const point=(x,y)=>({x:m.a*x+m.c*y+m.e-base.x,y:m.b*x+m.d*y+m.f-base.y});
    let opacity=1;for(let p=e;p&&p!==slide;p=p.parentElement)opacity*=parseFloat(getComputedStyle(p).opacity)||0;
    const scale=Math.hypot(m.a,m.b),stroke=color(c.stroke,opacity),fill=color(c.fill,opacity),lineWidth=parseFloat(c.strokeWidth)*scale;
    const basic={name:'Diagram '+tag,stroke,fill,lineWidth,dashed:c.strokeDasharray!=='none'};
    if(tag==='text'){
     const tspans=[...e.querySelectorAll('tspan')];
     for(const t of tspans.length?tspans:[e]){
      const b=rect(t),st=textStyle(t);st.color=fill;st.fontSize*=scale;
      items.push({type:'svgtext',name:t.textContent,box:b,text:t.textContent,style:st});
     }continue;
    }
    if(['rect','circle','ellipse'].includes(tag)){
     const b=rect(e);items.push({type:'shape',geometry:tag==='rect'?'rect':'ellipse',box:b,...basic});
     if(c.fill.startsWith('url(')){
      // Preserve the light field grid using native lines.
      const bb=e.getBBox(),spacing=52;
      for(let x=Math.ceil(bb.x/spacing)*spacing;x<bb.x+bb.width;x+=spacing)items.push({type:'path',name:'Field grid',points:[point(x,bb.y),point(x,bb.y+bb.height)],stroke:'#c6ccc6/45',fill:'none',lineWidth:.6*scale});
      for(let y=Math.ceil(bb.y/spacing)*spacing;y<bb.y+bb.height;y+=spacing)items.push({type:'path',name:'Field grid',points:[point(bb.x,y),point(bb.x+bb.width,y)],stroke:'#c6ccc6/45',fill:'none',lineWidth:.6*scale});
     }continue;
    }
    if(tag==='line'){items.push({type:'path',points:[point(e.x1.baseVal.value,e.y1.baseVal.value),point(e.x2.baseVal.value,e.y2.baseVal.value)],...basic});continue;}
    if(tag==='polygon'||tag==='polyline'){items.push({type:'path',points:[...Array(e.points.numberOfItems)].map((_,i)=>{const p=e.points.getItem(i);return point(p.x,p.y)}),closed:tag==='polygon',...basic});continue;}
    const paths=(e.getAttribute('d')||'').match(/[Mm][^Mm]*/g)||[];
    for(const d of paths){const p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('d',d);const length=p.getTotalLength(),count=Math.max(1,Math.ceil(length/3)),points=[];for(let j=0;j<=count;j++){const q=p.getPointAtLength(length*j/count);points.push(point(q.x,q.y));}items.push({type:'path',points,closed:/[Zz]/.test(d),...basic});}
    if(c.markerEnd!=='none'){
     const length=e.getTotalLength(),a=e.getPointAtLength(Math.max(0,length-1)),b=e.getPointAtLength(length),p=point(b.x,b.y),pa=point(a.x,a.y),angle=Math.atan2(p.y-pa.y,p.x-pa.x),len=6*lineWidth,w=3*lineWidth;
     items.push({type:'path',name:'Route arrowhead',points:[{x:p.x-len*Math.cos(angle)+w*Math.sin(angle),y:p.y-len*Math.sin(angle)-w*Math.cos(angle)},p,{x:p.x-len*Math.cos(angle)-w*Math.sin(angle),y:p.y-len*Math.sin(angle)+w*Math.cos(angle)}],stroke,fill:'none',lineWidth:1.5*lineWidth});
    }
   }
   return {title:slide.querySelector('h2').innerText,notes:slide.querySelector('.speaker-notes').textContent,items,tables};
  }));
 }
 fs.writeFileSync(path.join(dir,'geometry.json'),JSON.stringify(data,null,2));
 console.log(data.map((s,i)=>({slide:i+1,text:s.items.filter(x=>['text','svgtext'].includes(x.type)).length,shapes:s.items.filter(x=>!['text','svgtext'].includes(x.type)).length,tables:s.tables.length})));
 await browser.close();
})();
