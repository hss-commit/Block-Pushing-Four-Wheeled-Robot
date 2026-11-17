from pathlib import Path
from copy import deepcopy
from zipfile import ZipFile, ZIP_DEFLATED
import posixpath as pp
from lxml import etree as E
work=Path('tmp/report-04')
ref=ZipFile('../机械设计/output/Pressure-Cone-Method-v2.pptx')
draft=ZipFile(work/'authored.pptx')
P='http://schemas.openxmlformats.org/presentationml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG='http://schemas.openxmlformats.org/package/2006/relationships'
def tag(ns,n):return f'{{{ns}}}{n}'
def read(z,n):return E.fromstring(z.read(n))
def ser(n):return E.tostring(n,encoding='UTF-8',xml_declaration=True,standalone=True)
def relpart(n):return pp.join(pp.dirname(n),'_rels',pp.basename(n)+'.rels')
def pages(n):return n.startswith(('/ppt/slides/','/ppt/notesSlides/'))
files={n:ref.read(n) for n in ref.namelist() if not pages('/'+n) and not n.startswith('docProps/thumbnail')}
ct=read(ref,'[Content_Types].xml')
for e in list(ct):
 if pages(e.get('PartName','')):ct.remove(e)
for e in read(draft,'[Content_Types].xml'):
 if pages(e.get('PartName','')):ct.append(deepcopy(e))
pres=read(ref,'ppt/presentation.xml')
ids=pres.find(tag(P,'sldIdLst'))
for e in list(ids):ids.remove(e)
pr=read(ref,'ppt/_rels/presentation.xml.rels')
for e in list(pr):
 if e.get('Type').endswith('/slide'):pr.remove(e)
for j in range(1,10):
 sid=f'rId{300+j}'
 E.SubElement(ids,tag(P,'sldId'),id=str(255+j),attrib={tag(R,'id'):sid})
 E.SubElement(pr,tag(PKG,'Relationship'),Id=sid,Type=R+'/slide',Target=f'slides/slide{j}.xml')
 for n in [f'ppt/slides/slide{j}.xml',f'ppt/notesSlides/notesSlide{j}.xml']:
  part=read(draft,n)
  if '/slides/' in n:
   for b in part.iter(tag(A,'bodyPr')):
    if b.getparent().tag==tag(P,'txBody'):
     for k in ['lIns','tIns','rIns','bIns']:b.set(k,'0')
  files[n]=ser(part)
  rel=read(draft,relpart(n))
  for e in rel:
   target=e.get('Target')
   if e.get('TargetMode')=='External':continue
   kind=e.get('Type').rsplit('/',1)[-1]
   absolute=target.lstrip('/') if target.startswith('/') else pp.normpath(pp.join(pp.dirname(n),target))
   if kind=='slideLayout':absolute='ppt/slideLayouts/slideLayout'+('31' if j==1 else '47')+'.xml'
   if kind=='image':
    dst='ppt/media/report04-'+pp.basename(absolute)
    files[dst]=draft.read(absolute)
    absolute=dst
   e.set('Target',pp.relpath(absolute,pp.dirname(n)))
  files[relpart(n)]=ser(rel)
app=read(ref,'docProps/app.xml')
for e in app:
 if E.QName(e).localname in ['Slides','Notes']:e.text='9'
core=read(ref,'docProps/core.xml')
for e in core:
 if E.QName(e).localname in ('title','subject','description','keywords'):
  e.text={'title':'The Block-Pushing Robot','subject':'Group 04 project progress'}.get(E.QName(e).localname,'')
rels=read(ref,'_rels/.rels')
for e in list(rels):
 if 'thumbnail' in e.get('Type'):rels.remove(e)
files.update({'docProps/core.xml':ser(core),'docProps/app.xml':ser(app),'[Content_Types].xml':ser(ct),'ppt/presentation.xml':ser(pres),'ppt/_rels/presentation.xml.rels':ser(pr),'_rels/.rels':ser(rels)})
with ZipFile(work/'candidate.pptx','w',ZIP_DEFLATED) as z:
 for n,v in files.items():z.writestr(n,v)

