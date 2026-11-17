"""Offline import/config check: no camera access or motor commands."""
import importlib
from pathlib import Path
import cv2, numpy, serial
from strategy.planner import Config
from vision.robot_vision import load_config
for name in ('control.launcher','control.keyboard_remote','control.vision_wifi_test',
             'control.vision_approach_test','control.bluetooth_link','vision.photo_vision'):
    importlib.import_module(name)
Config.load(Path(__file__).parent/'strategy'/'config.json')
load_config()
dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
assert cv2.aruco.generateImageMarker(dictionary,0,100).shape==(100,100)
assert hasattr(cv2,'imshow')
print('PASS: imports, configuration, ArUco generation. Camera/network/car NOT tested.')
print('OpenCV',cv2.__version__,'NumPy',numpy.__version__,'pyserial',serial.__version__)
