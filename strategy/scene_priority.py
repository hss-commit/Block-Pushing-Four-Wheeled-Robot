"""Image-only tactical preview. No robot pose, travel times or motor output.

Coordinates below are field-span fractions. On raw photos these are projected
image fractions, not metric geometry. The real executor still uses Planner.
"""

from math import hypot, isfinite
from pathlib import Path
from statistics import median

from strategy.planner import Config, capture_centers


DEFAULT_CONFIG = Config.load(Path(__file__).with_name("config.json"))


def rank_scene(regions, field, calibrated=False, config=None):
    c = config or DEFAULT_CONFIG
    for region in regions:
        region.pop("priority", None)
        region.pop("count_uncertain", None)
        region.pop("priority_deferred", None)
    report = {"mode": "scene_preview_without_robot_pose", "target_colour": "yellow",
              "calibrated": calibrated, "groups": [], "deferred": [],
              "requires_path_check": True, "executable": False,
              "parameters": {name: getattr(c, name) for name in
                             ("field_mm", "pusher_width_mm", "side_margin_mm", "block_half_mm",
                              "front_offset_mm", "approach_gap_mm", "body_margin_mm", "quick_depth_mm")},
              "warnings": ["缺少小车位置和朝向；排名是当前候选比较，不是固定执行顺序或全局最优路径。",
                           "排序只覆盖检出的区域；漏检和粘连会影响结果。",
                           "应覆盖全场；裁切形成的图像边界不能当作已确认的真实围墙。"]}
    if not calibrated:
        report["warnings"].append("原图未透视校正；距离、走廊宽度和墙边余量仅按图像投影估算。")
    if not field.get("valid") or not field.get("polygon_px"):
        report["warnings"].append("场地边界无效，不给优先级。")
        return report
    nx, ny = field["yellow_normal"]
    length = hypot(nx, ny)
    if not isfinite(length) or length <= 0:
        report["warnings"].append("目标方向无效，不给优先级。")
        return report
    nx, ny = nx / length, ny / length
    tx, ty = -ny, nx
    ox, oy = field["point_px"]

    def project(x, y):
        return x * tx + y * ty, (x-ox) * nx + (y-oy) * ny

    polygon = [project(x, y) for x, y in field["polygon_px"]]
    low = min(p[0] for p in polygon)
    width = max(p[0] for p in polygon) - low
    depth_span = max(p[1] for p in polygon) - min(p[1] for p in polygon)
    if min(width, depth_span) <= 1:
        report["warnings"].append("场地范围过小，不给优先级。")
        return report
    items = []
    areas = [r["area_px"] for r in regions if r.get("area_px", 0) > 0]
    typical_area = median(areas) if len(areas) >= 4 else None
    for index, region in enumerate(regions, 1):
        x, y, w, h = region["bbox_px"]
        corners = [project(px, py) for px, py in
                   ((x,y), (x+w-1,y), (x+w-1,y+h-1), (x,y+h-1))]
        lateral, depth = project(x+(w-1)/2, y+(h-1)/2)
        a, b = min(p[1] for p in corners), max(p[1] for p in corners)
        uncertainty = bool(typical_area and region["area_px"] > 2.2 * typical_area)
        region["count_uncertain"] = uncertainty
        items.append({"id": index, "lateral": (lateral-low)/width,
                      "depth": depth/depth_span, "back": a/depth_span, "front": b/depth_span,
                      "radius": (max(p[0] for p in corners)-min(p[0] for p in corners))/width/2,
                      "uncertain": uncertainty, "half": region.get("half", "unknown")})
    eligible = [r for r in items if r["half"] in ("blue", "on_line")]
    half_width = (c.pusher_width_mm/2-c.side_margin_mm-c.block_half_mm)/c.field_mm
    clearance = (c.pusher_width_mm/2+c.side_margin_mm)/c.field_mm
    approach = (c.front_offset_mm+c.block_half_mm+c.approach_gap_mm)/c.field_mm
    delivery = c.quick_depth_mm/c.field_mm
    candidates = {}
    # ponytail: projected, straight-corridor heuristic only; use pose-based Planner
    # and full-footprint path checks when execution is connected.
    edge_centers = [r["lateral"] + sign * (half_width-r["radius"])
                    for r in eligible if r["radius"] <= half_width for sign in (-1, 1)]
    for center in capture_centers((r["lateral"] for r in eligible), half_width, edge_centers):
        lane = sorted((r for r in eligible if abs(r["lateral"]-center)+r["radius"] <= half_width+1e-9),
                      key=lambda r: r["back"], reverse=True)
        for targets in (lane[i:j] for i in range(len(lane)) for j in range(i+1, len(lane)+1)):
            ids = tuple(sorted(r["id"] for r in targets))
            if not ids:
                continue
            back = min(r["back"] for r in targets)
            nearest = max(r["front"] for r in targets)
            push_depth = max(delivery, nearest + c.block_half_mm/c.field_mm)
            # Avoid knowingly disturbing blocks already acquired in yellow.
            if any(r["half"] == "yellow" and
                   abs(r["lateral"]-center) <= c.pusher_width_mm/c.field_mm/2+r["radius"] and
                   back <= r["back"] <= push_depth for r in items):
                continue
            uncertainty = any(r["uncertain"] for r in targets)
            wall = center < clearance or center > 1-clearance
            rear = back-approach < min(p[1] for p in polygon)/depth_span+c.body_margin_mm/c.field_mm
            risk = wall or rear
            effort = approach + max(0, push_depth-back) + c.approach_gap_mm/c.field_mm
            value = sum(0.65 if r["uncertain"] else 1 for r in targets)
            score = value / max(effort, 0.01) * (0.4 if risk else 1)
            reasons = [f"包含 {len(targets)} 个检测区域", f"最远目标离中线约 {max(0,-back):.0%} 场地深度",
                       "收益 / 直推与预留空间的相对代价；未计小车接近时间"]
            if uncertainty:
                reasons.append("含疑似粘连大区域，真实块数未知，收益折减")
            if wall:
                reasons.append("靠侧边，按当前推板参数缺少横向余量，降级待复核")
            if rear:
                reasons.append("背后接近空间不足，降级待复核")
            candidate = {"region_ids": list(ids), "region_count": len(ids),
                         "actual_block_count": None, "count_uncertain": uncertainty,
                         "score": round(score, 4), "geometry_risk": risk,
                         "corridor_center_fraction": round(center, 4),
                         "farthest_line_distance_fraction": round(max(0,-back),4),
                         "reasons": reasons}
            if ids not in candidates or candidate["score"] > candidates[ids]["score"]:
                candidates[ids] = candidate
    remaining = {r["id"] for r in eligible}
    # Produce a disjoint displayed shortlist; after any push it must be rebuilt.
    while remaining:
        available = [g for ids, g in candidates.items() if set(ids) <= remaining]
        if not available:
            break
        best = min(available, key=lambda g: (g["geometry_risk"], -g["score"], g["region_ids"]))
        best = dict(best, rank=len(report["groups"])+1)
        report["groups"].append(best)
        for index in best["region_ids"]:
            regions[index-1]["priority"] = best["rank"]
        remaining.difference_update(best["region_ids"])
    for index in sorted(remaining):
        regions[index-1]["priority_deferred"] = True
        report["deferred"].append({"region_id": index,
                                   "reason": "未找到满足当前走廊/已入区方块约束的候选；需重新观察或分开处理。"})
    return report


def priority_markdown(report):
    lines = ["# 场景推送候选优先级", "", "目标：黄色区。没有小车位姿；P1/P2 是候选排名，每次推送后需重算。", ""]
    lines += [f"- {warning}" for warning in report["warnings"]]
    lines += ["", "| 优先级 | 区域编号 | 相对评分 | 说明 |", "|---|---|---:|---|"]
    for group in report["groups"]:
        lines.append(f"| P{group['rank']} | {', '.join(map(str,group['region_ids']))} | {group['score']:.3f} | {'；'.join(group['reasons'])} |")
    for item in report["deferred"]:
        lines.append(f"\n区域 {item['region_id']} 暂缓：{item['reason']}")
    if not report["groups"]:
        lines.append("\n当前未生成可排序候选；不能据此认定场地没有待推方块。")
    return "\n".join(lines)+"\n"
