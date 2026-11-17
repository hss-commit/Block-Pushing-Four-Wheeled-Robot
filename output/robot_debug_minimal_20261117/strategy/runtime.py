"""Shared strategy entry for simulation and future live perception/telemetry.

No camera, GUI, transport or motor imports. All timestamps must be measured on
the host computer's time.monotonic() clock. This returns goals, not velocities.
"""
from dataclasses import dataclass
from math import isfinite

if __package__:
    from .planner import Block, Config, Decision, Planner, Pose, World
else:
    from planner import Block, Config, Decision, Planner, Pose, World


@dataclass(frozen=True)
class Observation:
    robot: Pose | None
    pose_seen_at_s: float | None
    blocks: tuple[Block, ...]
    blocks_seen_at_s: float | None
    collision_risk: bool  # Required result from the scene/path safety monitor.
    opponent: Pose | None = None
    opponent_seen_at_s: float | None = None
    opponent_pushing_ids: tuple[str, ...] = ()
    opening_disrupted: bool = False


@dataclass(frozen=True)
class Feedback:
    received_at_s: float | None  # Host receive time of the most recent heartbeat.
    completed_pushes: int  # Count only after confirmed release, not a timer alone.
    jammed: bool = False
    emergency_stop: bool = False


class StrategyRuntime:
    """One instance per match. Does not start motors or fabricate missing poses."""

    def __init__(self, config: Config, started_at_s: float):
        if not self._number(started_at_s) or started_at_s < 0:
            raise ValueError("Invalid match start time")
        self.planner = Planner(config)
        self.started_at_s = started_at_s
        self.last_now_s = started_at_s
        self.completed_pushes = 0

    @staticmethod
    def _number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)

    def _stop(self, reason):
        self.planner.lock_ids = ()
        return Decision(self.planner.phase, "STOP", reason)

    def decide(self, observation: Observation, feedback: Feedback, now_s: float) -> Decision:
        if not self._number(now_s) or now_s < self.last_now_s:
            return self._stop("主机时间无效或倒退")
        self.last_now_s = now_s
        if not isinstance(feedback.completed_pushes, int) or isinstance(feedback.completed_pushes, bool) or feedback.completed_pushes < self.completed_pushes:
            return self._stop("推送完成计数无效或倒退")
        flags = (observation.collision_risk, observation.opening_disrupted,
                 feedback.jammed, feedback.emergency_stop)
        if any(type(flag) is not bool for flag in flags):
            return self._stop("安全状态必须是明确的布尔值")
        if observation.robot is None:
            return self._stop("缺少机器人位姿，不能生成运动目标")
        timestamps = [observation.pose_seen_at_s, observation.blocks_seen_at_s, feedback.received_at_s]
        if observation.opponent is not None:
            timestamps.append(observation.opponent_seen_at_s)
        if any(not self._number(stamp) or stamp < 0 or stamp > now_s for stamp in timestamps):
            return self._stop("观测或心跳时间缺失、无效或来自未来")
        # Preserve acquisition timestamps for held detections. Never freshen them
        # just because this function was called again or a packet was received.
        world = World(
            elapsed_s=now_s - self.started_at_s,
            robot=observation.robot,
            blocks=observation.blocks,
            pose_age_s=now_s - observation.pose_seen_at_s,
            blocks_age_s=now_s - observation.blocks_seen_at_s,
            link_age_s=now_s - feedback.received_at_s,
            opponent=observation.opponent,
            opponent_age_s=now_s - observation.opponent_seen_at_s if observation.opponent else 0,
            opponent_pushing_ids=observation.opponent_pushing_ids,
            completed_pushes=feedback.completed_pushes,
            opening_disrupted=observation.opening_disrupted,
            collision_risk=observation.collision_risk,
            jammed=feedback.jammed,
            emergency_stop=feedback.emergency_stop,
        )
        result = self.planner.tick(world)
        # Do not accept progress reported by an already-expired heartbeat.
        if world.link_age_s <= self.planner.config.link_timeout_s:
            self.completed_pushes = feedback.completed_pushes
        return result
