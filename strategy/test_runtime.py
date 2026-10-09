from dataclasses import replace
from math import pi
from pathlib import Path
import subprocess
import sys
import unittest

from planner import Block, Config, Planner, Pose, World, revise_task_for_endgame
from runtime import Feedback, Observation, StrategyRuntime


def observed(t=100.0):
    return Observation(Pose(600, 800, -pi / 2), t,
                       (Block("a", 550, 610), Block("b", 650, 610)), t, collision_risk=False)


class RuntimeChecks(unittest.TestCase):
    def test_strategy_imports_without_site_packages_or_gui(self):
        code = "from strategy.runtime import StrategyRuntime,Observation,Feedback; from strategy.planner import Config,Pose,Block; import sys; r=StrategyRuntime(Config(),10); o=Observation(Pose(600,800),10,(Block('a',600,610),),10,False); assert r.decide(o,Feedback(10,0),10).action=='CAPTURE'; assert 'cv2' not in sys.modules and 'numpy' not in sys.modules"
        subprocess.run([sys.executable, "-S", "-c", code], cwd=Path(__file__).resolve().parents[1], check=True)

    def test_shared_active_task_endgame_policy(self):
        config = Config()
        task = Planner(config).tick(World(0, Pose(600, 800), (Block("a", 600, 610),)))
        self.assertEqual(revise_task_for_endgame(config, task, Pose(600, 800), "APPROACH"), ("REPLAN", None))
        action, changed = revise_task_for_endgame(config, task, Pose(600, 750), "PUSH")
        self.assertEqual(action, "CONTINUE")
        self.assertEqual(changed.phase, "ENDGAME")
        self.assertEqual(changed.delivery, "QUICK_CROSS")
        self.assertEqual(revise_task_for_endgame(config, task, Pose(600, 500), "PUSH")[0], "RELEASE")
        self.assertEqual(revise_task_for_endgame(config, task, Pose(600, 500), "RELEASE"), ("CONTINUE", task))

    def test_host_timestamps_feed_identical_shared_decisions(self):
        runtime, direct = StrategyRuntime(Config(), 100), Planner()
        for elapsed in (0, 0.2, 20, 77, 88):
            observation = observed(100 + elapsed)
            via_runtime = runtime.decide(observation, Feedback(100 + elapsed, 0), 100 + elapsed)
            via_world = direct.tick(World(elapsed, observation.robot, observation.blocks))
            self.assertEqual(via_runtime, via_world)

    def test_expired_frame_is_not_refreshed_by_repeat_calls(self):
        runtime = StrategyRuntime(Config(), 100)
        self.assertEqual(runtime.decide(observed(), Feedback(100, 0), 100).action, "CAPTURE")
        self.assertEqual(runtime.decide(observed(), Feedback(100.6, 0), 100.6).action, "STOP")
        self.assertEqual(runtime.decide(observed(100.7), Feedback(100.7, 0), 100.7).action, "CAPTURE")

    def test_missing_and_future_data_stop(self):
        for obs, feedback in (
            (replace(observed(), robot=None), Feedback(100, 0)),
            (replace(observed(), pose_seen_at_s=None), Feedback(100, 0)),
            (replace(observed(), blocks_seen_at_s=None), Feedback(100, 0)),
            (replace(observed(), pose_seen_at_s=101), Feedback(100, 0)),
            (observed(), Feedback(None, 0)),
            (replace(observed(), opponent=Pose(100, 100)), Feedback(100, 0)),
            (replace(observed(), collision_risk="False"), Feedback(100, 0)),
            (replace(observed(), robot=Pose(600, 800, "south")), Feedback(100, 0)),
        ):
            self.assertEqual(StrategyRuntime(Config(), 100).decide(obs, feedback, 100).action, "STOP")

    def test_stale_heartbeat_does_not_move(self):
        result = StrategyRuntime(Config(), 100).decide(observed(101), Feedback(100, 0), 101)
        self.assertEqual(result.action, "STOP")

    def test_feedback_progress_and_time_are_monotonic(self):
        runtime = StrategyRuntime(Config(), 100)
        self.assertEqual(runtime.decide(observed(), Feedback(100, 2), 100).phase, "MIDGAME")
        self.assertEqual(runtime.decide(observed(100.1), Feedback(100.1, 1), 100.1).action, "STOP")
        self.assertEqual(runtime.decide(observed(99), Feedback(99, 2), 99).action, "STOP")

    def test_simulator_uses_runtime_entry(self):
        from simulator import Simulation
        simulation = Simulation()
        self.assertIs(simulation.planner, simulation.runtime.planner)
        original = simulation.runtime.decide
        calls = []
        def record(observation, feedback, now_s):
            calls.append((observation, feedback, now_s))
            return original(observation, feedback, now_s)
        simulation.runtime.decide = record
        simulation.step(0.1)
        self.assertGreater(len(calls), 0)
        self.assertTrue(all(obs.pose_seen_at_s == now for obs, _, now in calls))


if __name__ == "__main__":
    unittest.main(verbosity=2)
