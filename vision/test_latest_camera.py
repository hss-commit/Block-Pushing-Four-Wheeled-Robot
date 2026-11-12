"""A slow consumer gets the newest frame; failures never replay an old frame."""
import queue
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vision.latest_camera import LatestCamera


class Device:
    def __init__(self):
        self.frames = queue.Queue()
        self.released = False

    def set(self, *args):
        return False  # Driver ignores buffer size; the latest slot must still work.

    def read(self):
        item = self.frames.get()
        if isinstance(item, Exception):
            raise item
        return item

    def release(self):
        self.released = True


def wait_frames(camera, count):
    with camera._condition:
        assert camera._condition.wait_for(lambda: camera._sequence >= count, timeout=2)


def main():
    device = Device()
    with patch('vision.latest_camera.cv2.VideoCapture', return_value=device):
        camera = LatestCamera(1)
    try:
        for frame in ('old', 'middle', 'newest'):
            device.frames.put((True, frame))
        wait_frames(camera, 3)
        assert camera.read() == (True, 'newest'), 'Queued old frames were replayed'
        stamp = camera.captured_at
        assert camera.read() == (False, None), 'Same frame was counted as a fresh observation'
        assert camera.captured_at == stamp
        # A frame acquired before a long processing pause must not become fresh
        # just because the consumer is only now reading the slot.
        device.frames.put((True, 'expired'))
        wait_frames(camera, 4)
        with camera._condition:
            camera._stamp -= 1
        assert camera.read() == (False, None), 'Old acquisition time was overwritten at consumption'
        device.frames.put((False, None))
        wait_frames(camera, 5)
        assert camera.read() == (False, None), 'Camera loss replayed an old image'
        device.frames.put(OSError('unplugged'))
        wait_frames(camera, 6)
        try:
            camera.read()
        except OSError:
            pass
        else:
            raise AssertionError('Capture error was hidden')
    finally:
        device.frames.put((False, None))
        camera.release()
    assert device.released and not camera._worker.is_alive()
    assert camera.read() == (False, None)
    print('PASS: slow consumer skips old frames, no duplicate observation, camera loss/error, release')


if __name__ == '__main__':
    main()
