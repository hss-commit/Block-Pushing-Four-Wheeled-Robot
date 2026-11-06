"""Exercise serial framing/failure handling without a Bluetooth device or motion."""
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from control.bluetooth_link import BluetoothLink


class SerialPeer:
    def __init__(self, *args, **kwargs):
        self.writes = []
        self.buffer = bytearray()
        self.result = None
        self.silent = False
        self.closed = False
        self.uptime = 0xfffffff0
        self.wrong_id = False

    def write(self, message):
        self.writes.append(message)
        token, path, *extra = message.decode('ascii').strip().split()
        if self.silent:
            return len(message)
        result = {'/status': 'ready', '/stop': 'stop_queued', '/pulse': 'pulse_queued', '/step': 'step_queued'}[path]
        reply = {'protocol': 'vision-bt-v1', 'id': token, 'result': self.result or result,
                 'pulse_ms': 250, 'step_ms': 120, 'uptime_ms': self.uptime}
        if self.wrong_id:
            self.buffer.extend((json.dumps({**reply, 'id': '0'*32})+'\n').encode())
        self.buffer.extend((json.dumps(reply)+'\n').encode())
        return len(message)

    def read_until(self, expected, size):
        # Force every reply to cross several reads, including stale reply IDs.
        if not self.buffer:
            time.sleep(.001)
            return b''
        length = min(13, size, len(self.buffer))
        newline = self.buffer.find(b'\n', 0, length)
        if newline >= 0:
            length = newline+1
        part = bytes(self.buffer[:length])
        del self.buffer[:length]
        return part

    def close(self):
        self.closed = True


def main():
    with patch('control.bluetooth_link.serial.Serial', SerialPeer):
        link = BluetoothLink('COM_TEST')
        link.connect()
        peer = link.serial
        assert [m.decode().split()[1] for m in peer.writes] == ['/status', '/stop', '/status']
        peer.wrong_id = True
        link.pulse()
        for direction in ('forward', 'left', 'right'):
            link.step(direction)
        movements = [m.decode().split() for m in peer.writes if m.decode().split()[1] in ('/step', '/pulse')]
        assert len(movements) == 4
        assert all(int(m[3]) == (peer.uptime+200) & 0xffffffff for m in movements)
        assert len({m[0] for m in movements}) == 4
        before = len(peer.writes)
        try:
            link.step('backward')
        except ValueError:
            pass
        else:
            raise AssertionError('invalid movement accepted')
        assert len(peer.writes) == before
        peer.result = 'busy'
        try:
            link.step('left')
        except ValueError:
            pass
        else:
            raise AssertionError('busy rejection ignored')
        assert len(peer.writes) == before+2, 'movement retried after rejection'
        peer.result = None
        peer.silent = True
        before = len(peer.writes)
        try:
            link.pulse()
        except TimeoutError:
            pass
        else:
            raise AssertionError('missing status accepted')
        assert len(peer.writes) == before+1
        assert peer.writes[-1].decode().split()[1] == '/status', 'motion sent without fresh status'
        link.close()
        assert peer.closed and link.serial is None
    print('PASS: handshake, stop, fragmented/stale replies, pulse and directions, wraparound expiry, invalid direction, busy/no retry, timeout before motion, close')


if __name__ == '__main__':
    main()
