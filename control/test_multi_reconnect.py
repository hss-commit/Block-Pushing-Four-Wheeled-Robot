"""Reconnect in-place without releasing camera; require explicit start again."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch, Mock

import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from control import vision_approach_test as app


def check(idle_failure=False):
    world=dict(now=0.,frames=0,connects=0,steps=0,errors=0,released=False)
    frame=np.zeros((1200,1200,3),np.uint8)
    class Capture:
        def read(self):
            world['now']+=.1;world['frames']+=1
            self.captured_at=world['now']
            return True,frame
        def release(self): world['released']=True
    class Controller:
        def __init__(self):
            self.active=self.finished=False;self.completed=2;self.state='PREPARE'
            self.task=None
            self.last_plan=dict(command='stop',reason='READY',can_start=True)
        def rearm(self):
            self.__init__();self.completed=0
        def stop(self,reason):
            self.active=False;self.finished=True;self.state='STOPPED'
            self.last_plan=dict(command='stop',reason=reason,can_start=False)
            return self.last_plan
        def update(self,*args,**kwargs):
            if world['connects']==1:
                self.completed=2  # Simulate two previously verified deliveries.
            self.last_plan=dict(command='forward' if self.active else 'stop',reason='PREPARING',
                                can_start=not self.active and world['frames']>=3)
            return self.last_plan
        def _invalid(self,reason):
            self.last_plan=dict(command='stop',reason=reason,can_start=False)
            return self.last_plan
        def start(self): self.active=True;return True
    control=Controller()
    class Link:
        def connect(self):
            world['connects']+=1
            if not idle_failure and world['connects']==2: raise TimeoutError('still disconnected')
        def request(self,path):
            if idle_failure and not world.get('idle_failed'):
                world['idle_failed']=True
                raise TimeoutError('idle status packet lost')
            return {'result':'ready'}
        def step(self,direction):
            world['steps']+=1
            if not idle_failure:
                raise TimeoutError('lost while requesting first step')
            return {'result':'step_queued'}
        def stop(self): return {'result':'stop_queued'}
    destroyed=Mock()
    def error_window(name,error,**kwargs):
        world['errors']+=1
        assert kwargs['allow_reconnect'] and not control.active
        assert not world['released'] and not destroyed.called
        return True  # User explicitly presses R each time; second retry succeeds.
    clicks=[0]
    def install_mouse(name,callback):
        if not clicks[0]: callback(cv2.EVENT_LBUTTONDOWN,100,100,0,None)
        clicks[0]+=1
    with tempfile.TemporaryDirectory() as folder, ExitStack() as stack, redirect_stdout(io.StringIO()):
        calibration=Mock(return_value=(Capture(),[],0,(1200,1200)))
        for obj,name,value in (
            (app.sys,'argv',['test','--multi-push','--host','http://127.0.0.1']),
            (app,'OUTPUT',Path(folder)),(app,'MultiPushControl',lambda *args,**kwargs:control),
            (app,'GentleLink',lambda *args:Link()),(app,'calibration',calibration),
            (app,'rectify',lambda frame,corners:frame),
            (app,'sample_colour',lambda *args:[0,255,230]),(app,'detect_robot',lambda image,**kwargs:{}),
            (app,'detect_midline',lambda image,**kwargs:{}),
            (app,'segment',lambda *args,**kwargs:(np.zeros((1200,1200),np.uint8),[])),
            (app,'annotated',lambda image,*args,**kwargs:image.copy()),(app,'draw_robot',lambda *args,**kwargs:None),
            (app,'show_stopped_error',error_window),(app.time,'monotonic',lambda:world['now']),
            (cv2,'namedWindow',lambda *args:None),(cv2,'setMouseCallback',install_mouse),
            (cv2,'imshow',lambda *args:None),(cv2,'getWindowProperty',lambda *args:1),
            (cv2,'destroyAllWindows',destroyed),
            (cv2,'waitKey',lambda *args:32 if world['frames']==1 else
                27 if (world['steps'] if idle_failure else world['frames']>=5) else 0),
        ): stack.enter_context(patch.object(obj,name,value))
        app.main()
        events=[json.loads(line) for path in Path(folder).glob('*/events.jsonl')
                for line in path.read_text(encoding='utf-8').splitlines()]
        calibration.assert_called_once()
    assert sum(e['event']=='start_requested' for e in events)==1
    assert any(e['event']=='start_accepted' for e in events), 'Early SPACE request was discarded'
    if idle_failure:
        assert world['errors']==0 and world['connects']==1 and world['steps']==1
        assert any(e['event']=='idle_link_wait' for e in events)
        assert any(e['event']=='idle_link_recovered' for e in events)
        print('PASS: one early SPACE survives idle status loss, auto recheck stays in same window, starts only after ready')
        return
    assert world['errors']==2 and world['connects']==3
    assert world['steps']==1, 'Motion automatically resumed after reconnect'
    assert control.completed==2 and not control.active
    assert world['released'] and destroyed.call_count==1, 'Cleanup happened before user exit'
    assert any(e['event']=='reconnected' and e['requires_space'] for e in events)
    with patch.object(cv2,'namedWindow'),patch.object(cv2,'imshow'), \
         patch.object(cv2,'getWindowProperty',return_value=1), \
         patch.object(cv2,'waitKey',side_effect=[0,ord('r')]):
        assert app.show_stopped_error('test',TimeoutError('test'),allow_reconnect=True) is True
    print('PASS: in-window R retry, repeated reconnect failure, camera/calibration retained, progress retained, no automatic motion, cleanup only on explicit exit')


if __name__=='__main__':
    check()
    check(idle_failure=True)
