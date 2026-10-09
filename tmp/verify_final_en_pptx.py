from pathlib import Path
import zipfile, json, posixpath, io, hashlib
import xml.etree.ElementTree as ET
from PIL import Image, ImageOps, ImageDraw
root=Path.cwd(); build=root/'tmp/ppt-build-en'
manifest=json.loads((build/'manifest.json').read_text(encoding='utf-8'))
ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
canvas=Image.new('RGB',(1440,4*296),'#dde1dd'); draw=ImageDraw.Draw(canvas)
checks=[]
with zipfile.ZipFile(root/'输出/机器人推块比赛_阶段汇报_英文版.pptx') as z:
 for i,m in enumerate(manifest,1):
  slide=f'ppt/slides/slide{i}.xml'; xml=ET.fromstring(z.read(slide))
  rels=ET.fromstring(z.read(f'ppt/slides/_rels/slide{i}.xml.rels'))
  targets={r.attrib['Id']:posixpath.normpath(posixpath.join('ppt/slides',r.attrib['Target'])).lstrip('/') for r in rels}
  pics=xml.findall('.//p:pic',ns); assert len(pics)==1
  pic=pics[0]; embed=pic.find('.//a:blip',ns).attrib['{'+ns['r']+'}embed']
  data=z.read(targets[embed]); assert data==Path(m['png']).read_bytes(),i
  x=pic.find('.//a:xfrm',ns); assert x.find('a:off',ns).attrib=={'x':'0','y':'0'}
  assert x.find('a:ext',ns).attrib=={'cx':'18288000','cy':'10287000'}
  notes_target=next(targets[r.attrib['Id']] for r in rels if r.attrib['Type'].endswith('/notesSlide'))
  note_xml=ET.fromstring(z.read(notes_target))
  notes='\n'.join(''.join(p.itertext()) for p in note_xml.findall('.//a:t',ns))
  assert ''.join(notes.split())==''.join(m['notes'].split()),(i,notes,m['notes'])
  im=Image.open(io.BytesIO(data)); assert im.size==(3840,2160)
  thumb=im.convert('RGB').resize((464,261),Image.Resampling.LANCZOS)
  col=(i-1)%3; row=(i-1)//3
  canvas.paste(thumb,(col*480+8,row*296+8)); draw.text((col*480+12,row*296+274),str(i),fill='#24372e')
  checks.append({'page':i,'image_exact':True,'notes_exact':True,'full_frame':True})
canvas.save(build/'final-contact-sheet.jpg',quality=92)
(build/'content-verification.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
print('PASS: 11 full-frame 4K images identical to approved HTML captures; all 11 speaker notes match.')
import re
assert all(not re.search(r'[\u4e00-\u9fff]',m['visibleText']+m['notes']) for m in manifest)
print('PASS: all slide content and notes are English.')
readme=root/'README.md'
text=readme.read_text(encoding='utf-8')
entry='### 2026-09-29\n\n- 课程要求使用英文汇报。已沿用确认的 A 风格及 11 页结构，生成 `机器人推块比赛_阶段汇报_英文版.html` 和 [英文版 PPTX](输出/机器人推块比赛_阶段汇报_英文版.pptx)。主体、图中标注和备注讲稿均改为英文；保留中文原版。英文 PPT 仍为高清图片页面，正文不能在 PowerPoint 中逐项编辑，备注可编辑。\n\n'
if '### 2026-09-29' not in text:
 text=text.replace('### 2026-09-28',entry+'### 2026-09-28',1)
 readme.write_text(text,encoding='utf-8')
