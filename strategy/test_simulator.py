from dataclasses import replace
from math import hypot
import unittest

from planner import Config, Pose
from simulator import Simulation, render


class ContinuousChecks(unittest.TestCase):
    def test_whole_match_moves_blocks_and_stops(self):
        sim = Simulation()
        initial = {b.id: (b.x, b.y) for b in sim.blocks}
        for _ in range(880):
            sim.step(0.1)
        self.assertEqual([stage for _, stage in sim.history], ["OPENING", "MIDGAME", "ENDGAME", "FINISHED"])
        self.assertGreaterEqual(sim.completed, 2)
        self.assertGreater(sum(initial[b.id] != (b.x, b.y) for b in sim.blocks), 0)
        self.assertEqual(sim.state, "STOP")
        last = (sim.robot, tuple(sim.blocks))
        sim.step(2)
        self.assertEqual(last, (sim.robot, tuple(sim.blocks)))
        self.assertEqual(sim.elapsed, 90)

    def test_no_scene_teleports_and_speed_independence(self):
        sim = Simulation()
        for _ in range(500):
            previous = sim.robot
            blocks = {b.id: b for b in sim.blocks}
            sim.step(0.025)
            self.assertLessEqual(hypot(sim.robot.x - previous.x, sim.robot.y - previous.y), 300 * 0.025 + 1e-6)
            for block in sim.blocks:
                self.assertLessEqual(hypot(block.x - blocks[block.id].x, block.y - blocks[block.id].y), 250 * 0.025 + 1e-6)
        one, fast = Simulation(), Simulation()
        for _ in range(240):
            one.step(0.025)
        for _ in range(40):
            fast.step(0.15)
        self.assertAlmostEqual(one.robot.x, fast.robot.x, places=5)
        self.assertAlmostEqual(one.robot.y, fast.robot.y, places=5)
        self.assertEqual(one.blocks, fast.blocks)

    def test_dragged_block_triggers_recapture(self):
        sim = Simulation()
        sim.step(30)
        self.assertEqual(sim.current.action, "WAIT")
        sim.move_block("B4", 600, 620)
        sim.step(0.1)
        self.assertEqual(sim.current.action, "RECAPTURE")
        self.assertIn("B4", sim.current.target_ids)

    def test_live_endgame_event_and_obstacle(self):
        sim = Simulation()
        sim.step(75.5)
        sim.move_block("B8", 600, 610)
        sim.step(0.05)
        self.assertEqual(sim.current.phase, "ENDGAME")
        self.assertEqual(sim.current.delivery, "QUICK_CROSS")
        previous = sim.robot
        sim.opponent = Pose(previous.x + 30, previous.y)
        sim.scene_changed()
        sim.step(0.05)
        self.assertEqual(sim.state, "STOP")
        self.assertEqual(sim.robot, previous)

    def test_mirrored_delivery_and_reset(self):
        sim = Simulation(replace(Config(), target_half="upper"))
        sim.step(4)
        self.assertGreater(sim.completed, 0)
        delivered = [b for b in sim.blocks if b.y > 650]
        self.assertTrue(delivered)
        for block in delivered:
            self.assertAlmostEqual(block.y, 900)
        sim.reset()
        self.assertEqual(sim.elapsed, 0)
        self.assertEqual(sim.completed, 0)
        frame = render(sim)
        self.assertEqual(frame.shape, (775, 1050, 3))


if __name__ == "__main__":
    unittest.main(verbosity=2)
