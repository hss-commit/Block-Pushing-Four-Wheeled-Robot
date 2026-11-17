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


def simulate(fault=None, start=(600.,950.), boundary_y=600, push_sign=-1,
             extra_detection=False, one_delivery=False):
    control=MultiPushControl(one_delivery=one_delivery)
    x,y=start;heading=push_sign*math.pi/2
    blocks=[Block('a',400,boundary_y-push_sign*100),Block('b',800,boundary_y-push_sign*100)]
    states=set();commands=[];verified=[];detoured=False
    for i in range(2200):
        now=i*.04
        observed=tuple(blocks)
        if extra_detection and control.state=='PUSH' and i%2==0:
            observed+=(Block('transient',1100,350),)
        field={**FIELD,'yellow_normal':[0,-push_sign],'point_px':[600,(1200-boundary_y)*1199/1200]}
        pose=robot(x,y,heading)
        captured=link=now
        if control.state=='PUSH' and fault:
            if fault=='lost': observed=tuple(b for b in blocks if b.id not in control.task.target_ids)
            if fault=='stale': captured=now-1
            if fault=='field': field={'valid':False}
            if fault=='side_flip': field['yellow_normal']=[0,push_sign]
        if fault=='release_lost' and control.state=='RELEASE':
            field['point_px'][1]+=100
        plan=control.update(pose,observed,field,captured,now,link)
        if fault in ('lost','stale','field','release_lost') and control.state=='SELECT' and control.task is None and i>31:
            assert plan['command']=='stop' and control.active and control.completed==0,plan
            if fault=='release_lost':
                assert plan['reason']=='DELIVERED BLOCK LEFT YELLOW / RESELECT',plan
            return
        if i>=30 and not control.active and not control.finished:
            control.start()
        states.add(control.state)
        detoured |= len(control.path)>1
        if control.completed>len(verified):
            verified.append(tuple((b.id,b.y) for b in blocks))
            assert all(push_sign*(b.y-boundary_y)>=30 for b in blocks if b.id in control.verified)
            assert control.state==('DONE' if one_delivery else 'SELECT')
        if control.finished:
            if fault:
                assert control.state=='STOPPED' and control.completed==0,plan
            elif one_delivery:
                assert control.state=='DONE' and control.completed==1,plan
                assert len(verified)==1 and plan['reason']=='ONE BLOCK VERIFIED',plan
            else:
                assert control.state=='DONE' and control.completed==2,plan
                assert len(verified)==2 and all(push_sign*(b.y-boundary_y)>=30 for b in blocks)
                assert {'APPROACH','ALIGN','PUSH','RELEASE','SELECT','DONE'}<=states
                assert {'left','right','forward','backward'}<=set(commands)
                if start==(250.,600.): assert detoured
            assert plan['command']=='stop'
            return
        command=plan['command'];commands.append(command)
        if command in ('left','right'):
            heading+=(.04 if command=='left' else -.04)
        elif command in ('forward','backward') and not (fault=='stalled' and control.state=='PUSH'):
            distance=4 if command=='forward' else -4
            x+=distance*math.cos(heading);y+=distance*math.sin(heading)
            if control.state=='PUSH' and command=='forward':
                blocks=[Block(b.id,b.x,push_sign*max(push_sign*b.y,push_sign*y+62))
                        if b.id in control.task.target_ids else b for b in blocks]
    raise AssertionError(('Multi-block simulation did not finish',control.state,control.last_plan,x,y))


def main():
    control=MultiPushControl()
    pose=robot(600,950,-math.pi/2)
    blocks=(Block('a',400,700),Block('b',800,700))
    control.update(pose,blocks,FIELD,0,1,1)
    assert not control.finished, 'Preparing on a slow frame permanently locked the test'
    edge_pose=robot(20,950,-math.pi/2)
    bad_blocks=blocks+(Block('outlier',5,700),)
    for bad_pose, bad_scene, reason in (
        (pose,bad_blocks,'INVALID VISUAL GEOMETRY'),
        (edge_pose,blocks,'CAR BODY OUTSIDE FIELD'),
    ):
        plan=control.update(bad_pose,bad_scene,FIELD,1.1,1.1,1.1)
        assert plan['reason']==reason and plan['command']=='stop'
        assert not control.finished and not control.start()
        moving=MultiPushControl()
        moving.active=True
        plan=moving.update(bad_pose,bad_scene,FIELD,1.1,1.1,1.1)
        assert plan['reason']==reason and plan['command']=='stop' and moving.finished
    near_edge_pose=robot(110,950,-math.pi/2)
    plan=control.update(near_edge_pose,blocks,FIELD,1.2,1.2,1.2)
    assert plan['can_start'], plan
    for i in range(12):
        t=2+i*.1
        control.update(pose,blocks,FIELD,t,t,t)
    assert control.start()
    # Round-trip waiting is permitted only when the next observation is NEW.
    assert control.update(pose,blocks,FIELD,5.0,5.0,5.0)['command']=='stop'
    assert not control.finished
    control.update(pose,blocks,FIELD,5.0,5.3,5.3)
    assert control.active and control.state=='SELECT' and control.task is None
    assert control.last_plan['command']=='stop'
    assert control.update(pose,blocks,FIELD,5.4,5.4,5.4)['reason']=='TASK SELECTED'
    simulate()
    simulate(one_delivery=True)
    simulate(extra_detection=True)
    simulate(start=(250.,600.))
    simulate(start=(600.,750.),boundary_y=400)
    simulate(start=(600.,450.),boundary_y=800,push_sign=1)
    for fault in ('lost','stale','field','side_flip','stalled','release_lost'):
        simulate(fault)
    tracker=MovingBlocks()
    first=tracker.update([dict(bbox_px=[0,0,20,20],x_mm=400,y_mm=700)])
    second=tracker.update([dict(bbox_px=[0,0,60,50],x_mm=400,y_mm=680)])
    assert first[0].id==second[0].id
    try:
        tracker.update([dict(bbox_px=[0,0,20,20],x_mm=400,y_mm=680)]*2)
    except ValueError:
        pass
    else: raise AssertionError('Ambiguous detections accepted')
    path=route((300,600),(900,600),(Block('obstacle',600,600),),125)
    assert len(path)>1, 'Obstacle was not routed around'
    print('PASS: two sequential yellow deliveries/reverse/verified count; lost/stale/field/stall handling; moving IDs; obstacle detour')


if __name__=='__main__':
    main()
