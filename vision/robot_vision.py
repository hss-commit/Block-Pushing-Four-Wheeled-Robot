"""Red-wheel visual prototype. Wider wheel pair is the front; never drives motors."""

from itertools import combinations
from math import atan2

import cv2
import numpy as np


def detect_robot(image, front_ratio=1.08):
    """Return current-frame evidence only. Coordinates are pixels, y downward."""
    scale = min(1, 900 / max(image.shape[:2]))
    small = cv2.resize(image, None, fx=scale, fy=scale)
    height, width = small.shape[:2]
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    red = (((hsv[:, :, 0] <= 10) | (hsv[:, :, 0] >= 173)) &
           (hsv[:, :, 1] >= 180) & (hsv[:, :, 2] >= 80)).astype(np.uint8) * 255
    candidates = []
    # Different distances need different gap sizes to join a wheel's red arcs.
    for fraction in (.025, .045, .065, .08):
        size = max(3, round(min(height, width) * fraction)) | 1
        closed = cv2.morphologyEx(red, cv2.MORPH_CLOSE,
                                 cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)))
        count, _, stats, _ = cv2.connectedComponentsWithStats(closed)
        wheels = []
        for x, y, w, h, area in stats[1:]:
            if not (.0008 * width * height < area < .065 * width * height and
                    .45 < w / h < 2.5 and min(w, h) > 6):
                continue
            # Boundary-clipped wheels cannot give a reliable pair spacing.
            if x <= 1 or y <= 1 or x+w >= width-1 or y+h >= height-1:
                continue
            red_fill = np.count_nonzero(red[y:y+h,x:x+w])/(w*h)
            dark_fill = np.count_nonzero(hsv[y:y+h,x:x+w,2] < 85)/(w*h)
            # The user's wheels contain black rollers; solid red blocks do not.
            if not .08 < red_fill < .85 or dark_fill < .12:
                continue
            wheels.append((np.array([x+w/2, y+h/2]), (x, y, w, h), float(area)))
        wheels = sorted(wheels, key=lambda w: w[2], reverse=True)[:14]
        for group in combinations(wheels, 4):
            points = np.array([w[0] for w in group])
            diameters = np.array([max(w[1][2:]) for w in group])
            if diameters.max() / diameters.min() > 2.3:
                continue
            for a, b, c, d in ((0, 1, 2, 3), (0, 2, 1, 3), (0, 3, 1, 2)):
                v1, v2 = points[b]-points[a], points[d]-points[c]
                l1, l2 = np.linalg.norm(v1), np.linalg.norm(v2)
                m1, m2 = (points[a]+points[b])/2, (points[c]+points[d])/2
                delta = m2-m1
                depth = np.linalg.norm(delta)
                if min(l1, l2, depth) < 1:
                    continue
                parallel = abs(np.dot(v1, v2)/(l1*l2))
                skew = max(abs(np.dot(v1, delta)/(l1*depth)),
                           abs(np.dot(v2, delta)/(l2*depth)))
                if (parallel < .94 or skew > .35 or max(l1, l2)/min(l1, l2) > 1.6 or
                        not .8 < (l1+l2)/2/depth < 3.8 or diameters.max() > depth*.9 or
                        min(l1, l2) < diameters.max()*1.5):
                    continue
                # Reward equally sized wheel clusters and complete red evidence.
                score = sum(w[2] for w in group) * parallel * (1-skew) / (diameters.max()/diameters.min())
                front, rear = (m1, m2) if l1 > l2 else (m2, m1)
                candidates.append((score, points, group, front, rear, max(l1,l2)/min(l1,l2)))
    if not candidates:
        return {"detected": False, "heading_valid": False, "reason": "NEED FOUR RED WHEELS"}
    candidates.sort(key=lambda item: item[0], reverse=True)
    best = candidates[0]
    _, points, group, front, rear, ratio = best
    center = points.mean(axis=0)
    # Multiple distinct plausible cars: refuse to select an arbitrary one.
    if any(other[0] > best[0]*.8 and np.linalg.norm(other[1].mean(axis=0)-center) >
           np.linalg.norm(front-rear)*.5 for other in candidates[1:]):
        return {"detected": False, "heading_valid": False, "reason": "MULTIPLE WHEEL GROUPS"}
    heading_valid = ratio >= front_ratio
    hull_points = []
    for _, (x,y,w,h), _ in group:
        hull_points.extend(((x,y),(x+w,y),(x+w,y+h),(x,y+h)))
    hull = cv2.convexHull(np.float32(hull_points)).reshape(-1,2)/scale
    direction = front-rear
    return {"detected": True, "heading_valid": bool(heading_valid),
            "reason": "FRONT = WIDER PAIR" if heading_valid else "HEADING UNCERTAIN",
            "center_px": (center/scale).tolist(), "wheels_px": (points/scale).tolist(),
            "front_px": (front/scale).tolist() if heading_valid else None,
            "rear_px": (rear/scale).tolist() if heading_valid else None,
            "heading_rad": atan2(-direction[1], direction[0]) if heading_valid else None,
            "pair_width_ratio": float(ratio), "body_polygon_px": hull.tolist(),
            "executable": False}


def draw_robot(image, robot, calibrated=False, field_mm=1200):
    """Draw on an existing result; label ground-plane coordinates as estimates."""
    colour = (0,255,0) if robot.get("heading_valid") else (0,170,255)
    label = "ROBOT: " + robot["reason"]
    if robot["detected"]:
        for p in robot["wheels_px"]:
            cv2.circle(image, tuple(np.rint(p).astype(int)), 9, colour, 2)
        center = tuple(np.rint(robot["center_px"]).astype(int))
        cv2.polylines(image, [np.rint(robot["body_polygon_px"]).astype(np.int32)], True, colour, 2)
        cv2.drawMarker(image, center, colour, cv2.MARKER_CROSS, 22, 2)
        if robot["heading_valid"]:
            end = tuple(np.rint(np.array(robot["center_px"])+
                                 .65*(np.array(robot["front_px"])-robot["rear_px"])).astype(int))
            cv2.arrowedLine(image, center, end, colour, 4, tipLength=.25)
        if calibrated:
            x,y = robot["center_px"]
            robot["center_ground_estimate_mm"] = [x*field_mm/(image.shape[1]-1),
                                                   (image.shape[0]-1-y)*field_mm/(image.shape[0]-1)]
            label += " | approx %.0f, %.0f mm" % tuple(robot["center_ground_estimate_mm"])
    y = image.shape[0]-20
    cv2.rectangle(image,(0,y-27),(image.shape[1],image.shape[0]),(25,25,25),-1)
    cv2.putText(image,label,(12,y),cv2.FONT_HERSHEY_SIMPLEX,.65,colour,2,cv2.LINE_AA)


def exclude_robot_regions(regions, robot):
    if not robot["detected"]:
        return regions
    hull = np.float32(robot["body_polygon_px"])
    return [r for r in regions if cv2.pointPolygonTest(hull,
            (r["bbox_px"][0]+r["bbox_px"][2]/2,r["bbox_px"][1]+r["bbox_px"][3]/2),False) < 0]
