"""Run retained checks in separate processes; never contacts the real car."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
GROUPS = {
    '视觉': ['vision/test_latest_camera.py', 'vision/test_robot_vision.py', 'vision/test_photo_vision.py',
             'vision/test_camera_vision.py', 'vision/test_video_vision.py',
             'vision/test_reflections.py', 'vision/test_priority_results.py'],
    '通信与控制': ['control/test_launcher.py', 'control/test_keyboard_remote.py', 'control/test_vision_wifi.py',
                   'control/test_bluetooth_link.py', 'control/test_approach_control.py',
                   'control/test_single_push_control.py'],
    '直接推块联调': ['control/test_push_integration.py', 'control/test_multi_push_control.py',
                     'control/test_multi_push_integration.py', 'control/test_multi_reconnect.py'],
    '比赛策略': ['strategy/test_planner.py', 'strategy/test_runtime.py',
                 'strategy/test_scene_priority.py', 'strategy/test_simulator.py'],
}


def main():
    failures = []
    total = 0
    for group, files in GROUPS.items():
        print(f'\n【{group}】', flush=True)
        for file in files:
            total += 1
            print(f'检查：{file}', flush=True)
            env = {**os.environ, 'PYTHONPATH': str(ROOT)+os.pathsep+os.environ.get('PYTHONPATH', '')}
            result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/file)], cwd=ROOT, env=env)
            if result.returncode:
                failures.append(file)
    print(f'\n共{total}项：通过{total-len(failures)}，失败{len(failures)}。', flush=True)
    for file in failures:
        print('失败：'+file)
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
