"""Reproduce the first real-photo calibration, without a GUI or color picking."""
import ast
import inspect
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vision"))
import cv2
from photo_vision import choose_photo, read_photo, rectify, write_png

sample_dir = ROOT / "vision" / "samples"
config = json.loads((sample_dir / "empty_field_calibration.json").read_text(encoding="utf-8"))
photo = read_photo(sample_dir / config["image"])
field = rectify(photo, config["corners_px_tl_tr_br_bl"])
folder = ROOT / "vision" / "results" / "empty-field"
folder.mkdir(parents=True, exist_ok=True)
write_png(folder / "rectified.png", field)
write_png(folder / "preview.png", cv2.resize(field, (700, 700)))
marked = photo.copy()
for number, (x, y) in enumerate(config["corners_px_tl_tr_br_bl"], 1):
    cv2.circle(marked, (x, y), 7, (0, 0, 255), -1)
    cv2.putText(marked, str(number), (x + 8, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
write_png(folder / "selected-corners.png", marked)
assert field.shape == (1200, 1200, 3)
assert read_photo(folder / "rectified.png").shape == field.shape

# Parse the actual chooser command without opening a modal dialog.
function = ast.parse(inspect.getsource(choose_photo)).body[0]
assignment = next(item for item in function.body if isinstance(item, ast.Assign))
script = ROOT / "tmp" / "check_photo_picker.ps1"
script.write_text(ast.literal_eval(assignment.value), encoding="utf-8-sig")
command = "$tokens=$null; $errors=$null; [System.Management.Automation.Language.Parser]::ParseFile((Join-Path (Get-Location) 'tmp/check_photo_picker.ps1'), [ref]$tokens, [ref]$errors) | Out-Null; if($errors.Count){ $errors | Out-String | Write-Output; exit 1 }; Write-Output 'Photo picker syntax: OK'"
subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], cwd=ROOT, check=True)
print("Real empty-field photo: corrected and saved; no block-detection claim.")
