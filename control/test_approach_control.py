"""Shared strategy/approach/HTTP tests. No device, camera or physical motion."""
import json
import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import cv2
import numpy as np

from vision_approach_test import DirectionLink
from approach_control import ApproachControl, StationaryBlocks
from strategy.planner import Block, Config, Pose, World
from strategy.runtime import StrategyRuntime
from vision.photo_vision import detect_midline, segment
from vision.robot_vision import detect_robot, exclude_robot_regions

FIELD={'valid':True,'yellow_normal':[0,1],'point_px':[600,600]}
BLOCKS=(Block('a',600,650),)


def robot(x=600,y=900,heading=-math.pi/2):
    p=[x*1199/1200,(1200-y)*1199/1200]
    return {'detected':True,'heading_valid':True,'center_px':p,'heading_rad':heading,
            'body_polygon_px':[[p[0]+a,p[1]+b] for a,b in [(-40,-60),(40,-60),(40,60),(-40,60)]]}


def prepare(heading=-math.pi/2):
    control=ApproachControl()
    for t in (0,.3,.6):
        plan=control.update(robot(heading=heading),BLOCKS,FIELD,t,t,t)
    assert plan['can_start'],plan
    assert control.start()
    return control


def main():
    for heading,expected in ((-math.pi/2,'forward'),(0,'right'),(math.pi,'left')):
        control=prepare(heading)
        plan=control.update(robot(heading=heading),BLOCKS,FIELD,.7,.7,.7)
        assert plan['command']==expected,plan
        assert isinstance(control.runtime,StrategyRuntime)
        # Same candidate generator, no second tactical selection implementation.
        candidates=list(control.runtime.planner._candidates(World(0,Pose(600,900,heading),BLOCKS),90))
        assert any(list(c.approach_mm)==plan['goal_mm'] and c.target_ids==tuple(plan['target_ids']) for c in candidates)
    control=prepare()
    control.update(robot(),BLOCKS,FIELD,.7,.7,.7)
    plan=control.update(robot(y=830),BLOCKS,FIELD,.9,.9,.9)
    assert plan['command']=='stop' and 'REACHED' in plan['reason'],plan
    assert not control.active and control.finished
    assert not control.start()
    for bad_blocks,bad_robot,bad_field,acquired in (
        ((),robot(),FIELD,.8),
        (BLOCKS,{'detected':False},FIELD,.8),
        (BLOCKS,{**robot(),'heading_valid':False},FIELD,.8),
        (BLOCKS,robot(),{'valid':False},.8),
        (BLOCKS,robot(),FIELD,.1),
        ((Block('a',620,650),),robot(),FIELD,.8),
        (BLOCKS,robot(x=850),FIELD,.8),
    ):
        control=prepare();control.update(robot(),BLOCKS,FIELD,.7,.7,.7)
        plan=control.update(bad_robot,bad_blocks,bad_field,acquired,.8,.8)
        assert plan['command']=='stop' and not control.active,plan
    control=prepare();control.update(robot(),BLOCKS,FIELD,.7,.7,.7)
    plan=control.update(robot(),BLOCKS,FIELD,1,1,.5)
    assert 'STALE' in plan['reason']
    control=prepare();control.update(robot(),BLOCKS,FIELD,.7,.7,.7)
    plan=control.update(robot(),BLOCKS+(Block('obstacle',600,860),),FIELD,.8,.8,.8)
    assert plan['command']=='stop' and not control.active,plan
    control=prepare();control.update(robot(),BLOCKS,FIELD,.7,.7,.7)
    plan=control.update(robot(),BLOCKS,FIELD,5,5,5)
    assert 'PROGRESS' in plan['reason'],plan
    control=prepare()
    plan=control.update(robot(),(Block('replacement',600,650),),FIELD,.7,.7,.7)
    assert 'BEFORE START' in plan['reason'] and not control.active,plan
    print('PASS: shared strategy goals, left/right/forward, observed arrival, lost/moved target, pose jump, stale input, obstacle, no progress, no automatic restart')

    tracker=StationaryBlocks()
    regions=[{'bbox_px':[590,540,20,20],'x_mm':600,'y_mm':650},
             {'bbox_px':[690,540,20,20],'x_mm':700,'y_mm':650}]
    first=tracker.update(regions)
    second=tracker.update(list(reversed(regions)))
    assert {b.x:b.id for b in first}=={b.x:b.id for b in second}
    assert tracker.update([])==()
    assert tracker.update(regions)[0].id!=first[0].id
    try:
        tracker.update([{'bbox_px':[0,0,80,20],'x_mm':300,'y_mm':300}])
    except ValueError:
        pass
    else:
        raise AssertionError('Merged block accepted')

    # Actual OpenCV perception including wheel exclusion and yellow mapping.
    image=np.full((1200,1200,3),(200,90,20),np.uint8)
    image[600:]=(20,220,240)
    for x,y in ((490,190),(710,190),(480,310),(720,310)):
        cv2.circle(image,(x,y),24,(0,0,230),-1)
        cv2.circle(image,(x,y),13,(15,15,15),-1)
    cv2.rectangle(image,(590,580),(609,599),(0,0,230),-1)
    detected=detect_robot(image)
    assert detected['heading_valid'],detected
    field=detect_midline(image)
    assert field['valid'],field
    _,found=segment(image,[0,255,230],h_tol=18,min_area=90,field=field)
    found=exclude_robot_regions(found,detected)
    assert len(found)==1,found
    blocks=StationaryBlocks().update(found)
    control=ApproachControl()
    for t in (0,.3,.6):
        plan=control.update(detected,blocks,field,t,t,t)
    assert plan['can_start'],plan
    assert plan['command']=='forward',plan
    print('PASS: image -> wheel/block detection -> stable IDs -> shared strategy -> forward decision')

    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def handle_request(self):
            data=parse_qs(self.rfile.read(int(self.headers.get('Content-Length',0))).decode())
            requests.append((self.path,data))
            self.send_response(200);self.end_headers()
            self.wfile.write(json.dumps({'protocol':'vision-pulse-v1','pulse_ms':250,'step_ms':120,
                'result':{'/status':'ready','/stop':'stop_queued','/step':'step_queued'}[self.path]}).encode())
        do_POST=handle_request
        do_GET=handle_request
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        link=DirectionLink('http://127.0.0.1:'+str(server.server_port));link.connect()
        for direction in ('left','right','forward'):
            link.step(direction)
        link.stop()
        assert [r[1]['direction'][0] for r in requests if r[0]=='/step']==['left','right','forward']
        tokens=[r[1]['id'][0] for r in requests if r[0]=='/step']
        assert len(set(tokens))==3
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
    print('PASS: real loopback HTTP capability check, directional commands, unique IDs, stop (no real car)')


if __name__=='__main__':
    main()
