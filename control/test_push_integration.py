"""Camera pixels -> actual controller -> loopback HTTP -> moving block -> stop.

Uses the real application loop and HTTP client, never a camera or physical car.
"""
from contextlib import ExitStack, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
from urllib.parse import parse_qs

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from control import vision_approach_test as app
from control.single_push_control import SinglePushControl
from control.straight_push_control import StraightPush
from strategy.planner import Config
from vision.robot_vision import detect_robot
from vision.test_robot_vision import paste_marker, TEST_CONFIG


def check(case='push', distance=100):
    round_trip = case == 'round_trip'
    origin, block_start = (760., 680.) if round_trip else (950., 750.)
    world = dict(now=0., car=origin, block=block_start, frames=0, requests=[], pending=0)
    control = (StraightPush(Config.load(Path(app.__file__).resolve().parent.parent/'strategy/config.json'))
               if round_trip else SinglePushControl(distance_mm=distance))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_request(self):
            data = parse_qs(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode())
            world['requests'].append((self.command, self.path, data))
            if self.path == '/step':
                direction, = data['direction']
                assert direction in (('forward', 'backward') if round_trip else ('forward',)), data
                assert len(data['id'][0]) == 32
                if case != 'reject':
                    world['pending'] += 1 if direction == 'forward' else -1
            result = {'/status': 'ready', '/stop': 'stop_queued', '/step': 'step_queued'}[self.path]
            if case == 'reject' and self.path == '/step':
                result = 'busy'
            payload = json.dumps(dict(protocol='vision-pulse-v1', pulse_ms=250,
                                      step_ms=120, gentle_step_ms=80, reverse_step=True, result=result)).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = handle_request
        do_POST = handle_request

    class Camera:
        def read(self):
            world['now'] += .1
            self.captured_at = world['now']
            world['frames'] += 1
            if world['pending']:
                if case != 'stalled':
                    world['car'] -= 10 * world['pending']
                    if world['pending'] > 0:
                        world['block'] = min(world['block'], world['car']-(60 if round_trip else 115))
                world['pending'] = 0
            image = np.full((1200, 1200, 3), (200, 90, 20), np.uint8)
            image[600:] = (20, 220, 240)
            if case != 'lost_marker' or world['car'] == 950:
                paste_marker(image, (600, 1200-world['car']), 50 if round_trip else 100, 2)
            y = round(1200-world['block'])
            if not round_trip or world['car']-world['block'] > 65:
                cv2.rectangle(image, (590, y-10), (609, y+9), (0, 0, 230), -1)
            return True, image

        def release(self):
            world['released'] = True

    def error_window(name, error):
        assert case == 'reject', str(error)
        assert control.finished and not control.active
        world['error'] = str(error)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack, redirect_stdout(io.StringIO()):
            mode_args = ['--straight-push'] if round_trip else ['--single-push', '--push-distance', str(distance)]
            argv = ['push-test', *mode_args, '--host', f'http://127.0.0.1:{server.server_port}']

            def key(*args):
                if control.finished or world['frames'] > (95 if round_trip else 250):
                    return 27
                if round_trip and control.last_plan['can_start']:
                    return 32
                return 0
            for obj, name, value in (
                (app.sys, 'argv', argv), (app, 'OUTPUT', Path(folder)),
                (app, 'StraightPush' if round_trip else 'SinglePushControl', lambda *args: control),
                (app, 'detect_robot', lambda image, **kwargs: detect_robot(image, TEST_CONFIG, **kwargs)),
                (app, 'calibration', lambda index: (Camera(), [], 0, (1200, 1200))),
                (app, 'rectify', lambda frame, corners: frame),
                (app, 'show_stopped_error', error_window),
                (app.time, 'monotonic', lambda: world['now']),
                (cv2, 'namedWindow', lambda *args: None),
                (cv2, 'setMouseCallback', lambda name, callback:
                    callback(cv2.EVENT_LBUTTONDOWN, 350, round((1200-block_start)*700/1200), 0, None)),
                (cv2, 'imshow', lambda *args: None),
                (cv2, 'getWindowProperty', lambda *args: 1),
                (cv2, 'waitKey', key),
                (cv2, 'destroyAllWindows', lambda: None),
            ):
                stack.enter_context(patch.object(obj, name, value))
            returned = app.main()
            events = [json.loads(line) for path in Path(folder).glob('*/events.jsonl')
                      for line in path.read_text(encoding='utf-8').splitlines()]
        steps = [data['id'][0] for _, path, data in world['requests'] if path == '/step']
        assert steps and len(set(steps)) == len(steps), control.last_plan
        assert world['requests'][-1][1] == '/stop' and world['released'], world
        if round_trip:
            assert control.state == 'DONE' and control.completed == 1, control.last_plan
            assert abs(world['car']-origin) <= 10 and world['block'] <= 585, world
            motion = [data['direction'][0] if path == '/step' else 'stop'
                      for _, path, data in world['requests'] if path in ('/step', '/stop')]
            first_reverse = motion.index('backward')
            assert motion[first_reverse-2:first_reverse] == ['forward', 'stop'], motion
            assert 'forward' not in motion[first_reverse:] and motion[-1] == 'stop', motion
        elif case == 'push':
            assert control.state == 'DONE', control.last_plan
            assert 750-world['block'] >= distance, world
            assert control.last_plan['block_progress_mm'] >= distance
            assert any(e['event'] == 'plan' and e['plan'].get('state') == 'DONE' for e in events)
        else:
            assert control.state == 'STOPPED' and not control.active, control.last_plan
            assert world['block'] == 750, world
            if case == 'reject':
                assert returned is False and len(steps) == 1, 'Rejected motion was retried'
                assert any(e['event'] == 'error' for e in events)
            else:
                reason = 'NO VISUAL PROGRESS' if case == 'stalled' else 'NEED ROBOT MARKER'
                assert reason in control.last_plan['reason'], control.last_plan
        detail = 'push, stop, reverse, final stop' if round_trip else f'{case}, target={distance}mm'
        print(f'PASS: actual app + ArUco + block pixels + HTTP: {detail}')
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


if __name__ == '__main__' and '--round-trip' in sys.argv:
    check('round_trip')
elif __name__ == '__main__':
    check('round_trip')
    for distance in (20, 100, 150):
        check(distance=distance)
    for case in ('stalled', 'lost_marker', 'reject'):
        check(case)
