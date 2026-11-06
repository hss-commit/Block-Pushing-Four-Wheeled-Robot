"""Bench approach executor using the SAME StrategyRuntime and Planner as simulation.

Only approaches an existing tactical goal; never pushes, detours or claims arrival
from elapsed time. Input image is rectified to 1200 square, yellow at the bottom.
"""
from dataclasses import asdict, replace
import math

import numpy as np

from strategy.planner import Block, Config, Pose
from strategy.runtime import Feedback, Observation, StrategyRuntime


class StationaryBlocks:
    """Match visible stationary blocks; reject ambiguous associations, hold no ghosts.

    This is for approach testing only; not a tracker for contact/pushed blocks.
    """
    def __init__(self):
        self.previous = {}
        self.counter = 0

    def update(self, regions):
        current = {}
        for region in regions:
            if max(region['bbox_px'][2:]) > 40:
                self.previous = {}
                raise ValueError('MERGED / OVERSIZE BLOCK')
            point = (float(region['x_mm']), float(region['y_mm']))
            matches = [key for key,p in self.previous.items() if math.dist(point,p) < 15]
            if len(matches) > 1 or (matches and matches[0] in current):
                self.previous = {}
                raise ValueError('AMBIGUOUS BLOCK TRACK')
            if matches:
                key = matches[0]
            else:
                self.counter += 1
                key = f'live-{self.counter}'
            current[key] = point
        self.previous = current
        return tuple(Block(key,*point) for key,point in current.items())


def segment_distance(point, start, end):
    delta = end-start
    length2 = float(delta@delta)
    t = min(1., max(0., float((point-start)@delta)/length2)) if length2 else 0.
    return float(np.linalg.norm(point-(start+t*delta)))


class ApproachControl:
    def __init__(self, config=None):
        self.base_config = config or Config()
        self.active = False
        self.finished = False
        self.runtime = None
        self.task = None
        self.ready_since = None
        self.signature = None
        self.anchor = None
        self.last_now = None
        self.previous_pose = None
        self.progress_at = None
        self.best_cost = None
        self.last_plan = {'command':'stop','reason':'WAIT FOR CALIBRATION','can_start':False}

    def stop(self, reason):
        self.active = False
        self.finished = True
        self.ready_since = None
        self.last_plan = {**self.last_plan,'command':'stop','reason':reason,'can_start':False}
        return self.last_plan

    def rearm(self):
        self.__init__(self.base_config)

    def start(self):
        if self.last_plan.get('can_start') and not self.finished:
            self.active = True
            self.runtime = None
            self.task = None
            self.previous_pose = None
            return True
        return False

    def update(self, robot, blocks, field, captured_at, now, link_at):
        if (not all(math.isfinite(x) for x in (now,captured_at,link_at)) or
                (self.last_now is not None and now < self.last_now) or
                not 0 <= now-captured_at <= .2 or not 0 <= now-link_at <= .3):
            return self.stop('STALE VISION / WIFI')
        self.last_now = now
        if not robot.get('detected') or not robot.get('heading_valid'):
            if self.active:
                return self.stop('ROBOT LOST / HEADING UNCERTAIN')
            self.ready_since = None
            return self._waiting('NEED ROBOT HEADING')
        if (not field.get('valid') or field['yellow_normal'][1] < .97 or
                abs(field['point_px'][1]-599.5) > 120):
            return self.stop('FIELD / YELLOW DIRECTION INVALID')
        center = np.array(robot['center_px'],float)*self.base_config.field_mm/1199
        center[1] = self.base_config.field_mm-center[1]
        pose = Pose(*center,float(robot['heading_rad']))
        raw_hull = np.array(robot['body_polygon_px'],float)*self.base_config.field_mm/1199
        raw_hull[:,1] = self.base_config.field_mm-raw_hull[:,1]
        radius = float(np.linalg.norm(raw_hull-center,axis=1).max())+20
        forward = np.array([math.cos(pose.heading),math.sin(pose.heading)])
        front = max(self.base_config.front_offset_mm,float(((raw_hull-center)@forward).max()))
        cfg = replace(self.base_config,target_half='lower',front_offset_mm=front,
                      body_margin_mm=max(self.base_config.body_margin_mm,radius),
                      approach_gap_mm=max(self.base_config.approach_gap_mm,radius-front+50))
        if not np.isfinite(center).all() or not math.isfinite(radius) or not 0 < radius < cfg.field_mm/2:
            return self.stop('INVALID ROBOT FOOTPRINT')
        if self.previous_pose is not None and self.active:
            previous_center, previous_heading = self.previous_pose
            angle = abs((pose.heading-previous_heading+math.pi)%(2*math.pi)-math.pi)
            if np.linalg.norm(center-previous_center)>80 or angle>math.radians(40):
                return self.stop('ROBOT POSE JUMP')
        self.previous_pose = (center.copy(),pose.heading)
        current_collision = min(center)<radius or max(center)>cfg.field_mm-radius
        current_collision |= any(math.dist(center,(b.x,b.y)) < radius+cfg.block_half_mm*math.sqrt(2) for b in blocks)
        observation = Observation(pose,captured_at,blocks,captured_at,bool(current_collision))
        feedback = Feedback(link_at,0)
        if self.active and self.runtime is None:
            if (self.anchor is None or np.linalg.norm(center-self.anchor[0])>10 or
                    abs((pose.heading-self.anchor[1]+math.pi)%(2*math.pi)-math.pi)>math.radians(8)):
                return self.stop('SCENE CHANGED BEFORE START')
            self.runtime = StrategyRuntime(cfg,now)
            self.started_at = now
            self.progress_at = now
            self.best_cost = None
        runtime = self.runtime if self.active else StrategyRuntime(cfg,now)
        decision = runtime.decide(observation,feedback,now)
        if decision.action == 'STOP':
            if self.active:
                return self.stop('STRATEGY STOP: '+decision.reason)
            return self._waiting('FOOTPRINT / STRATEGY STOP',decision)
        if self.finished:
            return self._waiting('TEST FINISHED / R: REARM',decision)
        if self.active:
            if now-self.started_at > 20:
                return self.stop('20s TEST LIMIT')
            if self.task is None:
                if decision.target_ids != self.signature:
                    return self.stop('TARGET CHANGED BEFORE START')
                self.task = decision
                self.target_anchors = {b.id:(b.x,b.y) for b in blocks if b.id in decision.target_ids}
            if (not self.task.target_ids or not set(self.task.target_ids) <= {b.id for b in blocks} or
                    any(math.dist((b.x,b.y),self.target_anchors[b.id])>15 for b in blocks if b.id in self.task.target_ids)):
                return self.stop('LOCKED BLOCK LOST / MOVED')
            if decision.phase != self.task.phase:
                return self.stop('PHASE CHANGED / REPLAN')
            task = self.task
        else:
            task = decision
        if task.approach_mm is None:
            return self._waiting('NO STRATEGY APPROACH GOAL',task)
        goal = np.array(task.approach_mm,float)
        # Conservative circular footprint, all observed blocks, no hidden detours.
        if (min(goal)<radius or max(goal)>cfg.field_mm-radius or
                any(segment_distance(np.array([b.x,b.y]),center,goal)<radius+cfg.block_half_mm*math.sqrt(2)
                    for b in blocks)):
            if self.active:
                return self.stop('STRAIGHT ROUTE BLOCKED')
            return self._waiting('STRAIGHT ROUTE BLOCKED',task)
        distance = float(np.linalg.norm(goal-center))
        error = (math.atan2(goal[1]-pose.y,goal[0]-pose.x)-pose.heading+math.pi)%(2*math.pi)-math.pi
        command = 'left' if error>math.radians(12) else 'right' if error < -math.radians(12) else 'forward'
        if distance<=25:
            return self.stop('APPROACH REACHED / NO PUSH') if self.active else self._waiting('ALREADY AT APPROACH',task)
        if self.active:
            cost = distance+radius*abs(error)
            if self.best_cost is None or cost<self.best_cost-8:
                self.best_cost,self.progress_at = cost,now
            elif now-self.progress_at > 4:
                return self.stop('NO VISUAL PROGRESS / STOP')
        signature = task.target_ids
        if (signature != self.signature or self.anchor is None or
                np.linalg.norm(center-self.anchor[0])>10 or
                abs((pose.heading-self.anchor[1]+math.pi)%(2*math.pi)-math.pi)>math.radians(8)):
            self.ready_since = now
            self.signature = signature
            self.anchor = (center.copy(),pose.heading)
        ready = not self.finished and self.ready_since is not None and now-self.ready_since >= .5
        self.last_plan = {'command':command,'reason':'AUTO APPROACH' if self.active else 'PREVIEW / SPACE TO START',
                          'can_start':bool(ready and not self.active),'goal_mm':goal.tolist(),
                          'distance_mm':distance,'angle_error_deg':math.degrees(error),
                          'target_ids':list(task.target_ids),'decision':asdict(task),'footprint_radius_mm':radius}
        return self.last_plan

    def _waiting(self, reason, decision=None):
        self.ready_since = None
        self.last_plan = {'command':'stop','reason':reason,'can_start':False}
        if decision:
            self.last_plan['decision'] = asdict(decision)
        return self.last_plan
