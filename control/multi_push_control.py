"""One block per task, shared competition selection, visually verified delivery.

Controlled empty-field bench test; no opponent prediction or occlusion recovery.
"""
from dataclasses import replace
from heapq import heappop, heappush
import math

import cv2
import numpy as np

from control.approach_control import segment_distance
from strategy.planner import Block, Config, Pose
from strategy.runtime import Feedback, Observation, StrategyRuntime


class MovingBlocks:
    """Only visible, uniquely associated detections get persistent IDs."""
    def __init__(self):
        self.previous = {}
        self.counter = 0

    def update(self, regions):
        current = {}
        for region in regions:
            point = (float(region['x_mm']), float(region['y_mm']))
            matches = [key for key,p in self.previous.items() if math.dist(point,p)<=30]
            if len(matches)>1 or (matches and matches[0] in current):
                raise ValueError('AMBIGUOUS BLOCK TRACK')
            if matches:
                key = matches[0]
            else:
                self.counter += 1
                key = f'multi-{self.counter}'
            current[key] = point
        self.previous = current
        return tuple(Block(key,*point) for key,point in current.items())


def route(start, goal, blocks, radius, field=1200):
    """40mm grid, all observed blocks inflated by the rotating car footprint."""
    start,goal = tuple(start),tuple(goal)
    obstacles = [np.array([b.x,b.y]) for b in blocks]
    def clear(a,b):
        if any(v<radius or v>field-radius for p in (a,b) for v in p):
            return False
        return all(segment_distance(p,np.array(a),np.array(b))>=radius+15 for p in obstacles)
    if clear(start,goal):
        return [goal]
    spacing = 40
    points = [(x,y) for x in range(spacing,int(field),spacing)
              for y in range(spacing,int(field),spacing) if clear((x,y),(x,y))]
    # Start and goal retain their actual coordinates; never snap through obstacles.
    seeds = [p for p in points if math.dist(start,p)<=80 and clear(start,p)]
    costs, previous = {}, {}
    queue = []
    for p in seeds:
        costs[p]=math.dist(start,p);previous[p]=None
        heappush(queue,(costs[p]+math.dist(p,goal),p))
    valid=set(points)
    while queue:
        _,p=heappop(queue)
        if math.dist(p,goal)<=80 and clear(p,goal):
            path=[goal,p]
            while previous[path[-1]] is not None:
                path.append(previous[path[-1]])
            path.reverse()
            compact=[];current=start
            while path:
                i=max(i for i,q in enumerate(path) if clear(current,q))
                current=path[i];compact.append(current);path=path[i+1:]
            return compact
        for dx,dy in ((40,0),(-40,0),(0,40),(0,-40),(40,40),(40,-40),(-40,40),(-40,-40)):
            q=(p[0]+dx,p[1]+dy)
            cost=costs[p]+math.hypot(dx,dy)
            if q in valid and cost<costs.get(q,math.inf) and clear(p,q):
                costs[q],previous[q]=cost,p
                heappush(queue,(cost+math.dist(q,goal),q))
    return []


class MultiPushControl:
    def __init__(self, config=None, *, one_delivery=False):
        self.base_config = config or Config()
        self.one_delivery = one_delivery
        self.active = self.finished = False
        self.state = 'PREPARE'
        self.last_plan = dict(command='stop',reason='CLICK BLOCK COLOUR',can_start=False)
        self.runtime = self.task = None
        self.completed = 0
        self.verified = set()
        self.previous_pose = None
        self.ready_push_sign = None
        self.path = []

    def stop(self, reason, done=False):
        self.active=False;self.finished=True
        self.state='DONE' if done else 'STOPPED'
        self.last_plan={**self.last_plan,'command':'stop','reason':reason,
                        'state':self.state,'can_start':False,'completed':self.completed}
        return self.last_plan

    def rearm(self):
        self.__init__(self.base_config, one_delivery=self.one_delivery)

    def start(self):
        if self.last_plan.get('can_start') and not self.finished:
            self.active=True;self.state='SELECT'
            return True
        return False

    def _waiting(self, reason):
        self.last_plan=dict(command='stop',reason=reason,state=self.state,
                            completed=self.completed,can_start=False)
        return self.last_plan

    def _invalid(self, reason):
        if self.active:
            return self.stop(reason)
        self.ready_push_sign=None
        return self._waiting(reason)

    def _reselect(self, reason):
        if self.active:
            self.task=None
            self.path=[]
            self.previous_pose=None
            self.state='SELECT'
        return self._waiting(reason)

    def plan(self, command, reason, goal=None):
        self.last_plan=dict(command=command,reason=reason,state=self.state,
                            completed=self.completed,can_start=False,
                            target_ids=list(self.task.target_ids) if self.task else [])
        if goal is not None:
            self.last_plan['goal_mm']=list(map(float,goal))
        return self.last_plan

    def update(self, robot, blocks, field, captured_at, now, link_at):
        if self.finished:
            return self.last_plan
        if (not all(math.isfinite(v) for v in (captured_at,now,link_at)) or
                not 0<=now-captured_at<=.2 or not 0<=now-link_at<=.3):
            return self._reselect('STALE VISION / LINK / WAIT FOR FRESH FRAME')
        if not robot.get('detected') or not robot.get('heading_valid') or not robot.get('geometry_valid'):
            return self._reselect('ROBOT MARKER / BODY LOST')
        if (not field.get('valid') or
                abs(field['yellow_normal'][0])>abs(field['yellow_normal'][1])*math.tan(math.radians(15)) or
                abs(field['yellow_normal'][1])<.85):
            return self._reselect('FIELD / YELLOW DIRECTION INVALID')
        scale=self.base_config.field_mm/1199
        nx,ny=field['yellow_normal']
        push_sign=-1 if ny>0 else 1
        push_heading=push_sign*math.pi/2
        if self.active and self.ready_push_sign is not None and push_sign!=self.ready_push_sign:
            return self.stop('YELLOW SIDE CHANGED / RESTART AFTER CHECKING SCENE')
        px,py=field['point_px']
        def boundary_y_at(x):
            return self.base_config.field_mm - py*scale + (x-px*scale)*nx/ny

        boundary_y=boundary_y_at(self.base_config.field_mm/2)
        if not 0<boundary_y<self.base_config.field_mm:
            return self._reselect('FIELD / YELLOW DIRECTION INVALID')
        center=np.asarray(robot['center_px'],float)*scale
        hull=np.asarray(robot['body_polygon_px'],float)*scale
        center[1]=1200-center[1];hull[:,1]=1200-hull[:,1]
        heading=float(robot['heading_rad'])
        if (center.shape!=(2,) or hull.ndim!=2 or hull.shape[1]!=2 or len(hull)<3 or
                not np.isfinite(center).all() or not np.isfinite(hull).all() or not math.isfinite(heading) or
                any(not math.isfinite(b.x) or not math.isfinite(b.y) or not 10<=b.x<=1190 or not 10<=b.y<=1190 for b in blocks)):
            return self._invalid('INVALID VISUAL GEOMETRY')
        if np.any(hull<0) or np.any(hull>self.base_config.field_mm):
            return self._invalid('CAR BODY OUTSIDE FIELD')
        current={b.id:(b.x,b.y) for b in blocks}
        if len(current)!=len(blocks):
            return self._invalid('AMBIGUOUS BLOCK TRACK')
        if self.active and self.previous_pose is not None:
            p,h=self.previous_pose
            if math.dist(p,center)>50 or abs((heading-h+math.pi)%(2*math.pi)-math.pi)>.4:
                return self._reselect('ROBOT POSE JUMP')
        if self.task and self.task.target_ids[0] not in current:
            return self._reselect('TARGET LOST / RESELECT')
        self.previous_pose=(center.copy(),heading)
        radius=float(np.linalg.norm(hull-center,axis=1).max())+15
        forward=np.array([math.cos(heading),math.sin(heading)])
        front=float(np.max((hull-center)@forward))
        width=float(np.ptp((hull-center)@np.array([-forward[1],forward[0]])))
        for b in blocks:
            if self.task and b.id in self.task.target_ids and self.state in ('PUSH','RELEASE'):
                continue
            if cv2.pointPolygonTest(np.float32(hull),(b.x,b.y),True)>=-10:
                return self._invalid('BLOCK OVERLAPS CAR')
        if not self.active:
            self.ready_push_sign=push_sign
            if not blocks:
                return self._waiting('WAIT FOR BLOCK DETECTION')
            self._waiting('READY / SPACE: START DELIVERY')
            self.last_plan['can_start']=True
            return self.last_plan
        if self.runtime is None:
            cfg=replace(self.base_config,target_half='lower' if push_sign<0 else 'upper',
                boundary_y_mm=boundary_y,pusher_width_mm=width,
                front_offset_mm=front,body_margin_mm=radius,approach_gap_mm=max(50,radius-front+35),
                quick_depth_mm=40,safe_depth_mm=60,deep_depth_mm=80,capture_limit=1)
            self.runtime=StrategyRuntime(cfg,now)
            self.started_at=now;self.progress_at=now;self.best_cost=math.inf
        cfg=self.runtime.planner.config
        paths={}

        def reachable(choice):
            a=np.array(choice.approach_mm)
            end=np.array(choice.push_to_mm)
            if any(b.id not in choice.target_ids and segment_distance(np.array([b.x,b.y]),a,end)<radius+15 for b in blocks):
                return False
            path=route(center,choice.approach_mm,blocks,radius)
            if not path:
                return False
            paths[tuple(choice.approach_mm)]=path
            return True

        decision=self.runtime.decide(Observation(Pose(*center,heading),captured_at,blocks,captured_at,False),
                                     Feedback(link_at,self.completed),now,
                                     feasible=reachable if self.state=='SELECT' else None)
        if decision.action=='STOP':
            return self.stop('STRATEGY STOP: '+decision.reason)
        if self.state=='SELECT':
            if not blocks:
                return self._waiting('WAIT FOR BLOCK DETECTION')
            pending=[b for b in blocks if push_sign*(b.y-boundary_y_at(b.x))<=cfg.block_half_mm]
            if not pending:
                return self.stop('ALL OBSERVED BLOCKS INSIDE YELLOW',done=True)
            if decision.action=='WAIT' or len(decision.target_ids)!=1:
                return self.stop('NO REACHABLE BLOCK / CLEAR APPROACH AREA')
            self.task=decision;self.path=paths[tuple(decision.approach_mm)]
            self.state='APPROACH';self.progress_at=now;self.best_cost=math.inf
            return self.plan('stop','TASK SELECTED',self.path[0])
        target=next(b for b in blocks if b.id==self.task.target_ids[0])
        point=np.array([target.x,target.y])
        heading_error=(push_heading-heading+math.pi)%(2*math.pi)-math.pi
        if self.state=='APPROACH':
            goal=np.array(self.path[0]);distance=math.dist(center,goal)
            if distance<=15:
                self.path.pop(0)
                self.best_cost=math.inf;self.progress_at=now
                if not self.path:
                    self.state='ALIGN';self.best_cost=math.inf;self.progress_at=now
                return self.plan('stop','WAYPOINT REACHED')
            if any(segment_distance(np.array([b.x,b.y]),center,goal)<radius+15 for b in blocks):
                return self.stop('APPROACH PATH NOW BLOCKED')
            error=(math.atan2(goal[1]-center[1],goal[0]-center[0])-heading+math.pi)%(2*math.pi)-math.pi
            cost=distance+radius*abs(error)
            command='left' if error>.10 else 'right' if error<-.10 else 'forward'
        elif self.state=='ALIGN':
            error=heading_error
            cost=radius*abs(error)
            goal=point
            if abs(error)<=.06:
                self.state='PUSH';self.best_cost=math.inf;self.progress_at=now
                return self.plan('stop','ALIGNED / START PUSH')
            command='left' if error>0 else 'right'
        elif self.state=='PUSH':
            goal=np.array(self.task.push_to_mm)
            if any(b.id!=target.id and segment_distance(np.array([b.x,b.y]),center,goal)<radius+15 for b in blocks):
                return self.stop('PUSH CORRIDOR BLOCKED / SEPARATE BLOCKS')
            error=abs(heading_error)
            if error>.14 or abs(center[0]-point[0])>15:
                return self.stop('PUSH LINE / HEADING DRIFT')
            delivery_depth=push_sign*(point[1]-boundary_y_at(point[0]))
            if delivery_depth>=30:
                reverse_distance=max(80,radius+45-front-cfg.block_half_mm)
                self.state='RELEASE';self.release_goal=center+np.array([0.,-push_sign*reverse_distance])
                self.best_cost=math.inf;self.progress_at=now;self.verify_since=None
                return self.plan('stop','VISUAL DELIVERY REACHED / REVERSE NEXT')
            if push_sign*(center[1]-goal[1])>=0:
                return self._reselect('PUSH TRAVEL COMPLETE / RESELECT')
            cost=math.dist(center,goal)+30-delivery_depth
            command='forward'
        else:  # RELEASE: reverse by observed displacement, then verify the block.
            goal=self.release_goal
            if push_sign*(point[1]-boundary_y_at(point[0]))<30:
                return self._reselect('DELIVERED BLOCK LEFT YELLOW / RESELECT')
            if abs(center[0]-goal[0])>15 or abs(heading_error)>.14:
                return self.stop('RELEASE DRIFT')
            if math.dist(center,goal)<=10:
                if self.verify_since is None:
                    self.verify_since=now
                if now-self.verify_since>=.5:
                    self.verified.add(target.id);self.completed+=1
                    self.task=None
                    if self.one_delivery:
                        return self.stop('ONE BLOCK VERIFIED',done=True)
                    self.state='SELECT'
                return self.plan('stop','VERIFY RELEASE / YELLOW POSITION')
            if any(b.id!=target.id and segment_distance(np.array([b.x,b.y]),center,goal)<radius+15 for b in blocks):
                return self.stop('REVERSE PATH BLOCKED')
            cost=math.dist(center,goal);command='backward'
        if cost<self.best_cost-3:
            self.best_cost=cost;self.progress_at=now
        elif now-self.progress_at>4:
            return self.stop('NO VISUAL PROGRESS')
        return self.plan(command,self.state+' / YELLOW DELIVERY',goal)
