"""Test 8: local approach, turn correction and two observed deliveries."""
from copy import deepcopy
import math
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from control.multi_push_control import MultiPushControl
from control.test_multi_push_control import robot, FIELD
from strategy.planner import Block, Decision
import cv2
import numpy as np
from vision.photo_vision import segment


def check_recovery():
    blocks=(Block('a',425,852),Block('b',597,777),Block('c',700,738))
    control=MultiPushControl(field_guided=True)
    pose=robot(655,965,math.pi)
    control.update(pose,blocks,FIELD,1,1,1)
    assert control.start()
    control.update(pose,blocks,FIELD,1.1,1.1,1.1)
    target_id=control.task.target_ids
    overshoot=robot(655,965,control.task.heading_rad+.5)
    plan=control.update(overshoot,blocks,FIELD,1.2,1.2,1.2)
    assert plan['command']=='right' and control.task.target_ids==target_id,plan
    assert not plan.get('standard_step'),plan
    plan=control.update(overshoot,blocks,FIELD,1.2,1.5,1.5)
    assert plan['command']=='stop' and control.task.target_ids==target_id and control.state=='ALIGN',plan
    plan=control.update(overshoot,blocks,FIELD,1.6,1.6,1.6)
    assert plan['command']=='right' and control.task.target_ids==target_id,plan
    plan=control.update(overshoot,blocks,FIELD,7,7,7)
    assert control.active and not control.finished and control.state=='SELECT',plan
    with patch('control.multi_push_control.route',side_effect=AssertionError('Full route used')):
        control=MultiPushControl(field_guided=True)
        pose=robot(655,965,math.pi/2)
        control.update(pose,blocks,FIELD,1,1,1)
        assert control.start()
        plan=control.update(pose,blocks,FIELD,1.1,1.1,1.1)
        assert plan['command'] in ('left','right','forward'),plan
        assert control.state=='APPROACH' and not control.finished,plan


def check_deliveries():
    control=MultiPushControl(field_guided=True)
    x,y,heading=600.,950.,-math.pi/2
    blocks=[Block('a',400,700),Block('b',800,700)]
    commands=set()
    normal_straight_steps=0
    for i in range(3500):
        now=i*.08
        plan=control.update(robot(x,y,heading),tuple(blocks),FIELD,now,now,now)
        command=plan['command'];commands.add(command)
        assert not plan.get('startup_pulse'),plan
        if command in ('left','right'):
            assert not plan.get('standard_step'),plan
        normal_straight_steps+=bool(plan.get('standard_step'))
        if plan.get('can_start'):
            control.start()
        if control.finished or (control.completed==2 and control.state=='SELECT'):
            break
        if command in ('left','right'):
            heading+=.08 if command=='left' else -.08
        elif command in ('forward','backward'):
            distance=4 if command=='forward' else -4
            dx,dy=distance*math.cos(heading),distance*math.sin(heading)
            x+=dx;y+=dy
            if command=='forward' and control.state=='PUSH':
                moved=[]
                for block in blocks:
                    ahead=(block.x-x)*math.cos(heading)+(block.y-y)*math.sin(heading)
                    lateral=-(block.x-x)*math.sin(heading)+(block.y-y)*math.cos(heading)
                    touching=block.id in control.task.target_ids and 35<ahead<70 and abs(lateral)<90
                    moved.append(Block(block.id,block.x+dx,block.y+dy) if touching else block)
                blocks=moved
    assert not control.finished and control.state=='SELECT' and control.completed==2,(control.last_plan,blocks)
    assert all(block.y<=585 for block in blocks),blocks
    assert {'left','right','forward','backward'}<=commands,commands
    assert normal_straight_steps>0,'Straight driving never uses normal motor power'


def check_detection_dropout():
    control=MultiPushControl(field_guided=True)
    pose=robot(600,950,-math.pi/2)
    yellow=(Block('yellow',850,400),)
    control.update(pose,yellow,FIELD,1,1,1)
    assert control.start()
    for i in range(20):
        now=1.1+i*.1
        plan=control.update(pose,yellow,FIELD,now,now,now)
        assert not control.finished and control.active and control.completed==0,plan
        assert plan['reason']=='NO BLUE BLOCK DETECTED / KEEP SCANNING',plan
    plan=control.update(pose,yellow+(Block('blue',600,700),),FIELD,4,4,4)
    assert control.task and control.task.target_ids==('blue',),plan
    hsv=np.full((1200,1200,3),(110,180,180),np.uint8)
    hsv[600:]=(25,220,230)
    for x,hue in ((200,162),(400,174),(600,3)):
        hsv[300:320,x:x+20]=(hue,208,147)
    _,regions=segment(cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR),[176,208,147],h_tol=16,
                      min_area=90,square_side_mm=20,allow_blurred_square=True)
    assert len(regions)==3,regions


def check_rear_waypoint():
    control=MultiPushControl(field_guided=True)
    pose=robot(600,800,-math.pi/2)
    blocks=(Block('a',850,700),)
    control.update(pose,blocks,FIELD,1,1,1)
    assert control.start()
    control.update(pose,blocks,FIELD,1.1,1.1,1.1)
    control.state='APPROACH'
    control.task=Decision('TEST','CAPTURE','REAR WAYPOINT',target_ids=('a',),
                          approach_mm=(600,950),push_to_mm=(850,550),heading_rad=-math.pi/2)
    control.path=[(600,950)]
    control.progress_at=1.1;control.best_cost=math.inf
    plan=control.update(pose,blocks,FIELD,1.2,1.2,1.2)
    assert plan['command']=='backward' and plan['approach_reverse'],plan
    assert abs(plan['heading_error_deg'])<1,plan
    plan=control.update(pose,blocks+(Block('front',600,720),),FIELD,1.21,1.21,1.21)
    assert plan['command']=='backward',plan
    plan=control.update(pose,blocks+(Block('rear',600,880),),FIELD,1.22,1.22,1.22)
    assert plan['reason']=='REVERSE APPROACH BLOCKED / USE FORWARD',plan
    # The real reported geometry should choose a 52-degree right correction,
    # instead of the old 128-degree left turn.
    control.path=[(649.6,886.884)]
    control.target_lock['point']=[649.4,764.9]
    control.approach_reverse=None;control.reverse_approach_blocked=False
    pose=robot(486.125,800.822,math.radians(-100.5))
    control.previous_pose=None
    plan=control.update(pose,(Block('a',649.4,764.9),),FIELD,1.3,1.3,1.3)
    assert plan['approach_reverse'] and plan['command']=='right',plan
    assert -55<plan['heading_error_deg']<-48,plan
    # New live failure: 296mm is beyond the original reverse-distance cutoff,
    # but the tail is only 20 degrees off the goal, so begin backing up.
    control.path=[(696.5,886.44)]
    control.target_lock['point']=[696.5,784.4]
    control.approach_reverse=None;control.reverse_approach_blocked=False
    control.previous_pose=None
    pose=robot(473.09,691.60,math.radians(-119.47))
    plan=control.update(pose,(Block('a',696.5,784.4),),FIELD,1.4,1.4,1.4)
    assert plan['command']=='backward' and plan['approach_reverse'],plan
    # Stronger pulses must not reset the independent no-progress timer.
    control.approach_reverse=False
    control.progress_at=1.4
    plan=control.update(pose,(Block('a',696.5,784.4),),FIELD,2.7,2.7,2.7)
    plan=control.update(pose,(Block('a',696.5,784.4),),FIELD,4,4,4)
    assert plan['command'] in ('left','right') and plan.get('normal_turn_clear'),plan
    progress_at=control.progress_at
    plan=control.update(pose,(Block('a',696.5,784.4),),FIELD,4.1,4.1,4.1)
    assert not plan.get('normal_turn_step'),plan
    assert control.progress_at==progress_at
    plan=control.update(pose,(Block('a',696.5,784.4),),FIELD,8.2,8.2,8.2)
    assert control.state=='SELECT' and plan['command']=='stop',plan


def check_release_handoff():
    def at_delivery():
        control=MultiPushControl(field_guided=True)
        pose=robot(600,650,-math.pi/2)
        blocks=(Block('a',600,582),Block('b',900,750))
        control.update(pose,blocks,FIELD,1,1,1)
        assert control.start()
        control.task=Decision('TEST','CAPTURE','DELIVERY',target_ids=('a',),
                              push_to_mm=(600,550),heading_rad=-math.pi/2)
        control.state='PUSH'
        control.update(pose,blocks,FIELD,1.1,1.1,1.1)
        assert control.state=='RELEASE',control.last_plan
        return control,blocks

    control,blocks=at_delivery()
    # Lost colour after a measured crossing must not cancel backing away.
    plan=control.update(robot(600,654,-math.pi/2),blocks[1:],FIELD,1.2,1.2,1.2)
    assert plan['command']=='backward' and control.state=='RELEASE',plan
    # A step can overshoot the release point by more than the old 10mm disk.
    released_y=float(control.release_goal[1])+18
    pose=robot(600,released_y,-math.pi/2)
    control.previous_pose=None
    plan=control.update(pose,blocks[1:],FIELD,1.3,1.3,1.3)
    assert plan['command']=='stop' and control.completed==0,plan
    # A new tracking ID at the same measured location is verified once.
    renamed=(Block('new-a',600,582),blocks[1])
    for now in (1.4,1.7,2.0):
        plan=control.update(pose,renamed,FIELD,now,now,now,
                            recent_obstacles=(blocks[0],))
    assert control.completed==1 and control.state=='SELECT',plan
    plan=control.update(pose,renamed,FIELD,2.1,2.1,2.1)
    assert control.task.target_ids==('b',) and control.active,plan

    # Permanent dropout cannot release the target lock or invent a count.
    control,blocks=at_delivery()
    pose=robot(600,float(control.release_goal[1])+18,-math.pi/2)
    control.previous_pose=None
    for now in (1.2,1.7,2.1):
        plan=control.update(pose,blocks[1:],FIELD,now,now,now)
    assert control.state=='RELEASE' and control.completed==0,plan
    control.update(pose,blocks[1:],FIELD,2.2,2.2,2.2)
    assert control.task.target_ids==('a',) and control.target_lock['id']=='a',control.last_plan

    # If it visibly returns to blue during release, no success is recorded.
    control,blocks=at_delivery()
    plan=control.update(robot(600,654,-math.pi/2),
                        (Block('a',600,610),blocks[1]),FIELD,1.2,1.2,1.2)
    assert control.state=='SELECT' and control.completed==0,plan


def check_contact_occlusion():
    def touching():
        control=MultiPushControl(field_guided=True)
        pose=robot(600,800,-math.pi/2)
        blocks=(Block('a',600,740),Block('b',900,750))
        control.update(pose,(Block('a',600,720),blocks[1]),FIELD,1,1,1)
        assert control.start()
        control.task=Decision('TEST','CAPTURE','PUSH',target_ids=('a',),
                              push_to_mm=(600,550),heading_rad=-math.pi/2)
        control.state='PUSH'
        plan=control.update(pose,blocks,FIELD,1.1,1.1,1.1)
        assert plan['command']=='forward',plan
        return control,blocks

    control,blocks=touching()
    plan=control.update(robot(600,800,-math.pi/2),blocks[1:],FIELD,1.2,1.2,1.2)
    assert plan['command']=='forward' and plan.get('block_estimated') and not plan.get('standard_step'),plan
    assert control.task.target_ids==('a',) and control.completed==0,plan
    # Real observations during transport restore ordinary measured tracking.
    plan=control.update(robot(600,785,-math.pi/2),
                        (Block('a',600,725),blocks[1]),FIELD,1.3,1.3,1.3)
    assert plan['command']=='forward' and control.task.target_ids==('a',),plan
    assert control.contact_hidden_at is None,plan

    control,blocks=touching()
    plan=control.update(robot(600,800,-math.pi/2),
        blocks[1:]+(Block('ahead',600,720),),FIELD,1.2,1.2,1.2)
    assert plan['command']=='stop' and 'BLOCKED' in plan['reason'],plan
    control,blocks=touching()
    for now,y in ((1.2,800),(1.3,760),(1.4,720),(1.5,680),(1.6,640),(1.7,600)):
        plan=control.update(robot(600,y,-math.pi/2),blocks[1:],FIELD,now,now,now)
    assert plan['command']=='stop' and control.state=='RELEASE' and control.completed==0,plan
    for now,y in ((1.8,640),(1.9,680),(2.0,float(control.release_goal[1]))):
        plan=control.update(robot(600,y,-math.pi/2),blocks[1:],FIELD,now,now,now)
    assert control.completed==0 and plan['command']=='stop',plan
    revealed=(Block('new-a',600,540),blocks[1])
    for now in (2.1,2.4,2.7):
        plan=control.update(robot(600,y,-math.pi/2),revealed,FIELD,now,now,now)
    assert control.completed==1 and control.state=='SELECT',plan

    # Single-block mode must also refuse to count an estimated release.
    control,blocks=touching()
    control.one_delivery=True
    for now,y in ((1.2,800),(1.3,760),(1.4,720),(1.5,680),(1.6,640),(1.7,600)):
        plan=control.update(robot(600,y,-math.pi/2),blocks[1:],FIELD,now,now,now)
    for now,y in ((1.8,640),(1.9,680),(2.0,float(control.release_goal[1]))):
        plan=control.update(robot(600,y,-math.pi/2),blocks[1:],FIELD,now,now,now)
    assert control.completed==0 and not control.finished,plan

    control,blocks=touching()
    plan=control.update(robot(600,790,-math.pi/2+.2),blocks[1:],FIELD,1.2,1.2,1.2)
    assert plan['command']=='stop' and 'DRIFT' in plan['reason'],plan
    control,blocks=touching()
    for now in (1.2,3,5.3):
        plan=control.update(robot(600,800,-math.pi/2),blocks[1:],FIELD,now,now,now)
    assert plan['command']=='stop' and 'NO CAR PROGRESS' in plan['reason'],plan
    control,blocks=touching()
    lost_pose={**robot(600,800,-math.pi/2),'detected':False}
    plan=control.update(lost_pose,blocks[1:],FIELD,1.2,1.2,1.2)
    assert plan['command']=='stop',plan
    plan=control.update(robot(600,800,-math.pi/2),blocks[1:],FIELD,1.0,1.4,1.4)
    assert plan['command']=='stop',plan


def check_contact_association():
    from control.multi_push_control import MovingBlocks
    from vision.photo_vision import ClickedBlock
    tracker=MovingBlocks()
    region=dict(x_mm=600,y_mm=740,bbox_px=[590,450,20,20])
    first=tracker.update([region],1)[0]
    hint={first.id:(600,600)}
    assert tracker.update([],2,association_hints=hint)==()
    assert tracker.previous=={} and first.id in tracker.regions
    revealed=dict(x_mm=600,y_mm=600,bbox_px=[590,590,20,20])
    assert tracker.update([revealed],2.1,association_hints=hint)[0].id==first.id
    clicked=ClickedBlock((600,460))
    assert clicked.update([region],1)
    assert clicked.update([],2,expected_point=(600,600))==[]
    assert clicked.update([revealed],2.1,expected_point=(600,600))==[revealed]


def check_target_commitment():
    control=MultiPushControl(field_guided=True)
    pose=robot(600,950,-math.pi/2)
    blocks=(Block('a',600,700),Block('b',800,780))
    control.update(pose,blocks,FIELD,1,1,1)
    assert control.start()
    control.update(pose,blocks,FIELD,1.1,1.1,1.1)
    assert control.task.target_ids==('a',)
    for now in (1.2,2,3):
        plan=control.update({**pose,'detected':False},blocks,FIELD,now,now,now)
        assert plan['command']=='stop' and control.task.target_ids==('a',),plan
    for now in (3.1,4,5):
        plan=control.update(pose,blocks[1:],FIELD,now,now,now)
        assert plan['command']=='stop' and control.task.target_ids==('a',),plan
    renamed=(Block('new-a',600,700),blocks[1])
    control.update(pose,renamed,FIELD,5.1,5.1,5.1)
    assert control.task.target_ids==('new-a',),control.last_plan
    control._reselect('PATH CHANGED / REPLAN SAME BLOCK')
    plan=control.update(pose,(renamed[0],Block('b',610,850)),FIELD,5.2,5.2,5.2)
    assert control.task.target_ids==('new-a',),plan

    # Reproduce the live failure: marker disappears during hidden transport.
    control=MultiPushControl(field_guided=True)
    pose=robot(600,800,-math.pi/2)
    control.update(pose,(Block('a',600,720),blocks[1]),FIELD,1,1,1)
    assert control.start()
    control.task=Decision('TEST','CAPTURE','PUSH',target_ids=('a',),push_to_mm=(600,550),heading_rad=-math.pi/2)
    control.state='PUSH'
    control.update(pose,(Block('a',600,740),blocks[1]),FIELD,1.1,1.1,1.1)
    control.update(pose,blocks[1:],FIELD,1.2,1.2,1.2)
    for now in (1.3,2,3):
        plan=control.update({**pose,'detected':False},blocks[1:],FIELD,now,now,now)
        assert plan['command']=='stop' and control.task.target_ids==('a',),plan
    plan=control.update(pose,blocks[1:],FIELD,3.1,3.1,3.1)
    assert plan['command']=='forward' and control.task.target_ids==('a',) and control.completed==0,plan


def check_reveal_after_replan():
    control=MultiPushControl(field_guided=True)
    pose=robot(600,800,-math.pi/2)
    target=Block('a',600,735)
    other=Block('b',900,750)
    control.update(pose,(Block('a',600,710),other),FIELD,1,1,1)
    assert control.start()
    control._lock_target(target,(target,other))
    control._reselect('CONTACT PUSH PATH BLOCKED / REOBSERVE')
    plan=control.update(pose,(other,Block('rear',600,880)),FIELD,1.1,1.1,1.1)
    assert plan['command']=='stop' and 'BACKUP BLOCKED' in plan['reason'],plan
    plan=control.update(pose,(other,),FIELD,1.2,1.2,1.2)
    assert plan['command']=='backward' and plan['target_ids']==['a'],plan
    for now,y in ((1.4,830),(1.6,857)):
        plan=control.update(robot(600,y,-math.pi/2),(other,),FIELD,now,now,now)
    assert plan['command']=='stop' and control.completed==0,plan
    renamed=Block('new-a',600,735)
    plan=control.update(robot(600,857,-math.pi/2),(renamed,other),FIELD,1.8,1.8,1.8)
    assert control.task.target_ids==('new-a',) and control.completed==0,plan

    # A target lost near the boundary can reappear fully inside yellow.
    control.target_lock['point']=[600,601]
    control._reselect('RECHECK BOUNDARY')
    yellow=Block('new-a',600,580)
    pose=robot(600,770,-math.pi/2)
    plan=control.update(pose,(yellow,other),FIELD,2,2,2)
    assert control.state=='RELEASE' and control.completed==0,plan
    for now in (2.1,2.4,2.7):
        plan=control.update(pose,(yellow,other),FIELD,now,now,now)
    assert control.completed==1 and control.state=='SELECT',plan


def check_midfield_verification():
    control=MultiPushControl(field_guided=True,midfield=True)
    other=Block('b',900,700)
    initial=(Block('a',600,690),other)

    def observe(y, blocks, now, frame_age=0):
        return control.update(robot(600,y,-math.pi/2),blocks,FIELD,now-frame_age,now,now)

    observe(760,initial,0)
    assert control.start()
    for now in (.1,.2,.3):
        observe(760,initial,now)
    field_dropout=deepcopy(control)
    pose=robot(600,720,-math.pi/2)
    plan=field_dropout.update(pose,(other,),{'valid':False},.4,.4,.4)
    assert plan['command']=='stop' and field_dropout.midfield_push_goal is not None,plan
    plan=field_dropout.update(pose,(other,),FIELD,.5,.5,.5)
    assert plan['command']=='forward' and plan['target_ids']==['a'],plan

    jumped=deepcopy(control)
    for now in (.4,.5):
        plan=jumped.update(robot(600,650,-math.pi/2),(other,),FIELD,now,now,now)
        assert plan['command']=='stop' and jumped.finished,plan

    for frame,y in enumerate(range(720,299,-40),start=1):
        blocks=(other,Block('new-object',600,690)) if y==600 else (other,)
        plan=observe(y,blocks,.3+frame*.1)
        assert plan['target_ids']==['a'],plan
    observe(300,(other,),1.5)
    assert control.state=='RELEASE',control.last_plan
    observe(340,(other,),1.6)
    observe(385,(other,),1.7)
    rear_y=float(control.release_goal[1])
    observe(rear_y,(other,),1.75)
    x,y=control.release_point

    # A detection carrying the old ID is outside the expected release position.
    for now in (1.8,2.35):
        plan=observe(rear_y,(Block('a',x+100,y),other),now)
        assert control.completed==0 and not control.finished,plan

    # The search and verification timers both require fresh observations.
    observe(rear_y,(other,),2.5,frame_age=.4)
    plan=observe(rear_y,(other,),2.75)
    assert control.completed==0 and not control.finished,plan
    revealed=(Block('new-a',x,y),other)
    observe(rear_y,revealed,2.8)
    observe(rear_y,revealed,3.1,frame_age=.4)
    plan=observe(rear_y,revealed,3.4)
    assert control.completed==0,plan
    for now in (3.65,3.95):
        plan=observe(rear_y,revealed,now)
    assert control.completed==1 and control.state=='SELECT',plan


if __name__=='__main__':
    check_recovery()
    check_deliveries()
    check_detection_dropout()
    check_rear_waypoint()
    check_release_handoff()
    check_contact_occlusion()
    check_contact_association()
    check_target_commitment()
    check_reveal_after_replan()
    check_midfield_verification()
    print('PASS: two deliveries; hidden contact transport/reveal/verify; drift/stall/obstacle stops; measured-only association hints')
