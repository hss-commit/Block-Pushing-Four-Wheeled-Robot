"""One block per task, shared competition selection, visually verified delivery.

Controlled empty-field bench test with bounded contact transport and visual verification.
"""
from dataclasses import replace
from heapq import heappop, heappush
import math

import cv2
import numpy as np

from control.approach_control import segment_distance
from strategy.planner import Block, Config, Decision, Pose
from strategy.runtime import Feedback, Observation, StrategyRuntime


class MovingBlocks:
    """Only visible, uniquely associated detections get persistent IDs."""
    TRACK_WINDOW_SECONDS = .75
    MATCH_MARGIN_MM = 5

    def __init__(self):
        self.previous = {}
        self.last_seen = {}
        self.counter = 0
        self.regions = {}

    def update(self, regions, captured_at=None, *, association_hints=None):
        current = {}
        previous = self.previous
        if captured_at is not None:
            previous = {key: point for key,point in previous.items()
                        if captured_at-self.last_seen.get(key,captured_at)<=self.TRACK_WINDOW_SECONDS}
        counter = self.counter
        hints=association_hints or {}
        association={**previous,**hints}
        for region in regions:
            point = (float(region['x_mm']), float(region['y_mm']))
            matches = sorted((math.dist(point,p),key) for key,p in association.items())
            close_alternative = len(matches)>1 and matches[1][0]<=30
            if close_alternative and (captured_at is None or
                                      matches[1][0]-matches[0][0]<=self.MATCH_MARGIN_MM):
                raise ValueError('AMBIGUOUS BLOCK TRACK')
            if matches and matches[0][0]<=30:
                key = matches[0][1]
                if key in current:
                    raise ValueError('AMBIGUOUS BLOCK TRACK')
            else:
                counter += 1
                key = f'multi-{counter}'
            current[key] = point
        self.counter = counter
        self.previous = {**previous,**current} if captured_at is not None else current
        self.regions={key:region for key,region in self.regions.items() if key in self.previous or key in hints}
        self.regions.update(zip(current,regions))
        if captured_at is not None:
            self.last_seen = {key:self.last_seen.get(key,captured_at) for key in previous}
            self.last_seen.update(dict.fromkeys(current,captured_at))
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
    def __init__(self, config=None, *, one_delivery=False, field_guided=False):
        self.base_config = config or Config()
        self.one_delivery = one_delivery
        self.field_guided = field_guided
        self.active = self.finished = False
        self.state = 'PREPARE'
        self.last_plan = dict(command='stop',reason='CLICK BLOCK COLOUR',can_start=False)
        self.runtime = self.task = None
        self.completed = 0
        self.startup_pulse_used = False
        self.verified = set()
        self.previous_pose = None
        self.vision_missing_since = None
        self.ready_push_sign = None
        self.path = []
        self.approach_reverse = None
        self.reverse_approach_blocked = False
        self.release_point = None
        self.release_wait_since = None
        self.release_track_ids = set()
        self.contact_seen_at = None
        self.contact_anchor = None
        self.contact_target_id = None
        self.contact_hidden_at = None
        self.contact_best = -math.inf
        self.contact_progress_at = None
        self.target_lock = None

    def stop(self, reason, done=False):
        self.active=False;self.finished=True
        self.state='DONE' if done else 'STOPPED'
        self.last_plan={**self.last_plan,'command':'stop','reason':reason,
                        'state':self.state,'can_start':False,'completed':self.completed}
        return self.last_plan

    def rearm(self):
        self.__init__(self.base_config, one_delivery=self.one_delivery, field_guided=self.field_guided)

    def start(self):
        if self.last_plan.get('can_start') and not self.finished:
            self.active=True;self.state='SELECT'
            return True
        return False

    def _waiting(self, reason):
        self.last_plan=dict(command='stop',reason=reason,state=self.state,
                            completed=self.completed,can_start=False,
                            target_ids=list(self.task.target_ids) if self.task else
                            [self.target_lock['id']] if self.target_lock else [])
        return self.last_plan

    def _lock_target(self, block, blocks):
        if self.field_guided and self.target_lock is None:
            self.target_lock=dict(id=block.id,point=[block.x,block.y],
                                  other_ids={b.id for b in blocks if b.id!=block.id})

    def _invalid(self, reason):
        if self.active:
            return self.stop(reason)
        self.ready_push_sign=None
        return self._waiting(reason)

    def _reselect(self, reason):
        if (self.field_guided and self.active and self.state=='RELEASE' and self.task is not None and
                not reason.startswith('DELIVERED BLOCK LEFT YELLOW')):
            self.verify_since=None
            return self._waiting(reason+' / KEEP CURRENT TARGET')
        self.vision_missing_since=None
        self.contact_seen_at=None
        self.contact_anchor=None;self.contact_hidden_at=None
        self.contact_target_id=None
        if self.active:
            self.task=None
            self.path=[]
            self.previous_pose=None
            self.state='SELECT'
        return self._waiting(reason)

    def _missing_vision(self, reason, now):
        if (self.one_delivery or self.field_guided) and self.active and self.task is not None:
            if self.vision_missing_since is None:
                self.vision_missing_since=now
            if self.field_guided:
                if self.state=='RELEASE':
                    self.verify_since=None
                return self._waiting(reason+' / KEEP CURRENT TARGET')
            if now-self.vision_missing_since<=.6:
                if self.state=='RELEASE':
                    self.verify_since=None
                return self._waiting(reason+' / WAIT FOR FRESH DETECTION')
        return self._reselect(reason+' / RESELECT')

    def contact_estimate(self, robot):
        """Association hint only; never enters the observed block list."""
        if not self.active or not self.field_guided:
            return None
        if self.task is None:
            return None if self.target_lock is None else tuple(self.target_lock['point'])
        if self.state=='RELEASE' and self.release_point is not None:
            return tuple(self.release_point)
        if (self.state!='PUSH' or self.contact_anchor is None or
                self.contact_target_id!=self.task.target_ids[0]):
            return None if self.target_lock is None else tuple(self.target_lock['point'])
        if not robot.get('detected') or not robot.get('geometry_valid'):
            return None
        center=np.asarray(robot['center_px'],float)*self.base_config.field_mm/1199
        center[1]=self.base_config.field_mm-center[1]
        origin,point,_=self.contact_anchor
        return tuple(point+center-origin)

    def _begin_release(self, center, direction, radius, front, point, now):
        reverse_distance=max(80,radius+45-front-self.base_config.block_half_mm)
        self.release_direction=direction.copy()
        self.state='RELEASE';self.release_goal=center-direction*reverse_distance
        self.release_point=np.asarray(point,float).copy();self.release_wait_since=None
        self.release_track_ids={self.task.target_ids[0]}
        self.best_cost=math.inf;self.progress_at=now;self.verify_since=None

    def _carry_hidden(self, center, hull, heading, obstacles, now, push_sign, boundary_y_at, nx, ny):
        origin,last_point,start_heading=self.contact_anchor
        forward=np.array([math.cos(start_heading),math.sin(start_heading)])
        side=np.array([-forward[1],forward[0]])
        delta=center-origin
        travel=float(delta@forward)
        error=abs((heading-start_heading+math.pi)%(2*math.pi)-math.pi)
        point=last_point+delta
        if self.target_lock is not None:
            self.target_lock['point']=point.tolist()
        if self.contact_hidden_at is None:
            self.contact_hidden_at=now;self.contact_best=travel;self.contact_progress_at=now
        if error>.14 or abs(delta@side)>15 or travel<-10:
            return self._reselect('CONTACT PUSH DRIFT / REOBSERVE TARGET')
        if travel>self.contact_best+3:
            self.contact_best=travel;self.contact_progress_at=now
        elif now-self.contact_progress_at>4:
            return self._reselect('CONTACT PUSH NO CAR PROGRESS / REOBSERVE')
        front=float(np.max((hull-center)@forward))
        radius=float(np.linalg.norm(hull-center,axis=1).max())+15
        tip=center+forward*front
        tip_depth=push_sign*(tip[1]-boundary_y_at(tip[0]))
        depth_per_mm=push_sign*(forward[1]-forward[0]*nx/ny)
        if depth_per_mm<=.35:
            return self._reselect('CONTACT PUSH DIRECTION INVALID / REOBSERVE')
        # Crossing uses the push face rather than a possibly hidden block's
        # roof-plane projection. The estimate is never proof of delivery.
        if (tip_depth>=self.base_config.block_half_mm+20 or travel>=200 or
                now-self.contact_hidden_at>=20):
            self._begin_release(center,forward,radius,front,point,now)
            return self.plan('stop','CONTACT PUSH ENDED / REVERSE AND VERIFY')
        current_forward=np.array([math.cos(heading),math.sin(heading)])
        swept=cv2.convexHull(np.float32(np.vstack((hull,hull+current_forward*30))))
        margin=math.sqrt(2)*self.base_config.block_half_mm+5
        if (np.any(swept<0) or np.any(swept>self.base_config.field_mm) or
                any(cv2.pointPolygonTest(swept,(float(b.x),float(b.y)),True)>=-margin
                    for b in obstacles)):
            return self._reselect('CONTACT PUSH PATH BLOCKED / REOBSERVE')
        self.previous_pose=(center.copy(),heading)
        remaining=(self.base_config.block_half_mm+20-tip_depth)/depth_per_mm
        plan=self.plan('forward','CONTACT PUSH / CAR POSITION / BLOCK UNOBSERVED',
                       center+forward*min(remaining,200-travel))
        plan.update(block_estimated=True,estimated_block_mm=point.tolist(),
                    contact_travel_mm=round(travel,1),robot_center_mm=center.tolist(),
                    robot_heading_deg=round(math.degrees(heading),2))
        return plan

    def plan(self, command, reason, goal=None):
        self.last_plan=dict(command=command,reason=reason,state=self.state,
                            completed=self.completed,can_start=False,
                            target_ids=list(self.task.target_ids) if self.task else [])
        if goal is not None:
            self.last_plan['goal_mm']=list(map(float,goal))
        return self.last_plan

    def update(self, robot, blocks, field, captured_at, now, link_at, *, target_block_id=None,
               recent_obstacles=()):
        targets = tuple(b for b in blocks if target_block_id is None or b.id == target_block_id)
        if self.finished:
            return self.last_plan
        if (not all(math.isfinite(v) for v in (captured_at,now,link_at)) or
                not 0<=now-captured_at<=.2 or not 0<=now-link_at<=.3):
            if self.field_guided and self.active:
                return self._waiting('STALE VISION / LINK / WAIT FOR FRESH FRAME')
            return self._reselect('STALE VISION / LINK / WAIT FOR FRESH FRAME')
        if not robot.get('detected') or not robot.get('heading_valid') or not robot.get('geometry_valid'):
            reason='ROBOT MARKER / BODY LOST'
            if (self.one_delivery or self.field_guided) and self.task is not None:
                return self._missing_vision(reason,now)
            return self._reselect(reason)
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
        if self.field_guided and self.active and self.task is not None and self.target_lock is None:
            existing=next((b for b in blocks if b.id==self.task.target_ids[0]),None)
            if existing is not None:
                self._lock_target(existing,blocks)
        if self.field_guided and self.active and self.target_lock is not None:
            lock=self.target_lock
            matches=sorted((math.dist((b.x,b.y),lock['point']),b.id,b) for b in blocks
                           if b.id not in lock['other_ids'] and
                           math.dist((b.x,b.y),lock['point'])<=(60 if b.id==lock['id'] else 15))
            matched=(matches[0][2] if matches and
                     (len(matches)==1 or matches[1][0]-matches[0][0]>5) else None)
            if matched is not None:
                old_id=lock['id'];lock['id']=matched.id;lock['point']=[matched.x,matched.y]
                if self.task is not None and matched.id!=old_id:
                    self.task=replace(self.task,target_ids=(matched.id,))
                    if self.contact_target_id==old_id:
                        self.contact_target_id=matched.id
                    if self.state=='RELEASE':
                        self.release_track_ids.add(matched.id)
                targets=(matched,)
            elif self.task is None:
                return self._waiting('CURRENT BLOCK NOT VERIFIED / WAIT FOR SAME TARGET')
            else:
                targets=()
        local_release=(self.field_guided and self.state=='RELEASE')
        if local_release and self.task.target_ids[0] not in current:
            # Delivery colours often disappear against the destination floor.
            # A newly assigned ID is usable only with one nearby observation.
            matches=[b for b in blocks if math.dist((b.x,b.y),self.release_point)<=40 and
                     (self.target_lock is None or b.id not in self.target_lock['other_ids'])]
            if len(matches)==1:
                self.task=replace(self.task,target_ids=(matches[0].id,))
                self.release_track_ids.add(matches[0].id)
        task_target=self.task.target_ids[0] if self.task else None
        obstacles=tuple(blocks)+tuple(b for b in recent_obstacles
                                      if b.id not in current and b.id!=task_target and
                                      not (local_release and b.id in self.release_track_ids))
        if len(current)!=len(blocks):
            return self._invalid('AMBIGUOUS BLOCK TRACK')
        if self.active and self.previous_pose is not None:
            p,h=self.previous_pose
            if math.dist(p,center)>50 or (not self.field_guided and
                    abs((heading-h+math.pi)%(2*math.pi)-math.pi)>.4):
                return self._reselect('ROBOT POSE JUMP')
        if self.field_guided and self.vision_missing_since is not None:
            missing_time=now-self.vision_missing_since
            self.progress_at+=missing_time
            if self.contact_seen_at is not None:
                self.contact_seen_at+=missing_time
            if self.contact_hidden_at is not None:
                self.contact_hidden_at+=missing_time
            if self.contact_progress_at is not None:
                self.contact_progress_at+=missing_time
            self.vision_missing_since=None
        if self.task and self.task.target_ids[0] not in current and not local_release:
            if (self.field_guided and self.state=='PUSH' and self.contact_anchor is not None and
                    self.contact_target_id==self.task.target_ids[0] and
                    (self.contact_hidden_at is not None or now-self.contact_seen_at<=.6)):
                return self._carry_hidden(center,hull,heading,obstacles,now,push_sign,boundary_y_at,nx,ny)
            return self._missing_vision('TARGET LOST',now)
        if self.contact_hidden_at is not None and not local_release:
            self.contact_hidden_at=None;self.progress_at=now
        if self.vision_missing_since is not None:
            missing_time=now-self.vision_missing_since
            if missing_time>.6 and not self.field_guided:
                return self._reselect('VISION RECOVERY TOO LATE / RESELECT')
            self.progress_at+=missing_time
            if self.contact_hidden_at is not None:
                self.contact_hidden_at+=missing_time
            if self.contact_progress_at is not None:
                self.contact_progress_at+=missing_time
            self.vision_missing_since=None
        self.previous_pose=(center.copy(),heading)
        radius=float(np.linalg.norm(hull-center,axis=1).max())+15
        forward=np.array([math.cos(heading),math.sin(heading)])
        front=float(np.max((hull-center)@forward))
        width=float(np.ptp((hull-center)@np.array([-forward[1],forward[0]])))
        aim_at_block=self.field_guided or (self.one_delivery and target_block_id is not None)
        target_overlaps_car=False
        for b in blocks:
            if self.task and b.id in self.task.target_ids and self.state in ('PUSH','RELEASE'):
                continue
            if cv2.pointPolygonTest(np.float32(hull),(b.x,b.y),True)>=-10:
                if not aim_at_block or b.id!=task_target or self.state not in ('APPROACH','ALIGN'):
                    return self._invalid('BLOCK OVERLAPS CAR')
                target_overlaps_car=True
        if not self.active:
            self.ready_push_sign=push_sign
            if not targets:
                return self._waiting('WAIT FOR BLOCK DETECTION')
            if self.one_delivery and all(push_sign*(b.y-boundary_y_at(b.x))>self.base_config.block_half_mm
                                         for b in targets):
                return self._waiting('BLOCK ALREADY IN YELLOW / PLACE IN BLUE')
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
        heading_error=(push_heading-heading+math.pi)%(2*math.pi)-math.pi
        local_navigation=self.field_guided and not self.one_delivery
        active_target_id=self.task.target_ids[0] if self.task else target_block_id

        def rotated_hull(angle):
            cos,sin=math.cos(angle),math.sin(angle)
            return center+(hull-center)@np.array([[cos,sin],[-sin,cos]])

        def clear_turn(error):
            steps=max(1,math.ceil(abs(error)/math.radians(10)))
            padding=radius*abs(error)/(2*steps)
            for angle in np.linspace(0,error,steps+1):
                turned=rotated_hull(angle)
                if (np.any(turned<padding) or np.any(turned>cfg.field_mm-padding) or
                        any(cv2.pointPolygonTest(np.float32(turned),(float(b.x),float(b.y)),True)
                            >=-padding-cfg.block_half_mm for b in obstacles)):
                    return False
            return True

        def clear_translation(start_hull, travel, ignored_id):
            swept_hull=cv2.convexHull(np.float32(np.vstack((start_hull,start_hull+travel))))
            obstacle_margin=math.sqrt(2)*cfg.block_half_mm+5
            return (np.all(swept_hull>=0) and np.all(swept_hull<=cfg.field_mm) and
                    all(b.id==ignored_id or
                        cv2.pointPolygonTest(swept_hull,(float(b.x),float(b.y)),True)<-obstacle_margin
                        for b in obstacles))

        def forward_push_goal(target, direction=forward, ignored_id=active_target_id):
            side=np.array([-direction[1],direction[0]])
            angle=math.atan2(direction[1],direction[0])-heading
            push_hull=rotated_hull(angle)
            front_edge=(push_hull[:2]-center)@side
            offset=np.asarray(target)-center
            ahead=float(offset@direction)
            lateral=float(offset@side)
            margin=cfg.block_half_mm+5
            contact_allowance=(2*cfg.block_half_mm if self.state=='PUSH' or target_overlaps_car
                               else cfg.block_half_mm)
            if (ahead<front-contact_allowance or
                    not min(front_edge)+margin<=lateral<=max(front_edge)-margin):
                return None
            depth=push_sign*(target[1]-boundary_y_at(target[0]))
            depth_per_mm=push_sign*(direction[1]-direction[0]*nx/ny)
            if depth_per_mm<=.1:
                return None
            travel=max(0,ahead-front)+(max(0,45-depth)/depth_per_mm)
            displacement=direction*travel
            if local_navigation and (np.any(push_hull+displacement<0) or
                                     np.any(push_hull+displacement>cfg.field_mm)):
                return None
            checked_travel=(displacement*min(1,15/max(1,np.linalg.norm(displacement)))
                            if local_navigation else displacement)
            return center+displacement if clear_translation(push_hull,checked_travel,ignored_id) else None

        if self.state=='SELECT' and aim_at_block:
            chosen=None
            for block in sorted(targets,key=lambda b:math.dist(center,(b.x,b.y))):
                target=current[block.id]
                target_depth=push_sign*(target[1]-boundary_y_at(target[0]))
                if target_depth>cfg.block_half_mm:
                    continue
                direct_goal=forward_push_goal(target,ignored_id=block.id)
                if direct_goal is not None:
                    chosen=block,target,direct_goal,heading
                    break
                offset=np.asarray(target)-center
                if chosen is None and offset@forward>front:
                    bearing=math.atan2(offset[1],offset[0])
                    # A block can fit across the push face at several headings.
                    # Find one that leaves adjacent blocks outside the sweep.
                    for angle_offset in (0,10,-10,20,-20,30,-30):
                        aim_heading=bearing+math.radians(angle_offset)
                        aim_error=(aim_heading-heading+math.pi)%(2*math.pi)-math.pi
                        aim=np.array([math.cos(aim_heading),math.sin(aim_heading)])
                        direct_goal=forward_push_goal(target,aim,block.id)
                        if direct_goal is not None and (local_navigation or clear_turn(aim_error)):
                            chosen=block,target,direct_goal,aim_heading
                            break
            if chosen is not None:
                block,target,direct_goal,aim_heading=chosen
                self._lock_target(block,blocks)
                self.task=Decision('TEST','CAPTURE','DIRECT SINGLE BLOCK',
                                   target_ids=(block.id,),push_to_mm=tuple(map(float,direct_goal)),
                                   heading_rad=aim_heading)
                self.path=[]
                self.state='ALIGN';self.progress_at=now;self.best_cost=math.inf
                return self.plan('stop','AT PUSH LINE / ALIGN',target)

        if self.state=='SELECT' and local_navigation:
            pending=[b for b in targets if push_sign*(b.y-boundary_y_at(b.x))<=cfg.block_half_mm]
            if not targets:
                return self._waiting('WAIT FOR BLOCK DETECTION')
            if not pending:
                # A colour/shape dropout is not evidence that every block was
                # delivered. Keep scanning so newly visible blue blocks resume.
                return self._waiting('NO BLUE BLOCK DETECTED / KEEP SCANNING')
            block=min(pending,key=lambda b:math.dist(center,(b.x,b.y)))
            self._lock_target(block,blocks)
            # Approach behind the block without requiring an entire clear route.
            # The actual next motion is checked against the current body below.
            approach=(block.x,block.y-push_sign*(front+cfg.block_half_mm+35))
            approach=tuple(float(v) for v in np.clip(approach,front+20,cfg.field_mm-front-20))
            self.task=Decision('TEST','CAPTURE','LOCAL SINGLE BLOCK',target_ids=(block.id,),
                               approach_mm=approach,push_to_mm=(block.x,boundary_y_at(block.x)+push_sign*45),
                               heading_rad=push_heading)
            self.path=[approach]
            self.approach_reverse=None
            self.reverse_approach_blocked=False
            self.state='APPROACH';self.progress_at=now;self.best_cost=math.inf
            # Continue below and issue the first small motion in this frame.

        def reachable(choice):
            if target_block_id is not None and tuple(choice.target_ids) != (target_block_id,):
                return False
            a=np.array(choice.approach_mm)
            end=np.array(choice.push_to_mm)
            if any(b.id not in choice.target_ids and segment_distance(np.array([b.x,b.y]),a,end)<radius+15 for b in obstacles):
                return False
            path=route(center,choice.approach_mm,obstacles,radius)
            if not path:
                return False
            paths[tuple(choice.approach_mm)]=path
            return True

        decision=(Decision('TEST','WAIT','LOCAL CONTROL') if local_navigation else
                  self.runtime.decide(Observation(Pose(*center,heading),captured_at,blocks,captured_at,False),
                                     Feedback(link_at,self.completed),now,
                                     feasible=reachable if self.state=='SELECT' else None))
        if decision.action=='STOP':
            return self.stop('STRATEGY STOP: '+decision.reason)
        if self.state=='SELECT':
            if not targets:
                return self._waiting('WAIT FOR BLOCK DETECTION')
            pending=[b for b in targets if push_sign*(b.y-boundary_y_at(b.x))<=cfg.block_half_mm]
            if not pending:
                return self.stop('ALL OBSERVED BLOCKS INSIDE YELLOW',done=True)
            if decision.action=='WAIT' or len(decision.target_ids)!=1:
                plan=(self._waiting('WAITING FOR A CLEAR PUSH PATH') if self.field_guided and not self.one_delivery
                      else self.stop('NO REACHABLE BLOCK / CLEAR APPROACH AREA'))
                plan['robot_center_mm']=center.tolist()
                plan['blocking_candidates_mm']=[(b.x,b.y) for b in blocks]
                return plan
            self.task=decision;self.path=paths[tuple(decision.approach_mm)]
            self._lock_target(next(b for b in blocks if b.id==self.task.target_ids[0]),blocks)
            self.state='APPROACH';self.progress_at=now;self.best_cost=math.inf
            return self.plan('stop','TASK SELECTED',self.path[0])
        target=next((b for b in blocks if b.id==self.task.target_ids[0]),None)
        target_visible=target is not None
        if target is None:
            # Only RELEASE can reach here: the last measured delivered position
            # is for clearance, never evidence for another successful count.
            target=Block(self.task.target_ids[0],*self.release_point)
        point=np.array([target.x,target.y])
        push_goal=forward_push_goal(point) if aim_at_block and self.state in ('APPROACH','ALIGN') else None
        if target_overlaps_car and push_goal is None:
            return self._reselect('TARGET OVERLAPS CAR OUTSIDE CLEAR PUSH CORRIDOR')
        if self.state=='APPROACH':
            if push_goal is not None:
                self.path=[]
                self.state='PUSH';self.progress_at=now;self.best_cost=math.inf
                return self.plan('stop','BLOCK IN FORWARD PATH / START PUSH')
            goal=np.array(self.path[0]);distance=math.dist(center,goal)
            if distance<=15:
                self.path.pop(0)
                self.best_cost=math.inf;self.progress_at=now
                if not self.path:
                    self.state='ALIGN';self.best_cost=math.inf;self.progress_at=now
                return self.plan('stop','WAYPOINT REACHED')
            for block in (() if local_navigation else obstacles):
                clearance=radius+15
                if block.id in self.task.target_ids:
                    # Match the radius used to plan the standoff. A small
                    # detection shift must not turn that endpoint into an obstacle.
                    clearance=cfg.body_margin_mm+10
                if segment_distance(np.array([block.x,block.y]),center,goal)<clearance:
                    return self._reselect('APPROACH PATH CHANGED / REPLAN')
            error=(math.atan2(goal[1]-center[1],goal[0]-center[0])-heading+math.pi)%(2*math.pi)-math.pi
            if local_navigation:
                # A rear waypoint does not require turning the nose through
                # 180 degrees. Align the tail and approach it in reverse.
                # Choose a gear once for this waypoint. Reverse is for short
                # repositioning, not long travel across the field.
                if self.reverse_approach_blocked:
                    self.approach_reverse=False
                elif self.approach_reverse is None:
                    self.approach_reverse=(abs(error)>math.radians(100) and
                                           (distance<=max(250,2*radius) or abs(error)>=math.radians(150)))
                if self.approach_reverse:
                    error=(error+2*math.pi)%(2*math.pi)-math.pi
            cost=distance+radius*abs(error)
            tolerance=(math.radians(25) if local_navigation and self.approach_reverse else
                       math.radians(12) if local_navigation and distance>=40 else .10)
            command=('left' if error>tolerance else 'right' if error<-tolerance else
                     'backward' if local_navigation and self.approach_reverse else 'forward')
        elif self.state=='ALIGN':
            error=heading_error
            if aim_at_block:
                aim_heading=(self.task.heading_rad if self.task.approach_mm is None else
                             math.atan2(point[1]-center[1],point[0]-center[0]))
                error=(aim_heading-heading+math.pi)%(2*math.pi)-math.pi
            cost=radius*abs(error)
            goal=point
            if push_goal is not None or (not aim_at_block and abs(error)<=.06):
                self.state='PUSH';self.best_cost=math.inf;self.progress_at=now
                return self.plan('stop','ALIGNED / START PUSH')
            if aim_at_block and (abs(error)<=.06 or (not local_navigation and not clear_turn(error))):
                return self._reselect('PUSH CORRIDOR NOT CLEAR / REPLAN')
            command='left' if error>0 else 'right'
        elif self.state=='PUSH':
            goal=np.array(self.task.push_to_mm)
            offset=point-center
            side=np.array([-forward[1],forward[0]])
            # Arm slightly before the face reaches the block, so a single
            # camera interval cannot skip from visible approach to lost contact.
            if (front-40<=offset@forward<=front+2*cfg.block_half_mm+35 and
                    abs(offset@side)<=width/2-cfg.block_half_mm):
                self.contact_seen_at=now
                self.contact_anchor=(center.copy(),point.copy(),heading)
                self.contact_target_id=target.id
            else:
                self.contact_seen_at=None
                self.contact_anchor=None
            if not aim_at_block and any(b.id!=target.id and segment_distance(np.array([b.x,b.y]),center,goal)<radius+15 for b in blocks):
                return self.stop('PUSH CORRIDOR BLOCKED / SEPARATE BLOCKS')
            error=abs(heading_error)
            if not aim_at_block and (error>.14 or abs(center[0]-point[0])>15):
                return self.stop('PUSH LINE / HEADING DRIFT')
            delivery_depth=push_sign*(point[1]-boundary_y_at(point[0]))
            delivery_threshold=cfg.block_half_mm+5 if local_navigation else 30
            if delivery_depth>=delivery_threshold:
                self._begin_release(center,forward if aim_at_block else np.array([0.,float(push_sign)]),
                                    radius,front,point,now)
                return self.plan('stop','VISUAL DELIVERY REACHED / REVERSE NEXT')
            if aim_at_block:
                goal=forward_push_goal(point)
                if goal is None:
                    return self._reselect('BLOCK OUTSIDE CLEAR PUSH CORRIDOR / REPLAN')
            elif push_sign*(center[1]-goal[1])>=0:
                return self._reselect('PUSH TRAVEL COMPLETE / RESELECT')
            cost=math.dist(center,goal)+30-delivery_depth
            command='forward'
        else:  # RELEASE: reverse by observed displacement, then verify the block.
            goal=self.release_goal
            delivery_threshold=cfg.block_half_mm if local_navigation else 30
            if target_visible:
                self.release_point=point.copy()
            if target_visible and push_sign*(point[1]-boundary_y_at(point[0]))<delivery_threshold:
                return self._reselect('DELIVERED BLOCK LEFT YELLOW / RESELECT')
            release_side=np.array([-self.release_direction[1],self.release_direction[0]])
            release_turn=math.atan2(self.release_direction[1],self.release_direction[0])
            release_error=(release_turn-heading+math.pi)%(2*math.pi)-math.pi
            if abs((center-goal)@release_side)>15 or abs(release_error)>.14:
                return self.stop('RELEASE DRIFT')
            released=((center-goal)@self.release_direction<=10 if local_navigation
                      else math.dist(center,goal)<=10)
            if released:
                if self.field_guided and not target_visible:
                    self.verify_since=None
                    if self.release_wait_since is None:
                        self.release_wait_since=now
                    if now-self.release_wait_since>=.8:
                        return self._reselect('RELEASED / WAIT FOR CURRENT BLOCK VERIFICATION')
                    return self.plan('stop','RELEASED / LOOK FOR DELIVERED BLOCK')
                self.release_wait_since=None
                if self.verify_since is None:
                    self.verify_since=now
                if now-self.verify_since>=.5:
                    self.verified.add(target.id);self.completed+=1
                    self.target_lock=None
                    self.startup_pulse_used=False
                    self.task=None
                    self.path=[];self.approach_reverse=None
                    self.reverse_approach_blocked=False;self.previous_pose=None
                    if self.one_delivery:
                        return self.stop('ONE BLOCK VERIFIED',done=True)
                    self.state='SELECT'
                return self.plan('stop','VERIFY RELEASE / YELLOW POSITION')
            if aim_at_block:
                if not clear_translation(hull,goal-center,active_target_id):
                    return self.stop('REVERSE PATH BLOCKED OR OUTSIDE FIELD')
            elif any(b.id!=target.id and segment_distance(np.array([b.x,b.y]),center,goal)<radius+15 for b in blocks):
                return self.stop('REVERSE PATH BLOCKED')
            cost=math.dist(center,goal);command='backward'
        if cost<self.best_cost-3:
            self.best_cost=cost;self.progress_at=now
        elif now-self.progress_at>4:
            if local_navigation:
                return self._reselect('NO VISUAL PROGRESS / RETRY TARGET')
            return self.stop('NO VISUAL PROGRESS')
        if local_navigation and self.state in ('APPROACH','ALIGN','PUSH'):
            if command in ('left','right'):
                clear=clear_turn(.12 if command=='left' else -.12)
            else:
                direction=-forward if command=='backward' else forward
                clear=clear_translation(hull,direction*15,active_target_id if self.state=='PUSH' else None)
            if not clear:
                if self.state=='APPROACH' and self.approach_reverse:
                    self.reverse_approach_blocked=True
                    self.approach_reverse=False
                    return self.plan('stop','REVERSE APPROACH BLOCKED / USE FORWARD',goal)
                # Make space for the next correction, rather than rejecting a
                # distant goal because the full route is currently obstructed.
                if clear_translation(hull,-forward*15,None):
                    command='backward'
                else:
                    return self._waiting('NEXT STEP BLOCKED / WAIT FOR SPACE')
        plan=self.plan(command,self.state+' / YELLOW DELIVERY',goal)
        if local_navigation and command in ('left','right'):
            # The transport selects breakaway steps from observed turn response.
            # Check their larger sweep before authorizing higher power. Never
            # reset the no-progress timer merely because we sent more power.
            plan['normal_turn_clear']=clear_turn(.35 if command=='left' else -.35)
            plan['heading_error_deg']=round(math.degrees(error),2)
        if local_navigation and self.state=='APPROACH':
            plan['approach_reverse']=self.approach_reverse
            plan['heading_error_deg']=round(math.degrees(error),2)
        if local_navigation and command in ('forward','backward'):
            # 80ms at 0.04 repeatedly spends most of the cycle starting the
            # motors. Use the existing 120ms / 0.1 straight step in open space;
            # retain gentle steps for the final 25mm and all turns.
            remaining=math.dist(center,goal)
            direction=forward if command=='forward' else -forward
            ignored_id=active_target_id if self.state=='PUSH' else None
            if remaining>=25 and clear_translation(hull,direction*30,ignored_id):
                plan['standard_step']=True
        if aim_at_block and self.state=='ALIGN':
            plan['heading_error_deg']=round(math.degrees(error),2)
        if aim_at_block and self.state in ('APPROACH','ALIGN','PUSH'):
            plan['robot_center_mm']=center.tolist()
            plan['robot_heading_deg']=round(math.degrees(heading),2)
            plan['block_center_mm']=point.tolist()
            if not local_navigation and self.state=='PUSH' and now-self.progress_at>=1.5:
                plan['standard_step']=True
            if (not local_navigation and self.state=='PUSH' and not self.startup_pulse_used and
                    now-self.progress_at>=2.5 and math.dist(center,goal)>=50):
                plan['startup_pulse']=True
        return plan
