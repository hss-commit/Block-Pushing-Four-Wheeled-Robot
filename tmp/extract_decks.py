from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import re

root = Path(r'C:\1')
out = Path('tmp/deck_text.txt')
lines = []
for path in sorted(root.glob('*.pptx'), key=lambda p: p.name.lower()):
    lines.append(f'\n===== {path.name} =====')
    with ZipFile(path) as z:
        slides = sorted((n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)), key=lambda n: int(re.search(r'(\d+)\.xml', n).group(1)))
        lines.append(f'SLIDES: {len(slides)}')
        for slide in slides:
            xml = ET.fromstring(z.read(slide))
            paras = []
            for p in xml.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}p'):
                s = ''.join(t.text or '' for t in p.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}t')).strip()
                if s:
                    paras.append(s)
            n = int(re.search(r'(\d+)\.xml', slide).group(1))
            lines.append(f'\n-- Slide {n} --')
            lines.extend(paras)
out.write_text('\n'.join(lines), encoding='utf-8')
print(out, 'lines', len(lines), 'chars', sum(map(len, lines)))
