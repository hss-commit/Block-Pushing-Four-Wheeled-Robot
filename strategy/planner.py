"""Three-phase tactical decisions. Returns goals, never motor commands.

Positions: millimetres, origin lower-left; heading: radians from +x, CCW.
Input block IDs must come from confirmed, persistent tracking.
"""
from dataclasses import dataclass, replace
import json
from math import hypot, isfinite, pi
from pathlib import Path


@dataclass(frozen=True)
class Config:
    target_half: str = "lower"
    field_mm: float = 1200
    match_s: float = 90
    opening_s: float = 18
    opening_pushes: int = 2
    endgame_remaining_s: float = 15
    stop_remaining_s: float = 2
    pusher_width_mm: float = 350
    side_margin_mm: float = 20
    front_offset_mm: float = 120
    body_margin_mm: float = 100
    block_half_mm: float = 10
    approach_gap_mm: float = 40
    quick_depth_mm: float = 120
    safe_depth_mm: float = 300
    deep_depth_mm: float = 420
    near_line_mm: float = 160
    secure_extra_mm: float = 50
    travel_speed_mm_s: float = 300
    push_speed_mm_s: float = 250
    turn_speed_rad_s: float = 1
    detour_factor: float = 1.5
    align_s: float = 1
    release_s: float = 1
    opponent_speed_mm_s: float = 250
    opponent_radius_mm: float = 100
    race_margin_s: float = 0.7
    threat_distance_mm: float = 350
    collision_distance_mm: float = 150
    pose_timeout_s: float = 0.5
    blocks_timeout_s: float = 0.5
    opponent_timeout_s: float = 0.5
    link_timeout_s: float = 0.3
    target_lock_s: float = 0.8
    opening_lateral_penalty: float = 1.5

    def __post_init__(self):
        if self.target_half not in ("lower", "upper"):
            raise ValueError("target_half must be lower or upper")
        for name, value in vars(self).items():
            if name != "target_half" and (not isinstance(value, (int, float)) or not isfinite(value) or value <= 0):
                raise ValueError(f"Invalid config: {name}")
        if not (self.stop_remaining_s < self.endgame_remaining_s < self.match_s - self.opening_s):
            raise ValueError("Phase times overlap")
        if not (self.quick_depth_mm < self.safe_depth_mm <= self.deep_depth_mm < self.field_mm / 2):
            raise ValueError("Invalid delivery depths")
        if self.pusher_width_mm <= 2 * (self.side_margin_mm + self.block_half_mm):
            raise ValueError("No usable capture width")
        if self.pusher_width_mm + 2 * self.side_margin_mm >= self.field_mm or self.detour_factor < 1:
            raise ValueError("Invalid geometry or travel estimate")

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    heading: float = -pi / 2


@dataclass(frozen=True)
class Block:
    id: str
    x: float
    y: float


@dataclass(frozen=True)
class World:
    elapsed_s: float
    robot: Pose
    blocks: tuple[Block, ...]
    pose_age_s: float = 0
    blocks_age_s: float = 0
    link_age_s: float = 0
    opponent: Pose | None = None
    opponent_age_s: float = 0
    opponent_pushing_ids: tuple[str, ...] = ()
    completed_pushes: int = 0  # Cumulative count supplied by the action executor.
    opening_disrupted: bool = False
    collision_risk: bool = False  # Footprint/path supervisor can interrupt any phase.
    jammed: bool = False
    emergency_stop: bool = False


@dataclass(frozen=True)
class Decision:
    phase: str
    action: str
    reason: str
    target_ids: tuple[str, ...] = ()
    delivery: str | None = None
    approach_mm: tuple[float, float] | None = None
    push_to_mm: tuple[float, float] | None = None
    heading_rad: float | None = None
    estimated_s: float = 0
    score: float = 0
    requires_path_check: bool = True


def distance(a, b):
    return hypot(a.x - b.x, a.y - b.y)


def revise_task_for_endgame(config, task, robot, execution_state):
    """Shared policy for a task already executing when ENDGAME begins.

    The real executor and the simulator must both apply this transition.
    Geometry, motion and release completion still belong to the executor.
    """
    if execution_state in ("APPROACH", "ALIGN"):
        return "REPLAN", None
    if execution_state == "RELEASE":
        return "CONTINUE", task
    if execution_state != "PUSH":
        return "REPLAN", None
    sign = -1 if config.target_half == "lower" else 1
    y = config.field_mm / 2 + sign * (config.quick_depth_mm - config.front_offset_mm - config.block_half_mm)
    if sign * (y - robot.y) <= 0:
        return "RELEASE", task
    return "CONTINUE", replace(task, phase="ENDGAME", delivery="QUICK_CROSS", push_to_mm=(robot.x, y))


class Planner:
    def __init__(self, config=None):
        self.config = config or Config()
        self.phase = "OPENING"
        self.last_time = -1.0
        self.previous_depth = {}
        self.lost_ids = set()
        self.lock_ids = ()
        self.lock_until = 0.0

    def depth(self, y):
        sign = -1 if self.config.target_half == "lower" else 1
        return sign * (y - self.config.field_mm / 2)

    def _stop(self, reason):
        self.lock_ids = ()
        return Decision(self.phase, "STOP", reason)

    def _valid(self, world):
        c = self.config
        numbers = [world.elapsed_s, world.pose_age_s, world.blocks_age_s,
                   world.link_age_s, world.opponent_age_s, world.completed_pushes]
        if any(not isinstance(n, (int, float)) or not isfinite(n) or n < 0 for n in numbers):
            return False
        if any(not isinstance(b.id, str) or not b.id for b in world.blocks):
            return False
        if world.elapsed_s < self.last_time or len({b.id for b in world.blocks}) != len(world.blocks):
            return False
        positions = [world.robot, *world.blocks] + ([world.opponent] if world.opponent else [])
        for p in positions:
            if not all(isinstance(v, (int, float)) and isfinite(v) and 0 <= v <= c.field_mm for v in (p.x, p.y)):
                return False
        return all(isinstance(p.heading, (int, float)) and isfinite(p.heading)
                   for p in (world.robot, world.opponent) if p is not None)

    def tick(self, world):
        c = self.config
        if not self._valid(world):
            return self._stop("输入数据无效或时间倒退")
        self.last_time = world.elapsed_s
        remaining = c.match_s - world.elapsed_s
        old_phase = self.phase
        if remaining <= c.stop_remaining_s:
            self.phase = "FINISHED"
        elif self.phase != "FINISHED":
            if remaining <= c.endgame_remaining_s:
                self.phase = "ENDGAME"
            elif self.phase == "OPENING" and (world.elapsed_s >= c.opening_s or
                    world.completed_pushes >= c.opening_pushes or world.opening_disrupted):
                self.phase = "MIDGAME"
        if self.phase != old_phase:
            self.lock_ids = ()
        if self.phase == "FINISHED":
            return self._stop("进入赛末停车时间")
        if world.emergency_stop or world.jammed or world.collision_risk:
            return self._stop("急停、卡住或碰撞风险；中止本次目标")
        if world.pose_age_s > c.pose_timeout_s or world.blocks_age_s > c.blocks_timeout_s:
            return self._stop("视觉数据过期，等待重新确认")
        if world.link_age_s > c.link_timeout_s:
            return self._stop("通信状态过期")
        if world.opponent and world.opponent_age_s > c.opponent_timeout_s:
            return self._stop("对手位置过期，不能继续按旧位置规划")
        if world.opponent and distance(world.robot, world.opponent) < c.collision_distance_mm:
            return self._stop("对手距离过近")

        ids = {b.id for b in world.blocks}
        self.lost_ids.intersection_update(ids)
        for block in world.blocks:
            progress = self.depth(block.y)
            if self.previous_depth.get(block.id, -1) > c.block_half_mm and progress <= 0:
                self.lost_ids.add(block.id)
            if progress >= c.safe_depth_mm:
                self.lost_ids.discard(block.id)
        self.previous_depth = {b.id: self.depth(b.y) for b in world.blocks}

        candidates = list(self._candidates(world, remaining))
        if not candidates:
            self.lock_ids = ()
            return Decision(self.phase, "WAIT", "没有可在剩余时间内完成的合适目标")
        best = max(candidates, key=lambda choice: choice.score)
        locked = next((choice for choice in candidates if choice.target_ids == self.lock_ids), None)
        if locked and world.elapsed_s < self.lock_until and locked.score >= best.score * 0.5:
            return locked
        if best.target_ids != self.lock_ids:
            self.lock_until = world.elapsed_s + c.target_lock_s
        self.lock_ids = best.target_ids
        return best

    def _candidates(self, world, remaining):
        c = self.config
        sign = -1 if c.target_half == "lower" else 1
        opponent = world.opponent
        eligible = [b for b in world.blocks if b.id not in world.opponent_pushing_ids and (
            self.depth(b.y) <= c.block_half_mm or
            (self.phase != "OPENING" and self.depth(b.y) < c.near_line_mm and opponent and
             distance(b, opponent) < c.threat_distance_mm))]
        half_width = c.pusher_width_mm / 2 - c.side_margin_mm - c.block_half_mm
        side_clearance = c.pusher_width_mm / 2 + c.side_margin_mm
        centers = {world.robot.x, *(b.x for b in eligible)}
        centers.update((a.x + b.x) / 2 for a in eligible for b in eligible
                       if abs(a.x - b.x) <= 2 * half_width)
        for center in sorted(centers):
            if not side_clearance <= center <= c.field_mm - side_clearance:
                continue
            targets = [b for b in eligible if abs(b.x - center) <= half_width]
            if not targets:
                continue
            foreign = [b for b in targets if self.depth(b.y) <= c.block_half_mm]
            if self.phase == "ENDGAME" and len(targets) == 1 and self.depth(targets[0].y) < -c.safe_depth_mm:
                continue
            action = "RECAPTURE" if any(b.id in self.lost_ids for b in foreign) else "CAPTURE" if foreign else "SECURE"
            threatened = opponent is not None and min(distance(b, opponent) for b in targets) < c.threat_distance_mm
            if self.phase == "ENDGAME" or (threatened and action != "SECURE"):
                delivery, goal_depth = "QUICK_CROSS", c.quick_depth_mm
            elif action == "SECURE" and len(targets) >= 3:
                delivery, goal_depth = "DEEP_SECURE", c.deep_depth_mm
            else:
                delivery, goal_depth = "SAFE_DEPTH", c.safe_depth_mm
            # Never move an already-acquired block back toward the middle.
            goal_depth = max(goal_depth, max(self.depth(b.y) for b in targets) + c.secure_extra_mm)
            first_depth = min(self.depth(b.y) for b in targets)
            target_ids = {b.id for b in targets}
            blockers = [b for b in world.blocks if b.id not in target_ids and abs(b.x - center) <= half_width and
                        first_depth - c.block_half_mm <= self.depth(b.y) <= goal_depth + c.block_half_mm]
            if blockers:
                # Keep already-delivered blocks undisturbed by shortening this delivery.
                short_depth = max(c.quick_depth_mm, max(self.depth(b.y) for b in targets) + c.secure_extra_mm)
                if short_depth >= goal_depth or any(self.depth(b.y) <= short_depth + c.block_half_mm for b in blockers):
                    continue
                goal_depth, delivery = short_depth, "QUICK_CROSS"
            behind_depth = first_depth - c.front_offset_mm - c.block_half_mm - c.approach_gap_mm
            end_depth = goal_depth - c.front_offset_mm - c.block_half_mm
            behind = Pose(center, c.field_mm / 2 + sign * behind_depth)
            end = Pose(center, c.field_mm / 2 + sign * end_depth)
            if any(not c.body_margin_mm <= p.y <= c.field_mm - c.body_margin_mm for p in (behind, end)):
                continue
            if goal_depth + c.block_half_mm + c.side_margin_mm > c.field_mm / 2:
                continue
            if opponent:
                nearest_y = max(min(behind.y, end.y), min(opponent.y, max(behind.y, end.y)))
                clearance = c.pusher_width_mm / 2 + c.opponent_radius_mm + c.side_margin_mm
                if hypot(opponent.x - center, opponent.y - nearest_y) <= clearance:
                    continue  # Known opponent overlaps the straight push corridor.
            heading = sign * pi / 2
            turn = abs((heading - world.robot.heading + pi) % (2 * pi) - pi)
            approach_s = distance(world.robot, behind) * c.detour_factor / c.travel_speed_mm_s
            approach_s += turn / c.turn_speed_rad_s + c.align_s
            if opponent and foreign:
                opponent_eta = min(distance(b, opponent) for b in foreign) / c.opponent_speed_mm_s
                if opponent_eta <= approach_s + c.race_margin_s:
                    continue  # Do not enter a race we cannot conservatively win.
            push_s = (end_depth - behind_depth) / c.push_speed_mm_s
            duration = approach_s + push_s + c.release_s
            if duration > remaining - c.stop_remaining_s:
                continue
            # ponytail: time is a conservative heuristic, not a collision-free route.
            # The executor must recompute feasibility after actual path planning.
            value = len(foreign) + 0.7 * (len(targets) - len(foreign))
            if self.phase == "OPENING":
                value /= 1 + c.opening_lateral_penalty * abs(center - world.robot.x) / c.pusher_width_mm
            reposition_s = 0 if self.phase == "ENDGAME" else (
                abs(end_depth - behind_depth) * c.detour_factor + c.pusher_width_mm) / c.travel_speed_mm_s
            score = value / (duration + reposition_s)
            reasons = {"OPENING": "优先前方捕获走廊，尽早完成首轮推送",
                       "MIDGAME": "比较方块收益、接近耗时和对手到达时间",
                       "ENDGAME": "剩余时间内短推入区，预留释放及停车时间"}
            yield Decision(self.phase, action, reasons[self.phase], tuple(sorted(b.id for b in targets)),
                           delivery, (behind.x, behind.y), (end.x, end.y), heading, duration, score)
