"""Fixed-input checks retained separately from the continuous visual demo."""
import argparse
from dataclasses import asdict
import json
from math import pi
from pathlib import Path

from planner import Block, Config, Planner, Pose, World


def scenarios():
    return [
        ("开局：先推正前方的一排", World(0, Pose(600, 800), (
            Block("a", 530, 610), Block("b", 600, 610), Block("c", 670, 610), Block("d", 950, 650)))),
        ("中盘：首批已入区，获取另一组", World(24, Pose(600, 400), (
            Block("a", 530, 300), Block("b", 600, 300), Block("c", 670, 300),
            Block("d", 800, 620), Block("e", 860, 650)), completed_pushes=2)),
        ("中盘：已获得的方块被推回中线外", World(45, Pose(600, 800), (
            Block("a", 530, 625), Block("b", 600, 625), Block("c", 670, 625)), completed_pushes=2)),
        ("终盘：用最短必要推送完成入区", World(77, Pose(600, 800), (
            Block("a", 530, 610), Block("b", 600, 620), Block("c", 670, 630)), completed_pushes=3)),
        ("任何阶段：碰撞风险打断当前任务", World(78, Pose(600, 780), (
            Block("a", 530, 610),), collision_risk=True)),
        ("最后两秒：停车", World(88, Pose(600, 420), ())),
    ]


def main():
    parser = argparse.ArgumentParser(description="三阶段策略场景演示，无车辆连接")
    parser.add_argument("--target-half", choices=("upper", "lower"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    cfg = Config.load(Path(__file__).with_name("config.json"))
    if args.target_half:
        cfg = Config(**{**vars(cfg), "target_half": args.target_half})
    planner = Planner(cfg)
    report = []
    for title, world in scenarios():
        if cfg.target_half == "upper":
            world = World(**{**vars(world),
                "robot": Pose(world.robot.x, cfg.field_mm - world.robot.y, pi / 2),
                "blocks": tuple(Block(b.id, b.x, cfg.field_mm - b.y) for b in world.blocks)})
        decision = planner.tick(world)
        report.append({"scenario": title, "elapsed_s": world.elapsed_s, "decision": asdict(decision)})
        if not args.json:
            print(f"\n{world.elapsed_s:>4.0f}s | {title}\n  {decision.phase} / {decision.action}: {decision.reason}")
            if decision.target_ids:
                print(f"  方块 {', '.join(decision.target_ids)}；{decision.delivery}；估计 {decision.estimated_s:.1f}s")
                print(f"  接近点 {decision.approach_mm} → 推送终点 {decision.push_to_mm}（小车中心坐标，毫米）")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("\n这是策略场景检查；时间为待实测的估计值，执行前仍需检查路径。")


if __name__ == "__main__":
    main()
