"""One manually aligned push and return to the starting position."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Target:
    x: float
    y: float


class FrameBlocks:
    """Each frame is independent. The scene contains one block."""
    def update(self, regions):
        return tuple(Target(float(r['x_mm']), float(r['y_mm'])) for r in regions)


class StraightPush:
    def __init__(self, config):
        self.config = config
        self.rearm()

    def rearm(self):
        self.active = self.finished = False
        self.state = 'PREPARE'
        self.completed = 0
        self.last_now = None
        self.origin = self.forward = self.line = None
        self.started_at = self.verify_since = None
        self._waiting('CLICK BLOCK COLOUR')

    def _plan(self, reason, command='stop', ready=False):
        self.last_plan = dict(command=command, reason=reason, state=self.state,
                              completed=self.completed, can_start=ready)
        return self.last_plan

    def _waiting(self, reason):
        return self._plan(reason)

    def stop(self, reason, done=False):
        self.active, self.finished = False, True
        self.state = 'DONE' if done else 'STOPPED'
        return self._plan(reason)

    def _invalid(self, reason):
        return self.stop(reason) if self.active else self._waiting(reason)

    def start(self):
        if self.finished or not self.last_plan['can_start']:
            return False
        self.active = True
        self.state = 'PUSH'
        self.started_at = self.last_now
        return True

    def update(self, robot, blocks, field, captured_at, now, link_at):
        if self.finished:
            return self.last_plan
        self.last_now = now
        if not (0 <= now-captured_at <= .2 and 0 <= now-link_at <= .3):
            return self._invalid('STALE CAMERA / CAR REPLY')
        if not all(robot.get(k) for k in ('detected', 'heading_valid', 'geometry_valid')):
            return self._invalid('CAR MARKER / BODY LOST')
        scale = self.config.field_mm / 1199
        robot_x, robot_y = robot['center_px']
        x, y = robot_x*scale, self.config.field_mm-robot_y*scale
        angle = float(robot['heading_rad'])
        fx, fy = math.cos(angle), math.sin(angle)
        hull = [(hx*scale, self.config.field_mm-hy*scale)
                for hx, hy in robot['body_polygon_px']]
        if any(not 60 <= coord <= self.config.field_mm-60 for point in hull for coord in point):
            return self._invalid('CAR TOO CLOSE TO EDGE')
        if len(blocks) > 1:
            return self._invalid('KEEP ONLY ONE BLOCK ON THE FIELD')
        target = blocks[0] if blocks else None

        if not self.active:
            if not field.get('valid'):
                return self._waiting('BLUE/YELLOW LINE NOT VISIBLE')
            px, py = field['point_px']
            dx, ny = field['yellow_normal']
            lx, ly, dy = px*scale, self.config.field_mm-py*scale, -ny
        else:
            lx, ly, dx, dy = self.line

        def depth(px, py):
            return (px-lx)*dx + (py-ly)*dy

        half = self.config.block_half_mm
        front_depth = max(depth(hx, hy) for hx, hy in hull)
        target_depth = depth(target.x, target.y) if target else None
        if not self.active:
            facing = fx*dx + fy*dy
            if facing < .95:
                return self._waiting('POINT CAR TOWARD YELLOW')
            front = max((hx-x)*fx + (hy-y)*fy for hx, hy in hull)
            if (target is None or target_depth > -half or
                    abs((target.x-x)*fy - (target.y-y)*fx) > 15 or
                    not -10 <= (target.x-x)*fx + (target.y-y)*fy-front-half <= 55):
                return self._waiting('PLACE ONE BLOCK DIRECTLY IN FRONT OF THE PUSHER')
            if (10-front_depth)/facing > 200:
                return self._waiting('MOVE CAR AND BLOCK CLOSER TO THE LINE')
            self.origin, self.forward = (x, y), (fx, fy)
            self.line = lx, ly, dx, dy
            return self._plan('READY / SPACE: PUSH AND RETURN', ready=True)

        if now-self.started_at > 20:
            return self.stop('20s TEST LIMIT')
        start_x, start_y = self.origin
        ax, ay = self.forward
        if abs((x-start_x)*ay - (y-start_y)*ax) > 20 or fx*ax + fy*ay < .99:
            return self.stop('CAR DRIFTED FROM PUSH LINE')
        travel = (x-start_x)*ax + (y-start_y)*ay
        if travel > 220 or travel < -20:
            return self.stop('TRAVEL LIMIT')
        if self.state == 'PUSH':
            if target and abs((target.x-start_x)*ay - (target.y-start_y)*ax) > 25:
                return self.stop('BLOCK DRIFTED FROM PUSH LINE')
            # The pusher can hide the block. Its pose can trigger the return,
            # but delivery is counted only from the block seen after stopping.
            if (target is not None and target_depth >= half+5) or front_depth >= 10:
                self.state = 'RETURN'
                return self._plan('PUSH REACHED / STOP BEFORE RETURN')
            return self._plan('PUSH TOWARD YELLOW', command='forward')
        if self.state == 'RETURN':
            if travel > 10:
                return self._plan('RETURN TO START', command='backward')
            self.state = 'VERIFY'
            self.verify_since = now
            return self._plan('RETURNED / STOP AND CHECK BLOCK')
        if now-self.verify_since >= .3 and target is not None:
            if target_depth >= half+5:
                self.completed = 1
                return self.stop('ROUND TRIP COMPLETE / BLOCK IN YELLOW', done=True)
            return self.stop('RETURNED / BLOCK NOT FULLY IN YELLOW')
        if now-self.verify_since >= 1.5:
            return self.stop('RETURNED / BLOCK NOT VISIBLE')
        return self._plan('RETURNED / CHECKING BLOCK')
