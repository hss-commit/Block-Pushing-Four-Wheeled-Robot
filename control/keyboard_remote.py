"""Windows hold-to-drive remote with renewable device-side expiry."""
import argparse
from datetime import datetime
import logging
from pathlib import Path
import sys
import time
import threading
import uuid

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from control.vision_wifi_test import WifiLink, OUTPUT

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())

class RemoteLink(WifiLink):
    # Human-controlled hold updates tolerate the measured 200-300ms hotspot RTT.
    # Autonomous vision clients retain WifiLink's 180ms deadline.
    request_timeout = .6

    def request(self, path, data=None):
        started = time.perf_counter()
        LOGGER.info('request path=%s data=%s timeout_s=%s', path, data, self.request_timeout)
        try:
            result = super().request(path, data)
        except (OSError, ValueError) as error:
            LOGGER.exception('request_failed path=%s elapsed_ms=%.0f', path,
                             (time.perf_counter()-started)*1000)
            raise OSError(f'小车通信失败（{path}，等待上限{self.request_timeout:g}秒）：{error}') from error
        LOGGER.info('response path=%s elapsed_ms=%.0f result=%s', path,
                    (time.perf_counter()-started)*1000, result)
        return result

    def connect(self):
        super().connect()
        status = self.request('/status')
        if status.get('manual_hold_ms') != 700 or status.get('manual_ramp_v') != 1:
            raise ValueError('请先重新上传新版“手机热点联动测试”固件，此版本需要低速起步和渐进加速。')

    def hold(self, direction):
        if direction not in ('forward', 'backward', 'left', 'right'):
            raise ValueError('无效遥控方向')
        response = self.request('/manual', {'id': uuid.uuid4().hex, 'direction': direction})
        if response.get('result') != 'manual_queued':
            raise ValueError('小车未接受持续遥控：'+str(response))


class HeldKeys:
    """Require neutral keys after focus loss/stop before allowing motion again."""
    def __init__(self):
        self.armed = False

    def update(self, pressed, focused):
        if not focused or pressed & {'stop', 'quit'}:
            self.armed = False
            return 'stop'
        directions = pressed & {'forward', 'backward', 'left', 'right'}
        if not directions:
            self.armed = True
            return 'stop'
        return next(iter(directions)) if self.armed and len(directions) == 1 else 'stop'


class RemoteWorker:
    """Only the latest fresh key state is sent; networking never blocks key-up."""
    def __init__(self, link):
        self.link = link
        self.condition = threading.Condition()
        self.closed = threading.Event()
        self.desired, self.updated = 'stop', time.monotonic()
        self.error = None
        self.ready = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def submit(self, direction):
        with self.condition:
            changed = direction != self.desired
            self.desired, self.updated = direction, time.monotonic()
            if changed:
                LOGGER.info('intent=%s', direction)
                self.condition.notify_all()

    def _run(self):
        try:
            self.link.connect()
            self.ready = True
            LOGGER.info('remote_ready')
            last = 'stop'
            while not self.closed.is_set():
                with self.condition:
                    intent = self.desired
                    direction = intent if time.monotonic()-self.updated <= .2 else 'stop'
                if direction == 'stop':
                    if last != 'stop':
                        self.link.stop()
                else:
                    self.link.hold(direction)
                last = direction
                with self.condition:
                    self.condition.wait_for(lambda: self.closed.is_set() or self.desired != intent, timeout=.1)
        except (OSError, ValueError) as error:
            self.error = error
            LOGGER.exception('remote_locked')
        finally:
            self.ready = False
            try:
                self.link.stop()
            except (OSError, ValueError):
                LOGGER.exception('stop_unconfirmed')

    def close(self):
        self.closed.set()
        with self.condition:
            self.condition.notify_all()
        self.thread.join(timeout=3)


def run(link):
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    name = 'Robot keyboard remote'
    keys = {0x57:'forward', 0x26:'forward', 0x53:'backward', 0x28:'backward',
            0x41:'left', 0x25:'left', 0x44:'right', 0x27:'right',
            0x20:'stop', 0x58:'stop', 0x51:'quit', 0x1b:'quit'}
    worker = None
    state = HeldKeys()
    try:
        cv2.namedWindow(name, cv2.WINDOW_AUTOSIZE)
        cv2.imshow(name, np.zeros((300,720,3), np.uint8))
        cv2.waitKey(1)
        handle = user32.FindWindowW(None, name)
        if not handle:
            raise OSError('无法找到遥控窗口')
        worker = RemoteWorker(link)
        print('点击新打开的遥控窗口；按住W/S/A/D或方向键持续运动，松开停车。空格/X停车，Q/Esc退出。')
        print('低速起步，按住逐渐加速；转向更慢。松开或换方向后重新从低速起步。')
        while True:
            focused = user32.GetForegroundWindow() == handle
            pressed = {label for key,label in keys.items() if user32.GetAsyncKeyState(key) & 0x8000} if focused else set()
            if 'quit' in pressed or cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE)<1:
                break
            direction = state.update(pressed, focused)
            worker.submit(direction if worker.ready else 'stop')
            if worker.error:
                raise worker.error
            panel = np.full((300,720,3),25,np.uint8)
            lines = ('HOLD W / UP: forward     S / DOWN: backward',
                     'HOLD A / LEFT: turn left  D / RIGHT: turn right',
                     'Release: STOP | SPACE / X: STOP | Q / Esc: exit',
                     ('CONNECTED' if worker.ready else 'CONNECTING')+' | '+direction.upper(),
                     'Slow start | Hold longer: faster | Gentle turning')
            for row,text in enumerate(lines):
                cv2.putText(panel,text,(15,40+48*row),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,230,255),1,cv2.LINE_AA)
            cv2.imshow(name,panel)
            cv2.waitKey(15)
    finally:
        if worker:
            worker.close()
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description='按住方向键连续遥控，松开或窗口失焦停车。')
    parser.add_argument('--host', required=True)
    args = parser.parse_args()
    folder = OUTPUT / ('keyboard-remote-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(folder/'events.log', encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    print('遥控日志：', folder/'events.log')

    try:
        run(RemoteLink(args.host))
    finally:
        LOGGER.removeHandler(handler)
        handler.close()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyboardInterrupt) as error:
        print('遥控已退出：', error)
        raise SystemExit(1)
