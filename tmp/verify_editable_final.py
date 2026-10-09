from pathlib import Path
import zipfile,xml.etree.ElementTree as E,json,re,hashlib
D=Path('tmp/editable-en');data=json.loads((D/'geometry.json').read_text(encoding='utf-8'));target=Path('输出/机器人推块比赛_阶段汇报_英文可编辑版.pptx')
N={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
norm=lambda s:re.sub(r'\s+','',s)
counts=[]
with zipfile.ZipFile(target)as z:
 for i,original in enumerate(data,1):
  r=E.fromstring(z.read(f'ppt/slides/slide{i}.xml'));texts=''.join(t.text or '' for t in r.findall('.//a:t',N));expected=[]
  for it in original['items']:
   if it['type']=='text':expected.append(''.join(x['text']for l in it['lines']for x in l['runs']))
   elif it['type']=='svgtext':expected.append(it['text'])
  for table in original['tables']:
   expected.extend(c['value']for row in table['rows']for c in row['cells'])
  assert all(norm(t)in norm(texts)for t in expected),i
  assert not r.findall('.//p:pic',N),i
  assert len(r.findall('.//a:tbl',N))==(1 if i in [4,5,10]else 0),i
  notes=E.fromstring(z.read(f'ppt/notesSlides/notesSlide{i}.xml'))
  nt=''.join(t.text or ''for t in notes.findall('.//a:t',N));assert norm(nt)==norm(original['notes']),i
  counts.append({'slide':i,'native_shapes':len(r.findall('.//p:sp',N)),'tables':len(r.findall('.//a:tbl',N)),'pictures':0,'content_match':True,'notes_match':True})
with zipfile.ZipFile(D/'edit-test.pptx')as z:
 assert b'EDIT TEST: Robot Competition'in z.read('ppt/slides/slide1.xml')
 assert b'EDIT TEST: table cell'in z.read('ppt/slides/slide4.xml')
assert target.read_bytes()==(D/'candidate-adjusted.pptx').read_bytes()
(D/'content-verification.json').write_text(json.dumps(counts,indent=2),encoding='utf-8')
print(json.dumps({'slide_count':11,'native_shapes':sum(c['native_shapes']for c in counts),'native_tables':3,'pictures':0,'content_and_notes':'PASS','round_trip_edit_test':'PASS','bytes':target.stat().st_size}))
p=Path('README.md');text=p.read_text(encoding='utf-8');entry='- 用户明确要求英文 PPT 必须可编辑。已重建 [英文可编辑版 PPTX](输出/机器人推块比赛_阶段汇报_英文可编辑版.pptx)，保留 11 页和英文备注讲稿；正文及图中标注为原生文本框，三张表格为原生表格，场地、方块和路线为原生形状/自由曲线，无整页图片。已验证重新导入后能修改标题与表格单元格，并核对文字、讲稿与文件结构。此文件为当前应交付的版本，此前图片版仅供版式参考。\n\n'
if entry not in text:text=text.replace('### 2026-09-29\n\n','### 2026-09-29\n\n'+entry,1);p.write_text(text,encoding='utf-8')
