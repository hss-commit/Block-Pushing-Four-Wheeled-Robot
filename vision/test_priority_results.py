"""Check that batch detection and saved-result ranking use the same ranking."""
import json
import tempfile
from pathlib import Path

import cv2
import numpy as np

from photo_vision import process_batch, rank_saved_results, write_png


def main():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        image = np.full((1000,1000,3),(200,90,20),np.uint8)
        image[:500] = (20,220,240)
        for x in (450,550):
            cv2.rectangle(image,(x-10,550),(x+10,570),(30,40,180),-1)
        photo = root / "现场.png"
        write_png(photo,image)
        process_batch([str(photo)],[2,223,118],root/"detected")
        batch = json.loads((root/"detected/result.json").read_text(encoding="utf8"))[0]
        assert batch["priority"]["groups"][0]["region_ids"] == [1,2]
        photo.unlink()  # The original can be moved; do not re-segment drawn boxes.
        rank_saved_results(root/"detected",root/"ranked")
        ranked = json.loads((root/"ranked/result.json").read_text(encoding="utf8"))[0]
        assert ranked["regions"] == batch["regions"]
        assert ranked["priority"] == batch["priority"]
        assert ranked["ranking_basis"] == "saved_detection_regions_without_resegmentation"
        assert (root/"ranked/photo-1/ranked.png").exists()
        assert "P1" in (root/"ranked/photo-1/priority.md").read_text(encoding="utf8")
        try:
            rank_saved_results(root/"detected",root/"detected")
        except ValueError:
            pass
        else:
            raise AssertionError("Input results may be overwritten")
    print("PASS: batch/saved priorities agree; moved original supported; original results protected")


if __name__ == "__main__":
    main()
