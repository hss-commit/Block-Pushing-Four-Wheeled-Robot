from pathlib import Path
from html import escape

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'tmp'/'style-review'
DEST.mkdir(parents=True,exist_ok=True)
base=Path(r'C:\Users\Admin\.codex\skills\frontend-slides\viewport-base.css').read_text(encoding='utf-8')

def scene(dark=False):
    ink='#e4e6dc' if dark else '#303a39'
    muted='#9daaa9' if dark else '#75827c'
    accent='#c8a870' if dark else '#34695b'
    line='#5a6677' if dark else '#c6ccc6'
    opp='#829cb2' if dark else '#657d95'
    return f'''<svg viewBox="0 0 1000 740" role="img" aria-label="中盘目标比较示意：放弃有争夺风险的目标 A，转向目标 B。路径仅为策略示意。">
    <defs><pattern id="grid" width="52" height="52" patternUnits="userSpaceOnUse"><path d="M52 0H0V52" fill="none" stroke="{line}" stroke-width=".6" opacity=".45"/></pattern><marker id="tip" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M1 1L7 4L1 7" fill="none" stroke="{accent}" stroke-width="1.5"/></marker></defs>
    <rect x="72" y="95" width="520" height="260" fill="{opp}" opacity=".07"/><rect x="72" y="355" width="520" height="260" fill="{accent}" opacity=".08"/>
    <rect x="72" y="95" width="520" height="520" fill="url(#grid)" stroke="{line}" stroke-width="2"/>
    <path d="M72 355H592" stroke="{muted}" stroke-width="1.5" stroke-dasharray="9 9"/>
    <text x="72" y="65" fill="{muted}" font-size="25">对方半区</text><text x="72" y="659" fill="{muted}" font-size="25">我方半区</text>
    <rect x="174" y="268" width="99" height="214" fill="{accent}" opacity=".09"/>
    <path d="M174 268V482 M273 268V482" stroke="{accent}" stroke-width="1.5" stroke-dasharray="6 7"/>
    <g fill="{accent}"><rect x="193" y="326" width="14" height="14"/><rect x="215" y="333" width="14" height="14"/><rect x="238" y="326" width="14" height="14"/></g>
    <g fill="{opp}"><rect x="373" y="326" width="14" height="14"/><rect x="395" y="333" width="14" height="14"/><rect x="418" y="326" width="14" height="14"/></g>
    <ellipse cx="404" cy="333" rx="66" ry="52" fill="none" stroke="{opp}" stroke-width="1.4" stroke-dasharray="5 7"/>
    <path d="M330 476Q405 440 402 386" fill="none" stroke="{opp}" stroke-width="2.5" stroke-dasharray="8 8" opacity=".65"/>
    <path d="M490 230Q434 250 414 277" fill="none" stroke="{opp}" stroke-width="2.5" stroke-dasharray="8 8"/>
    <path d="M299 488H144V248Q144 231 163 231H205Q223 231 223 251V301" fill="none" stroke="{accent}" stroke-width="3.8" marker-end="url(#tip)"/>
    <path d="M224 365V442" fill="none" stroke="{accent}" stroke-width="3.8" marker-end="url(#tip)"/>
    <g><circle cx="319" cy="488" r="22" fill="{accent}"/><path d="M310 496l9-23 9 23-9-6z" fill="{'#1c2644' if dark else '#fff'}"/><circle cx="319" cy="488" r="33" fill="none" stroke="{accent}" opacity=".3" stroke-width="1.5"/></g>
    <g><circle cx="496" cy="226" r="20" fill="{opp}"/><path d="M487 223l21-9-8 21-2-10z" fill="{'#1c2644' if dark else '#fff'}"/></g>
    <text x="350" y="509" fill="{ink}" font-size="27">我方</text><text x="458" y="179" fill="{opp}" font-size="27">对手</text>
    <path d="M430 296L619 264H685" stroke="{opp}" stroke-width="1.5" fill="none"/><circle cx="430" cy="296" r="4" fill="{opp}"/>
    <text x="665" y="228" fill="{ink}" font-size="32" font-weight="600">目标 A</text><text x="665" y="304" fill="{muted}" font-size="27">双方接近</text><text x="665" y="345" fill="{muted}" font-size="27">争夺风险较高</text>
    <path d="M267 448L620 473H685" stroke="{accent}" stroke-width="1.5" fill="none"/><circle cx="267" cy="448" r="4" fill="{accent}"/>
    <text x="665" y="435" fill="{accent}" font-size="32" font-weight="600">目标 B</text><text x="665" y="513" fill="{muted}" font-size="27">可独立完成推送</text><text x="665" y="554" fill="{muted}" font-size="27">优先重新评估</text>
    </svg>'''

common='''
*{box-sizing:border-box}body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;color:var(--ink)}
.slide{padding:78px 90px;background:var(--slide-bg);color:var(--ink)}h1,h2,h3,p{margin:0}h1{font-size:65px;line-height:1.4;font-weight:600;letter-spacing:-1px}p{font-size:30px;line-height:1.75}svg{width:100%;height:100%;font-family:inherit} .slide.active{visibility:visible;opacity:1}
'''

a_css='''
:root{--stage-bg:#e6e8e1;--slide-bg:#f7f8f3;--ink:#28332f;--muted:#768179;--accent:#34695b}
h1{border-bottom:2px solid #2c4033;padding-bottom:36px}.layout{display:grid;grid-template-columns:600px 1fr;gap:60px;margin-top:50px;height:718px}.reading{padding:20px 5px 0 0}.reading h2{font-size:42px;font-weight:500;line-height:1.6;margin-bottom:48px}.point{padding:24px 0;border-top:1px solid #d9ded5}.point h3{font-size:32px;font-weight:600;margin-bottom:10px}.point p{font-size:28px;color:#718076}.point:last-child h3{color:var(--accent)}.map{height:738px;margin-top:-17px}.reading h2 span{color:var(--accent)}
'''
a_body=f'''<h1>中盘决策：优先选择收益更高的目标</h1><div class="layout"><div class="reading"><h2>同一批方块出现争夺时，<br><span>先比较收益，再决定动作。</span></h2><div class="point"><h3>先检查可行性</h3><p>推板能覆盖，路径和绕后空间可达。</p></div><div class="point"><h3>再比较完整循环</h3><p>把接近、推送、释放与返回都计入耗时。</p></div><div class="point"><h3>到达时间接近时换目标</h3><p>降低正面对推的时间损失。</p></div></div><div class="map">{scene()}</div></div>'''

b_css='''
:root{--stage-bg:#1c2644;--slide-bg:#1c2644;--ink:#f0ece3;--muted:#a1aaba;--accent:#c8a870}
.slide{background-image:linear-gradient(#ffffff025 1px,transparent 1px)}.b-title{position:absolute;left:95px;top:146px;width:640px;font-family:"Noto Serif CJK SC","Source Han Serif SC","SimSun",serif;font-size:86px;line-height:1.5;font-weight:500}.b-title span{color:var(--accent)}.b-lead{position:absolute;top:460px;left:102px;width:570px;font-size:33px;line-height:1.85;color:#bfc4cc}.b-bottom{position:absolute;top:677px;left:102px;width:558px;border-top:1px solid #778197;padding-top:28px}.b-bottom div{padding:17px 0;display:flex;justify-content:space-between;font-size:30px}.b-bottom strong{color:#c8a870;font-weight:500}.b-map{position:absolute;right:25px;top:140px;width:1140px;height:843px}
'''
b_body=f'''<h1 class="b-title">目标选择与<br><span>对手干扰处理</span></h1><p class="b-lead">比较完整推送的留存收益，<br>让每一次改道都有明确依据。</p><div class="b-bottom"><div><span>接触时间接近</span><strong>切换目标</strong></div><div><span>对手已经推走</span><strong>等待释放后回收</strong></div></div><div class="b-map">{scene(True)}</div>'''

tree='''<svg viewBox="0 0 850 620" role="img" aria-label="目标选择决策流程">
<g fill="none" stroke="#a8b5bd" stroke-width="2"><path d="M390 80v65M390 229v62M160 291h468M160 291v55M390 291v55M628 291v55"/></g>
<rect x="106" y="6" width="568" height="78" fill="#eff3f5"/><text x="390" y="56" text-anchor="middle" font-size="29" fill="#273a4c">路径可达，目标宽度在推板覆盖范围内</text>
<rect x="151" y="145" width="478" height="84" fill="#23445c"/><text x="390" y="198" text-anchor="middle" font-size="32" fill="#fff">比较我方与对手的预计接触时间</text>
<g font-size="27" fill="#4e6474" text-anchor="middle"><text x="160" y="385">我方明显先到</text><text x="390" y="385">双方时间接近</text><text x="648" y="385">对手已开始推送</text></g>
<g stroke="#a8b5bd" stroke-width="2"><path d="M160 411v40M390 411v40M648 411v40"/></g>
<g fill="#edf2f2"><rect x="57" y="451" width="205" height="85"/><rect x="288" y="451" width="205" height="85"/><rect x="539" y="451" width="226" height="85"/></g>
<g font-size="33" fill="#23445c" text-anchor="middle"><text x="160" y="505">继续获取</text><text x="390" y="505">换一个目标</text><text x="651" y="505">准备落点回收</text></g></svg>'''
c_css='''
:root{--stage-bg:#e9edef;--slide-bg:#fff;--ink:#263c4d;--muted:#657a87;--accent:#23445c}
h1{font-size:71px;font-weight:600}.c-sub{font-size:36px;color:#657a87;margin-top:19px}.c-grid{display:grid;grid-template-columns:745px 1fr;gap:69px;margin-top:36px}.c-map{height:679px;border-top:2px solid #23445c;padding-top:23px}.c-map svg{transform:scale(1.02);transform-origin:center}.c-logic{padding-top:33px;border-top:2px solid #23445c}.c-logic svg{height:648px}.c-conclusion{position:absolute;left:90px;bottom:65px;right:90px;border-top:1px solid #d1dbe0;padding-top:27px;font-size:31px;color:#526976}
'''
c_body=f'''<h1>中盘策略</h1><p class="c-sub">目标筛选与动态重规划</p><div class="c-grid"><div class="c-map">{scene()}</div><div class="c-logic">{tree}</div></div><p class="c-conclusion">对已安全留在我方深区的方块不重复处理，将时间留给新的有效推送。</p>'''

scale='''const stage=document.querySelector('.deck-stage');function fit(){let s=Math.min(innerWidth/1920,innerHeight/1080);stage.style.transform=`translate(${(innerWidth-1920*s)/2}px,${(innerHeight-1080*s)/2}px) scale(${s})`;}addEventListener('resize',fit);fit();'''
pages=[]
for name,css,body in [('a',a_css,a_body),('b',b_css,b_body),('c',c_css,c_body)]:
    page='<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>中盘策略</title><style>'+base+common+css+'</style></head><body><div class="deck-viewport"><main class="deck-stage"><section class="slide active">'+body+'</section></main></div><script>'+scale+'</script></body></html>'
    (DEST/f'{name}.html').write_text(page,encoding='utf-8');pages.append(page)

picker='''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>汇报视觉方向对比</title><style>*{box-sizing:border-box}body{margin:0;background:#171b1d;color:#f4f4ee;font:15px "Microsoft YaHei",sans-serif;height:100vh;overflow:hidden}.toolbar{height:78px;display:flex;justify-content:center;gap:14px;align-items:center;padding:12px}button{font:inherit;cursor:pointer;padding:12px 22px;border:1px solid #505956;border-radius:5px;color:#d6dad7;background:transparent}button.active{background:#f4f5f0;color:#23322b;border-color:#f4f5f0}iframe{position:absolute;top:78px;left:0;width:100%;height:calc(100% - 78px);border:0;visibility:hidden}iframe.active{visibility:visible}button:focus-visible{outline:2px solid #f2bd72;outline-offset:2px}@media(max-width:600px){button{padding:10px;font-size:12px}.toolbar{gap:6px}}</style></head><body><nav class="toolbar" aria-label="选择视觉方向"><button class="active" onclick="show(0)">A · 工程评审</button><button onclick="show(1)">B · 深色叙事</button><button onclick="show(2)">C · 策略推演</button></nav>'''
for i,page in enumerate(pages):
    picker+=f'<iframe title="视觉方向 {chr(65+i)}" class="{"active" if i==0 else ""}" srcdoc="{escape(page,quote=True)}"></iframe>'
picker+='''<script>function show(n){document.querySelectorAll('iframe').forEach((e,i)=>e.classList.toggle('active',i===n));document.querySelectorAll('button').forEach((e,i)=>{e.classList.toggle('active',i===n);e.setAttribute('aria-pressed',i===n);});}document.addEventListener('keydown',e=>{if(['1','2','3'].includes(e.key))show(Number(e.key)-1);});</script></body></html>'''
(ROOT/'汇报风格对比.html').write_text(picker,encoding='utf-8')
print('Created 3 strategy-slide directions and self-contained comparison page.')
