from pathlib import Path
import json,re
from pptx import Presentation
from pptx.util import Inches,Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.xmlchemy import OxmlElement

ROOT=Path(__file__).resolve().parents[1]
data=json.loads((ROOT/'tmp/report-03/geometry.json').read_text(encoding='utf-8'))
prs=Presentation();prs.slide_width=Inches(16);prs.slide_height=Inches(9)
def coord(px):return Inches(px/100)
def color(css):
    if css.startswith('#'):return RGBColor.from_string(css[1:])
    return RGBColor(*map(int,re.findall(r'\d+',css)[:3]))
for i,page in enumerate(data):
    slide=prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid();slide.background.fill.fore_color.rgb=color('#f5f4ee')
    for j,r in enumerate(page['rules']):
        shape=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,coord(r['x']),coord(r['y']),coord(r['w']),coord(r['h']))
        shape.name=f'Separator {j+1}';shape.fill.solid();shape.fill.fore_color.rgb=color('#3f7159' if r['cover'] else '#cdd2c8');shape.line.fill.background()
    for j,item in enumerate(page['items']):
        shape=slide.shapes.add_textbox(coord(item['x']),coord(item['y']),coord(item['w']+3),coord(item['h']+16))
        shape.name=f'Editable text {j+1}'
        tf=shape.text_frame;tf.clear();tf.word_wrap=True
        tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
        for k,line in enumerate(item['text'].split('\n')):
            p=tf.paragraphs[0] if k==0 else tf.add_paragraph()
            p.text=line;p.font.name='Segoe UI';p.font.size=Pt(item['size']*.72);p.font.bold=item['bold'];p.font.color.rgb=color(item['color'])
            p.line_spacing=Pt(item['line']*.72);p.space_before=Pt(0);p.space_after=Pt(0)
            for run in p.runs:
                east=OxmlElement('a:ea');east.set('typeface','Microsoft YaHei');run._r.get_or_add_rPr().append(east)
                if item['kicker']:run._r.get_or_add_rPr().set('spc','144')
    slide.notes_slide.notes_text_frame.text=page['notes']
out=ROOT/'输出/机器人推块比赛_第三次汇报_成果与计划_可编辑版.pptx'
prs.save(out)
check=Presentation(out)
assert len(check.slides)==11
assert all(len(s.shapes)==0 for s in list(check.slides)[8:])
for s,p in zip(check.slides,data):
    assert s.notes_slide.notes_text_frame.text==p['notes']
    assert [x.text for x in s.shapes if x.has_text_frame and x.text]==[x['text'] for x in p['items']]
print(f'Verified 11 slides, native editable text, 3 empty slides, and matching Chinese notes.\n{out}')
