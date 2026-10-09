"""Continuous OpenCV sandbox driven by planner.py, with simplified kinematics.

No hardware commands. Approach routing approximates the chassis as a circle;
wheel dynamics, pusher swept-volume, friction and occlusion are not simulated.
"""
import argparse
from dataclasses import replace
from heapq import heappop, heappush
from math import atan2, cos, hypot, pi, sin
from pathlib import Path
import time

import cv2
import numpy as np

from planner import Block, Config, Pose, revise_task_for_endgame
from runtime import Feedback, Observation, StrategyRuntime

ROOT = Path(__file__).resolve().parent
WINDOW = "Robot strategy - continuous OpenCV demo"
FIELD_X, FIELD_Y, FIELD_PX = 28, 112, 600


def angle_delta(target, current):
    return (target - current + pi) % (2 * pi) - pi


def segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    fraction = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy or 1)
    fraction = max(0, min(1, fraction))
    return hypot(point[0] - start[0] - fraction * dx, point[1] - start[1] - fraction * dy)


class Simulation:
    def __init__(self, config=None):
        self.config = config or Config.load(ROOT / "config.json")
        self.reset()

    def reset(self):
        c = self.config
        self.runtime = StrategyRuntime(c, started_at_s=0.0)
        self.planner = self.runtime.planner
        self.elapsed = 0.0
        self.robot = Pose(c.field_mm / 2, c.field_mm * 2 / 3)
        self.blocks = [Block(f"B{i + 1}", c.field_mm * x / 1200, c.field_mm / 2 + 10)
                       for i, x in enumerate((285, 375, 465, 555, 645, 735, 825, 915))]
        if c.target_half == "upper":
            self.robot = Pose(self.robot.x, c.field_mm - self.robot.y, pi / 2)
            self.blocks = [replace(b, y=c.field_mm - b.y) for b in self.blocks]
        self.next_id = len(self.blocks) + 1
        self.opponent = None
        self.completed = 0
        self.task = None
        self.route = []
        self.state = "SELECT"
        self.note = "Finding a target from the current scene"
        self.retry_at = 0.0
        self.release_until = 0.0
        self.release_point = None
        self.current = self.decide()
        self.history = [(0.0, "OPENING")]

    def decide(self):
        # A real source fills these same records; real motion still needs its own executor.
        observation = Observation(
            robot=self.robot, pose_seen_at_s=self.elapsed,
            blocks=tuple(self.blocks), blocks_seen_at_s=self.elapsed,
            collision_risk=False,
            opponent=self.opponent,
            opponent_seen_at_s=self.elapsed if self.opponent else None,
        )
        feedback = Feedback(received_at_s=self.elapsed, completed_pushes=self.completed)
        return self.runtime.decide(observation, feedback, now_s=self.elapsed)

    def scene_changed(self):
        self.task, self.route = None, []
        self.state, self.note, self.retry_at = "SELECT", "Scene changed: replanning", self.elapsed

    def move_block(self, block_id, x, y):
        half, edge = self.config.block_half_mm, self.config.field_mm
        x, y = max(half, min(edge - half, x)), max(half, min(edge - half, y))
        if any(b.id != block_id and hypot(b.x - x, b.y - y) < 2 * half + 3 for b in self.blocks):
            return False
        self.blocks = [replace(b, x=x, y=y) if b.id == block_id else b for b in self.blocks]
        self.scene_changed()
        return True

    def add_block(self, x, y):
        if len(self.blocks) >= 30:
            self.note = "Sandbox limit: 30 blocks"
            return
        if any(hypot(b.x - x, b.y - y) < 2 * self.config.block_half_mm + 3 for b in self.blocks):
            return
        self.blocks.append(Block(f"B{self.next_id}", x, y))
        self.next_id += 1
        self.scene_changed()

    def clear_segment(self, start, end):
        c = self.config
        margin = c.body_margin_mm
        if any(not margin <= v <= c.field_mm - margin for p in (start, end) for v in p):
            return False
        if any(segment_distance((b.x, b.y), start, end) < margin + c.block_half_mm for b in self.blocks):
            return False
        return self.opponent is None or segment_distance(
            (self.opponent.x, self.opponent.y), start, end) > margin + c.opponent_radius_mm

    def approach_route(self, goal):
        """Small grid search for this sandbox's circular-chassis approximation."""
        start = (self.robot.x, self.robot.y)
        if self.clear_segment(start, goal):
            return [goal]
        c, count = self.config, 25
        spacing = (c.field_mm - 2 * c.body_margin_mm) / count

        def point(node):
            return (c.body_margin_mm + node[0] * spacing, c.body_margin_mm + node[1] * spacing)

        def nearby(p):
            nx, ny = (round((v - c.body_margin_mm) / spacing) for v in p)
            return [(nx + dx, ny + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                    if 0 <= nx + dx <= count and 0 <= ny + dy <= count]

        starts = [n for n in nearby(start) if self.clear_segment(start, point(n))]
        ends = {n for n in nearby(goal) if self.clear_segment(point(n), goal)}
        queue, costs, previous = [], {}, {}
        for node in starts:
            cost = hypot(point(node)[0] - start[0], point(node)[1] - start[1])
            costs[node], previous[node] = cost, None
            heappush(queue, (cost + hypot(point(node)[0] - goal[0], point(node)[1] - goal[1]), cost, node))
        while queue:
            _, cost, node = heappop(queue)
            if cost > costs[node]:
                continue
            if node in ends:
                path = [goal, point(node)]
                while previous[node] is not None:
                    node = previous[node]
                    path.append(point(node))
                path.reverse()
                # Collapse visible grid segments so the vehicle does not zigzag.
                route, current = [], start
                while path:
                    index = max(i for i, p in enumerate(path) if self.clear_segment(current, p))
                    current = path[index]
                    route.append(current)
                    path = path[index + 1:]
                return route
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                neighbor = (node[0] + dx, node[1] + dy)
                if not (0 <= neighbor[0] <= count and 0 <= neighbor[1] <= count):
                    continue
                new_cost = cost + hypot(dx, dy) * spacing
                if new_cost < costs.get(neighbor, float("inf")) and self.clear_segment(point(node), point(neighbor)):
                    costs[neighbor], previous[neighbor] = new_cost, node
                    heappush(queue, (new_cost + hypot(point(neighbor)[0] - goal[0], point(neighbor)[1] - goal[1]), new_cost, neighbor))
        return []

    def route_time(self, route, task):
        total, heading, previous = 0.0, self.robot.heading, (self.robot.x, self.robot.y)
        c = self.config
        for x, y in route:
            if hypot(x - previous[0], y - previous[1]) > 0.001:
                bearing = atan2(y - previous[1], x - previous[0])
                total += abs(angle_delta(bearing, heading)) / c.turn_speed_rad_s
                total += hypot(x - previous[0], y - previous[1]) / c.travel_speed_mm_s
                heading = bearing
            previous = (x, y)
        return total + abs(angle_delta(task.heading_rad, heading)) / c.turn_speed_rad_s + c.align_s + (
            hypot(task.push_to_mm[0] - previous[0], task.push_to_mm[1] - previous[1]) / c.push_speed_mm_s) + c.release_s

    def turn(self, heading, dt):
        delta = angle_delta(heading, self.robot.heading)
        limit = self.config.turn_speed_rad_s * dt
        self.robot = replace(self.robot, heading=self.robot.heading + max(-limit, min(limit, delta)))
        return abs(delta) <= limit

    def move(self, goal, speed, dt, reverse=False):
        dx, dy = goal[0] - self.robot.x, goal[1] - self.robot.y
        length = hypot(dx, dy)
        if length < 0.01:
            return True
        heading = atan2(dy, dx) + (pi if reverse else 0)
        if abs(angle_delta(heading, self.robot.heading)) > 0.02:
            self.turn(heading, dt)
            return False
        fraction = min(1, speed * dt / length)
        self.robot = replace(self.robot, x=self.robot.x + dx * fraction, y=self.robot.y + dy * fraction)
        return fraction == 1

    def push_blocks(self, old_robot):
        c = self.config
        sign = -1 if c.target_half == "lower" else 1
        old_front = sign * old_robot.y + c.front_offset_mm
        new_front = sign * self.robot.y + c.front_offset_mm
        changed = {}
        # No lateral sliding: contact translates blocks along the push axis.
        for block in sorted(self.blocks, key=lambda b: sign * b.y):
            progress = sign * block.y
            if abs(block.x - self.robot.x) > c.pusher_width_mm / 2 + c.block_half_mm:
                continue
            if progress < old_front - c.block_half_mm - 0.01:
                continue
            progress = max(progress, new_front + c.block_half_mm)
            for other in changed.values():
                if abs(block.x - other.x) < 2 * c.block_half_mm:
                    progress = max(progress, sign * other.y + 2 * c.block_half_mm)
            if c.block_half_mm <= sign * progress <= c.field_mm - c.block_half_mm:
                changed[block.id] = replace(block, y=sign * progress)
        self.blocks = [changed.get(b.id, b) for b in self.blocks]

    def step(self, dt):
        if dt <= 0:
            return
        # Substeps make 1x and accelerated playback use the same motion rules.
        while dt > 1e-9:
            tick = min(dt, 0.025)
            self._step(tick)
            dt -= tick

    def _step(self, dt):
        c = self.config
        self.elapsed = min(c.match_s, self.elapsed + dt)
        previous_phase = self.current.phase
        self.current = self.decide()
        if self.current.phase != previous_phase:
            self.history.append((self.elapsed, self.current.phase))
        if self.current.action == "STOP":
            self.task, self.route, self.state = None, [], "STOP"
            self.note = "Match finished" if self.current.phase == "FINISHED" else "Safety stop"
            return
        if previous_phase != "ENDGAME" and self.current.phase == "ENDGAME" and self.task:
            action, revised = revise_task_for_endgame(c, self.task, self.robot, self.state)
            if action == "REPLAN":
                self.scene_changed()
            elif action == "RELEASE":
                self.begin_release()
            else:
                self.task = revised
        if self.task is None:
            if self.elapsed < self.retry_at:
                return
            task = self.current
            if task.action == "WAIT":
                self.state, self.note = "WAIT", "No viable target - add or drag a block"
                return
            route = self.approach_route(task.approach_mm)
            if not route or self.route_time(route, task) > c.match_s - c.stop_remaining_s - self.elapsed:
                self.state, self.note = "WAIT", "Route blocked or insufficient time"
                self.retry_at = self.elapsed + 0.5
                return
            self.task, self.route, self.state = task, route, "APPROACH"
            self.note = "Following current target; no scripted scene jumps"
        if self.state == "APPROACH":
            if self.move(self.route[0], c.travel_speed_mm_s, dt):
                self.route.pop(0)
                if not self.route:
                    self.state = "ALIGN"
        elif self.state == "ALIGN":
            if self.turn(self.task.heading_rad, dt):
                self.state = "PUSH"
        elif self.state == "PUSH":
            previous = self.robot
            reached = self.move(self.task.push_to_mm, c.push_speed_mm_s, dt)
            self.push_blocks(previous)
            if reached:
                self.begin_release()
        elif self.state == "RELEASE":
            self.move(self.release_point, 60, dt, reverse=True)
            if self.elapsed >= self.release_until:
                self.completed += 1
                self.task, self.route, self.state = None, [], "SELECT"

    def begin_release(self):
        sign = -1 if self.config.target_half == "lower" else 1
        self.state = "RELEASE"
        self.release_until = self.elapsed + self.config.release_s
        self.release_point = (self.robot.x, self.robot.y - sign * 30)


def render(sim, paused=False, speed=1):
    canvas = np.full((775, 1050, 3), (244, 246, 244), np.uint8)
    c = sim.config

    def text(value, x, y, scale=0.55, color=(48, 62, 48)):
        cv2.putText(canvas, value, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)

    def point(x, y):
        return (round(FIELD_X + x / c.field_mm * FIELD_PX), round(FIELD_Y + (1 - y / c.field_mm) * FIELD_PX))

    text("ROBOT STRATEGY / LIVE 2D SANDBOX", 28, 35, 0.8)
    text(f"{sim.elapsed:05.1f}s / {c.match_s:g}s    {speed}x    {'PAUSED' if paused else 'RUNNING'}", 28, 66, 0.7)
    cv2.rectangle(canvas, (28, 83), (628, 91), (211, 218, 211), -1)
    cv2.rectangle(canvas, (28, 83), (28 + round(600 * sim.elapsed / c.match_s), 91), (73, 143, 89), -1)
    cv2.rectangle(canvas, point(0, c.field_mm), point(c.field_mm, c.field_mm / 2), (185, 121, 49), -1)
    cv2.rectangle(canvas, point(0, c.field_mm / 2), point(c.field_mm, 0), (96, 211, 236), -1)
    cv2.rectangle(canvas, point(0, c.field_mm), point(c.field_mm, 0), (76, 86, 76), 2)
    cv2.line(canvas, point(0, c.field_mm / 2), point(c.field_mm, c.field_mm / 2), (245, 245, 245), 2)
    target_ids = set(sim.task.target_ids) if sim.task else set()
    if sim.task:
        start = point(sim.robot.x, sim.robot.y)
        for waypoint in sim.route:
            finish = point(*waypoint)
            cv2.line(canvas, start, finish, (240, 245, 240), 2, cv2.LINE_AA)
            start = finish
        finish = point(*sim.task.push_to_mm)
        cv2.drawMarker(canvas, finish, (250, 250, 250), cv2.MARKER_CROSS, 20, 2)
    for block in sim.blocks:
        p = point(block.x, block.y)
        radius = max(5, round(c.block_half_mm / c.field_mm * FIELD_PX))
        cv2.rectangle(canvas, (p[0] - radius, p[1] - radius), (p[0] + radius, p[1] + radius), (55, 55, 218), -1)
        if block.id in target_ids:
            cv2.circle(canvas, p, radius + 5, (248, 248, 248), 2)
        text(block.id, p[0] + 8, p[1] - 8, 0.38, (245, 245, 245))
    robot = sim.robot
    forward = (cos(robot.heading), sin(robot.heading))
    lateral = (-forward[1], forward[0])
    vertices = [point(robot.x + a * forward[0] + b * lateral[0], robot.y + a * forward[1] + b * lateral[1])
                for a, b in ((60, 60), (60, -60), (-60, -60), (-60, 60))]
    cv2.fillConvexPoly(canvas, np.asarray(vertices, np.int32), (48, 65, 45))
    nose = (robot.x + c.front_offset_mm * forward[0], robot.y + c.front_offset_mm * forward[1])
    ends = [point(nose[0] + side * c.pusher_width_mm / 2 * lateral[0], nose[1] + side * c.pusher_width_mm / 2 * lateral[1]) for side in (-1, 1)]
    cv2.line(canvas, *ends, (230, 244, 225), 5, cv2.LINE_AA)
    cv2.arrowedLine(canvas, point(robot.x, robot.y), point(*nose), (244, 244, 244), 2)
    if sim.opponent:
        cv2.circle(canvas, point(sim.opponent.x, sim.opponent.y), round(c.opponent_radius_mm / c.field_mm * FIELD_PX), (70, 64, 130), -1)
        text("OPP", *point(sim.opponent.x - 30, sim.opponent.y), 0.4, (255, 255, 255))
    x = 660
    text("PHASE", x, 133, 0.5)
    text(sim.current.phase, x, 167, 0.9)
    text("EXECUTION", x, 218, 0.5)
    text(sim.state, x, 251, 0.8)
    action = sim.task.action if sim.task else sim.current.action
    text(action, x, 282, 0.6)
    text(sim.task.delivery if sim.task else "-", x, 311, 0.55)
    count = sum(sim.planner.depth(b.y) > c.block_half_mm for b in sim.blocks)
    text(f"In target half: {count} / {len(sim.blocks)}", x, 359, 0.6)
    text(f"Completed pushes: {sim.completed}", x, 391, 0.6)
    text(f"Target half: {c.target_half}", x, 423, 0.55)
    text("SPACE   pause / resume", x, 488)
    text("1 / 2 / 3   speed: 1x / 3x / 6x", x, 519, 0.5)
    text("R   restart       ESC   close", x, 550, 0.5)
    text("Left drag: move a block", x, 599, 0.5)
    text("Left click empty: add a block", x, 628, 0.5)
    text("Right click: place opponent", x, 657, 0.5)
    text("O   remove opponent", x, 686, 0.5)
    text(sim.note, 28, 744, 0.52)
    text("SIMULATION ONLY - simplified contacts and chassis routing", 28, 764, 0.42, (105, 114, 105))
    return canvas


def main():
    parser = argparse.ArgumentParser(description="OpenCV 连续策略演示：空格暂停，1/2/3 倍速，R 重启。")
    parser.add_argument("--target-half", choices=("lower", "upper"))
    args = parser.parse_args()
    config = Config.load(ROOT / "config.json")
    if args.target_half:
        config = replace(config, target_half=args.target_half)
    sim = Simulation(config)
    paused, speed, dragging = False, 1, None

    def mouse(event, x, y, flags, param):
        nonlocal dragging
        wx = (x - FIELD_X) / FIELD_PX * config.field_mm
        wy = (1 - (y - FIELD_Y) / FIELD_PX) * config.field_mm
        if event == cv2.EVENT_LBUTTONUP:
            dragging = None
        if not (0 <= wx <= config.field_mm and 0 <= wy <= config.field_mm):
            return
        if event == cv2.EVENT_LBUTTONDOWN:
            nearest = min(sim.blocks, key=lambda b: hypot(b.x - wx, b.y - wy), default=None)
            if nearest and hypot(nearest.x - wx, nearest.y - wy) <= 35:
                dragging = nearest.id
            elif config.block_half_mm <= wx <= config.field_mm - config.block_half_mm and config.block_half_mm <= wy <= config.field_mm - config.block_half_mm:
                sim.add_block(wx, wy)
        elif event == cv2.EVENT_MOUSEMOVE and dragging:
            sim.move_block(dragging, wx, wy)
        elif event == cv2.EVENT_RBUTTONDOWN:
            sim.opponent = Pose(wx, wy)
            sim.scene_changed()

    print("连续策略窗口：空格暂停/继续；1、2、3 切换 1/3/6 倍速；R 重启；Esc 退出。")
    print("左键拖动红色方块，点空白位置添块；右键放置对手障碍，O 移除对手。拖动时暂停计时。")
    print("模拟运动用于检查决策流程，尚未模拟真实摩擦、打滑或推板转弯扫掠。")
    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW, mouse)
    previous = time.perf_counter()
    try:
        while True:
            now = time.perf_counter()
            dt, previous = min(now - previous, 0.1), now
            if not paused and dragging is None:
                sim.step(dt * speed)
            cv2.imshow(WINDOW, render(sim, paused or dragging is not None, speed))
            key = cv2.waitKey(15) & 0xFF
            if key == 27 or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == ord(" "):
                paused = not paused
            elif key in (ord("r"), ord("R")):
                sim.reset()
                dragging = None
            elif key in (ord("1"), ord("2"), ord("3")):
                speed = {ord("1"): 1, ord("2"): 3, ord("3"): 6}[key]
            elif key in (ord("o"), ord("O")):
                sim.opponent = None
                sim.scene_changed()
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
