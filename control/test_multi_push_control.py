"""Two real controller deliveries with observed motion, routing and fault stops."""
import math
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from control.multi_push_control import MultiPushControl, MovingBlocks, route
from strategy.planner import Block

FIELD={'valid':True,'yellow_normal':[0,1],'point_px':[600,600]}


def robot(x,y,heading):
    forward=np.array([math.cos(heading),math.sin(heading)])
    side=np.array([-forward[1],forward[0]])
    center=np.array([x,y])
    hull=np.array([center+f*forward+s*side for f,s in [(50,100),(50,-100),(-50,-100),(-50,100)]])
    hull[:,1]=1200-hull[:,1]
    return dict(detected=True,heading_valid=True,geometry_valid=True,
        center_px=[x*1199/1200,(1200-y)*1199/1200],heading_rad=heading,
        body_polygon_px=(hull*1199/1200).tolist())


def simulate(fault=None, start=(600.,950.)):
    control=MultiPushControl()
    x,y=start;heading=-math.pi/2
    blocks=[Block('a',400,700),Block('b',800,700)]
    states=set();commands=[];verified=[];detoured=False
    for i in range(2200):
        now=i*.04
        observed=tuple(blocks)
        field=FIELD
        pose=robot(x,y,heading)
        captured=link=now
        if control.state=='PUSH' and fault:
            if fault=='lost': observed=tuple(b for b in blocks if b.id not in control.task.target_ids)
            if fault=='stale': captured=now-1
            if fault=='external':
                blocks=[Block(b.id,b.x,b.y-20) if b.id in control.task.target_ids else b for b in blocks]
                observed=tuple(blocks)
            if fault=='field': field={'valid':False}
        plan=control.update(pose,observed,field,captured,now,link)
        if i>=30 and not control.active and not control.finished:
            control.start()
        states.add(control.state)
        detoured |= len(control.path)>1
        if control.completed>len(verified):
            verified.append(tuple((b.id,b.y) for b in blocks))
            assert all(b.y<=570 for b in blocks if b.id in control.verified)
            assert control.state=='SELECT'
        if control.finished:
            if fault:
                assert control.state=='STOPPED' and control.completed==0,plan
            else:
                assert control.state=='DONE' and control.completed==2,plan
                assert len(verified)==2 and all(b.y<=570 for b in blocks)
                assert {'APPROACH','ALIGN','PUSH','RELEASE','SELECT','DONE'}<=states
                assert {'left','right','forward','backward'}<=set(commands)
                if start!=(600.,950.): assert detoured
            assert plan['command']=='stop'
            return
        command=plan['command'];commands.append(command)
        if command in ('left','right'):
            heading+=(.04 if command=='left' else -.04)
        elif command in ('forward','backward') and not (fault=='stalled' and control.state=='PUSH'):
            distance=4 if command=='forward' else -4
            x+=distance*math.cos(heading);y+=distance*math.sin(heading)
            if control.state=='PUSH' and command=='forward':
                blocks=[Block(b.id,b.x,min(b.y,y-62)) if b.id in control.task.target_ids else b for b in blocks]
    raise AssertionError(('Multi-block simulation did not finish',control.state,control.last_plan,x,y))


def main():
    control=MultiPushControl()
    pose=robot(600,950,-math.pi/2)
    blocks=(Block('a',400,700),Block('b',800,700))
    control.update(pose,blocks,FIELD,0,1,1)
    assert not control.finished, 'Preparing on a slow frame permanently locked the test'
    for i in range(12):
        t=2+i*.1
        control.update(pose,blocks,FIELD,t,t,t)
    assert control.start()
    # Round-trip waiting is permitted only when the next observation is NEW.
    assert control.update(pose,blocks,FIELD,3.9,3.9,3.9)['command']=='stop'
    assert not control.finished
    control.update(pose,blocks,FIELD,3.9,4.2,4.2)
    assert control.finished and not control.active, 'Stale actual image was accepted'
    simulate()
    simulate(start=(250.,600.))
    for fault in ('lost','stale','external','field','stalled'):
        simulate(fault)
    tracker=MovingBlocks()
    first=tracker.update([dict(bbox_px=[0,0,20,20],x_mm=400,y_mm=700)])
    second=tracker.update([dict(bbox_px=[0,0,20,20],x_mm=400,y_mm=680)])
    assert first[0].id==second[0].id
    try:
        tracker.update([dict(bbox_px=[0,0,20,20],x_mm=400,y_mm=680)]*2)
    except ValueError:
        pass
    else: raise AssertionError('Ambiguous detections accepted')
    path=route((300,600),(900,600),(Block('obstacle',600,600),),125)
    assert len(path)>1, 'Obstacle was not routed around'
    print('PASS: two sequential yellow deliveries/reverse/verified count; lost/stale/external/field/stall stops; moving IDs; obstacle detour')


if __name__=='__main__':
    main()
