from copy import deepcopy
from pathlib import Path
import sys
from zipfile import ZipFile

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Emu, Pt


source = Path(sys.argv[1])
work = Path(__file__).parent
deck = Presentation(source)
cover, single, multiple, field, next_test = list(deck.slides)
blue = '20599B'
dark = '122542'
muted = '46556B'
pale = 'EFF5FC'


def xy(value):
    return Emu(round(value * 9525))


def color(value):
    return RGBColor.from_string(value)


def text(slide, value, x, y, width, height, size=23, fill=dark, bold=False):
    shape = slide.shapes.add_textbox(xy(x), xy(y), xy(width), xy(height))
    frame = shape.text_frame
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    frame.word_wrap = True
    run = frame.paragraphs[0].add_run()
    run.text = value
    run.font.name = 'Aptos'
    run.font.size = Pt(size * .75)
    run.font.bold = bold
    run.font.color.rgb = color(fill)


def rect(slide, x, y, width, height, fill):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, xy(x), xy(y), xy(width), xy(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = color(fill)
    shape.line.fill.background()


def replace(shape, value):
    runs = [run for paragraph in shape.text_frame.paragraphs for run in paragraph.runs]
    runs[0].text = value
    for run in runs[1:]:
        run.text = ''
    shape.name = value


def notes(slide, value):
    slide.notes_slide.notes_text_frame.text = value


def page(title, number, speaker_notes):
    slide = deck.slides.add_slide(single.slide_layout)
    for placeholder in list(slide.placeholders):
        placeholder._element.getparent().remove(placeholder._element)
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color('FFFFFF')
    for shape in single.shapes:
        value = shape.text if shape.has_text_frame else ''
        if value in ('How one push ends', 'GROUP 04  /  ROBOT PROJECT', '02') or (
            not value and shape.left == xy(72)
        ):
            slide.shapes._spTree.insert_element_before(deepcopy(shape._element), 'p:extLst')
            if value == 'How one push ends':
                replace(slide.shapes[-1], title)
            if value == '02':
                replace(slide.shapes[-1], number)
    notes(slide, speaker_notes)
    return slide


def point(slide, heading, body, x, y, width):
    text(slide, heading, x, y, width, 35, 25, blue, True)
    text(slide, body, x, y + 39, width, 77, 23, muted)


feedback = page('How the camera guides each move', '02',
                'The camera corrects the field view using its corners. We read the position and heading from the robot tag, send a short movement command, then measure again from a fresh frame. A stale frame or a missing tag stops the sequence.\n\n中文提示：校正画面、短步移动、新帧复测。丢码或画面过期就停车。')
for x, heading, body in [
    (72, 'Read the field', 'Calibrate the overhead image and locate the robot and blocks.'),
    (462, 'Move in short steps', 'Send a short movement command to the ESP32.'),
    (852, 'Measure again', 'Use a fresh frame before deciding whether to move or stop.'),
]:
    rect(feedback, x, 222, 356, 152, pale)
    rect(feedback, x, 222, 356, 3, blue)
    text(feedback, heading, x + 18, 245, 320, 35, 25, blue, True)
    text(feedback, body, x + 18, 289, 320, 70, 22, muted)
point(feedback, 'When the view is unreliable', 'Stop if the frame is stale or the robot tag is lost.', 72, 447, 1050)

simulation = page('What passed in simulation', '05',
                  'The integration test used simulated camera frames and an ESP32 simulator. One-block checks covered 20, 100 and 150 mm plus stall, tag loss and a rejected command. A separate run verified two deliveries.\n\n中文提示：这是软件联调结果。单块测三种位移和三种异常，多块测两次连续入区。')
for y, heading, body in [
    (191, 'One block  /  20, 100 and 150 mm', 'The controller reached each target distance and stopped.'),
    (328, 'One block  /  three interruption cases', 'A stall, missing tag or rejected command stopped the run without reporting completion.'),
    (465, 'Two blocks  /  two verified deliveries', 'The controller backed away, checked each block in the yellow zone and stopped after the second delivery.'),
]:
    rect(simulation, 72, y, 4, 87, blue)
    point(simulation, heading, body, 93, y, 1085)

for shape in field.shapes:
    if not shape.has_text_frame:
        continue
    value = shape.text
    if value == 'Simulation and field results':
        replace(shape, 'Why the 10 Nov field run did not start')
    elif value == 'Simulation: 2 deliveries':
        replace(shape, 'What the camera saw')
    elif value.startswith('The program checked both blocks'):
        replace(shape, 'The camera marked merged or oversized regions as blocks.')
    elif value == 'Field attempt: no start':
        replace(shape, 'How the controller responded')
    elif value.startswith('Oversized detection boxes blocked'):
        replace(shape, 'The controller kept the robot stopped. No deliveries were verified in that run.')
notes(field, 'In the 10 November field attempt, large or merged detections blocked the startup check. The robot remained stopped. The following footage shows robot movement in a separate field recording.\n\n中文提示：11 月 10 日那次因识别框异常未启动，下一页是另一段实机演示素材。')

demo = page('Field demonstration', '07',
            'Watch how the robot approaches the blue–yellow boundary and moves away. The clip shows two selected sequences from the field footage.\n\n中文提示：视频选了两段实机靠近分界线和转向退开的过程。')
clip = work / 'Field_Demo_17s.mp4'
movie = demo.shapes.add_movie(str(clip), xy(72), xy(156), xy(844), xy(474.75),
                             poster_frame_image=str(work / 'poster.jpg'), mime_type='video/mp4')
movie.name = 'Field demonstration video'
for link in movie._element.xpath('.//a:hlinkClick'):
    if link.get(qn('r:id')) == '':
        del link.attrib[qn('r:id')]
# Hold the video on its poster until the presenter clicks the media.
for condition in demo._element.xpath('.//p:timing//p:video/p:cMediaNode/p:cTn/p:stCondLst/p:cond'):
    condition.set('evt', 'onClick')
    condition.set('delay', '0')
    target = OxmlElement('p:tgtEl')
    shape_target = OxmlElement('p:spTgt')
    shape_target.set('spid', str(movie.shape_id))
    target.append(shape_target)
    condition.append(target)
point(demo, 'Overhead field view', 'Watch the robot approach the blue–yellow boundary, then move away.', 951, 223, 257)
text(demo, 'Click video to play · 17 s', 951, 418, 257, 58, 20, muted, True)

for slide, old, new in [(single, '02', '03'), (multiple, '03', '04'),
                        (field, '04', '06'), (next_test, '05', '08')]:
    for shape in slide.shapes:
        if shape.has_text_frame and shape.text == old:
            replace(shape, new)

slide_ids = deck.slides._sldIdLst
original = list(slide_ids)
for index in (0, 5, 1, 2, 6, 3, 7, 4):
    slide_ids.append(original[index])
output = source.parent / 'Robot_Report_04_8_Slides.pptx'
deck.save(output)

with ZipFile(output) as archive:
    assert archive.testzip() is None
    assert any(name.endswith('.mp4') and archive.read(name) == clip.read_bytes()
               for name in archive.namelist())
    assert len(Presentation(output).slides) == 8
print(output)
