"""One visible block, straight ahead, one visually measured push; no turn commands."""
import math

import numpy as np

from strategy.planner import Config


class SinglePushControl:
    def __init__(self, config=None, distance_mm=100):
        if not math.isfinite(distance_mm) or not 20 <= distance_mm <= 150:
            raise ValueError('单次测试推送距离须为20～150mm')
        self.base_config = config or Config()
        self.distance_mm = distance_mm
        self.active = self.finished = False
        self.state = 'PREPARE'
        self.anchor = self.previous = None
        self.ready_since = self.last_now = None
        self.last_plan = {'command':'stop','reason':'CLICK A BLOCK TO SAMPLE COLOUR','can_start':False}

    def stop(self, reason, done=False):
        self.active = False
        self.finished = True
        self.state = 'DONE' if done else 'STOPPED'
        self.last_plan = {**self.last_plan,'command':'stop','reason':reason,
                          'state':self.state,'can_start':False}
        return self.last_plan

    def rearm(self):
        self.__init__(self.base_config, self.distance_mm)

    def start(self):
        # This mode starts itself once the stable-scene countdown finishes.
        return False

    def _waiting(self, reason, decision=None):
        if self.finished:
            return self.last_plan
        self.anchor = self.previous = self.ready_since = None
        self.state = 'PREPARE'
        self.last_plan = {'command':'stop','reason':reason,'state':self.state,'can_start':False}
        return self.last_plan

    def _invalid(self, reason):
        return self.stop(reason) if self.active else self._waiting(reason)

    def update(self, robot, blocks, field, captured_at, now, link_at):
        if self.finished:
            return self.last_plan
        if (not all(math.isfinite(v) for v in (captured_at,now,link_at)) or
                (self.last_now is not None and now < self.last_now) or
                not 0 <= now-captured_at <= .2 or not 0 <= now-link_at <= .3):
            return self._invalid('STALE VISION / WIFI')
        if self.last_now is not None and now-self.last_now>.35:
            self.last_now = now
            return self._invalid('VISION GAP / COUNTDOWN RESET')
        self.last_now = now
        if not robot.get('detected') or not robot.get('heading_valid'):
            return self._invalid('NEED FOUR WHEELS AND ROBOT HEADING')
        if not field.get('valid'):
            return self._invalid('FIELD CALIBRATION LOST')
        if len(blocks) != 1:
            return self._invalid('NEED EXACTLY ONE VISIBLE BLOCK')
        scale = self.base_config.field_mm / 1199
        try:
            center = np.asarray(robot['center_px'],dtype=float)*scale
            hull = np.asarray(robot['body_polygon_px'],dtype=float)*scale
            heading = float(robot['heading_rad'])
            target = np.array([blocks[0].x,blocks[0].y],dtype=float)
            if (center.shape != (2,) or hull.ndim != 2 or hull.shape[1] != 2 or len(hull)<3 or
                    not np.isfinite(center).all() or not np.isfinite(hull).all() or
                    not np.isfinite(target).all() or not math.isfinite(heading)):
                raise ValueError('invalid geometry')
        except (KeyError,TypeError,ValueError):
            return self._invalid('INVALID VISUAL GEOMETRY')
        center[1] = self.base_config.field_mm-center[1]
        hull[:,1] = self.base_config.field_mm-hull[:,1]
        forward = np.array([math.cos(heading),math.sin(heading)])
        side = np.array([-forward[1],forward[0]])
        front = float(np.max((hull-center)@forward))
        relative = target-center
        along = float(relative@forward)
        lateral = float(relative@side)
        gap = along-front-self.base_config.block_half_mm
        field_mm = self.base_config.field_mm
        if min(target) < 30 or max(target) > field_mm-30:
            return self._invalid('BLOCK TOO CLOSE TO FIELD EDGE')
        if np.any(hull < 20) or np.any(hull > field_mm-20) or front <= 0:
            return self._invalid('ROBOT TOO CLOSE TO FIELD EDGE')
        if along <= 0 or gap < -15:
            return self._invalid('BLOCK IS NOT IN FRONT / STOP')
        if not self.active and gap > 200:
            return self._waiting('PLACE ONE BLOCK WITHIN 200mm OF CAR FRONT')
        angle = abs(math.atan2(lateral,along))
        if abs(lateral)>20 or angle>math.radians(8):
            return self._invalid('ALIGN CAR WITH BLOCK / NO AUTOMATIC TURNS')

        if not self.active:
            changed = (self.anchor is None or math.dist(center,self.anchor['center'])>8 or
                       math.dist(target,self.anchor['target'])>5 or
                       abs((heading-self.anchor['heading']+math.pi)%(2*math.pi)-math.pi)>math.radians(4))
            if changed:
                self.anchor = {'center':center.copy(),'target':target.copy(),'heading':heading,
                               'forward':forward.copy(),'side':side.copy(),
                               'max_travel':max(0,gap)+self.distance_mm+30}
                self.ready_since = now
            goal = self.anchor['target']+self.distance_mm*self.anchor['forward']
            swept_end = hull+self.anchor['forward']*self.anchor['max_travel']
            if (min(goal)<30 or max(goal)>field_mm-30 or
                    np.any(swept_end<20) or np.any(swept_end>field_mm-20)):
                return self._waiting('NOT ENOUGH CLEAR FIELD FOR THIS PUSH')
            countdown = max(0.,3-(now-self.ready_since))
            self.state = 'COUNTDOWN'
            self.last_plan = {'command':'stop','reason':f'AUTO START IN {countdown:.1f}s / X CANCEL',
                              'state':self.state,'can_start':False,'goal_mm':goal.tolist(),
                              'countdown_s':countdown,'block_progress_mm':0.}
            if countdown>0:
                return self.last_plan
            self.active = True
            self.state = 'APPROACH'
            self.started_at = self.progress_at = now
            self.best_progress = 0.
            self.block_progress_at = None
            self.best_block_progress = 0.
            self.previous = None

        anchor = self.anchor
        heading_error = abs((heading-anchor['heading']+math.pi)%(2*math.pi)-math.pi)
        robot_delta = center-anchor['center']
        block_delta = target-anchor['target']
        robot_progress = float(robot_delta@anchor['forward'])
        progress = float(block_delta@anchor['forward'])
        if heading_error>math.radians(8) or abs(float(robot_delta@anchor['side']))>20:
            return self.stop('ROBOT DRIFTED / STOP')
        if abs(float(block_delta@anchor['side']))>20 or progress < -8:
            return self.stop('BLOCK LEFT PUSH LINE / STOP')
        if robot_progress < -10 or robot_progress>anchor['max_travel']:
            return self.stop('ROBOT TRAVEL LIMIT / WRONG DIRECTION')
        if self.previous is not None:
            old_center,old_target = self.previous
            if math.dist(center,old_center)>60 or math.dist(target,old_target)>25:
                return self.stop('ROBOT / BLOCK POSITION JUMP')
        self.previous = (center.copy(),target.copy())
        if progress>15 and (gap>45 or progress>robot_progress+20):
            return self.stop('BLOCK MOVED WITHOUT PLAUSIBLE CAR CONTACT')
        self.last_plan = {'command':'forward','reason':'AUTO STRAIGHT PUSH',
                          'state':self.state,'can_start':False,'goal_mm':(
                              anchor['target']+self.distance_mm*anchor['forward']).tolist(),
                          'block_progress_mm':progress,'robot_progress_mm':robot_progress,
                          'front_gap_mm':gap}
        if progress >= self.distance_mm and gap<=45 and robot_progress>=progress-20:
            return self.stop('VISUAL 100mm PUSH REACHED / STOP' if self.distance_mm==100 else
                             'VISUAL PUSH DISTANCE REACHED / STOP',done=True)
        if now-self.started_at>20:
            return self.stop('20s TEST LIMIT')
        total_progress = max(robot_progress,progress)
        if total_progress>self.best_progress+5:
            self.best_progress,self.progress_at = total_progress,now
        elif now-self.progress_at>3:
            return self.stop('NO VISUAL PROGRESS / STOP')
        if gap<=35:
            self.state = 'PUSH'
            if self.block_progress_at is None:
                self.block_progress_at = now
                self.best_block_progress = progress
            elif progress>self.best_block_progress+5:
                self.best_block_progress,self.block_progress_at = progress,now
            elif now-self.block_progress_at>2:
                return self.stop('CONTACT BUT BLOCK DID NOT MOVE / STOP')
        self.last_plan['state'] = self.state
        return self.last_plan
