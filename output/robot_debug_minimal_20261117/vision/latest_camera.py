"""Keep one newest webcam frame while the UI is busy processing."""
import threading
import time

import cv2


class LatestCamera:
    def __init__(self, index):
        self._device = cv2.VideoCapture(index)
        self._device.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._condition = threading.Condition()
        self._closed = threading.Event()
        self._sequence = self._consumed = 0
        self._latest = (False, None)
        self._error = None
        self._stamp = self.captured_at = time.monotonic()
        self._worker = threading.Thread(target=self._capture, daemon=True)
        self._worker.start()

    def _capture(self):
        try:
            while not self._closed.is_set():
                started = time.monotonic()
                result = self._device.read()
                with self._condition:
                    self._latest = result
                    self._stamp = started
                    self._sequence += 1
                    self._condition.notify_all()
                if not result[0]:
                    self._closed.wait(.02)
        except Exception as error:
            with self._condition:
                self._error = error
                self._sequence += 1
                self._condition.notify_all()
        finally:
            self._device.release()

    def read(self):
        with self._condition:
            self._condition.wait_for(lambda: self._closed.is_set() or
                self._sequence != self._consumed, timeout=.2)
            if self._closed.is_set():
                return False, None
            if self._error is not None:
                raise OSError('摄像头读取失败：'+str(self._error)) from self._error
            if self._sequence == self._consumed:
                return False, None
            self._consumed = self._sequence
            self.captured_at = self._stamp
            if time.monotonic()-self.captured_at > .2:
                return False, None
            return self._latest

    def release(self):
        self._closed.set()
        with self._condition:
            self._condition.notify_all()
        # A blocked driver read must not hang the UI or race a native release.
        self._worker.join(timeout=.5)
