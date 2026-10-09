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


def segment(image, sample, h_tol=10, s_tol=70, v_tol=90, min_area=150):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    center = np.asarray(sample, dtype=np.int16)
    delta_h = np.abs(hsv[:, :, 0].astype(np.int16) - center[0])
    # Hue is circular in OpenCV: red occurs on both sides of 0/179.
    hue = np.minimum(delta_h, 180 - delta_h) <= h_tol
    sat = np.abs(hsv[:, :, 1].astype(np.int16) - center[1]) <= s_tol
    val = np.abs(hsv[:, :, 2].astype(np.int16) - center[2]) <= v_tol
    mask = (hue & sat & val).astype(np.uint8) * 255
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    count, _, stats, centers = cv2.connectedComponentsWithStats(mask, connectivity=8)
    regions = []
    for index in range(1, count):
        x, y, width, height, area = map(int, stats[index])
        if area < min_area:
            continue
        cx, cy = map(float, centers[index])
        regions.append({
            "x_mm": round(cx * FIELD_MM / (SIZE - 1), 1),
            "y_mm": round((SIZE - 1 - cy) * FIELD_MM / (SIZE - 1), 1),
            "area_px": area, "bbox_px": [x, y, width, height],
        })
    return mask, sorted(regions, key=lambda region: (region["x_mm"], region["y_mm"]))


def annotated(image, regions):
    result = image.copy()
    for index, region in enumerate(regions, 1):
        x, y, width, height = region["bbox_px"]
        cv2.rectangle(result, (x, y), (x + width - 1, y + height - 1), (0, 255, 0), 2)
        label = f'{index}: ({region["x_mm"]:.0f}, {region["y_mm"]:.0f}) mm'
        cv2.putText(result, label, (min(x, SIZE - 320), max(22, y - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 80, 0), 3, cv2.LINE_AA)
        cv2.putText(result, label, (min(x, SIZE - 320), max(22, y - 8)),
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
    message = "Click TL, TR, BR, BL. Own half at bottom."

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


def inspect_photo(image, corners, source):
    name, controls = "2 - Click block | S: save | Esc: quit", "Mask and HSV controls"
    sample = None

    def mouse(event, x, y, flags, param):
        nonlocal sample
        if event == cv2.EVENT_LBUTTONDOWN:
            sx, sy = min(SIZE - 1, int(x * SIZE / PREVIEW)), min(SIZE - 1, int(y * SIZE / PREVIEW))
            # Sample the untouched image, never the rendered labels or boxes.
            sample = cv2.cvtColor(image[sy:sy + 1, sx:sx + 1], cv2.COLOR_BGR2HSV)[0, 0].tolist()
            print("取色 HSV:", sample)

    cv2.namedWindow(name, cv2.WINDOW_AUTOSIZE)
    cv2.namedWindow(controls, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(name, mouse)
    sliders = {"H tolerance": (10, 90), "S tolerance": (70, 255),
               "V tolerance": (90, 255), "Min area": (150, 2000)}
    for label, (value, maximum) in sliders.items():
        cv2.createTrackbar(label, controls, value, maximum, lambda value: None)
    previous = None
    mask, regions, result = np.zeros((SIZE, SIZE), np.uint8), [], image.copy()
    try:
        while True:
            values = [cv2.getTrackbarPos(label, controls) for label in sliders]
            state = (tuple(sample or []), *values)
            if state != previous:
                if sample is not None:
                    mask, regions = segment(image, sample, *values)
                    result = annotated(image, regions)
                    print(f"识别到 {len(regions)} 个同色区域（相连方块可能合并）。")
                cv2.imshow(name, cv2.resize(result, (PREVIEW, PREVIEW)))
                cv2.imshow(controls, cv2.resize(mask, (420, 420), interpolation=cv2.INTER_NEAREST))
                previous = state
            key = cv2.waitKey(30) & 0xFF
            if key == 27 or any(cv2.getWindowProperty(w, cv2.WND_PROP_VISIBLE) < 1 for w in (name, controls)):
                break
            if key in (ord("s"), ord("S")) and sample is not None:
                folder = OUTPUT / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                folder.mkdir(parents=True)
                write_png(folder / "detected.png", result)
                write_png(folder / "mask.png", mask)
                report = {"source": source, "field_mm": FIELD_MM,
                          "coordinate_system": "origin: lower-left; x: right; y: up",
                          "corners_in_photo_px": corners, "sample_hsv": sample,
                          "thresholds": dict(zip(sliders, values)), "regions": regions}
                (folder / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print("已保存到:", folder)
    finally:
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="OpenCV 手机照片识别：标定四角，点击取色，S 保存。")
    parser.add_argument("image", nargs="?", help="JPG/PNG 文件路径；留空则弹出选择窗口")
    parser.add_argument("--demo", action="store_true", help="用合成演示图练习操作")
    args = parser.parse_args()
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
