from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '机器人推块比赛_阶段汇报.html'
old = OUT.read_text(encoding='utf-8')
backup = ROOT / 'tmp' / 'report-v1.html'
if not backup.exists():
    backup.write_text(old, encoding='utf-8')
js = re.search(r'<script>([\s\S]*?)</script>', old).group(1)
js = re.sub(r"storageKey='[^']+'", "storageKey='robot-report-20260928-v2'", js)
base = Path(r'C:\Users\Admin\.codex\skills\frontend-slides\viewport-base.css').read_text(encoding='utf-8')
slides = []

def add(title, body, notes, cls=''):
    n = len(slides)+1
    slides.append(f'''<section class="slide {cls}" aria-label="第 {n} 页：{re.sub('<[^>]+>','',title)}">
    <h2 data-edit>{title}</h2><div class="content">{body}</div>
    <aside class="speaker-notes">{notes}</aside></section>''')

def robot(x, y, angle=0, scale=1, enemy=False, ghost=False):
    color = '#66809a' if enemy else '#282c2b'
    opacity = '.25' if ghost else '1'
    return f'''<g transform="translate({x} {y}) rotate({angle}) scale({scale})" opacity="{opacity}">
    <rect x="-42" y="-29" width="13" height="58" rx="5" fill="{color}"/><rect x="29" y="-29" width="13" height="58" rx="5" fill="{color}"/>
    <rect x="-31" y="-42" width="62" height="77" rx="10" fill="{color}" stroke="#fff" stroke-width="2"/>
    <rect x="-16" y="-25" width="32" height="32" rx="3" fill="#f8f7f4"/><path d="M-10 -19h8v8h-8z M4 -19h7v7H4z M-3 -5h12v7H-3z" fill="{color}"/>
    <path d="M-18 34L-50 49 M18 34L50 49 M-90 39V52Q0 68 90 52V39" fill="none" stroke="{color}" stroke-width="7" stroke-linecap="round"/>
    </g>'''

def blocks(points, color='#e56a40', size=17):
    return '<g>'+''.join(f'<rect x="{x-size/2}" y="{y-size/2}" width="{size}" height="{size}" rx="2" fill="{color}" stroke="#fcf7ee" stroke-width="2"/>' for x,y in points)+'</g>'

def route(d, color='#e65f38', dashed=False, width=5):
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round" {chr(32)+"stroke-dasharray=\"10 10\"" if dashed else ""}/>'

def down_arrow(x,y,length=80,color='#e65f38'):
    return route(f'M{x} {y}v{length}m-12 -13l12 13 12 -13',color)

def field(contents, labels=False, uid='field', square=False):
    vb = '0 0 620 660' if not square else '0 40 620 570'
    label = '<text x="77" y="126" class="field-label">对方半区</text><text x="77" y="551" class="field-label">我方半区</text>' if labels else ''
    return f'''<svg class="court" viewBox="{vb}" role="img" aria-label="推块策略场地示意">
    <rect x="55" y="70" width="510" height="260" fill="#dae5ee"/>
    <rect x="55" y="330" width="510" height="260" fill="#eae6bc"/>
    <rect x="55" y="70" width="510" height="520" rx="4" fill="none" stroke="#a7afaa" stroke-width="2"/>
    <path d="M55 330H565" stroke="#fff" stroke-width="3" stroke-dasharray="12 11"/>
    {label}{contents}</svg>'''

initial_blocks = blocks([(120,325),(192,325),(264,325),(336,325),(408,325),(480,325)])
hero_contents = '''<path d="M194 283H344V490H194Z" fill="#e56a4013"/>
<path d="M191 287V497 M347 287V497" stroke="#e56a40" stroke-width="2" stroke-dasharray="7 11"/>'''+initial_blocks+robot(269,216,scale=1.16)+down_arrow(269,367,94)
hero_board = field(hero_contents)
add('推块机器人<br><span>方案与策略</span>',f'''
<p class="cover-sub" data-edit>阶段工作汇报</p>
<div class="cover-art">{hero_board}</div>
<div class="cover-stroke"></div>''',
'建议用时 20 秒。本次主要汇报当前方案、推方块的策略，以及后续计划与两人分工。目前已形成设计思路，硬件仍在调研，型号与实物效果尚未确定。所有场地图均为动作示意，方块数量和机器人外形不代表最终实物。','cover')

task_field=field(initial_blocks+robot(269,216)+down_arrow(269,370,95),True)
add('把方块推入我方，<br>并保留到比赛结束。',f'''
<div class="task-art">{task_field}</div>
<div class="task-facts"><div><strong>&lt; 90<span>s</span></strong><p data-edit>单场自主完成</p></div>
<div><h3 data-edit>允许越线</h3><p data-edit>可以进入对方半区寻找推送位置</p></div>
<div><h3 data-edit>允许场外辅助</h3><p data-edit>用摄像头和电脑观察全场</p></div></div>''',
'建议用时 35 秒。比赛目标是终场在我方半区保留更多方块。场地为 1.2 米见方，方块约 2 厘米，初始沿中线附近排列。我们开局在对方半区，车头朝向我方，可直接推送。当前按底盘面积小于 150 平方厘米、最长边小于 40 厘米理解，推板如何计入尺寸仍需确认。比赛允许越线、场外摄像头和无线连接。','task')

camera_icon='''<svg viewBox="0 0 270 210"><path d="M30 80h178v94H30z" fill="#e5e7e1"/><rect x="35" y="70" width="179" height="92" rx="17" fill="#262c2a"/><circle cx="125" cy="116" r="30" fill="#f8f7f4"/><circle cx="125" cy="116" r="16" fill="#e86a43"/><path d="M213 88l29-18v90l-29-18" fill="#262c2a"/><path d="M94 163v18h65v-18" fill="none" stroke="#262c2a" stroke-width="8"/></svg>'''
laptop_icon='''<svg viewBox="0 0 270 210"><rect x="35" y="44" width="195" height="122" rx="10" fill="#282d2a"/><rect x="44" y="53" width="177" height="104" rx="3" fill="#eceee8"/><path d="M65 120l35-35 36 22 57-39" stroke="#e56a40" stroke-width="6" fill="none"/><circle cx="136" cy="107" r="6" fill="#282d2a"/><path d="M34 165L15 187h239l-23-22" fill="#282d2a"/><path d="M104 169h55l8 7H96z" fill="#f8f7f4"/></svg>'''
chip_icon='''<svg viewBox="0 0 270 210"><rect x="43" y="35" width="183" height="151" rx="10" fill="#e6e9df" stroke="#b5bdb2" stroke-width="2"/><rect x="87" y="64" width="95" height="85" rx="5" fill="#2c322d"/><path d="M105 52v12m21-12v12m21-12v12m20-12v12M105 149v14m21-14v14m21-14v14m20-14v14M74 83h13m-13 19h13m-13 22h13m95-41h14m-14 19h14m-14 22h14" stroke="#6a7568" stroke-width="5"/><circle cx="60" cy="52" r="5" fill="#a3ada0"/><circle cx="210" cy="168" r="5" fill="#a3ada0"/><rect x="53" y="166" width="28" height="8" fill="#e56a40"/></svg>'''
robot_icon=f'<svg viewBox="0 0 270 210">{robot(135,97,scale=1.35)}</svg>'
add('场外决策，车上执行。',f'''
<div class="system-flow">
<div class="system-item">{camera_icon}<h3 data-edit>顶置摄像头</h3><p data-edit>采集全场画面</p></div><div class="flow-arrow">→</div>
<div class="system-item">{laptop_icon}<h3 data-edit>场外电脑</h3><p data-edit>识别、选目标、规划动作</p></div><div class="flow-arrow wireless"><span>无线</span>→</div>
<div class="system-item">{chip_icon}<h3 data-edit>车载控制板</h3><p data-edit>轮速控制与状态反馈</p></div><div class="flow-arrow">→</div>
<div class="system-item">{robot_icon}<h3 data-edit>电机与推板</h3><p data-edit>移动、推送与释放</p></div>
</div><p class="system-summary" data-edit>电脑决定推哪里，车载控制板负责稳定执行。</p>''',
'建议用时 40 秒。摄像头获取全场图像，电脑识别机器人与方块，并选择目标和动作。电脑通过无线连接把速度指令发给车载控制板，控制板完成电机速度闭环、反馈与失联停车。控制芯片、板卡和底盘型号仍需选型，这里只确定模块职责。视觉计划采用 OpenCV 颜色分割识别方块，以顶部标记获取机器人位姿。','system')

add('已形成方案，<br>下一步验证可行性。','''
<div class="progress-rows">
<div><span class="stage-state complete">已完成</span><h3 data-edit>比赛需求梳理</h3><p data-edit>明确目标、初始布局与主要约束</p></div>
<div><span class="stage-state complete">已完成</span><h3 data-edit>系统与策略设计</h3><p data-edit>形成模块分工与分阶段推块思路</p></div>
<div><span class="stage-state">进行中</span><h3 data-edit>硬件调研</h3><p data-edit>具体型号仍在筛选，实物验证待开展</p></div>
</div>''',
'建议用时 35 秒。当前能够展示的成果是需求分析、整体架构和推块策略设计。硬件已经开展过多轮调研，但还没有形成最终选型结果，因此本次不把某个电机或控制板写成既定方案。接下来要通过原型验证这些设计是否有效。','progress-slide')

add('每一轮，争取更多有效留存。','''
<p class="strategy-premise" data-edit>目标选择同时考虑：覆盖数量、留存风险、完整循环耗时。</p>
<div class="strategy-phases"><article><div class="phase-symbol opening-symbol"><i></i><i></i><i></i><b>↓</b></div><h3 data-edit>开局</h3><p data-edit>直接推送<br>先拿首批</p></article>
<article><div class="phase-symbol middle-symbol"><svg viewBox="0 0 190 110"><path d="M20 90V54H153M78 54V20M125 54V90" fill="none" stroke="currentColor" stroke-width="5"/><circle cx="78" cy="20" r="9" fill="currentColor"/><circle cx="157" cy="54" r="9" fill="currentColor"/><circle cx="125" cy="92" r="9" fill="currentColor"/></svg></div><h3 data-edit>中盘</h3><p data-edit>动态选择<br>获取与保护</p></article>
<article><div class="phase-symbol end-symbol"><svg viewBox="0 0 190 110"><circle cx="97" cy="57" r="42" fill="none" stroke="currentColor" stroke-width="5"/><path d="M97 27v32l20 13" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round"/></svg></div><h3 data-edit>终盘</h3><p data-edit>减少绕行<br>及时入场</p></article></div>''',
'建议用时 45 秒。这是我们的策略主线。目标是比赛结束时的方块留存，因此要同时考虑一次能覆盖多少块、推过去之后是否容易被拿走，以及从接近、对准、推送、释放到返回的完整耗时。目标按推板有效覆盖宽度选取，留出两侧余量。开局利用初始优势，中盘根据局面攻防，终盘只执行来得及完成的推送。各阶段切换条件将在模拟赛中标定。','dark strategy-overview')

start=field('<rect x="176" y="282" width="181" height="209" fill="#e56a4014"/>'+initial_blocks+robot(265,223)+down_arrow(265,367,84))
pushed=field(blocks([(120,325),(408,325),(480,325),(192,466),(264,474),(336,466)])+robot(265,385)+down_arrow(265,293,42))
released=field(blocks([(120,325),(408,325),(480,325),(192,466),(264,474),(336,466)])+robot(265,385,ghost=True)+robot(265,334)+route('M365 400v-72m-10 12l10-12 10 12'))
returned=field(blocks([(120,325),(408,325),(480,325),(192,466),(264,474),(336,466)])+route('M265 350V200H445V240',dashed=True)+robot(445,237))
add('开局：直接推送，完成第一轮获取。',f'''
<div class="opening-steps">
<article>{start}<h3 data-edit>对准首批</h3><p data-edit>覆盖正前方的连续方块</p></article>
<article>{pushed}<h3 data-edit>推入我方</h3><p data-edit>兼顾留存与往返耗时</p></article>
<article>{released}<h3 data-edit>短退释放</h3><p data-edit>避免把已入场方块带回</p></article>
<article>{returned}<h3 data-edit>绕回后方</h3><p data-edit>为下一轮推送重新就位</p></article>
</div>''',
'建议用时 65 秒。开局我们已经在正确的一侧，先对准前方能够被推板稳定覆盖的连续方块，然后直接向我方推送。第一轮推入深度要兼顾留存概率与循环耗时，现阶段不用在页面上写死距离。推完后慢速短退，让方块脱离推板，再从侧边绕回下一批方块靠对方的一侧。返回时避开已经安全存放的方块。整个过程持续保留碰撞检查，通道被占用时减速、停车或换目标。图中外廓和方块数量只用于说明动作。','opening')

capture=field(blocks([(245,310),(280,310),(315,310),(110,468),(142,490)])+robot(280,206)+down_arrow(280,360,115),False)
secure=field(blocks([(238,381),(274,384),(310,380)])+robot(274,285)+down_arrow(274,421,95)+robot(450,350,90,.65,True),False)
recover=field(blocks([(274,290),(310,288),(345,293)])+robot(472,156,-90,.68,True)+route('M410 156h75m-12-10l12 10-12 10','#6b8094')+route('M140 420V201H310',dashed=True)+robot(310,198,.0,.82)+down_arrow(310,356,122),False)
add('中盘：跟随局面，选择收益更高的动作。',f'''
<div class="midgame-scenes"><article>{capture}<h3 data-edit>获取</h3><p data-edit>优先争取距离近、<br>推板能覆盖更多的目标。</p></article>
<article>{secure}<h3 data-edit>保护</h3><p data-edit>近线方块受到威胁时，<br>继续推深，降低被带走风险。</p></article>
<article>{recover}<h3 data-edit>回收</h3><p data-edit>预测对手的释放位置，<br>寻找重新推回我方的机会。</p></article></div>
<p class="midgame-rule" data-edit>双方到达时间接近时换目标，避免长时间正面对推。</p>''',
'建议用时 75 秒。中盘是策略的重点。第一种局面是有容易获得的新方块，就比较到达目标后方、对准、推送和返回的总耗时，优先选覆盖数量多且用时短的目标。第二种局面是我方近线的一批方块受到威胁，可以选择推深保护，但安全深区的方块无需反复处理。第三种局面是方块已经被对方推走，我们避免追车或正面对抗，预测对手释放后的落点，寻找重新推回的机会。如果双方几乎同时接触同一批方块，就换一个收益更高的目标。图中深灰是我方，蓝灰为对手。对手识别及落点预测目前属于待实现、待验证的策略。','midgame')

endboard=field(blocks([(174,148),(206,154)],'#9aa19c')+blocks([(384,313),(419,310)])+robot(344,421,180,.83)+route('M302 411H108V99H209V132','#afb6b1',True)+route('M379 420H482V216H400V251')+route('M391 238l9 13 10-13')+down_arrow(402,360,88)+'''<text x="276" y="135" class="diagram-label subtle">远端绕行</text><text x="286" y="554" class="diagram-label">优先处理近线目标</text>''',True)
add('终盘：只做来得及完成的推送。',f'''
<div class="endgame-layout"><div>{endboard}</div><div class="endgame-copy"><p class="time-condition" data-edit>预计整轮耗时<br><span>小于剩余时间</span></p><div class="endgame-rules"><p data-edit>优先过线，减少深推。</p><p data-edit>短退释放，避免最后带回。</p><p data-edit>切换时机由实测耗时确定。</p></div></div></div>''',
'建议用时 50 秒。时间越少，越需要判断这一轮是否真的来得及完成。我们比较的整轮耗时包括绕到目标后方、对准、推送和释放，并留出制动余量。终盘优先处理附近、靠中线、能够及时送入我方的目标，减少远距离绕行和没有必要的深推。不能在时间结束时把方块仍卡在推板里，具体释放和停车方式还取决于最终计分规则。图中灰色长路线表示不优先选择的远端目标，橙色路线表示较短的可行路线。','endgame')

add('先跑通单次推送，再增加策略。','''
<div class="plan-flow">
<div class="plan-stage"><span class="plan-dot"></span><h3 data-edit>参数确认</h3><p data-edit>规则、关键件<br>接口与采购清单</p></div>
<div class="plan-arrow">→</div>
<div class="parallel"><div><h3 data-edit>底盘控制</h3><p data-edit>装配、轮速与无线指令</p></div><div><h3 data-edit>视觉原型</h3><p data-edit>标定、定位与方块识别</p></div></div>
<div class="plan-arrow">→</div>
<div class="plan-stage"><span class="plan-dot"></span><h3 data-edit>单次循环</h3><p data-edit>接近、对准<br>推送、释放、返回</p></div>
<div class="plan-arrow">→</div>
<div class="plan-stage"><span class="plan-dot"></span><h3 data-edit>模拟比赛</h3><p data-edit>连续推块<br>阶段切换与对抗</p></div>
</div><p class="plan-conclusion" data-edit>底盘与视觉并行开发，基础循环稳定后再加入中盘攻防。</p>''',
'建议用时 45 秒。实施顺序与策略复杂度保持一致。先确认比赛细则、元件匹配、接口和采购清单，接着并行开发底盘和视觉原型。联调时先实现到达目标点与对准，再完整完成一次推送、释放和返回。基础循环稳定后，才加入连续推块、中盘攻防以及终盘切换。最后通过模拟赛记录留存、漏块和耗时，调整参数。具体日期由课程节点和到货情况确定。','plan')

add('两人并行开发，在整机联调汇合。','''
<div class="team-layout"><article><p class="member" data-edit>成员 A</p><h3 data-edit>机械与控制</h3><ul><li data-edit>底盘、推板与电气搭建</li><li data-edit>电机闭环与无线指令执行</li><li data-edit>异常停车与底盘测试</li></ul></article>
<article><p class="member" data-edit>成员 B</p><h3 data-edit>视觉与策略</h3><ul><li data-edit>场地标定与目标识别</li><li data-edit>目标选择与推块动作</li><li data-edit>电脑端控制与数据记录</li></ul></article></div>
<div class="shared-work"><b>共同负责</b><p data-edit>策略讨论、接口约定、整机联调与模拟比赛</p></div>''',
'建议用时 40 秒。这是两名成员的建议分工，姓名暂用 A 和 B。A 主责结构、电气和车载控制，保证小车能够稳定执行命令。B 主责视觉识别、目标选择与电脑端策略。两个人共同讨论策略，提前定义坐标、速度单位、通信与异常处理接口，之后共同完成整机联调、模拟比赛和汇报。分工可以根据实际技能和时间进一步调整。','team')

add('下一次汇报，<br>用运行结果验证方案。','''
<div class="deliverables"><div><span>能控制</span><p data-edit>无线指令<br>异常停车</p></div><div><span>能识别</span><p data-edit>机器人定位<br>方块识别</p></div><div><span>能推送</span><p data-edit>完整推送循环<br>测试记录</p></div></div>''',
'建议用时 25 秒。下一次汇报的目标是从方案说明进展到运行演示：底盘能执行无线指令并在异常时停车；视觉能输出机器人与方块位置；整机能完成完整推送，并提供误差、延迟、漏块和动作耗时记录。这些都是下一阶段的预期交付，目前尚未完成实测。内容依据项目 README、V3 策略方案与本次确认的汇报结构。硬件型号保持未定，历史候选不作为选型结论。','dark finale')

css=r'''
/* === RESTRAINED EDITORIAL SYSTEM === */
:root{--stage-bg:#1d201e;--slide-bg:#f8f7f4;--ink:#232925;--muted:#697169;--accent:#df603a;--line:#d9ddd5}
*{box-sizing:border-box}body{font-family:"Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif;color:var(--ink);-webkit-font-smoothing:antialiased}
.slide{padding:92px 106px;color:var(--ink);transition:opacity .28s ease;background:var(--slide-bg)}
.slide.dark{--slide-bg:#242b26;--ink:#f6f4eb;--muted:#b6bdae;--line:#596154;--accent:#ff956d}
h2{font-size:74px;line-height:1.35;font-weight:650;letter-spacing:-2px;margin:0;max-width:1708px}h3{font-size:42px;line-height:1.4;font-weight:600;margin:0 0 18px}p{font-size:32px;line-height:1.65;margin:0}.content{position:relative}span.accent{color:var(--accent)}.speaker-notes{display:none}
.court{display:block;width:100%;height:100%;overflow:visible}.field-label{font:29px "Microsoft YaHei",sans-serif;fill:#626f6b}.diagram-label{font:29px "Microsoft YaHei",sans-serif;fill:#313b32}.diagram-label.subtle{fill:#818c83}
/* === OPENING TITLE AND TASK === */
.cover h2{position:absolute;left:110px;top:294px;font-size:116px;line-height:1.3;letter-spacing:-4px;z-index:2}.cover h2 span{font-weight:350;color:#858d83}.cover .content{position:static;animation:none!important;transform:none!important}.cover-sub{position:absolute;left:118px;top:669px;font-size:36px;color:var(--muted)}.cover-stroke{position:absolute;left:118px;top:246px;width:86px;height:7px;background:var(--accent)}
.cover-art{position:absolute;width:970px;height:980px;top:36px;right:60px;transform:rotate(-12deg);transform-origin:center}.cover-art svg{filter:drop-shadow(4px 22px 14px #404c3710)}
.task h2{font-size:70px}.task .content{height:680px}.task-art{position:absolute;left:820px;top:-177px;width:840px;height:805px}.task-facts{padding-top:60px;width:715px;display:grid;gap:31px}.task-facts>div{padding:15px 0 25px;border-bottom:1px solid var(--line)}.task-facts>div:last-child{border-bottom:0}.task-facts strong{font-size:105px;line-height:1;font-weight:400;letter-spacing:-4px;color:var(--accent)}.task-facts strong span{font-size:43px;letter-spacing:0;margin-left:13px}.task-facts h3{font-size:42px;margin:0 0 6px}.task-facts p{font-size:30px;color:var(--muted);margin-top:10px}
/* === SYSTEM AND PROGRESS === */
.system-flow{display:grid;grid-template-columns:1fr 52px 1fr 70px 1fr 52px 1fr;align-items:center;margin-top:155px;gap:12px}.system-item{text-align:center}.system-item svg{height:230px;width:295px}.system-item h3{font-size:38px;margin-top:35px}.system-item p{font-size:27px;color:var(--muted)}.flow-arrow{font-size:58px;color:#9da69c;position:relative;margin-top:-120px}.flow-arrow span{font-size:24px;position:absolute;top:-29px;left:5px;white-space:nowrap}.system-summary{margin-top:105px;font-size:38px;text-align:center;color:var(--muted)}
.progress-rows{margin-top:60px}.progress-rows>div{display:grid;grid-template-columns:185px 480px 1fr;gap:28px;padding:43px 0;border-top:1px solid var(--line);align-items:center}.progress-rows h3{font-size:41px;margin:0}.progress-rows p{font-size:31px;color:var(--muted)}.stage-state{font-size:29px;color:var(--accent)}.stage-state.complete{color:#7a8478}
/* === STRATEGY CHAPTER === */
.strategy-overview h2{margin-top:18px}.strategy-premise{margin-top:38px;font-size:33px;color:var(--muted)}.strategy-phases{display:grid;grid-template-columns:repeat(3,1fr);gap:100px;margin-top:94px}.strategy-phases article{border-top:1px solid var(--line);padding-top:38px}.strategy-phases h3{font-size:68px;letter-spacing:4px;margin-top:40px;margin-bottom:23px}.strategy-phases p{font-size:41px;line-height:1.65;color:var(--muted)}.phase-symbol{height:110px;color:var(--accent);display:flex;align-items:center}.phase-symbol svg{height:110px;width:190px}.opening-symbol{gap:19px}.opening-symbol i{width:25px;height:25px;background:var(--accent)}.opening-symbol b{font-size:90px;font-weight:300;line-height:1;margin-left:34px}
.opening h2,.midgame h2{font-size:66px}.opening-steps{display:grid;grid-template-columns:repeat(4,1fr);gap:28px;margin-top:70px}.opening-steps .court{height:481px}.opening-steps h3{font-size:38px;margin:18px 0 12px;text-align:center}.opening-steps p{font-size:27px;text-align:center;color:var(--muted)}
.midgame-scenes{display:grid;grid-template-columns:repeat(3,1fr);gap:75px;margin-top:28px}.midgame-scenes .court{height:478px}.midgame-scenes h3{font-size:46px;margin:4px 0 16px}.midgame-scenes p{font-size:29px;line-height:1.65;max-width:485px;color:var(--muted)}.midgame-rule{font-size:33px;margin-top:39px;padding-top:28px;border-top:1px solid var(--line)}
.endgame h2{font-size:70px}.endgame-layout{display:grid;grid-template-columns:830px 1fr;gap:87px;margin-top:35px}.endgame-layout .court{height:746px}.endgame-copy{padding-top:75px}.time-condition{font-size:57px;font-weight:600;line-height:1.65;letter-spacing:-1px}.time-condition span{color:var(--accent)}.endgame-rules{margin-top:47px;border-top:1px solid var(--line);padding-top:35px}.endgame-rules p{font-size:32px;color:var(--muted);margin-bottom:20px}
/* === IMPLEMENTATION AND OWNERSHIP === */
.plan-flow{display:grid;grid-template-columns:295px 48px 424px 48px 280px 48px 285px;gap:40px;align-items:center;margin-top:126px}.plan-stage h3,.parallel h3{font-size:38px}.plan-stage p,.parallel p{font-size:28px;color:var(--muted);line-height:1.9}.plan-arrow{font-size:55px;color:#a2aaa0}.plan-dot{width:17px;height:17px;background:var(--accent);display:block;border-radius:50%;margin-bottom:40px}.parallel{padding:20px 30px;border-left:2px solid #ccd2c6;border-right:2px solid #ccd2c6}.parallel>div{padding:27px 0}.parallel>div+div{border-top:1px solid var(--line)}.plan-conclusion{margin-top:104px;padding-top:35px;border-top:1px solid var(--line);font-size:36px;color:var(--muted)}
.team h2{font-size:70px}.team-layout{display:grid;grid-template-columns:1fr 1fr;margin-top:85px;gap:98px}.team-layout article+article{border-left:1px solid var(--line);padding-left:98px}.member{color:var(--accent);font-size:31px;margin-bottom:23px}.team-layout h3{font-size:57px;margin-bottom:43px}.team-layout ul{list-style:none;padding:0;margin:0}.team-layout li{font-size:32px;margin-bottom:23px;line-height:1.6;color:var(--muted)}.shared-work{display:flex;align-items:baseline;gap:45px;border-top:1px solid var(--line);padding-top:36px;margin-top:61px}.shared-work b{font-size:31px;font-weight:500}.shared-work p{font-size:32px;color:var(--muted)}
.finale h2{font-size:99px;line-height:1.4;margin-top:66px;font-weight:500;letter-spacing:-2px}.deliverables{display:grid;grid-template-columns:repeat(3,1fr);gap:100px;margin-top:118px}.deliverables>div{border-top:1px solid var(--line);padding-top:38px}.deliverables span{font-size:54px;color:var(--accent);font-weight:500}.deliverables p{font-size:34px;line-height:1.8;color:var(--muted);margin-top:24px}
/* === MOTION AND HIDDEN PRESENTATION TOOLS === */
.slide.active h2{animation:arrive .42s both}.slide.active .content{animation:arrive .55s .08s both}@keyframes arrive{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.deck-controls{bottom:10px;display:flex;align-items:center;gap:4px;padding:5px 10px;border:1px solid #ffffff20;border-radius:10px;background:#202823ee;color:#f8f7ed;opacity:0;transition:opacity .2s;white-space:nowrap}.deck-controls:hover,.deck-controls:focus-within,body.controls-show .deck-controls{opacity:1}.deck-controls button{font:inherit;font-size:13px;color:inherit;border:0;border-radius:5px;background:transparent;cursor:pointer;padding:8px 10px}.deck-controls button:hover{background:#ffffff1f}.deck-controls output{font-size:12px;min-width:45px;text-align:center}.progress{display:none}.notes-panel{position:fixed;right:22px;bottom:68px;width:min(580px,90vw);max-height:65vh;overflow:auto;z-index:1005;background:#f8f7f4;color:#232925;padding:30px;box-shadow:0 15px 80px #0005;border:1px solid #c7cec1;border-radius:6px}.notes-panel[hidden]{display:none}.notes-panel h3{font-size:19px;margin:0 0 12px}.notes-panel p{font-size:17px;line-height:1.85;margin:0}.notes-panel button{float:right;border:0;background:transparent;font-size:23px;cursor:pointer}.hint{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:1010;color:#fff;background:#232b26ed;padding:9px 16px;border-radius:6px;font-size:13px;pointer-events:none;opacity:0;transition:opacity .2s}.hint.show{opacity:1}body.editing [data-edit]{outline:2px dashed #df603a80;outline-offset:6px;cursor:text}button:focus-visible{outline:2px solid #fcaa8d;outline-offset:2px}
@media print{@page{size:1920px 1080px;margin:0}.deck-controls,.progress,.notes-panel,.hint{display:none!important}.slide{-webkit-print-color-adjust:exact;print-color-adjust:exact}.slide [data-edit]{outline:0!important}.slide h2,.slide .content{animation:none!important;opacity:1!important}}
'''

html='''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>推块机器人 · 方案与策略</title><style>'''+base+css+'''</style></head><body><div class="deck-viewport"><main class="deck-stage" id="deckStage">'''+''.join(slides)+'''</main></div>
<nav class="deck-controls" aria-label="演示控制"><button id="prev" title="上一页（←）">←</button><output id="pageCount" aria-live="polite"></output><button id="next" title="下一页（→）">→</button><button id="fullscreen">全屏 F</button><button id="notesButton" aria-expanded="false">讲稿 N</button><button id="editButton">编辑文字</button><button id="saveButton">保存 HTML</button></nav>
<div class="progress" aria-hidden="true"><span id="bar"></span></div><div class="hint" id="hint"></div>
<aside class="notes-panel" id="notes" hidden aria-label="讲稿"><button id="closeNotes" aria-label="关闭讲稿">×</button><h3 id="noteTitle"></h3><p id="noteText"></p></aside><script>'''+js+'''</script></body></html>'''
OUT.write_text(html,encoding='utf-8')
print(f'Created {len(slides)} slides; {OUT.stat().st_size} bytes')
