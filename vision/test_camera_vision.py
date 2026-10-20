"""Check live processing with real OpenCV video I/O and simulated UI keys."""

import json
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np

import photo_vision as vision


def main():
    with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
        root = Path(temp)
        video = root / "camera.avi"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (1200, 1200))
        assert writer.isOpened(), "Test video encoder unavailable"
        for x in (300, 800, 500):
            frame = np.full((1200, 1200, 3), (200, 90, 20), np.uint8)
            frame[600:] = (20, 220, 240)
            cv2.rectangle(frame, (x - 20, 280), (x + 20, 320), (30, 40, 230), -1)
            writer.write(frame)
        writer.release()
        capture = cv2.VideoCapture(str(video))
        stack.callback(capture.release)
        corners = [[0, 0], [1199, 0], [1199, 1199], [0, 1199]]
        source = {"type": "camera", "index": 0, "frame_size_hw": (1200, 1200)}
        mouse = None
        keys = iter((0, ord("s"), ord("r")))

        def wait_key(delay):
            key = next(keys)
            if key == 0:
                mouse(cv2.EVENT_LBUTTONDOWN, 175, 175, 0, None)
            return key

        def set_mouse(name, callback):
            nonlocal mouse
            mouse = callback

        values = {"H tolerance": 10, "S tolerance": 70, "V tolerance": 90, "Min area": 150}
        for name in ("namedWindow", "imshow", "destroyAllWindows", "createTrackbar"):
            stack.enter_context(patch.object(cv2, name))
        stack.enter_context(patch.object(vision, "OUTPUT", root / "results"))
        stack.enter_context(patch.object(cv2, "setMouseCallback", side_effect=set_mouse))
        stack.enter_context(patch.object(cv2, "getTrackbarPos", side_effect=lambda label, window: values[label]))
        stack.enter_context(patch.object(cv2, "getWindowProperty", return_value=1))
        stack.enter_context(patch.object(cv2, "waitKey", side_effect=wait_key))
        assert vision.inspect_photo(frame, corners, source, capture) is True
        report_path = next((root / "results").glob("*/result.json"))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert len(report["regions"]) == 1, report["regions"]
        assert abs(report["regions"][0]["x_mm"] - 800) < 5, report
        assert report["regions"][0]["half"] == "blue", report
        assert report["field"]["valid"] and report["captured_at"]
        assert (report_path.parent / "source.png").exists()
        assert report["corners_in_frame_px"] == corners
        try:
            vision.inspect_photo(frame, corners, source, capture)
        except ValueError as error:
            assert "断开" in str(error)
        else:
            raise AssertionError("Camera disconnection was ignored")
        print("PASS: video frames, click sampling, moving block, midline, saved frame/JSON, recalibration, disconnection")

        device = Mock()
        device.read.return_value = (True, frame)
        stack.enter_context(patch.object(cv2, "VideoCapture", return_value=device))
        stack.enter_context(patch.object(cv2, "waitKey", return_value=13))
        stack.enter_context(patch.object(vision, "select_corners", return_value=(frame, corners)))
        stack.enter_context(patch.object(vision, "inspect_photo", side_effect=ValueError("disconnected")))
        try:
            vision.inspect_camera(0)
        except ValueError:
            pass
        device.release.assert_called_once()
        print("PASS: camera released after processing failure")


if __name__ == "__main__":
    main()
