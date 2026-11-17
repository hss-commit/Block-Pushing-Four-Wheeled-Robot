import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
const deps=process.env.RUNTIME_NODE_MODULES;
const {Presentation,PresentationFile}=await import(pathToFileURL(path.join(deps,'@oai/artifact-tool/dist/artifact_tool.mjs')));
const sharp=createRequire(path.join(deps,'package.json'))('sharp');
const p=Presentation.create({slideSize:{width:1280,height:720}});
const G='#20599B', D='#122542', S='#46556B', T='#EFF5FC', W='#FFFFFF', O='#A14C28', B='#E2EEFC', Y='#F8E7A8';
const work='tmp/report-04/compact';
await fs.mkdir(work,{recursive:true});
const invisible={fill:'none',width:0};
const box=(s,x,y,w,h,fill)=>s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:invisible});
function txt(s,value,x,y,w,h,{size=24,color=D,bold=false,align='left',vertical='top'}={}){
 const a=s.shapes.add({name:value.slice(0,70),geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:invisible});
 a.text=value;
 a.text.style={typeface:'Aptos',fontSize:size,bold,color,alignment:align,verticalAlignment:vertical,wrap:'square',insets:0};
 return a;
}
function notes(s,en,cn,source){s.speakerNotes.text=en+'\n\n中文提示：'+cn+(source?'\n\nSource: '+source:'');}
function slide(section,title,en,cn,source){
 const s=p.slides.add();s.background.fill=W;
 box(s,72,62,34,4,G);txt(s,title,72,78,1136,65,{size:47,bold:true});
 box(s,72,653,1136,1,'#D8E2EF');txt(s,'GROUP 04  /  ROBOT PROJECT',72,665,365,24,{size:15,bold:true,color:S});
 txt(s,section,1149,663,59,28,{size:17,bold:true,color:G,align:'right'});notes(s,en,cn,source);return s;
}
function point(s,h,v,x,y,w){txt(s,h,x,y,w,32,{size:25,bold:true,color:G});txt(s,v,x,y+38,w,82,{size:23,color:S});}
function strip(s,t,y=580){box(s,72,y,1136,54,T);box(s,72,y,4,54,G);txt(s,t,92,y,1096,54,{size:22,bold:true,vertical:'middle'});}
function centered(s,t,x,y,w,h,size=24,color=D,bold=false){return txt(s,t,x,y,w,h,{size,color,bold,align:'center',vertical:'middle'});}
function steps(s,items,y,{x=72,w=1136,h=128}={}){
 const cell=(w-32*(items.length-1))/items.length;
 items.forEach(([head,body],i)=>{const a=x+i*(cell+32);box(s,a,y,cell,3,G);box(s,a,y+3,cell,h-3,T);
 txt(s,head,a+16,y+17,cell-32,34,{size:24,bold:true,color:G});txt(s,body,a+16,y+58,cell-32,h-59,{size:20,color:S});
 if(i<items.length-1)centered(s,'→',a+cell,y+5,32,h-10,25,G,true);});
}
async function photo(s,file,crop,x,y,w,h,alt){const bytes=await sharp(file).extract(crop).png().toBuffer(), f=Math.min(w/crop.width,h/crop.height), a=crop.width*f,b=crop.height*f;
 s.images.add({blob:bytes,contentType:'image/png',alt,position:{left:x+(w-a)/2,top:y+(h-b)/2,width:a,height:b}});}
function arrowDown(s,x,y,h,color=G){box(s,x-2,y,4,h-11,color); const a=s.shapes.add({geometry:'triangle',position:{left:x-8,top:y+h-14,width:16,height:14},fill:color,line:invisible});a.rotation=180;}
function table(s,rows,x,y,w,h,widths){
 const t=s.tables.add({rows:rows.length,columns:widths.length,left:x,top:y,width:w,height:h,columnWidths:widths,values:rows});
 t.borders.assign({style:'solid',fill:'#D4E4DB',width:1});
 rows.forEach((row,r)=>{t.rows[r].height=h/rows.length;row.forEach((_,c)=>{const a=t.getCell(r,c);a.fill=r===0?G:r%2?T:W;
 a.text.style={typeface:'MiSans',fontSize:21,color:r===0?W:D,bold:r===0||c===0,verticalAlignment:'middle',insets:{left:14,right:10,top:4,bottom:4}};});});
}
{
 const s=p.slides.add();s.background.fill=W;
 box(s,72,110,48,5,G);
 txt(s,'BLOCK-PUSHING ROBOT',72,153,612,192,{size:66,bold:true});
 txt(s,'From one push to two verified deliveries in simulation',72,363,560,103,{size:29,color:S});
 txt(s,'GROUP 04  /  PROJECT UPDATE',72,619,410,35,{size:18,bold:true,color:G});
 await photo(s,'vision/results/2026-10-20-new-video/frame-00060.png',{left:15,top:419,width:1055,height:944},698,100,510,482,'Annotated field camera footage showing the blue and yellow zones');
 centered(s,'Field camera footage, 20 Oct',698,580,510,34,17,S);
 notes(s,'Last time, the robot could see the field and move. Today we will show how it checks whether a push worked, and what we still need to verify on the real field.','上次解决了看得见和能移动。这次讲怎么判断推块成功，以及还有哪些内容要在实车上确认。','Project records through 12 Nov 2026.');
}
{
 const s=slide('02','How one push ends','We begin with the robot facing a single block. The program approaches it, then tracks the block from the start of the push. The stop decision comes from the measured change in block position rather than the driver command duration.','单块测试先把车头对准方块。接近后以方块起始位置作基准，一边短动一边读新画面，达到 100 毫米目标就停车。','control/单块自主推送测试说明.md; control/single_push_control.py');
 point(s,'Start aligned','Start with the robot facing one block.',72,189,504);
 point(s,'Measure the block','Use fresh camera frames to track block travel.',72,314,504);
 point(s,'Stop at the target','Stop when the block has moved 100 mm.',72,439,504);
 box(s,632,154,560,377,T);
 centered(s,'Start of push',645,223,214,35,22,S);centered(s,'Stop point',951,223,215,35,22,S);
 box(s,726,292,52,52,'#C4573F');box(s,1033,292,52,52,'#C4573F');box(s,779,315,252,4,G);centered(s,'→',1004,288,30,51,29,G,true);
 box(s,751,377,309,2,G);box(s,751,369,2,18,G);box(s,1058,369,2,18,G);centered(s,'100 mm',758,397,298,48,31,G,true);
 centered(s,'Top view, not to scale',648,480,528,28,17,S);
}
{
 const s=slide('03','How the robot counts a delivery','For multiple blocks, reaching a distance is not enough. The robot selects an accessible block and pushes it fully into the yellow zone. It then backs away and checks that the whole block remains in the zone before counting it and selecting another.','多块不是简单重复推 100 毫米。需要先选有路线的目标，推入黄区，退开后再确认整个块还在黄区；确认后才计数、选下一块。','control/多块入区测试说明.md; control/multi_push_control.py');
 point(s,'Pick a reachable block','Check that the robot can get behind it and push it into the yellow zone.',72,187,541);
 point(s,'Back up and look again','Back away. Check that the whole block stays in the yellow zone for about half a second.',72,310,539);
 point(s,'Count it, then move on','Select the next block only after the check passes.',72,433,539);
 box(s,661,148,524,183,B);box(s,661,332,524,197,Y);box(s,661,330,524,3,W);
 txt(s,'BLUE ZONE',679,162,200,30,{size:19,bold:true,color:'#31537C'});txt(s,'YELLOW ZONE',679,345,210,30,{size:19,bold:true,color:'#6C5405'});
 box(s,852,190,58,71,G); centered(s,'Robot',850,211,62,26,16,W,true);
 box(s,864,281,34,34,'#C4573F');arrowDown(s,881,323,89,G);
 box(s,864,419,34,34,'#C4573F');txt(s,'Verified position',914,420,245,32,{size:20,bold:true,color:'#6C5405'});
 centered(s,'Delivery sequence, top view',662,540,524,33,17,S);
}
{
 const s=slide('04','Simulation and field results','The software test completed two successive deliveries and ended with a stop. The physical attempt on 10 November did not start: the camera marked some long or merged areas as blocks. The controller kept the robot stopped, so the run did not verify any delivery.','软件联调完成两块入黄区并最终停车。但 11 月 10 日那次现场没有启动：中线长条和粘连区域形成了过大的框，程序停车等待，记录的完成数是零。','tmp/reconnect-multi-check.log; vision/results/multi-push-20261110-174035-836654/events.jsonl; 10 Nov live screenshot.');
 point(s,'Simulation: 2 deliveries','The program checked both blocks in the yellow zone and stopped.',72,228,560);
 point(s,'Field attempt: no start','Oversized detection boxes blocked startup on 10 Nov.',72,392,560);

 await photo(s,'C:/Users/Admin/AppData/Local/Temp/codex-clipboard-6012ed96-a07b-4e73-9868-210fa97e2659.png',{left:69,top:65,width:824,height:736},664,154,531,399,'Live field screen with merged or oversized detection and zero verified blocks');
 centered(s,'Live screen: oversized boxes span the center line.',649,559,554,37,17,S);
}
{
 const s=slide('05','Next: repeat the test on the field','We will fix the camera, verify that the tag and the blocks stay visible, and start with two separated blocks. We will record the block displacement and check that the robot stops. For multi-block testing, we will only count a delivery after the robot backs away and the block remains in the yellow zone.','先固定相机并校准，放两块分开的同色块，确定识别不串框。先做一次单块 100 毫米实测，再测两块连续入区；每块都要在退车后确认留在黄区。全程保留视频和日志。','control/单块自主推送测试说明.md; control/多块入区测试说明.md');
 steps(s,[['01  Check the view','Fix the camera and check that both blocks are detected separately.'],['02  Test one push','Measure the 100 mm push and check that the robot stops.'],['03  Test two blocks','Check both deliveries after the robot backs away.']],224,{h:166});
 point(s,'Evidence to keep','Save the overhead video and log. Compare the recorded count with the video.',72,412,1136);
}
await (await PresentationFile.exportPptx(p)).save(path.join(work,'candidate.pptx'));

