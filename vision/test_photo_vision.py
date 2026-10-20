"""Small end-to-end checks on synthetic inputs, without requiring a camera."""

import tempfile
from pathlib import Path

import cv2
import numpy as np

from photo_vision import SIZE, annotated, read_photo, rectify, segment, write_png, detect_midline, classify_regions


def check_midline():
    # Off-centre boundary proves the detector observes colours, not image centre.
    image = np.full((600, 800, 3), (200, 90, 20), np.uint8)
    image[:, :310] = (20, 220, 240)
    field = detect_midline(image)
    assert field["valid"], field
    assert abs(field["point_px"][0] - 309.5) < 2, field
    assert field["yellow_normal"][0] < -0.99, field
    boxes = [{"bbox_px": box} for box in ([200, 200, 20, 20], [400, 200, 20, 20], [300, 200, 20, 20])]
    classify_regions(boxes, field)
    assert [r["half"] for r in boxes] == ["yellow", "blue", "on_line"], boxes
    assert "direction_arrow_px" not in boxes[0]
    for region in boxes[1:]:
        start, end = np.array(region["direction_arrow_px"])
        assert end[0] < start[0]
        assert np.dot(end - field["point_px"], field["yellow_normal"]) > field["line_band_px"]
    rotated = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    field_rotated = detect_midline(rotated)
    assert field_rotated["valid"] and field_rotated["yellow_normal"][1] < -0.99, field_rotated
    diagonal = image.copy()
    yy, xx = np.indices(diagonal.shape[:2])
    diagonal[xx < 200 + yy * 0.5] = (20, 220, 240)
    diagonal[xx >= 200 + yy * 0.5] = (200, 90, 20)
    assert detect_midline(diagonal)["valid"]
    # Single colour, a wide occlusion, and disconnected colour patches must fail.
    for invalid in (np.full_like(image, (200, 90, 20)), np.zeros_like(image)):
        missing = detect_midline(invalid)
        assert not missing["valid"], missing
        classify_regions(boxes, missing)
        assert all(r["half"] == "unknown" and "direction_arrow_px" not in r for r in boxes)
    gap = image.copy()
    gap[:, 280:350] = 0
    assert not detect_midline(gap)["valid"]
    print("PASS: observed off-centre/rotated/diagonal line, yellow direction, crossing blocks, fail-closed missing interface")


def main():
    check_midline()
    # Two red hues on opposite sides of the hue boundary should both survive.
    hsv = np.full((SIZE, SIZE, 3), (110, 180, 190), dtype=np.uint8)
    hsv[290:310, 390:410] = (1, 220, 220)
    hsv[790:810, 890:910] = (179, 220, 220)
    original = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    corners = np.float32([[110, 90], [1330, 180], [1250, 1340], [60, 1230]])
    source = np.float32([[0, 0], [SIZE - 1, 0], [SIZE - 1, SIZE - 1], [0, SIZE - 1]])
    transform = cv2.getPerspectiveTransform(source, corners)
    photo = cv2.warpPerspective(original, transform, (1450, 1450))
    field = rectify(photo, corners)
    _, regions = segment(field, [0, 220, 220])
    assert len(regions) == 2, regions
    expected = [(400, 900), (900, 400)]
    for region, (x, y) in zip(regions, expected):
        assert abs(region["x_mm"] - x) < 3, region
        assert abs(region["y_mm"] - y) < 3, region
    assert not segment(field, [50, 220, 220])[1], "Unrelated hue should not match"
    for invalid in ([[0, 0]] * 4, [[0, 0], [1199, 1199], [1199, 0], [0, 1199]]):
        try:
            rectify(original, invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid calibration accepted")
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "手机照片.png"
        write_png(path, original)
        assert np.array_equal(read_photo(path), original), "Chinese path image I/O failed"
        write_png(Path(temp) / "标注结果.png", annotated(field, regions))
    print(f"PASS: OpenCV {cv2.__version__}; perspective, HSV wrap, coordinates, invalid corners, Chinese paths")
    print("Synthetic regions:", regions)


if __name__ == "__main__":
    main()
