"""Single, manually aligned push into the yellow half."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Target:
    x: float
    y: float


class FrameBlocks:
    """Each frame is independent. The controller follows only its chosen target."""
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
        self.origin = self.target = self.forward = self.line = None
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
        if not field.get('valid'):
            return self._invalid('BLUE/YELLOW LINE NOT VISIBLE')
        scale = 1200 / 1199
        px, py = field['point_px']
        nx, ny = field['yellow_normal']
        line = (px*scale, 1200-py*scale, nx, -ny)
        lx, ly, dx, dy = self.line if self.active else line

        def depth(x, y):
            return (x-lx)*dx + (y-ly)*dy

        robot_x, robot_y = robot['center_px']
        x, y = robot_x*scale, 1200-robot_y*scale
        angle = float(robot['heading_rad'])
        fx, fy = math.cos(angle), math.sin(angle)
        hull = [(hx*scale, 1200-hy*scale) for hx, hy in robot['body_polygon_px']]
        if any(not 20 <= coord <= 1180 for point in hull for coord in point):
            return self._invalid('CAR TOO CLOSE TO EDGE')
        half = self.config.block_half_mm
        if not self.active:
            if fx*dx + fy*dy < .95:
                return self._waiting('POINT CAR TOWARD YELLOW')
            front = max((hx-x)*fx + (hy-y)*fy for hx, hy in hull)
            candidates = [b for b in blocks if depth(b.x, b.y) < half and
                          abs((b.x-x)*fy - (b.y-y)*fx) <= 15 and
                          -10 <= (b.x-x)*fx + (b.y-y)*fy-front-half <= 55]
            if len(candidates) != 1:
                return self._waiting('PLACE ONE BLUE BLOCK DIRECTLY IN FRONT OF PUSHER')
            self.origin, self.target, self.forward = (x, y), candidates[0], (fx, fy)
            self.line = line
            return self._plan('READY / SPACE: STRAIGHT PUSH', ready=True)

        if now-self.started_at > 20:
            return self.stop('20s TEST LIMIT')
        if abs(depth(line[0], line[1])) > 20 or line[2]*dx+line[3]*dy < .97:
            return self.stop('FIELD LINE CHANGED')
        start_x, start_y = self.origin
        ax, ay = self.forward
        if abs((x-start_x)*ay - (y-start_y)*ax) > 20 or fx*ax + fy*ay < .99:
            return self.stop('CAR DRIFTED FROM PUSH LINE')
        if (x-start_x)*ax + (y-start_y)*ay > 220:
            return self.stop('220mm TRAVEL LIMIT')
        candidates = [b for b in blocks if math.hypot(b.x-self.target.x, b.y-self.target.y) <= 35]
        if len(candidates) != 1:
            return self.stop('TARGET LOST / AMBIGUOUS')
        target = candidates[0]
        self.target = target
        if abs((target.x-start_x)*ay - (target.y-start_y)*ax) > 25:
            return self.stop('BLOCK DRIFTED FROM PUSH LINE')
        if depth(target.x, target.y) >= half+10:
            self.state = 'VERIFY'
            if self.verify_since is None:
                self.verify_since = now
            if now-self.verify_since >= .4:
                self.completed = 1
                return self.stop('ONE BLOCK INSIDE YELLOW', done=True)
            return self._plan('STOPPED / VERIFY YELLOW POSITION')
        if self.verify_since is not None:
            return self.stop('BLOCK LEFT YELLOW DURING VERIFY')
        front = max((hx-x)*fx + (hy-y)*fy for hx, hy in hull)
        width = max(abs((hx-x)*fy - (hy-y)*fx) for hx, hy in hull)
        for b in blocks:
            if b is target:
                continue
            ahead = (b.x-x)*fx + (b.y-y)*fy
            side = abs((b.x-x)*fy - (b.y-y)*fx)
            if front-half <= ahead <= front+90 and side <= width+half:
                return self.stop('ANOTHER BLOCK IN PUSH LANE')
        return self._plan('STRAIGHT PUSH', command='forward')
