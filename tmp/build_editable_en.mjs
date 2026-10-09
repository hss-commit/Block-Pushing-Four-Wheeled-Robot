import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Presentation,PresentationFile} from 'file:///C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dir=path.join(root,'tmp','editable-en');
const data=JSON.parse(await fs.readFile(path.join(dir,'geometry.json'),'utf8'));
const p=Presentation.create({slideSize:{width:1920,height:1080}});
const noLine={fill:'none',width:0};
function text(s,item){
 const st=item.style,svg=item.type==='svgtext';
 const lines=svg?[{y:item.box.top,x:item.box.left,runs:[{text:item.text,style:st}]}]:item.lines;
 const x=svg?item.box.left:Math.min(...lines.map(l=>l.x)),y=lines[0].y;
 let width=svg?item.box.width+12:item.box.width+8;
 width=Math.min(width,1888-x);
 const lh=svg?st.fontSize*1.2:st.lineHeight;
 const h=svg?st.fontSize*1.4:(lines.length-1)*lh+st.fontSize*1.4;
 const t=s.shapes.add({name:item.name,geometry:'textbox',position:{left:x,top:y,width,height:h},fill:'none',line:noLine});
 t.text=lines.map(l=>({runs:l.runs.map(r=>({run:r.text,textStyle:{fontSize:r.style.fontSize+'px',typeface:'Arial',bold:r.style.bold,color:r.style.color}})),spaceBefore:0,spaceAfter:0}));
 t.text.style={fontSize:st.fontSize,typeface:'Arial',bold:st.bold,color:st.color,alignment:'left',verticalAlignment:'top',autoFit:'none',wrap:'square',lineSpacing:lh/st.fontSize,insets:{left:0,right:0,top:0,bottom:0}};
 for(const l of lines)for(const r of l.runs){const range=t.text.get(r.text);range.fill=r.style.color;range.bold=r.style.bold;}
}
function shape(s,it){
 const line={fill:it.stroke||'none',width:it.lineWidth||0,style:it.dashed?'dashed':'solid'};
 if(it.type==='shape'){s.shapes.add({name:it.name,geometry:it.geometry,position:it.box,fill:it.fill,line});return;}
 const pts=it.points;if(!pts?.length)return;
 const xs=pts.map(p=>p.x),ys=pts.map(p=>p.y),x=Math.min(...xs),y=Math.min(...ys),w=Math.max(1,Math.max(...xs)-x),h=Math.max(1,Math.max(...ys)-y);
 const commands=pts.map((q,i)=>({[i?'lineTo':'moveTo']:{x:q.x-x,y:q.y-y}}));if(it.closed)commands.push({close:{}});
 s.shapes.add({name:it.name,geometry:'custom',position:{left:x,top:y,width:w,height:h},fill:it.fill||'none',line,customPaths:[{width:w,height:h,commands}]});
}
for(const [i,page]of data.entries()){
 const s=p.slides.add();s.background.fill='#f7f8f3';
 for(const it of page.items){if(['text','svgtext'].includes(it.type))text(s,it);else shape(s,it);}
 for(const table of page.tables){
  const b=table.box,rows=table.rows,cols=rows[0].cells.length;
  const t=s.tables.add({rows:rows.length,columns:cols,left:b.left,top:b.top,width:b.width,height:b.height,columnWidths:rows[0].cells.map(c=>c.box.width),values:rows.map(r=>r.cells.map(c=>c.value))});
  t.styleOptions={headerRow:false,firstColumn:false,bandedRows:false,bandedColumns:false};
  t.borders.assign({fill:'none',width:0});
  rows.forEach((r,ri)=>{t.rows[ri].height=r.height;r.cells.forEach((c,ci)=>{
   const cell=t.getCell(ri,ci),st=c.style;cell.fill=c.fill==='none'?'#f7f8f3':c.fill;
   cell.text.style={typeface:'Arial',fontSize:st.fontSize,bold:st.bold,color:st.color,alignment:'left',verticalAlignment:'middle',lineSpacing:st.lineHeight/st.fontSize,autoFit:'none',wrap:'square',insets:{left:c.margins.left,right:c.margins.right,top:0,bottom:0}};
   t.cells.block({row:ri,column:ci,rowCount:1,columnCount:1}).assign({margins:{left:c.margins.left,right:c.margins.right,top:0,bottom:0},anchor:'center'});
  });});
  // Native separator lines preserve the quiet table style without introducing vertical borders.
  let y=b.top;for(const r of rows){y+=r.height;shape(s,{type:'path',name:'Table row divider',points:[{x:b.left,y},{x:b.left+b.width,y}],stroke:'#d9ded5',lineWidth:1,fill:'none'});}
 }
 s.speakerNotes.textFrame.setText(page.notes);
 console.log(`Built editable slide ${i+1}`);
}
await(await PresentationFile.exportPptx(p)).save(path.join(dir,'candidate.pptx'));
await fs.writeFile(path.join(dir,'native-inspect.ndjson'),(await p.inspect({kind:'slide,textbox,shape,table',maxChars:500000})).ndjson);
console.log('Exported fully native candidate.');

