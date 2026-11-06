"""Measured single-block movement and stop checks. No hardware or motor requests."""
import math
import sys
import io
import tempfile
import json
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from control.single_push_control import SinglePushControl
from strategy.planner import Block
from vision.robot_vision import detect_robot, exclude_robot_regions
from vision.photo_vision import detect_midline, segment
from control import vision_approach_test as runner

FIELD={'valid':True}


def calibration_feedback_check():
    frame=np.zeros((800,800,3),np.uint8)
    class Capture:
        released=False
        def read(self): return True,frame.copy()
        def set(self,*args): pass
        def release(self): self.released=True
    capture=Capture()
    drawn=[]
    with ExitStack() as stack, redirect_stdout(io.StringIO()):
        for obj,name,value in (
            (cv2,'VideoCapture',lambda *args:capture),
            (cv2,'putText',lambda image,text,*args:drawn.append(text)),
            (cv2,'imshow',lambda *args:None),
            (cv2,'getWindowProperty',lambda *args:1),
            (cv2,'destroyAllWindows',lambda:None),
            (runner,'select_corners',lambda image:(image,[])),
            (runner,'detect_midline',lambda image:{'valid':False,'reason':'Boundary is short or inconsistent'}),
        ): stack.enter_context(patch.object(obj,name,value))
        stack.enter_context(patch.object(cv2,'waitKey',side_effect=[13,27]))
        assert runner.calibration(1) is None
    assert capture.released
    assert any('CALIBRATION FAILED: Boundary is short or inconsistent' in text for text in drawn),drawn
    assert any('FOUR real field corners' in text for text in drawn)
    print('PASS: rejected field calibration displays its reason and retry instructions, and releases camera on exit')
    shown=[]
    with patch.object(cv2,'namedWindow'), \
         patch.object(cv2,'imshow',side_effect=lambda *args:shown.append(True)), \
         patch.object(cv2,'getWindowProperty',return_value=1), \
         patch.object(cv2,'waitKey',side_effect=[0,0,27]):
        runner.show_stopped_error('error-test',TimeoutError('connection timeout'))
    assert len(shown)==3,'Error window closed without waiting for operator'
    print('PASS: error window stays visible until Esc or explicit window close')


def robot(y=900,x=600,heading=-math.pi/2):
    scale=1199/1200
    return {'detected':True,'heading_valid':True,'center_px':[x*scale,(1200-y)*scale],
            'heading_rad':heading,'body_polygon_px':[[a*scale,(1200-b)*scale] for a,b in
                [(x-40,y-60),(x+40,y-60),(x+40,y+60),(x-40,y+60)]]}


def tick(control,t,y=900,by=780,x=600,bx=600,blocks=None,**kwargs):
    return control.update(kwargs.pop('robot',robot(y,x)),
        (Block('single-0',bx,by),) if blocks is None else blocks,
        kwargs.pop('field',FIELD),kwargs.pop('captured',t),t,kwargs.pop('link',t))


def prepared():
    control=SinglePushControl()
    for i in range(31):
        plan=tick(control,i/10)
        if i<30:
            assert plan['command']=='stop' and not control.active
    assert control.active and plan['command']=='forward',plan
    return control


def runner_check(fault=None):
    """Actual GUI loop + pixel perception + controller + fake timed car, no SPACE."""
    world={'now':0.,'robot_y':950.,'block_y':750.,'frames':0,'commands':[]}
    controller=SinglePushControl()

    class Capture:
        def read(self):
            world['now']+=.1;world['frames']+=1
            if fault=='camera' and world['now']>=4:
                return False,None
            image=np.full((1200,1200,3),(200,90,20),np.uint8);image[600:]=(20,220,240)
            cy=1200-world['robot_y']
            for x,y in ((490,cy-60),(710,cy-60),(480,cy+60),(720,cy+60)):
                cv2.circle(image,(x,round(y)),24,(0,0,230),-1)
                cv2.circle(image,(x,round(y)),13,(15,15,15),-1)
            by=round(1200-world['block_y'])
            cv2.rectangle(image,(590,by-10),(609,by+9),(0,0,230),-1)
            return True,image
        def release(self):
            world['released']=True

    class Link:
        def connect(self):
            return self.stop()
        def request(self,path):
            assert path=='/status'
            if fault=='network' and world['now']>=4:
                raise TimeoutError('simulated Wi-Fi timeout')
            return {'result':'ready'}
        def step(self,direction):
            assert direction=='forward','Unverified turning command emitted'
            world['commands'].append(direction)
            world['robot_y']-=10
            world['block_y']=min(world['block_y'],world['robot_y']-95)
            return {'result':'step_queued'}
        def stop(self):
            world['commands'].append('stop')
            return {'result':'stop_queued'}

    def install_mouse(name,callback):
        callback(cv2.EVENT_LBUTTONDOWN,350,262,0,None)

    def stopped_error_window(name,error):
        assert fault is not None,'Unexpected application error: '+str(error)
        assert not controller.active and controller.finished
        assert world['commands'][-1]=='stop'
        world['error_window']=type(error).__name__

    with tempfile.TemporaryDirectory() as folder, ExitStack() as stack, redirect_stdout(io.StringIO()):
        for obj,name,value in (
            (runner,'OUTPUT',Path(folder)),
            (runner.sys,'argv',['vision_approach_test.py','--single-push','--host','http://127.0.0.1']),
            (runner,'SinglePushControl',lambda *args: controller),
            (runner,'DirectionLink',lambda *args: Link()),
            (runner,'calibration',lambda index:(Capture(),[],0,(1200,1200))),
            (runner,'rectify',lambda frame,corners: frame),
            (runner,'show_stopped_error',stopped_error_window),
            (runner.time,'monotonic',lambda:world['now']),
            (cv2,'namedWindow',lambda *args:None),
            (cv2,'setMouseCallback',install_mouse),
            (cv2,'imshow',lambda *args:None),
            (cv2,'getWindowProperty',lambda *args:1),
            (cv2,'waitKey',lambda *args:27 if controller.finished or world['frames']>250 else 0),
            (cv2,'destroyAllWindows',lambda:None),
        ):
            stack.enter_context(patch.object(obj,name,value))
        returned=runner.main()
        errors=[json.loads(line) for f in Path(folder).glob('*/events.jsonl') for line in
                f.read_text(encoding='utf-8').splitlines() if json.loads(line)['event']=='error']
    if fault:
        assert returned is False
        expected='TimeoutError' if fault=='network' else 'ValueError'
        assert controller.state=='STOPPED' and world['error_window']==expected
        assert len(errors)==1 and errors[0]['error_type']==expected
    else:
        assert controller.state=='DONE',controller.last_plan
        assert world['block_y']<=650 and 'forward' in world['commands'],world
    assert world['commands'][-1]=='stop' and world['released']
    print('PASS: '+('runtime '+fault+' failure stops/latches, records cause and retains an error window' if fault else
          'actual runner calibration/colour/camera frames -> automatic short steps -> observed block movement -> STOP, without SPACE'))


def main():
    calibration_feedback_check()
    control=prepared()
    for t,y in [(3.1,880),(3.2,860),(3.3,850)]:
        assert tick(control,t,y)['command']=='forward'
    for i in range(1,11):
        plan=tick(control,3.3+i/10,850-10*i,780-10*i)
        assert plan['command']==('stop' if i==10 else 'forward'),plan
    assert control.state=='DONE' and control.finished and not control.active
    assert plan['block_progress_mm']>=100
    for i in range(1,10):
        assert tick(control,4.3+i/10,750,680)['command']=='stop'
    assert not control.start()
    control.rearm()
    assert not control.finished and not control.active
    print('PASS: automatic countdown -> approach -> observed 100mm push -> stop; no SPACE, no automatic second push')

    for bad in (
        {'robot':{'detected':False}}, {'blocks':()},
        {'blocks':(Block('a',600,780),Block('b',700,780))},
        {'field':{'valid':False}}, {'captured':2.}, {'link':2.},
        {'x':650}, {'bx':650}, {'by':740}, {'y':800},
        {'robot':robot(heading=-math.pi/2+.3)},
    ):
        control=prepared()
        plan=tick(control,3.1,**bad)
        assert plan['command']=='stop' and control.finished, (bad,plan)
    control=prepared()
    assert 'GAP' in tick(control,4.)['reason']
    control=prepared()
    control.stop('MANUAL STOP')
    assert tick(control,3.1)['reason']=='MANUAL STOP'
    print('PASS: lost/multiple target, stale vision/link, pose/block jump, heading/lateral drift, frame gap and manual stop latch')

    control=SinglePushControl()
    for i in range(41):
        plan=tick(control,i/10,bx=650)
        assert plan['command']=='stop'
    assert not control.active
    # A countdown interrupted by a lost target must start over.
    control=SinglePushControl()
    for i in range(21): tick(control,i/10)
    tick(control,2.1,blocks=())
    for i in range(22,42):
        assert tick(control,i/10)['command']=='stop'
    # One later valid frame cannot stand in for continuously observed countdown.
    control=SinglePushControl();tick(control,0)
    assert tick(control,10)['command']=='stop' and not control.active
    # Reject a path whose final swept footprint would leave the calibrated field.
    control=SinglePushControl()
    assert tick(control,0,y=160,by=80)['command']=='stop'
    assert not control.active
    print('PASS: alignment/field-edge guards and continuous stable observation before auto start')

    control=prepared()
    for i in range(1,32):
        plan=tick(control,3+i/10)
    assert 'NO VISUAL PROGRESS' in plan['reason']
    control=prepared()
    tick(control,3.1,y=850)
    for i in range(1,22):
        plan=tick(control,3.1+i/10,y=850)
    assert 'BLOCK DID NOT MOVE' in plan['reason']
    control=prepared()
    # A hand moving the block while the car remains far away cannot count as a push.
    assert 'WITHOUT' in tick(control,3.1,by=760)['reason']
    print('PASS: no-progress, stalled contact and external block movement cannot fabricate success')

    # Real synthetic camera pixels through wheel/colour perception and the controller.
    image=np.full((1200,1200,3),(200,90,20),np.uint8);image[600:]=(20,220,240)
    for x,y in ((490,190),(710,190),(480,310),(720,310)):
        cv2.circle(image,(x,y),24,(0,0,230),-1);cv2.circle(image,(x,y),13,(15,15,15),-1)
    cv2.rectangle(image,(590,440),(609,459),(0,0,230),-1)
    detected=detect_robot(image);field=detect_midline(image)
    _,regions=segment(image,[0,255,230],h_tol=18,min_area=90,field=field)
    regions=exclude_robot_regions(regions,detected)
    assert len(regions)==1 and detected['heading_valid'],(regions,detected)
    control=SinglePushControl()
    blocks=(Block('single-0',regions[0]['x_mm'],regions[0]['y_mm']),)
    for i in range(31): plan=control.update(detected,blocks,field,i/10,i/10,i/10)
    assert plan['command']=='forward' and control.active,plan
    print('PASS: actual OpenCV pixels -> wheel/block detection -> stable automatic forward command')
    runner_check()
    runner_check('network')
    runner_check('camera')


if __name__=='__main__':
    main()
