"""Check video decoding, annotations, timing and moving detections end to end."""
import json
import tempfile
from pathlib import Path

import cv2
import numpy as np

from photo_vision import process_video


def main():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        source = root / "source.avi"
        writer = cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*"MJPG"),12,(600,600))
        assert writer.isOpened()
        for i in range(8):
            image = np.full((600,600,3),(200,90,20),np.uint8)
            image[:300] = (20,220,240)
            for x,y in [(200+i*4,400),(400,150)]:
                cv2.rectangle(image,(x-12,y-12),(x+12,y+12),(30,40,180),-1)
            writer.write(image)
        writer.release()
        process_video(source,[2,223,118],root/"output")
        report = json.loads((root/"output/result.json").read_text(encoding="utf8"))
        assert report["decoded_frames"] == 8
        assert abs(report["fps"]-12)<0.01
        assert report["region_count_min"] == report["region_count_max"] == 2
        assert all(f["counts"]["yellow"]==1 and f["counts"]["blue"]==1 for f in report["frames"])
        first = report["frames"][0]["regions"][0]["bbox_px"][0]
        last = report["frames"][-1]["regions"][0]["bbox_px"][0]
        assert last-first > 20, (first,last)
        assert not report["tracking"] and not report["executable"]
        assert all(not f["priority"]["executable"] for f in report["frames"])
        cap = cv2.VideoCapture(str(root/"output/annotated.mp4"))
        try:
            count=0
            while True:
                ok,frame=cap.read()
                if not ok:break
                assert frame.shape[:2]==(600,600)
                count+=1
            assert count==8,count
        finally:
            cap.release()
    print("PASS: eight real video frames, moving detections, counts, FPS, exported decode, preview-only priorities")


if __name__ == "__main__":
    main()
