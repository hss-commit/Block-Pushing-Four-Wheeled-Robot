import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
const deps=process.env.RUNTIME_NODE_MODULES;
const {Presentation,PresentationFile}=await import(pathToFileURL(path.join(deps,'@oai/artifact-tool/dist/artifact_tool.mjs')));
const sharp=createRequire(path.join(deps,'package.json'))('sharp');
const p=Presentation.create({slideSize:{width:1280,height:720}});
const G='#007C4F', D='#182622', S='#465952', T='#EDF6F1', W='#FFFFFF', O='#B24B0B', B='#DCE9F7', Y='#FAE9A5';
const work='tmp/report-04';
await fs.mkdir(work,{recursive:true});
const invisible={fill:'none',width:0};
const box=(s,x,y,w,h,fill)=>s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:invisible});
function txt(s,value,x,y,w,h,{size=24,color=D,bold=false,align='left',vertical='top'}={}){
 const a=s.shapes.add({name:value.slice(0,70),geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:invisible});
 a.text=value;
 a.text.style={typeface:'MiSans',fontSize:size,bold,color,alignment:align,verticalAlignment:vertical,wrap:'square',insets:0};
 return a;
}
function notes(s,en,cn,source){s.speakerNotes.text=en+'\n\n中文提示：'+cn+(source?'\n\nSource: '+source:'');}
function slide(section,title,en,cn,source){
 const s=p.slides.add();txt(s,section,36,15,102,61,{size:42,bold:true,color:W,align:'center',vertical:'middle'});
 txt(s,title,170,21,838,63,{size:title.length>42?30:34,bold:true,vertical:'middle'});notes(s,en,cn,source);return s;
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
 const s=p.slides.add();centered(s,'THE BLOCK-PUSHING ROBOT',160,352,960,68,54,W,true);
 centered(s,'From one push to repeated delivery',220,421,840,50,31,W);
 centered(s,'MECHATRONIC DESIGN   /   GROUP 04',295,491,690,36,21,W,true);
 notes(s,'Today we will show how we moved from separate vision and motion tests to a program that can plan and check repeated block deliveries.','今天汇报我们如何从独立的视觉和运动测试，推进到能规划并核验连续推块的程序。','Previous Group 04 project deck and repository records through 12 Nov 2026.');
}
{
 const s=slide('01','CAN THE ROBOT TELL WHEN A PUSH WORKED?','Last time, we showed that the camera could identify the field and that the robot could move. This time, the question is whether the robot can use a new image to see what actually moved before making its next decision.','上次展示了看得见场地和车能动。这次问一个更具体的问题：动作之后，怎样用新画面判断块到底有没有推到位？','输出/机器人推块比赛_第三次汇报_成果与计划_可编辑版.pptx; 程序与测试清单.md');
 point(s,'Where we started','The camera could see the field. The robot could move under PC control.',72,157,548);
 point(s,'What changed this round','The program checks the block after a move and uses that result to decide what to do next.',72,292,548);
 point(s,'What we still need to show','The software completed the sequence in a test. A physical run still needs to confirm it.',72,435,548);
 await photo(s,'vision/results/2026-10-20-new-video/frame-00060.png',{left:15,top:419,width:1055,height:944},680,135,506,420,'Annotated image of the real arena with the two zones and detected blocks');
 centered(s,'Field camera footage, 20 Oct',680,558,506,29,17,S);
}
{
 const s=slide('01','THE CAMERA CHECKS EACH MOVE','We correct the camera view using the four field corners. The tag on the robot gives its position and heading. After the ESP32 executes a short movement, the PC measures again from a fresh image. If the view is no longer reliable, the program stops instead of continuing from the old image.','用场地四角把画面校正，用车顶定位码读车的位置和朝向。电脑下发一次短动作，之后再看新画面。旧画面或丢定位时不继续推。','vision/latest_camera.py; control/vision_approach_test.py; control/多块入区测试说明.md');
 steps(s,[['01  See the field','Correct the view. Locate the robot and the block.'],['02  Move briefly','Send one short movement to the ESP32 over Wi-Fi.'],['03  Check again','Use a fresh frame to check the robot and the block.']],206,{h:151});
 box(s,106,394,1068,2,'#B8D9C9');centered(s,'The next move uses the latest valid frame.',105,423,1070,52,30,G,true);
 strip(s,'If the image is stale or the robot cannot be located, the controller stops.');
}
{
 const s=slide('02','ONE BLOCK: PUSH 100 mm AND STOP','We begin with the robot facing a single block. The program approaches it, then tracks the block from the start of the push. The stop decision comes from the measured change in block position rather than the driver command duration.','单块测试先把车头对准方块。接近后以方块起始位置作基准，一边短动一边读新画面，达到 100 毫米目标就停车。','control/单块自主推送测试说明.md; control/single_push_control.py');
 point(s,'Start aligned','Place one block ahead of the robot. The test follows a straight line.',72,155,504);
 point(s,'Measure the block','Compare the current block position with its position at the start of the push.',72,296,504);
 point(s,'Stop at the target','The default test ends when the camera measures 100 mm of block travel.',72,437,504);
 box(s,632,154,560,377,T);
 centered(s,'Start of push',645,223,214,35,22,S);centered(s,'Stop point',951,223,215,35,22,S);
 box(s,726,292,52,52,'#C4573F');box(s,1033,292,52,52,'#C4573F');box(s,779,315,252,4,G);centered(s,'→',1004,288,30,51,29,G,true);
 box(s,751,377,309,2,G);box(s,751,369,2,18,G);box(s,1058,369,2,18,G);centered(s,'100 mm',758,397,298,48,31,G,true);
 centered(s,'Top view, not to scale',648,480,528,28,17,S);
}
{
 const s=slide('02','SIX SOFTWARE CASES FOR ONE PUSH','The test runs the real vision processing and control program against simulated camera frames and a simulated ESP32. It reached each of the three distances. It also checked that a stall, a lost tag, or a rejected command does not count as a completed push.','电脑端联调跑了六种情况：20、100、150 毫米三种位移，以及卡住、丢码、指令被拒三种失败。这里运行了真实识别和控制程序，但相机画面和车端是模拟的。','tmp/multi-full-check.log, lines 199–204; control/test_push_integration.py');
 table(s,[['Case','Test input','Observed behavior'],['Target distance','20, 100 and 150 mm','Measured the target travel and stopped'],['No progress','Robot does not move','Stopped without reporting completion'],['Vision lost','Robot tag disappears','Stopped without reporting completion'],['Command rejected','Simulated ESP32 refuses a move','Stopped without retrying the move']],72,148,1136,343,[250,345,541]);
 strip(s,'The software passed all six cases. Real block travel still needs to be measured.',551);
}
{
 const s=slide('03','MULTIPLE BLOCKS: PUSH, BACK UP, VERIFY','For multiple blocks, reaching a distance is not enough. The robot selects an accessible block and pushes it fully into the yellow zone. It then backs away and checks that the whole block remains in the zone before counting it and selecting another.','多块不是简单重复推 100 毫米。需要先选有路线的目标，推入黄区，退开后再确认整个块还在黄区；确认后才计数、选下一块。','control/多块入区测试说明.md; control/multi_push_control.py');
 point(s,'Pick a block with a clear path','The planner checks that the robot can get behind the block and push it into the yellow zone.',72,152,541);
 point(s,'Back up and look again','The robot stops after backing away. The block must stay fully inside the yellow zone for about half a second.',72,302,539);
 point(s,'Count it and choose the next block','Blocks already in the yellow zone at the start do not count as new deliveries.',72,456,539);
 box(s,661,148,524,183,B);box(s,661,332,524,197,Y);box(s,661,330,524,3,W);
 txt(s,'BLUE ZONE',679,162,200,30,{size:19,bold:true,color:'#31537C'});txt(s,'YELLOW ZONE',679,345,210,30,{size:19,bold:true,color:'#6C5405'});
 box(s,852,190,58,71,G); centered(s,'Robot',850,211,62,26,16,W,true);
 box(s,864,281,34,34,'#C4573F');arrowDown(s,881,323,89,G);
 box(s,864,419,34,34,'#C4573F');txt(s,'Verified position',914,420,245,32,{size:20,bold:true,color:'#6C5405'});
 centered(s,'Delivery sequence, top view',662,540,524,33,17,S);
}
{
 const s=slide('03','TWO DELIVERIES PASSED IN SIMULATION','The software test completed two successive deliveries and ended with a stop. The physical attempt on 10 November did not start: the camera marked some long or merged areas as blocks. The controller kept the robot stopped, so the run did not verify any delivery.','软件联调完成两块入黄区并最终停车。但 11 月 10 日那次现场没有启动：中线长条和粘连区域形成了过大的框，程序停车等待，记录的完成数是零。','tmp/reconnect-multi-check.log; vision/results/multi-push-20261110-174035-836654/events.jsonl; 10 Nov live screenshot.');
 point(s,'Computer test','Two blocks entered the yellow zone. The controller backed up, checked each block and stopped at the end.',72,150,560);
 point(s,'Field attempt, 10 Nov','The start request arrived, but the controller rejected merged or oversized detections.',72,305,560);
 txt(s,'0 verified field deliveries in this attempt',72,469,552,68,{size:25,bold:true,color:O});
 await photo(s,'C:/Users/Admin/AppData/Local/Temp/codex-clipboard-6012ed96-a07b-4e73-9868-210fa97e2659.png',{left:69,top:65,width:824,height:736},664,129,531,425,'Live field screen with merged or oversized detection and zero verified blocks');
 centered(s,'Live screen: oversized boxes span the center line.',649,559,554,37,17,S);
}
{
 const s=slide('04','WHAT HAS TO IMPROVE BEFORE THE NEXT RUN?','The field logs showed two separate issues. Large false boxes blocked the start, and status requests sometimes timed out. The program now keeps a start request pending while it waits for stable input. If a problem occurs while moving, it still stops and requires a new start.','现场问题分成两类：过大框导致启动检查不过，热点状态查询也曾偶发超时。现在空格可以先提交启动请求，条件未稳就等待；车已动时发生异常仍停车，需要重新启动。','control/多块入区测试说明.md; tmp/one-space-multi-check.log; tmp/reconnect-multi-check.log');
 table(s,[['Field issue','Program response','What to verify on the field'],['Merged or oversized boxes','Wait for separate, stable detections','Start with well-spaced blocks and check the overlay'],['Wi-Fi status timeout','Recheck while stopped. Stop on a fault during motion.','Confirm stable connection and check restart behavior'],['Repeated start attempts','Keep one start request pending until checks pass','Confirm that the display explains what it is waiting for']],72,155,1136,356,[264,395,477]);
 strip(s,'The pending start request still requires valid vision and a working link.',561);
}
{
 const s=slide('04','NEXT TEST: TWO BLOCKS ON THE REAL FIELD','We will fix the camera, verify that the tag and the blocks stay visible, and start with two separated blocks. We will record the block displacement and check that the robot stops. For multi-block testing, we will only count a delivery after the robot backs away and the block remains in the yellow zone.','先固定相机并校准，放两块分开的同色块，确定识别不串框。先做一次单块 100 毫米实测，再测两块连续入区；每块都要在退车后确认留在黄区。全程保留视频和日志。','control/单块自主推送测试说明.md; control/多块入区测试说明.md');
 steps(s,[['01  Check the view','Calibrate the field. Confirm a stable robot tag and separate block boxes.'],['02  Test one push','Measure the real block travel against the 100 mm target and check the stop.'],['03  Test two blocks','Record two deliveries. Verify both after the robot backs away.']],183,{h:172});
 point(s,'Evidence to keep','Save the overhead video and the test log. Compare the program’s count with what the video shows.',72,412,1136);
 strip(s,'The next milestone is a recorded, repeatable physical run.',570);
}
await (await PresentationFile.exportPptx(p)).save(path.join(work,'authored.pptx'));

