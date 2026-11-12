"""Two camera-visible blocks -> real app + HTTP -> yellow -> retreat -> next."""
from contextlib import ExitStack, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
from urllib.parse import parse_qs

import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from control import vision_approach_test as app
from control.multi_push_control import MultiPushControl
from vision.robot_vision import detect_robot


def check(preview_delay=0):
    control=MultiPushControl()
    ages=[]
    original_update=control.update
    def checked_update(robot,blocks,field,captured,now,link_at):
        ages.append(now-captured)
        return original_update(robot,blocks,field,captured,now,link_at)
    world=dict(now=0.,x=600.,y=950.,heading=-math.pi/2,frames=0,
               blocks={'a':[400.,700.],'b':[800.,700.]},pending=[],requests=[])
    config=dict(marker_id=0,marker_size_mm=50,body_length_mm=100,body_width_mm=200,
                center_offset_right_mm=0,center_offset_forward_mm=0)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def handle_request(self):
            data=parse_qs(self.rfile.read(int(self.headers.get('Content-Length',0))).decode())
            world['requests'].append((self.path,data))
            if self.path=='/status':
                world['now']+=preview_delay
            if self.path=='/step':
                assert data['gentle']==['1']
                world['pending'].append(data['direction'][0])
            self.send_response(200);self.end_headers()
            self.wfile.write(json.dumps(dict(protocol='vision-pulse-v1',pulse_ms=250,step_ms=120,
                gentle_step_ms=80,result={'/status':'ready','/stop':'stop_queued','/step':'step_queued'}[self.path])).encode())
        do_GET=handle_request
        do_POST=handle_request
    class Camera:
        def read(self):
            world['now']+=.08;world['frames']+=1
            self.captured_at=world['now']
            for command in world['pending']:
                if command in ('left','right'):
                    world['heading']+=.08 if command=='left' else -.08
                else:
                    step=10 if command=='forward' else -10
                    world['x']+=step*math.cos(world['heading'])
                    world['y']+=step*math.sin(world['heading'])
                    if command=='forward' and control.state=='PUSH':
                        # Only the block physically ahead can be contacted.
                        for point in world['blocks'].values():
                            if abs(point[0]-world['x'])<20 and 40<world['y']-point[1]<75:
                                point[1]=min(point[1],world['y']-62)
            world['pending'].clear()
            image=np.full((1200,1200,3),(200,90,20),np.uint8);image[600:]=(20,220,240)
            marker=np.full((100,100),255,np.uint8)
            marker[25:75,25:75]=cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),0,50)
            marker=cv2.warpAffine(marker,cv2.getRotationMatrix2D((49.5,49.5),
                math.degrees(world['heading']-math.pi/2),1),(100,100),borderValue=255)
            x,y=round(world['x']),round(1200-world['y'])
            image[y-50:y+50,x-50:x+50]=cv2.cvtColor(marker,cv2.COLOR_GRAY2BGR)
            for bx,by in world['blocks'].values():
                bx,by=round(bx),round(1200-by)
                cv2.rectangle(image,(bx-10,by-10),(bx+9,by+9),(0,0,230),-1)
            return True,image
        def release(self): world['released']=True

    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack, redirect_stdout(io.StringIO()):
            def key(*args):
                if preview_delay:
                    return 27 if world['frames']>=8 else 0
                return 27 if control.finished or world['frames']>2400 else 32 if control.last_plan.get('can_start') else 0
            for obj,name,value in (
                (app.sys,'argv',['multi-test','--multi-push','--host',f'http://127.0.0.1:{server.server_port}']),
                (app,'OUTPUT',Path(folder)),(app,'MultiPushControl',lambda *args:control),
                (control,'update',checked_update),
                (app,'detect_robot',lambda image:detect_robot(image,config)),
                (app,'calibration',lambda index:(Camera(),[],0,(1200,1200))),
                (app,'rectify',lambda frame,corners:frame),
                (app.time,'monotonic',lambda:world['now']),
                (app,'show_stopped_error',lambda name,error:(_ for _ in ()).throw(AssertionError(str(error)))),
                (cv2,'namedWindow',lambda *args:None),(cv2,'destroyAllWindows',lambda:None),
                (cv2,'imshow',lambda *args:None),(cv2,'getWindowProperty',lambda *args:1),
                (cv2,'setMouseCallback',lambda name,callback:callback(cv2.EVENT_LBUTTONDOWN,233,292,0,None)),
                (cv2,'waitKey',key),
            ): stack.enter_context(patch.object(obj,name,value))
            app.main()
            events=[json.loads(line) for path in Path(folder).glob('*/events.jsonl')
                    for line in path.read_text(encoding='utf-8').splitlines()]
        if preview_delay:
            assert ages and max(ages)<=.2, ages
            assert not control.finished and not control.active,control.last_plan
            assert not any(path=='/step' for path,_ in world['requests'])
            assert app.GentleLink.request_timeout==.6 and app.WifiLink.request_timeout==.18
            print('PASS: slow status query precedes NEW camera acquisition; preparation remains usable, original mode timeout unchanged')
            return
        assert control.state=='DONE' and control.completed==2,(control.state,control.last_plan,world)
        assert all(point[1]<570 for point in world['blocks'].values())
        assert world['requests'][-1][0]=='/stop' and world['released']
        steps=[data for path,data in world['requests'] if path=='/step']
        assert len({s['id'][0] for s in steps})==len(steps)
        assert {'forward','backward','left','right'}<={s['direction'][0] for s in steps}
        assert max(e.get('plan',{}).get('completed',0) for e in events)==2
        print('PASS: actual ArUco/block pixels + complete application + real HTTP: two yellow deliveries, reverse/verify/reselect, gentle actions, final STOP')
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__':
    check()
    check(preview_delay=.25)
