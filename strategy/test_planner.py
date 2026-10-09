from dataclasses import replace
from math import pi
import unittest

from planner import Block, Config, Planner, Pose, World


def base(t=0, **kwargs):
    world = World(t, Pose(600, 800), (Block("a", 550, 610), Block("b", 650, 610)))
    return replace(world, **kwargs)


class StrategyChecks(unittest.TestCase):
    def test_phases_and_shorter_endgame_delivery(self):
        p = Planner()
        opening = p.tick(base())
        middle = p.tick(base(20))
        end = p.tick(base(77))
        self.assertEqual([opening.phase, middle.phase, end.phase], ["OPENING", "MIDGAME", "ENDGAME"])
        self.assertEqual(end.delivery, "QUICK_CROSS")
        self.assertLess(end.estimated_s, opening.estimated_s)
        self.assertEqual(p.tick(base(88)).action, "STOP")
        self.assertEqual(p.tick(base(89)).phase, "FINISHED")

    def test_early_midgame(self):
        self.assertEqual(Planner().tick(base(completed_pushes=2)).phase, "MIDGAME")
        self.assertEqual(Planner().tick(base(opening_disrupted=True)).phase, "MIDGAME")

    def test_safety_overrides_lock(self):
        for change in ({"pose_age_s": 0.51}, {"blocks_age_s": 0.51}, {"link_age_s": 0.31},
                       {"collision_risk": True}, {"jammed": True}, {"emergency_stop": True},
                       {"opponent": Pose(610, 810)}, {"opponent": Pose(100, 100), "opponent_age_s": 0.6}):
            p = Planner()
            self.assertEqual(p.tick(base()).action, "CAPTURE")
            self.assertEqual(p.tick(base(0.1, **change)).action, "STOP", change)

    def test_invalid_inputs_and_clock(self):
        self.assertEqual(Planner().tick(base(robot=Pose(float("nan"), 800))).action, "STOP")
        self.assertEqual(Planner().tick(base(blocks=(Block("a", 500, 600), Block("a", 600, 600)))).action, "STOP")
        p = Planner()
        p.tick(base(20))
        self.assertEqual(p.tick(base(19)).action, "STOP")
        with self.assertRaises(ValueError):
            Config(target_half="blue")

    def test_no_target_and_too_late(self):
        self.assertEqual(Planner().tick(base(blocks=())).action, "WAIT")
        self.assertEqual(Planner().tick(base(87.5)).action, "WAIT")
        self.assertEqual(Planner().tick(base(77, blocks=(Block("a", 600, 980),))).action, "WAIT")

    def test_direction_mirrors_coordinates(self):
        lower = Planner().tick(base())
        upper = Planner(Config(target_half="upper")).tick(base(robot=Pose(600, 400, pi / 2),
                    blocks=(Block("a", 550, 590), Block("b", 650, 590))))
        self.assertEqual(lower.target_ids, upper.target_ids)
        self.assertAlmostEqual(lower.push_to_mm[1] + upper.push_to_mm[1], 1200)
        self.assertAlmostEqual(lower.estimated_s, upper.estimated_s)

    def test_recapture_after_loss_and_do_not_chase_active_push(self):
        p = Planner()
        p.tick(base(20, blocks=(Block("a", 600, 300),)))
        self.assertEqual(p.tick(base(21, blocks=(Block("a", 600, 620),))).action, "RECAPTURE")
        self.assertEqual(p.tick(base(21.1, blocks=(Block("a", 600, 620),), opponent_pushing_ids=("a",))).action, "WAIT")

    def test_secure_only_threatened_shallow_blocks(self):
        shallow = (Block("a", 600, 520),)
        self.assertEqual(Planner().tick(base(20, blocks=shallow)).action, "WAIT")
        decision = Planner().tick(base(20, blocks=shallow, opponent=Pose(900, 530)))
        self.assertEqual(decision.action, "SECURE")
        self.assertEqual(Planner().tick(base(20, blocks=(Block("a", 600, 250),), opponent=Pose(900, 530))).action, "WAIT")

    def test_avoid_opponent_race(self):
        decision = Planner().tick(base(20, opponent=Pose(610, 620)))
        self.assertEqual(decision.action, "WAIT")

    def test_do_not_push_through_opponent_or_excluded_block(self):
        self.assertEqual(Planner().tick(base(20, opponent=Pose(600, 450))).action, "WAIT")
        world = base(20, blocks=(Block("a", 600, 620), Block("b", 600, 550)), opponent_pushing_ids=("b",))
        self.assertEqual(Planner().tick(world).action, "WAIT")

    def test_short_delivery_preserves_existing_safe_blocks(self):
        decision = Planner().tick(base(20, blocks=(Block("a", 600, 620), Block("safe", 650, 300))))
        self.assertEqual(decision.target_ids, ("a",))
        self.assertEqual(decision.delivery, "QUICK_CROSS")
        self.assertAlmostEqual(600 - decision.push_to_mm[1] + 120 + 10, 120)

    def test_opening_prefers_front_and_corridor_is_not_overwide(self):
        blocks = tuple(Block(str(i), x, 610) for i, x in enumerate((250, 400, 550, 700, 850, 1000)))
        decision = Planner().tick(base(blocks=blocks))
        selected = [b.x for b in blocks if b.id in decision.target_ids]
        self.assertLessEqual(max(selected) - min(selected), 290)
        self.assertLessEqual(abs(decision.approach_mm[0] - 600), 150)

    def test_lock_survives_jitter_but_not_lost_target(self):
        p = Planner()
        first = p.tick(base())
        second = p.tick(base(0.1, blocks=(Block("a", 552, 610), Block("b", 652, 610))))
        self.assertEqual(first.target_ids, second.target_ids)
        self.assertEqual(p.tick(base(0.2, blocks=())).action, "WAIT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
