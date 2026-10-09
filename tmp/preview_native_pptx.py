from pathlib import Path
import zipfile,xml.etree.ElementTree as E,html
D=Path('tmp/editable-en');N={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
def px(v):return float(v)/9525
def color(el,default='none'):
 if el is None:return default
 f=el.find('a:solidFill/a:srgbClr',N)
 if f is None:return default
 a=f.find('a:alpha',N);alpha=float(a.get('val'))/100000 if a is not None else 1
 c=f.get('val');return '#'+c if alpha==1 else f'rgba({int(c[:2],16)},{int(c[2:4],16)},{int(c[4:],16)},{alpha})'
def getbox(x):
 off=x.find('a:off',N);ext=x.find('a:ext',N)
 return px(off.get('x')),px(off.get('y')),px(ext.get('cx')),px(ext.get('cy'))
def runstyle(r,default):
 p=r.find('a:rPr',N)
 if p is None:p=default
 size=float(p.get('sz','2400'))/75 if p is not None else 32
 bold=p.get('b','0')=='1' if p is not None else False
 return size,bold,color(p,'#28332f')
def lineheight(p,size):
 pts=p.find('a:pPr/a:lnSpc/a:spcPts',N);pct=p.find('a:pPr/a:lnSpc/a:spcPct',N)
 return float(pts.get('val'))/75 if pts is not None else size*float(pct.get('val'))/100000 if pct is not None else size*1.2
def text_svg(body,x,y):
 out=[]
 for p in body.findall('a:p',N):
  default=p.find('a:pPr/a:defRPr',N);runs=p.findall('a:r',N)
  if not runs:continue
  size=runstyle(runs[0],default)[0]; spans=[]
  for r in runs:
   fs,b,c=runstyle(r,default);t=r.find('a:t',N)
   spans.append(f'<tspan fill="{c}" font-size="{fs}" font-weight="{700 if b else 400}">{html.escape(t.text or "")}</tspan>')
  out.append(f'<text x="{x}" y="{y+size*.905}" font-family="Arial" xml:space="preserve">'+''.join(spans)+'</text>')
  y+=lineheight(p,size)
 return ''.join(out)
with zipfile.ZipFile(D/'candidate-adjusted.pptx')as z:
 for i in range(1,12):
  r=E.fromstring(z.read(f'ppt/slides/slide{i}.xml'));parts=[]
  for element in r.find('p:cSld/p:spTree',N):
   if element.tag.endswith('}sp'):
    props=element.find('p:spPr',N);xf=props.find('a:xfrm',N)
    if xf is None:continue
    x,y,w,h=getbox(xf);fill=color(props);ln=props.find('a:ln',N);stroke=color(ln);sw=px(ln.get('w','0'))if ln is not None else 0
    dash=' stroke-dasharray="8 8"'if ln is not None and ln.find('a:prstDash',N)is not None and ln.find('a:prstDash',N).get('val')!='solid' else ''
    attrs=f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash}'
    preset=props.find('a:prstGeom',N);cust=props.find('a:custGeom',N)
    if preset is not None:
     if preset.get('prst')=='ellipse':parts.append(f'<ellipse cx="{x+w/2}" cy="{y+h/2}" rx="{w/2}" ry="{h/2}" {attrs}/>')
     else:parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" {attrs}/>')
    if cust is not None:
     for p in cust.findall('a:pathLst/a:path',N):
      pw=float(p.get('w'));ph=float(p.get('h'));commands=[]
      for cmd in p:
       name=cmd.tag.split('}')[-1];pt=cmd.find('a:pt',N)
       if name=='close':commands.append('Z')
       elif pt is not None:commands.append(('M' if name=='moveTo' else 'L')+f'{x+float(pt.get("x"))/pw*w},{y+float(pt.get("y"))/ph*h}')
      parts.append(f'<path d="{" ".join(commands)}" {attrs} stroke-linejoin="round"/>')
    tx=element.find('p:txBody',N)
    if tx is not None:parts.append(text_svg(tx,x,y))
   elif element.tag.endswith('}graphicFrame'):
    tb=element.find('.//a:tbl',N)
    if tb is None:continue
    x,y,w,h=getbox(element.find('p:xfrm',N));widths=[px(c.get('w'))for c in tb.findall('a:tblGrid/a:gridCol',N)];rows=[]
    for row in tb.findall('a:tr',N):
     cells=[];rh=px(row.get('h'))
     for cell,cw in zip(row.findall('a:tc',N),widths):
      pr=cell.find('a:tcPr',N);tx=cell.find('a:txBody',N);paras=[]
      for p in tx.findall('a:p',N):
       runs=p.findall('a:r',N);default=p.find('a:pPr/a:defRPr',N);spans=[]
       if not runs:continue
       fs=runstyle(runs[0],default)[0]
       for rr in runs:
        sz,b,c=runstyle(rr,default);t=rr.find('a:t',N)
        spans.append(f'<span style="font-size:{sz}px;font-weight:{700 if b else 400};color:{c}">{html.escape(t.text or "")}</span>')
       paras.append(f'<div style="line-height:{lineheight(p,fs)}px">{"".join(spans)}</div>')
      ml=px(pr.get('marL','0'));mr=px(pr.get('marR','0'))
      cells.append(f'<div class="cell" style="width:{cw}px;height:{rh}px;padding:0 {mr}px 0 {ml}px;background:{color(pr,"transparent")}">{"".join(paras)}</div>')
     rows.append('<div style="display:flex">'+''.join(cells)+'</div>')
    parts.append(f'<foreignObject x="{x}" y="{y}" width="{w+1}" height="{h+1}"><div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial">'+''.join(rows)+'</div></foreignObject>')
  out='<html><head><meta charset="utf-8"><style>html,body{margin:0;background:#f7f8f3}.cell{box-sizing:border-box;display:flex;flex-direction:column;justify-content:center;flex-shrink:0}svg{display:block}</style></head><body><svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080"><rect width="1920" height="1080" fill="#f7f8f3"/>'+''.join(parts)+'</svg></body></html>'
  (D/f'preview-{i:02}.html').write_text(out,encoding='utf-8')
print('Generated previews from native PPTX XML for all 11 pages.')

