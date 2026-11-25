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
from control import launcher
from control.multi_push_control import MultiPushControl
from vision.robot_vision import detect_robot


def check(preview_delay=0, *, in_process=False, local=False, turn_profiles=False, turn_breakaway=False,
          occlude_contact=False, marker_dropout=False, continuous=False, rolling_marker_loss=False,
          live_edge_stop=False, rolling_lease_loss=False, midfield=False):
    control=MultiPushControl(field_guided=local,midfield=midfield)
    ages=[]
    original_update=control.update
    def checked_update(robot,blocks,field,captured,now,link_at,**kwargs):
        ages.append(now-captured)
        assert captured>=world['observe_after'], (captured,world['observe_after'])
        if midfield:
            assert not kwargs.get('continuous_drive'), 'Menu 8 must not request rolling motion'
        return original_update(robot,blocks,field,captured,now,link_at,**kwargs)
    world=dict(now=0.,x=600.,y=950.,heading=-math.pi/2,frames=0,
               blocks={'a':[400.,700.],'b':[800.,700.]},pending=[],requests=[],observe_after=-math.inf)
    world['turn_unlocked']=not turn_breakaway
    world['occluded_frames']=0
    world['occluded_blocks']=set()
    world['marker_dropout_frames']=0
    drive_wheels=None
    drive_expiry=-math.inf
    drive_segments=0
    handoffs=[]
    drive_plans=[]
    last_drive_plan=None
    renewals=0
    rolling_stop_at=None
    rolling_marker_missing=False
    if occlude_contact:
        world['blocks']={'a':[600.,700.],'b':[400.,700.]}
    if midfield:
        world['blocks']={'a':[410.,715.],'b':[790.,705.]}
        world['heading']=-math.pi/2+.45
        if marker_dropout:
            world.update(x=580.,y=820.,heading=math.radians(155))
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
                gentle=data.get('gentle')==['1']
                assert gentle or (local and (data['direction'][0] in ('forward','backward') or
                                              control.last_plan.get('normal_turn_step')))
                if turn_breakaway and data['direction'][0] in ('left','right'):
                    world['turn_unlocked']=not gentle
                world['pending'].append(data['direction'][0])
                duration={'medium':.06,'fine':.035}.get(data.get('turn_profile',[''])[0],.08 if gentle else .12)
                world['observe_after']=world['now']+duration+.02
            if self.path=='/stop':
                world['observe_after']=-math.inf
            self.send_response(200);self.end_headers()
            self.wfile.write(json.dumps(dict(protocol='vision-pulse-v1',pulse_ms=250,step_ms=120,
                gentle_step_ms=80,result={'/status':'ready','/stop':'stop_queued','/step':'step_queued'}[self.path],
                **({'medium_turn_ms':60,'fine_turn_ms':35} if turn_profiles else {}))).encode())
        do_GET=handle_request
        do_POST=handle_request
    class Camera:
        def read(self):
            nonlocal rolling_marker_missing
            world['now']+=.08;world['frames']+=1
            if rolling_lease_loss and drive_wheels:
                world['now']+=.36
            self.captured_at=world['now']
            if drive_wheels and self.captured_at<drive_expiry:
                left,right=drive_wheels
                world['heading']+=(right-left)*.08/130
                world['pending'].append('forward')
            for command in world['pending']:
                if command in ('left','right'):
                    if world['turn_unlocked']:
                        world['heading']+=.08 if command=='left' else -.08
                else:
                    step=10 if command=='forward' else -10
                    if command=='forward' and drive_wheels and self.captured_at<drive_expiry:
                        step=.04*sum(drive_wheels)
                        if continuous and len(drive_plans)==1 and not rolling_marker_loss:
                            # A faster first segment reaches the visual endpoint before its timer.
                            step*=1.55
                    world['x']+=step*math.cos(world['heading'])
                    world['y']+=step*math.sin(world['heading'])
                    if command=='forward' and control.state=='PUSH':
                        # Only the block physically ahead can be contacted.
                        for point in world['blocks'].values():
                            if local:
                                ox,oy=point[0]-world['x'],point[1]-world['y']
                                ahead=ox*math.cos(world['heading'])+oy*math.sin(world['heading'])
                                lateral=-ox*math.sin(world['heading'])+oy*math.cos(world['heading'])
                                if 30<ahead<75 and abs(lateral)<90:
                                    point[0]+=step*math.cos(world['heading'])
                                    point[1]+=step*math.sin(world['heading'])
                                continue
                            if abs(point[0]-world['x'])<20 and 40<world['y']-point[1]<75:
                                point[1]=min(point[1],world['y']-62)
            world['pending'].clear()
            if live_edge_stop and any(path=='/step' for path,_ in world['requests']):
                world.update(x=600.,y=85.,heading=-math.pi/2)
            image=np.full((1200,1200,3),(200,90,20),np.uint8);image[600:]=(20,220,240)
            marker=np.full((100,100),255,np.uint8)
            marker[25:75,25:75]=cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),0,50)
            marker=cv2.warpAffine(marker,cv2.getRotationMatrix2D((49.5,49.5),
                math.degrees(world['heading']-math.pi/2),1),(100,100),borderValue=255)
            x,y=round(world['x']),round(1200-world['y'])
            if rolling_marker_loss and drive_wheels and not rolling_marker_missing:
                rolling_marker_missing=True
            elif marker_dropout and control.contact_anchor is not None and world['marker_dropout_frames']<12:
                world['marker_dropout_frames']+=1
            else:
                image[y-50:y+50,x-50:x+50]=cv2.cvtColor(marker,cv2.COLOR_GRAY2BGR)
            for block_id,(bx,by) in world['blocks'].items():
                if occlude_contact and control.state=='PUSH' and control.contact_anchor is not None:
                    ox,oy=bx-world['x'],by-world['y']
                    ahead=ox*math.cos(world['heading'])+oy*math.sin(world['heading'])
                    lateral=-ox*math.sin(world['heading'])+oy*math.cos(world['heading'])
                    if 30<ahead<(85 if midfield else 80) and abs(lateral)<90:
                        world['occluded_frames']+=1
                        world['occluded_blocks'].add(block_id)
                        continue
                bx,by=round(bx),round(1200-by)
                cv2.rectangle(image,(bx-10,by-10),(bx+9,by+9),(0,0,230),-1)
            return True,image
        def release(self): world['released']=True

    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    class LocalResponse:
        def __init__(self,request):
            nonlocal drive_wheels,drive_expiry,drive_segments,rolling_stop_at,last_drive_plan,renewals
            self.path=request.full_url.removeprefix(f'http://127.0.0.1:{server.server_port}')
            data=parse_qs((request.data or b'').decode())
            world['requests'].append((self.path,data))
            if self.path=='/status':
                world['now']+=preview_delay
            if self.path=='/step':
                assert world['now']>=drive_expiry
                gentle=data.get('gentle')==['1']
                if continuous and not (live_edge_stop or midfield) and data['direction'][0] in ('forward','backward'):
                    assert gentle
                assert gentle or (local and (data['direction'][0] in ('forward','backward') or
                                              control.last_plan.get('normal_turn_step')))
                if turn_breakaway and data['direction'][0] in ('left','right'):
                    world['turn_unlocked']=not gentle
                if midfield and data['direction'][0] in ('forward','backward'):
                    assert gentle and 'turn_profile' not in data,data
                world['pending'].append(data['direction'][0])
                duration={'medium':.06,'fine':.035}.get(data.get('turn_profile',[''])[0],.08 if gentle else .12)
                world['observe_after']=world['now']+duration+.02
            if self.path=='/drive':
                assert continuous and local
                new_plan=control.last_plan is not last_drive_plan
                if drive_wheels and world['now']<drive_expiry and new_plan:
                    handoffs.append((drive_plans[-1],world['now']))
                if not new_plan:
                    assert world['now']<drive_expiry
                    renewals+=1
                drive_segments+=1
                drive_wheels=tuple(int(data[side][0]) for side in ('left','right'))
                assert sum(drive_wheels)==100 and all(40<=wheel<=60 for wheel in drive_wheels),drive_wheels
                hold_ms=int(data['hold_ms'][0])
                assert hold_ms==350
                drive_expiry=world['now']+hold_ms/1000
                if new_plan:
                    drive_plans.append((world['now'],drive_wheels,control.last_plan['drive_replan_s']))
                    last_drive_plan=control.last_plan
                world['observe_after']=world['now']
            if self.path=='/stop':
                if rolling_marker_missing and drive_wheels and rolling_stop_at is None:
                    rolling_stop_at=world['now']
                    assert rolling_stop_at<drive_expiry
                drive_wheels=None
                drive_expiry=-math.inf
                world['observe_after']=-math.inf
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self,size):
            return json.dumps(dict(protocol='vision-pulse-v1',pulse_ms=250,step_ms=120,
                gentle_step_ms=80, gentle_straight_speed=.05, reverse_step=True,
                result={'/status':'ready','/stop':'stop_queued','/step':'step_queued',
                        '/drive':'drive_queued'}[self.path],
                **({'drive_hold_ms':2000} if (continuous and not live_edge_stop) or midfield else {}),
                **({'medium_turn_ms':60,'fine_turn_ms':35} if turn_profiles else {}))).encode()
    try:
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack, redirect_stdout(io.StringIO()):
            if in_process:
                stack.enter_context(patch('urllib.request.OpenerDirector.open',
                    lambda opener,request,**kwargs:LocalResponse(request)))
            def key(*args):
                if rolling_marker_loss and rolling_stop_at is not None:
                    return 27
                if live_edge_stop and control.finished:
                    return 27
                if rolling_lease_loss and control.finished:
                    return 27
                if preview_delay:
                    return 27 if world['frames']>=8 else 0
                if midfield and control.finished:
                    world['space_after_finish']=world.get('space_after_finish',0)+1
                    return 32 if world['space_after_finish']<=3 else 27
                delivered=local and not midfield and control.completed==2 and control.state=='SELECT'
                return 27 if control.finished or delivered or world['frames']>(750 if midfield else 2400) else 32 if control.last_plan.get('can_start') else 0
            mode_args=launcher.command({'ip':'127.0.0.1','camera':0},'8')[3:]
            if not midfield:
                mode_args.remove('--midfield')
            mode_args[-1]=f'http://127.0.0.1:{server.server_port}'
            for obj,name,value in (
                (app.sys,'argv',mode_args),
                (app,'OUTPUT',Path(folder)),(app,'MultiPushControl',lambda *args,**kwargs:control),
                (control,'update',checked_update),
                (app,'detect_robot',lambda image,**kwargs:detect_robot(image,config,**kwargs)),
                (app,'calibration',lambda index:(Camera(),[],0,(1200,1200))),
                (app,'rectify',lambda frame,corners:frame),
                (app.time,'monotonic',lambda:world['now']),
                (app,'show_stopped_error',lambda name,error,**kwargs:(_ for _ in ()).throw(AssertionError(str(error)))),
                (cv2,'namedWindow',lambda *args:None),(cv2,'destroyAllWindows',lambda:None),
                (cv2,'imshow',lambda *args:None),(cv2,'getWindowProperty',lambda *args:1),
                (cv2,'setMouseCallback',lambda name,callback:callback(cv2.EVENT_LBUTTONDOWN,239 if midfield else 233,283 if midfield else 292,0,None)),
                (cv2,'waitKey',key),
            ): stack.enter_context(patch.object(obj,name,value))
            app.main()
            events=[json.loads(line) for path in Path(folder).glob('*/events.jsonl')
                    for line in path.read_text(encoding='utf-8').splitlines()]
        if midfield and not live_edge_stop:
            if control.state!='DONE' or control.completed!=2:
                for event in [e for e in events if e['event']=='command'][-32:]:
                    plan=event['plan']
                    print(event['command'],plan['reason'],plan.get('robot_center_mm'),plan.get('goal_mm'),
                          plan.get('heading_error_deg'),event.get('drive_wheels'))
            assert control.state=='DONE' and control.completed==2,(control.last_plan,world['x'],world['y'],world['blocks'])
            assert world['occluded_blocks']=={'a','b'} and all(b[1]<285 for b in world['blocks'].values()),world['blocks']
            midpoints=[e['plan']['goal_mm'][1] for e in events if e.get('event')=='plan' and
                       'CAR AT YELLOW MIDFIELD' in e['plan']['reason']]
            assert len(midpoints)==2 and all(abs(y-300)<=12 for y in midpoints),midpoints
            assert sum(e['event']=='start_accepted' for e in events)==1
            assert sum(e['event']=='start_rejected' for e in events)==3
            assert not any(path in ('/drive','/pulse') for path,_ in world['requests'])
            straight=[e for e in events if e['event']=='command' and e['command'] in ('forward','backward')]
            assert {e['command'] for e in straight}=={'forward','backward'}
            assert all(e['step_ms']==80 and e['response']['gentle_straight_speed']==.05 for e in straight)
            if marker_dropout:
                assert world['marker_dropout_frames']==12
                stopped=[e['plan'] for e in events if e.get('event')=='plan' and
                         'ROBOT MARKER / BODY LOST' in e['plan']['reason']]
                assert stopped and all(plan['command']=='stop' and plan['target_ids'] for plan in stopped)
            assert len([e for e in events if e['event']=='command' and
                        e['plan']['reason']=='CAR AT YELLOW MIDFIELD / REVERSE NEXT' and
                        e['command']=='stop'])==2
            assert any(data.get('direction')==['backward'] for _,data in world['requests'])
            assert world['requests'][-1][0]=='/stop'
            print('PASS: one menu 8 start, two midfield deliveries with hidden blocks, retreat and verification after each')
            return
        if preview_delay:
            assert ages and max(ages)<=.2, ages
            assert not control.finished and not control.active,control.last_plan
            assert not any(path=='/step' for path,_ in world['requests'])
            assert app.GentleLink.request_timeout==.6 and app.WifiLink.request_timeout==.18
            print('PASS: slow status query precedes NEW camera acquisition; preparation remains usable, original mode timeout unchanged')
            return
        if rolling_lease_loss:
            assert control.last_plan['reason']=='DRIVE LEASE EXPIRED / LOCKED STOP'
            assert drive_segments==1 and not control.active
            print('PASS: missed renewal locks motion without issuing another drive command')
            return
        if live_edge_stop:
            assert control.last_plan['reason']=='TOO CLOSE TO FIELD EDGE / LOCKED STOP'
            assert drive_segments==0 and not control.active
            paths=[path for path,_ in world['requests']]
            first_step=paths.index('/step')
            assert paths[first_step+1]=='/stop' and paths.count('/step')==1
            print('PASS: short-step fallback locks at the wall buffer')
            return
        if rolling_marker_loss:
            assert rolling_stop_at is not None and rolling_stop_at-drive_plans[0][0]<=.081
            assert drive_segments==1
            print('PASS: marker loss stops an active segment on the next camera frame')
            return
        assert control.state==('SELECT' if local else 'DONE') and control.completed==2,(control.state,control.last_plan,world)
        if local:
            assert control.active and not control.finished
        assert all(point[1]<(590 if occlude_contact else 585 if local else 570)
                   for point in world['blocks'].values()),world['blocks']
        assert world['requests'][-1][0]=='/stop' and world['released']
        steps=[data for path,data in world['requests'] if path=='/step']
        assert len({s['id'][0] for s in steps})==len(steps)
        required={'forward','backward'} if occlude_contact else {'forward','backward','left','right'}
        directions={s['direction'][0] for s in steps}
        if continuous:
            assert renewals and handoffs, 'Test 8 did not renew motion and continue into a fresh plan'
            assert any(l!=r for _,(l,r),_ in drive_plans), drive_plans
            assert any(duration>=1 for _,_,duration in drive_plans), drive_plans
            assert any(now-start<min(1,duration) for (start,_,duration),now in handoffs), handoffs
            directions.add('forward')
        assert required<=directions
        if turn_profiles:
            turns=[s for s in steps if s['direction'][0] in ('left','right')]
            assert turns and all(s.get('turn_profile') in (['medium'],['fine']) or
                                 'gentle' not in s for s in turns),turns
            assert all('turn_profile' not in s for s in steps if s['direction'][0] in ('forward','backward'))
        if turn_breakaway:
            assert any(s['direction'][0] in ('left','right') and 'gentle' not in s for s in steps)
        assert max(e.get('plan',{}).get('completed',0) for e in events)==2
        if occlude_contact:
            assert world['occluded_frames']>10,world['occluded_frames']
            assert any(e.get('plan',{}).get('block_estimated') for e in events)
        if marker_dropout:
            assert world['marker_dropout_frames']==12
            marker_wait=[e['plan'] for e in events if e.get('event')=='plan' and
                         'ROBOT MARKER / BODY LOST' in e.get('plan',{}).get('reason','')]
            assert marker_wait and all(p.get('target_ids') for p in marker_wait),marker_wait
        assert any(e.get('plan',{}).get('reason')=='WAIT FOR FRAME AFTER STEP' for e in events)
        print('PASS: actual ArUco/block pixels + complete application + '+
              ('in-process HTTP transport' if in_process else 'real HTTP')+
              (' / local test 8' if local else '')+
              (' / contact blocks hidden then visually verified' if occlude_contact else '')+
              ': two yellow deliveries, reverse/verify/reselect, bounded steps, final STOP')
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__' and '--midfield' in sys.argv:
    check(in_process=True,local=True,occlude_contact=True,midfield=True)
elif __name__=='__main__':
    check(in_process=True,local=True,occlude_contact=True,midfield=True)
    check(in_process='--in-process' in sys.argv)
    check(in_process='--in-process' in sys.argv,local=True)
    check(in_process='--in-process' in sys.argv,local=True,occlude_contact=True,marker_dropout=True)
    check(in_process='--in-process' in sys.argv,local=True,turn_breakaway=True)
    check(in_process='--in-process' in sys.argv,local=True,turn_profiles=True,turn_breakaway=True)
    check(preview_delay=.25,in_process='--in-process' in sys.argv)
    if '--in-process' in sys.argv:
        check(in_process=True,local=True,occlude_contact=True,midfield=True,marker_dropout=True)
        check(in_process=True,local=True,midfield=True,live_edge_stop=True)
        check(in_process=True,local=True,continuous=True)
        check(in_process=True,local=True,continuous=True,rolling_marker_loss=True)
        check(in_process=True,local=True,continuous=True,live_edge_stop=True)
        check(in_process=True,local=True,continuous=True,rolling_lease_loss=True)
