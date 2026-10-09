from pathlib import Path
import zipfile,json,xml.etree.ElementTree as E
D=Path('tmp/editable-en');data=json.loads((D/'geometry.json').read_text(encoding='utf-8'))
N={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
for k,v in N.items():E.register_namespace(k,v)
def spacing(tx,height):
 for pp in tx.findall('a:p/a:pPr',N):
  ls=pp.find('a:lnSpc',N)
  if ls is None:ls=E.Element('{'+N['a']+'}lnSpc');pp.insert(0,ls)
  ls.clear();E.SubElement(ls,'{'+N['a']+'}spcPts',{'val':str(round(height*75))})
with zipfile.ZipFile(D/'candidate.pptx')as src,zipfile.ZipFile(D/'candidate-adjusted.pptx','w',zipfile.ZIP_DEFLATED)as dst:
 for item in src.infolist():
  b=src.read(item.filename)
  if item.filename.startswith('ppt/slides/slide')and item.filename.endswith('.xml'):
   i=int(Path(item.filename).stem[5:])-1;r=E.fromstring(b)
   shapes=[s for s in r.findall('.//p:sp',N)if s.find('p:txBody',N)is not None]
   texts=[it for it in data[i]['items']if it['type']in ['text','svgtext']]
   assert len(shapes)==len(texts)
   for s,it in zip(shapes,texts):
    height=it['style']['fontSize']*1.2 if it['type']=='svgtext' else it['style']['lineHeight']
    spacing(s.find('p:txBody',N),height)
   for table,original in zip(r.findall('.//a:tbl',N),data[i]['tables']):
    for row,rr in zip(table.findall('a:tr',N),original['rows']):
     for c,cc in zip(row.findall('a:tc',N),rr['cells']):spacing(c.find('a:txBody',N),cc['style']['lineHeight'])
   for lock in r.findall('.//a:spLocks',N):lock.attrib.pop('noGrp',None)
   b=E.tostring(r,encoding='utf-8',xml_declaration=True)
  dst.writestr(item,b)
print('Adjusted native paragraph spacing; unlocked grouping.')
