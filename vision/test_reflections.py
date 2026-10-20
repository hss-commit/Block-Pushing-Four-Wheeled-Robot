"""Regression checks for pale block faces and the saved DroidCam scene."""

import json
from pathlib import Path

import cv2
import numpy as np

from photo_vision import SIZE, read_photo, rectify, segment, detect_midline, sample_colour


def main():
    hsv = np.full((SIZE, SIZE, 3), (110, 180, 190), np.uint8)
    # A pale face connected to a saturated edge is one complete block.
    hsv[300:340, 400:440] = (175, 120, 190)
    hsv[300:340, 400:408] = (1, 220, 150)
    # A second bright red block should survive sampling a darker red block.
    hsv[500:540, 700:740] = (1, 220, 245)
    # Low-saturation disconnected clutter must not become a block.
    hsv[800:840, 900:940] = (175, 100, 190)
    image = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    _, regions = segment(image, [2, 223, 118])
    assert len(regions) == 2, regions
    assert regions[0]["area_px"] >= 1500, regions
    print("PASS: pale faces recovered, bright red retained, disconnected pale clutter rejected")
    # Median patch ignores an isolated bad pixel, including across hue 0/179.
    patch = np.full((9, 9, 3), (179, 220, 150), np.uint8)
    patch[4, 4] = (0, 0, 255)
    colour = sample_colour(cv2.cvtColor(patch, cv2.COLOR_HSV2BGR), 4, 4)
    assert min(abs(colour[0]-179), 180-abs(colour[0]-179)) <= 1, colour
    assert colour[1] > 200 and colour[2] == 150, colour
    # A saturated red item outside the detected field must be excluded.
    scene = np.full((600, 800, 3), 210, np.uint8)
    scene[100:500, 100:400] = (20, 220, 240)
    scene[100:500, 400:700] = (200, 90, 20)
    scene[200:220, 200:220] = (30, 40, 180)
    scene[20:40, 20:40] = (30, 40, 180)
    field = detect_midline(scene)
    assert field["valid"], field
    assert len(segment(scene, [2, 223, 118], field=field)[1]) == 1
    print("PASS: robust patch sample and exclusion of coloured objects outside field")

    root = Path(__file__).parent / "results" / "20261020-162420-808682"
    if not (root / "source.png").exists():
        print("SKIP: local saved DroidCam scene unavailable")
        return
    report = json.loads((root / "result.json").read_text(encoding="utf-8"))
    image = rectify(read_photo(root / "source.png"), report["corners_in_frame_px"])
    _, regions = segment(image, report["sample_hsv"], field=detect_midline(image))
    # Manually marked centres on the original 640x480 frame: 11 yellow, 9 blue.
    points = np.float32([[382,103], [332,147], [319,167], [344,182], [383,170],
                         [322,200], [339,195], [359,194], [468,184], [485,195], [444,213],
                         [196,275], [210,276], [237,293], [262,306], [267,319],
                         [282,282], [273,342], [284,343], [310,335]])
    matrix = cv2.getPerspectiveTransform(np.float32(report["corners_in_frame_px"]),
                                         np.float32([[0,0],[1199,0],[1199,1199],[0,1199]]))
    expected = cv2.perspectiveTransform(points[None], matrix)[0]
    actual = np.array([[r["x_mm"] * 1199 / 1200, (1200-r["y_mm"]) * 1199 / 1200]
                       for r in regions])
    assert len(regions) == 20, len(regions)
    distances = np.linalg.norm(expected[:, None] - actual[None, :], axis=2)
    assert (distances.min(axis=1) < 18).all(), distances.min(axis=1)
    assert len(set(distances.argmin(axis=1))) == 20, "Two targets matched one detection"
    print("PASS: saved scene matches 20 individually marked blocks")


if __name__ == "__main__":
    main()
