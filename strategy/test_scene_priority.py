import unittest

from strategy.scene_priority import rank_scene, priority_markdown


FIELD = {"valid": True, "point_px": [500, 500], "yellow_normal": [0, -1],
         "polygon_px": [[0, 0], [1000, 0], [1000, 1000], [0, 1000]]}


def region(x, y, half="blue", width=20, height=20, area=400):
    return {"bbox_px": [x-(width-1)/2, y-(height-1)/2, width, height], "area_px": area, "half": half}


class ScenePriorityChecks(unittest.TestCase):
    def test_near_pair_beats_distant_block_in_same_lane(self):
        regions = [region(450, 550), region(550, 560), region(500, 900)]
        report = rank_scene(regions, FIELD)
        self.assertEqual(report["groups"][0]["region_ids"], [1, 2])
        self.assertFalse(report["executable"])
        self.assertFalse(report["calibrated"])
        ids = [i for g in report["groups"] for i in g["region_ids"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(regions[0]["priority"], 1)

    def test_same_lane_does_not_mean_unlimited_width(self):
        regions = [region(220, 550), region(450, 550), region(680, 550), region(900, 550)]
        report = rank_scene(regions, FIELD)
        for group in report["groups"]:
            xs = [regions[i-1]["bbox_px"][0] for i in group["region_ids"]]
            self.assertLessEqual(max(xs)-min(xs), 242)

    def test_wall_candidate_demoted_and_yellow_not_selected(self):
        report = rank_scene([region(20, 520), region(500, 620), region(850, 200, "yellow")], FIELD)
        self.assertEqual(report["groups"][0]["region_ids"], [2])
        self.assertTrue(report["groups"][-1]["geometry_risk"])
        self.assertNotIn(3, [i for g in report["groups"] for i in g["region_ids"]])

    def test_known_yellow_block_in_push_lane_prevents_candidate(self):
        report = rank_scene([region(500, 550), region(500, 450, "yellow")], FIELD)
        self.assertFalse(report["groups"])
        self.assertTrue(report["deferred"])

    def test_merged_blob_not_credited_as_six_blocks(self):
        regions = [region(500, 550, width=90, height=60, area=3000),
                   region(200, 200, "yellow"), region(400, 200, "yellow"),
                   region(600, 200, "yellow"), region(800, 200, "yellow")]
        report = rank_scene(regions, FIELD)
        self.assertTrue(regions[0]["count_uncertain"])
        self.assertEqual(report["groups"][0]["region_count"], 1)
        self.assertIsNone(report["groups"][0]["actual_block_count"])
        self.assertIn("真实块数未知", priority_markdown(report))

    def test_invalid_field_clears_stale_rank_and_empty_scene_is_explicit(self):
        regions = [dict(region(500, 550), priority=1)]
        report = rank_scene(regions, {"valid": False})
        self.assertFalse(report["groups"])
        self.assertNotIn("priority", regions[0])
        self.assertIn("未生成", priority_markdown(rank_scene([], FIELD)))

    def test_rotation_preserves_priority(self):
        regions = [region(450, 550), region(550, 560), region(500, 900)]
        expected = rank_scene(regions, FIELD)["groups"]
        rotated = [region(1000-y, x) for x, y in [(450,550),(550,560),(500,900)]]
        field = dict(FIELD, yellow_normal=[1, 0])
        actual = rank_scene(rotated, field)["groups"]
        self.assertEqual([g["region_ids"] for g in expected], [g["region_ids"] for g in actual])
        self.assertEqual([g["score"] for g in expected], [g["score"] for g in actual])


if __name__ == "__main__":
    unittest.main()
