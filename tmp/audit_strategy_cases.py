"""Reproduce observed strategy gaps without modifying production behavior."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "strategy"))
from planner import Block, Config, Planner, Pose, World
from runtime import Feedback, Observation, StrategyRuntime
from simulator import Simulation

report = {}

# The capture strip is narrower than the actual pusher's contact envelope.
decision = Planner().tick(World(20, Pose(600, 800), (
    Block("target", 600, 620), Block("already-safe", 760, 400))))
assert decision.target_ids == ("target",) and decision.approach_mm[0] == 600
assert abs(760 - decision.approach_mm[0]) < 350 / 2 + 10
report["pusher_edge_unchecked"] = {
    "action": decision.action, "selected": decision.target_ids,
    "pusher_contact_half_width_mm": 185, "checked_half_width_mm": 145,
    "unselected_block_lateral_offset_mm": 160,
    "push_end_robot_center": decision.push_to_mm,
}

# A distant block in the same lateral lane invalidates the reachable near one.
near = Block("near", 600, 610)
single = Planner().tick(World(20, Pose(600, 800), (near,)))
combined = Planner().tick(World(20, Pose(600, 800), (near, Block("far", 600, 1100))))
assert single.action == "CAPTURE" and combined.action == "WAIT"
report["distant_block_hides_near_target"] = {"near_only": single.action, "near_and_far": combined.action}

# The top-ranked task fails route time checking although another task fits.
sim = Simulation()
sim.elapsed = 84
sim.blocks = [Block("near", 600, 610), Block("right1", 850, 610),
              Block("right2", 900, 610), Block("right3", 950, 610)]
decision = sim.decide()
route = sim.approach_route(decision.approach_mm)
actual = sim.route_time(route, decision)
choices = list(sim.planner._candidates(World(84, sim.robot, tuple(sim.blocks)), 6))
feasible = []
for choice in choices:
    route = sim.approach_route(choice.approach_mm)
    if route and sim.route_time(route, choice) <= 4:
        feasible.append(choice.target_ids)
sim.step(0.025)
assert actual > 4 and feasible and sim.state == "WAIT"
report["no_route_rejection_feedback"] = {
    "selected": decision.target_ids, "strategy_estimate_s": round(decision.estimated_s, 2),
    "route_estimate_s": round(actual, 2), "usable_time_s": 4,
    "other_feasible_targets": feasible, "executor_state": sim.state,
}

# Freshness is checked only after stage changes in Planner.tick.
runtime = StrategyRuntime(Config(), 100)
def observe(t):
    return Observation(Pose(600, 800), t, (Block("a", 600, 610),), t, False)
runtime.decide(observe(100), Feedback(100, 0), 100)
stale = runtime.decide(observe(100.2), Feedback(99, 2), 100.2)
recovered = runtime.decide(observe(100.3), Feedback(100.3, 0), 100.3)
assert stale.action == "STOP" and stale.phase == "MIDGAME" and recovered.phase == "MIDGAME"
report["stale_progress_changes_stage"] = {
    "stale_feedback_action": stale.action, "stale_feedback_phase": stale.phase,
    "fresh_feedback_with_zero_completions_phase": recovered.phase,
}
print(json.dumps(report, ensure_ascii=False, indent=2))
