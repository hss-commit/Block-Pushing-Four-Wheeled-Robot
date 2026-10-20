"""Phone-photo prototype: OpenCV calibration, HSV segmentation and coordinates."""

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

FIELD_MM = 1200
SIZE = 1200
PREVIEW = 700
OUTPUT = Path(__file__).resolve().parent / "results"


def choose_photo():
    # Native Windows dialog avoids depending on the bundled Python's Tcl/Tk.
    command = """
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = 'Select a phone photo'
$dialog.Filter = 'Photos (*.jpg;*.jpeg;*.png;*.bmp)|*.jpg;*.jpeg;*.png;*.bmp|All files (*.*)|*.*'
try {
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        [Console]::Write($dialog.FileName)
    }
} finally { $dialog.Dispose() }
"""
    result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-Command", command],
                            capture_output=True, text=True, encoding="utf-8", check=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    return result.stdout.strip()


def read_photo(path):
    # np.fromfile supports Chinese Windows paths, including this project folder.
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("无法读取照片，请使用 JPG 或 PNG；HEIC 请先转换成 JPG。")
    return image


def write_png(path, image):
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("无法保存 PNG 图片。")
    encoded.tofile(path)


def rectify(image, corners):
    points = np.asarray(corners, dtype=np.float32)
    if points.shape != (4, 2) or not np.isfinite(points).all():
        raise ValueError("请选择四个有效的场地内角。")
    height, width = image.shape[:2]
    if (points < 0).any() or (points[:, 0] >= width).any() or (points[:, 1] >= height).any():
        raise ValueError("四角必须位于照片内。")
    # In image coordinates, TL -> TR -> BR -> BL has positive signed area.
    if (not cv2.isContourConvex(points) or
            cv2.contourArea(points, oriented=True) < width * height * 0.01):
        raise ValueError("四角顺序或面积不正确，请按左上、右上、右下、左下重选。")
    target = np.float32([[0, 0], [SIZE - 1, 0], [SIZE - 1, SIZE - 1], [0, SIZE - 1]])
    matrix = cv2.getPerspectiveTransform(points, target)
    return cv2.warpPerspective(image, matrix, (SIZE, SIZE))


def sample_colour(image, x, y):
    """Median of a small untouched patch, with circular hue handling."""
    height, width = image.shape[:2]
    x, y = min(width - 1, max(0, x)), min(height - 1, max(0, y))
    patch = image[max(0, y-3):min(height, y+4), max(0, x-3):min(width, x+4)]
    pixels = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.int16)
    anchor = cv2.cvtColor(image[y:y+1, x:x+1], cv2.COLOR_BGR2HSV)[0, 0, 0]
    hues = (pixels[:, 0] - int(anchor) + 90) % 180 - 90
    return [int((int(anchor) + np.median(hues)) % 180),
            int(np.median(pixels[:, 1])), int(np.median(pixels[:, 2]))]


def segment(image, sample, h_tol=10, s_tol=70, v_tol=90, min_area=150, field=None):
    """Grow saturated colour seeds into connected paler/shadowed faces."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    center = np.asarray(sample, dtype=np.int16)
    delta_h = np.abs(hsv[:, :, 0].astype(np.int16) - center[0])
    # Hue is circular in OpenCV: red occurs on both sides of 0/179.
    hue = np.minimum(delta_h, 180 - delta_h) <= h_tol
    sat = hsv[:, :, 1] >= max(50, int(center[1]) - s_tol)
    val = hsv[:, :, 2] >= max(25, int(center[2]) - v_tol)
    seeds = hue & sat & val
    # Reflection reduces saturation; exposure changes brightness. Retain a
    # relaxed component only when it contains multiple confident seed pixels.
    weak_hue = np.minimum(delta_h, 180 - delta_h) <= min(90, h_tol + 3)
    weak_sat = hsv[:, :, 1] >= max(50, int(center[1]) - 2 * s_tol)
    mask = (weak_hue & weak_sat & val).astype(np.uint8) * 255
    if field and field.get("valid") and field.get("polygon_px"):
        roi = np.zeros(image.shape[:2], np.uint8)
        cv2.fillConvexPoly(roi, np.rint(field["polygon_px"]).astype(np.int32), 255)
        mask = cv2.bitwise_and(mask, roi)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    count, labels, stats, centers = cv2.connectedComponentsWithStats(mask, connectivity=8)
    seed_counts = np.bincount(labels[seeds].ravel(), minlength=count)
    keep = np.zeros(count, np.uint8)
    regions = []
    for index in range(1, count):
        x, y, width, height, area = map(int, stats[index])
        if area < min_area or seed_counts[index] < 3:
            continue
        keep[index] = 255
        cx, cy = map(float, centers[index])
        regions.append({
            "x_mm": round(cx * FIELD_MM / (SIZE - 1), 1),
            "y_mm": round((SIZE - 1 - cy) * FIELD_MM / (SIZE - 1), 1),
            "area_px": area, "bbox_px": [x, y, width, height],
        })
    return keep[labels], sorted(regions, key=lambda region: (region["x_mm"], region["y_mm"]))


def detect_midline(image):
    """Fit the observed blue/yellow interface, not the image centre.

    Returns pixel geometry, with the unit normal pointing into yellow.
    A missing or inconsistent boundary is explicitly invalid.
    """
    height, width = image.shape[:2]
    scale = min(900 / max(height, width), 1)
    small = cv2.resize(image, None, fx=scale, fy=scale)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    masks = [cv2.inRange(hsv, np.array(lo), np.array(hi)) for lo, hi in (
        ((90, 80, 45), (135, 255, 255)), ((18, 80, 45), (40, 255, 255)))]
    labels = np.zeros(small.shape[:2], np.uint8)
    for value, mask in enumerate(masks, 1):
        count, components, stats, _ = cv2.connectedComponentsWithStats(mask)
        if count < 2:
            return {"valid": False, "reason": "Blue or yellow field missing"}
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        if stats[largest, cv2.CC_STAT_AREA] < labels.size * 0.05:
            return {"valid": False, "reason": "Insufficient field colour coverage"}
        labels[components == largest] = value
    points = []
    max_gap = max(3, int(min(labels.shape) * 0.035))
    for transposed in (False, True):
        rows = labels.T if transposed else labels
        for row_number, row in enumerate(rows):
            indices = np.flatnonzero(row)
            if len(indices) < 2:
                continue
            changes = np.flatnonzero((row[indices[:-1]] != row[indices[1:]]) &
                                     (np.diff(indices) <= max_gap))
            for index in changes:
                position = float(indices[index] + indices[index + 1]) / 2
                points.append((row_number, position) if transposed else (position, row_number))
    if len(points) < 30:
        return {"valid": False, "reason": "Not enough visible blue/yellow interface"}
    points = np.asarray(points, np.float32)
    vx, vy, px, py = cv2.fitLine(points, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
    tangent = np.array([vx, vy], dtype=float)
    normal = np.array([-vy, vx], dtype=float)
    origin = np.array([px, py], dtype=float)
    residuals = np.abs((points - origin) @ normal)
    span = (points - origin) @ tangent
    if (np.quantile(residuals, 0.95) > min(labels.shape) * 0.015 or
            np.ptp(span) < min(labels.shape) * 0.25):
        return {"valid": False, "reason": "Boundary is short or inconsistent"}
    yellow_y, yellow_x = np.nonzero(labels == 2)
    blue_y, blue_x = np.nonzero(labels == 1)
    yellow_dist = (np.column_stack((yellow_x, yellow_y)) - origin) @ normal
    if np.median(yellow_dist) < 0:
        normal = -normal
        yellow_dist = -yellow_dist
    blue_dist = (np.column_stack((blue_x, blue_y)) - origin) @ normal
    if np.mean(yellow_dist > 0) < 0.9 or np.mean(blue_dist < 0) < 0.9:
        return {"valid": False, "reason": "Colours do not form two reliable halves"}
    ends = [(origin + tangent * position) / scale for position in (span.min(), span.max())]
    contours, _ = cv2.findContours((labels > 0).astype(np.uint8), cv2.RETR_EXTERNAL,
                                  cv2.CHAIN_APPROX_SIMPLE)
    polygon = cv2.convexHull(np.vstack(contours)).reshape(-1, 2).astype(float) / scale
    return {"valid": True, "reason": "Observed blue/yellow interface",
            "polygon_px": polygon.tolist(),
            "point_px": (origin / scale).tolist(), "yellow_normal": normal.tolist(),
            "endpoints_px": [end.tolist() for end in ends],
            "fit_error_p95_px": float(np.quantile(residuals, 0.95) / scale),
            "line_band_px": max(3.0, min(height, width) * 0.005),
            "target_colour": "yellow"}


def classify_regions(regions, field):
    """Conservative bbox-side classification; no motion command is produced."""
    for region in regions:
        region["half"] = "unknown"
        region["suggestion"] = "NO DIRECTION"
        region.pop("direction_arrow_px", None)
        if not field["valid"]:
            continue
        x, y, w, h = region["bbox_px"]
        origin = np.asarray(field["point_px"])
        normal = np.asarray(field["yellow_normal"])
        corners = np.array([[x, y], [x+w-1, y], [x+w-1, y+h-1], [x, y+h-1]])
        distances = (corners - origin) @ normal
        band = field["line_band_px"]
        half = "yellow" if distances.min() > band else "blue" if distances.max() < -band else "on_line"
        region["half"] = half
        region["suggestion"] = "HOLD" if half == "yellow" else "TOWARD YELLOW"
        if half != "yellow":
            centre = np.array([x + (w-1)/2, y + (h-1)/2])
            distance = float((centre - origin) @ normal)
            depth = max(w, h) * 2 + band
            region["direction_arrow_px"] = [centre.tolist(), (centre + normal * (depth - distance)).tolist()]
    return regions


def annotated(image, regions, field=None, calibrated=True, details=False):
    result = image.copy()
    if field is not None:
        if field["valid"]:
            start, end = [tuple(np.rint(p).astype(int)) for p in field["endpoints_px"]]
            cv2.line(result, start, end, (255, 255, 255), 4, cv2.LINE_AA)
            cv2.line(result, start, end, (255, 0, 255), 2, cv2.LINE_AA)
        status = "MIDLINE DETECTED | TARGET: YELLOW" if field["valid"] else "MIDLINE UNKNOWN | NO DIRECTION"
        cv2.putText(result, status, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                    (255, 0, 255), 2, cv2.LINE_AA)
        counts = {half: sum(r.get("half") == half for r in regions)
                  for half in ("yellow", "blue", "on_line", "unknown")}
        summary = f"TOTAL: {len(regions)} | Y: {counts['yellow']} B: {counts['blue']} LINE: {counts['on_line']} ?: {counts['unknown']}"
        cv2.putText(result, summary, (15, 58), cv2.FONT_HERSHEY_SIMPLEX,
                    0.65, (0, 255, 0), 2, cv2.LINE_AA)
    label_boxes = []
    for index, region in enumerate(regions, 1):
        x, y, width, height = region["bbox_px"]
        cv2.rectangle(result, (x, y), (x + width - 1, y + height - 1), (0, 255, 0), 2)
        label = f'{index}: ({region["x_mm"]:.0f}, {region["y_mm"]:.0f}) mm' if calibrated and details else str(index)
        if "half" in region:
            label += ' ' + {"yellow": "Y", "blue": "B", "on_line": "LINE", "unknown": "?"}[region["half"]]
        if "direction_arrow_px" in region:
            origin, destination = np.asarray(region["direction_arrow_px"])
            delta = destination - origin
            end = origin + delta * min(1, 36 / max(float(np.linalg.norm(delta)), 1))
            start, end = [tuple(np.rint(p).astype(int)) for p in (origin, end)]
            cv2.arrowedLine(result, start, end, (0, 255, 255), 2, cv2.LINE_AA, tipLength=0.3)
        text_width = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0][0]
        label_x = max(0, min(x, image.shape[1] - text_width - 5))
        label_y = max(82, y - 8)
        for offset in (0, 22, -22, 44, -44, 66, -66):
            candidate_y = min(image.shape[0] - 5, max(82, label_y + offset))
            box = (label_x, candidate_y - 18, label_x + text_width, candidate_y + 4)
            if not any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1]
                       for b in label_boxes):
                label_y = candidate_y
                break
        label_boxes.append((label_x, label_y - 18, label_x + text_width, label_y + 4))
        cv2.putText(result, label, (label_x, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 80, 0), 3, cv2.LINE_AA)
        cv2.putText(result, label, (label_x, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)
    return result


def demo_image():
    """Artificial input for learning the controls; not a real camera sample."""
    image = np.full((900, 1000, 3), 225, np.uint8)
    cv2.rectangle(image, (100, 50), (900, 450), (185, 105, 45), -1)
    cv2.rectangle(image, (100, 450), (900, 850), (45, 205, 230), -1)
    for x, y in [(250, 440), (420, 460), (600, 430), (770, 470)]:
        cv2.rectangle(image, (x - 7, y - 7), (x + 6, y + 6), (35, 45, 225), -1)
    return image


def select_corners(image):
    name = "1 - Corners: TL TR BR BL | Enter: confirm | R: reset | Esc: quit"
    scale = min(1100 / image.shape[1], 720 / image.shape[0], 1)
    preview = cv2.resize(image, None, fx=scale, fy=scale)
    points = []
    message = "Click TL, TR, BR, BL. Target colour: yellow."

    def mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append((x, y))
        elif event == cv2.EVENT_RBUTTONDOWN and points:
            points.pop()

    cv2.namedWindow(name, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(name, mouse)
    try:
        while True:
            frame = preview.copy()
            for number, point in enumerate(points, 1):
                cv2.circle(frame, point, 5, (0, 0, 255), -1)
                cv2.putText(frame, str(number), (point[0] + 8, point[1]),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.putText(frame, message, (10, 26), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (20, 20, 20), 2, cv2.LINE_AA)
            cv2.imshow(name, frame)
            key = cv2.waitKey(30) & 0xFF
            if key == 27 or cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE) < 1:
                return None
            if key in (ord("r"), ord("R")):
                points.clear()
            if key in (10, 13) and len(points) == 4:
                corners = np.asarray(points, np.float32)
                corners[:, 0] *= image.shape[1] / preview.shape[1]
                corners[:, 1] *= image.shape[0] / preview.shape[0]
                try:
                    return rectify(image, corners), corners.tolist()
                except ValueError as error:
                    print(error)
                    message = "Invalid corners. Press R and select TL, TR, BR, BL."
    finally:
        cv2.destroyAllWindows()


def inspect_photo(image, corners, source, capture=None):
    live = capture is not None
    name = "2 - Click block | D: coordinates | S: save | R: recalibrate | Esc: quit"
    controls = "Mask and HSV controls"
    sample = None
    details = False
    field = detect_midline(image)
    print("中线检测:", field["reason"], "；本次目标区：黄色")

    def mouse(event, x, y, flags, param):
        nonlocal sample
        if event == cv2.EVENT_LBUTTONDOWN:
            sx, sy = min(SIZE - 1, int(x * SIZE / PREVIEW)), min(SIZE - 1, int(y * SIZE / PREVIEW))
            # Sample the untouched image, never the rendered labels or boxes.
            sample = sample_colour(image, sx, sy)
            print("取色 HSV:", sample)

    cv2.namedWindow(name, cv2.WINDOW_AUTOSIZE)
    cv2.namedWindow(controls, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(name, mouse)
    sliders = {"H tolerance": (10, 90), "S tolerance": (70, 255),
               "V tolerance": (90, 255), "Min area": (150, 2000)}
    for label, (value, maximum) in sliders.items():
        cv2.createTrackbar(label, controls, value, maximum, lambda value: None)
    previous = None
    mask, regions, result = np.zeros((SIZE, SIZE), np.uint8), [], annotated(image, [], field)
    try:
        while True:
            if live:
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise ValueError("摄像头画面已断开，请检查 DroidCam 后重新启动。")
                if frame.shape[:2] != source["frame_size_hw"]:
                    raise ValueError("摄像头分辨率已改变，请重新启动并校正四角。")
                image = rectify(frame, corners)
                field = detect_midline(image)
            values = [cv2.getTrackbarPos(label, controls) for label in sliders]
            state = (tuple(sample or []), *values, details)
            if live or state != previous:
                if sample is not None:
                    mask, regions = segment(image, sample, *values, field=field)
                    classify_regions(regions, field)
                    result = annotated(image, regions, field, details=details)
                    if not live:
                        print(f"识别到 {len(regions)} 个同色区域（相连方块可能合并）。")
                else:
                    result = annotated(image, [], field)
                cv2.imshow(name, cv2.resize(result, (PREVIEW, PREVIEW)))
                cv2.imshow(controls, cv2.resize(mask, (420, 420), interpolation=cv2.INTER_NEAREST))
                previous = state
            key = cv2.waitKey(30) & 0xFF
            if key == 27 or any(cv2.getWindowProperty(w, cv2.WND_PROP_VISIBLE) < 1 for w in (name, controls)):
                break
            if live and key in (ord("r"), ord("R")):
                return True
            if key in (ord("d"), ord("D")):
                details = not details
            if key in (ord("s"), ord("S")) and sample is not None:
                folder = OUTPUT / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                folder.mkdir(parents=True)
                write_png(folder / "detected.png", result)
                write_png(folder / "mask.png", mask)
                if live:
                    write_png(folder / "source.png", frame)
                report = {"source": source, "field_mm": FIELD_MM,
                          "coordinate_system": "origin: lower-left; x: right; y: up",
                          "corners_in_photo_px": corners, "sample_hsv": sample,
                          "thresholds": dict(zip(sliders, values)), "regions": regions,
                          "field": field, "target_colour": "yellow",
                          "segmentation": "seeded-colour-v2",
                          "direction_is_not_a_path_or_motor_command": True}
                if live:
                    report["captured_at"] = datetime.now().isoformat(timespec="milliseconds")
                    report["corners_in_frame_px"] = report.pop("corners_in_photo_px")
                (folder / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print("已保存到:", folder)
    finally:
        cv2.destroyAllWindows()


def inspect_camera(index):
    """Preview a Windows webcam, then reuse the calibrated photo controls."""
    name = "Camera | N: next | P: previous | Enter: select corners | Esc: quit"
    capture = None
    try:
        while True:
            if capture is None:
                print(f"打开摄像头 {index}；N 下一个，P 上一个，Enter 选四角，Esc 退出。")
                capture = cv2.VideoCapture(index)
            ok, frame = capture.read()
            if ok and frame is not None:
                scale = min(1100 / frame.shape[1], 720 / frame.shape[0], 1)
                preview = cv2.resize(frame, None, fx=scale, fy=scale)
            else:
                preview = np.zeros((360, 800, 3), np.uint8)
                cv2.putText(preview, "No video. Check DroidCam, or press N / P.",
                            (15, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(preview, f"Camera {index} | N/P: switch | Enter: calibrate",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
            cv2.imshow(name, preview)
            key = cv2.waitKey(30) & 0xFF
            if key == 27 or cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE) < 1:
                return
            if key in (ord("n"), ord("N"), ord("p"), ord("P")):
                index = max(0, index + (1 if key in (ord("n"), ord("N")) else -1))
                capture.release()
                capture = None
            elif key in (10, 13) and ok and frame is not None:
                cv2.destroyAllWindows()
                selected = select_corners(frame)
                if selected is None:
                    return
                image, corners = selected
                source = {"type": "camera", "index": index, "frame_size_hw": frame.shape[:2]}
                print("点击方块中心取色；S 保存当前帧，R 重新校正，Esc 退出。请固定手机和场地。")
                if not inspect_photo(image, corners, source, capture):
                    return
    finally:
        if capture is not None:
            capture.release()
        cv2.destroyAllWindows()


def process_batch(paths, sample, output):
    """Reproducible non-GUI photo check, using pixel coordinates only."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    reports, panels = [], []
    for index, path in enumerate(paths, 1):
        image = read_photo(path)
        scale = min(1824 / image.shape[1], 1)
        if scale < 1:
            image = cv2.resize(image, None, fx=scale, fy=scale)
        field = detect_midline(image)
        mask, regions = segment(image, sample, field=field)
        # segment's millimetres assume a rectified 1200-square image.
        for region in regions:
            region.pop("x_mm")
            region.pop("y_mm")
        classify_regions(regions, field)
        result = annotated(image, regions, field, calibrated=False)
        folder = output / f"photo-{index}"
        folder.mkdir(exist_ok=True)
        write_png(folder / "detected.png", result)
        write_png(folder / "mask.png", mask)
        report = {"source": str(Path(path).resolve()), "processing_scale": scale,
                  "coordinate_unit": "processing image pixels", "calibrated": False,
                  "sample_hsv": sample, "thresholds": {"h_tol": 10, "s_tol": 70, "v_tol": 90, "min_area": 150},
                  "field": field, "regions": regions,
                  "direction_is_not_a_path_or_motor_command": True}
        (folder / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        reports.append(report)
        panel = np.full((760, 960, 3), 245, np.uint8)
        ratio = min(940 / result.shape[1], 680 / result.shape[0])
        thumb = cv2.resize(result, None, fx=ratio, fy=ratio)
        th, tw = thumb.shape[:2]
        panel[65:65+th, (960-tw)//2:(960-tw)//2+tw] = thumb
        cv2.putText(panel, f"Photo {index}: {len(regions)} blocks | line: {field['valid']}",
                    (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
        panels.append(panel)
        counts = {half: sum(r["half"] == half for r in regions) for half in ("yellow", "blue", "on_line", "unknown")}
        print(f"Photo {index}: midline={field['valid']}, regions={len(regions)}, halves={counts}")
    rows = []
    for i in range(0, len(panels), 2):
        rows.append(np.hstack([panels[i], panels[i+1] if i+1 < len(panels) else np.full_like(panels[i], 245)]))
    write_png(output / "overview.png", np.vstack(rows))
    (output / "result.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Results:", output.resolve())


def main():
    parser = argparse.ArgumentParser(description="OpenCV 手机照片识别：标定四角，点击取色，S 保存。")
    parser.add_argument("image", nargs="?", help="JPG/PNG 文件路径；留空则弹出选择窗口")
    parser.add_argument("--demo", action="store_true", help="用合成演示图练习操作")
    parser.add_argument("--camera", nargs="?", const=0, type=int, metavar="INDEX",
                        help="实时摄像头识别，默认编号 0；预览时 N/P 切换摄像头")
    parser.add_argument("--batch", nargs="+", metavar="PHOTO", help="无窗口批量检查：检测中线、分区及朝黄色区的方向")
    parser.add_argument("--sample-hsv", nargs=3, type=int, default=[3, 196, 148], help="批量模式的方块取色 H S V")
    parser.add_argument("--output", default=str(OUTPUT / "midline-batch"), help="批量结果目录")
    args = parser.parse_args()
    if args.camera is not None:
        if args.camera < 0 or args.image or args.demo or args.batch:
            parser.error("--camera 需要非负编号，不能与照片、--demo 或 --batch 同用")
        inspect_camera(args.camera)
        return
    if args.batch:
        if not (0 <= args.sample_hsv[0] <= 179 and all(0 <= v <= 255 for v in args.sample_hsv[1:])):
            parser.error("HSV must be H=0..179, S/V=0..255")
        process_batch(args.batch, args.sample_hsv, args.output)
        return
    if args.demo:
        image, source = demo_image(), "synthetic-demo"
        print("演示图：场地在彩色区域，四角为左上、右上、右下、左下。")
    else:
        filename = args.image
        if not filename:
            filename = choose_photo()
        if not filename:
            return
        image, source = read_photo(filename), str(Path(filename).resolve())
    print("第一步：按左上→右上→右下→左下选四角，Enter 确认，R 重选。")
    selected = select_corners(image)
    if selected is not None:
        field, corners = selected
        print("第二步：点击方块中心取色，调节滑块，S 保存结果，Esc 退出。")
        inspect_photo(field, corners, source)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError, cv2.error) as error:
        print("运行失败:", error)
        raise SystemExit(1)
