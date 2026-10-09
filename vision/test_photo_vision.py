"""Small end-to-end checks on synthetic inputs, without requiring a camera."""

import tempfile
from pathlib import Path

import cv2
import numpy as np

from photo_vision import SIZE, annotated, read_photo, rectify, segment, write_png


def main():
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
