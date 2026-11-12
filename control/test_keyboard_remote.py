"""Hold/release/focus, nonblocking input, stale UI and real loopback HTTP."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from control import keyboard_remote as remote


def until(predicate, timeout=2):
    deadline = time.monotonic()+timeout
    while not predicate():
        assert time.monotonic()<deadline, 'Timed out waiting for worker'
        time.sleep(.01)


def main():
    keys = remote.HeldKeys()
    assert keys.update({'forward'}, True) == 'stop'
    assert keys.update(set(), True) == 'stop'
    for _ in range(100):
        assert keys.update({'forward'}, True) == 'forward'
    assert keys.update(set(), True) == 'stop'  # Release, no OS repeat involved.
    assert keys.update({'left'}, True) == 'left'
    assert keys.update({'left'}, False) == 'stop'
    assert keys.update({'left'}, True) == 'stop'  # Refocus cannot restart held keys.
    keys.update(set(), True)
    assert keys.update({'right'}, True) == 'right'
    assert keys.update({'right', 'stop'}, True) == 'stop'
    assert keys.update({'right'}, True) == 'stop'
    keys.update(set(), True)
    assert keys.update({'forward', 'backward'}, True) == 'stop'

    requests = []
    supported = True
    rejected = False
    delay = 0.
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_request(self):
            from urllib.parse import parse_qs
            data = parse_qs(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode())
            requests.append((self.path, data, time.monotonic()))
            time.sleep(delay)
            result = {'/status':'ready', '/stop':'stop_queued', '/manual':'manual_queued'}[self.path]
            self.send_response(500 if rejected and self.path == '/manual' else 200)
            self.end_headers()
            try:
                self.wfile.write(json.dumps(dict(protocol='vision-pulse-v1', pulse_ms=250,
                    step_ms=120, manual_hold_ms=700, manual_ramp_v=1 if supported else 0, result=result)).encode())
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
        do_GET = handle_request
        do_POST = handle_request

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    link = remote.RemoteLink(f'http://127.0.0.1:{server.server_port}')
    worker = None
    try:
        link.connect()
        for direction in ('forward', 'backward', 'left', 'right'):
            link.hold(direction)
        commands = [data for path,data,_ in requests if path == '/manual']
        assert [c['direction'][0] for c in commands] == ['forward','backward','left','right']
        assert len({c['id'][0] for c in commands}) == 4
        supported = False
        try:
            link.connect()
        except ValueError:
            pass
        else:
            raise AssertionError('Old firmware accepted')
        supported = True
        delay = .25
        assert link.request('/status')['result'] == 'ready'
        assert remote.WifiLink.request_timeout == .18

        delay = .12
        requests.clear()
        worker = remote.RemoteWorker(link)
        until(lambda: worker.ready)
        # UI remains responsive while HTTP runs; renew for longer than one lease.
        end = time.monotonic()+1.2
        while time.monotonic()<end:
            start = time.monotonic()
            worker.submit('forward')
            assert time.monotonic()-start<.05
            time.sleep(.02)
        renewals = [t for path,_,t in requests if path == '/manual']
        assert len(renewals)>=4
        assert max(b-a for a,b in zip(renewals, renewals[1:]))<.7
        worker.submit('stop')
        until(lambda: requests[-1][0] == '/stop')
        count = sum(path == '/manual' for path,_,_ in requests)
        time.sleep(.25)
        assert sum(path == '/manual' for path,_,_ in requests) == count
        worker.submit('backward')
        until(lambda: requests[-1][0] == '/manual')
        # Stop updating UI: the worker must cease renewal without any key-up.
        until(lambda: requests[-1][0] == '/stop')
        worker.close()
        assert not worker.thread.is_alive()
        worker = None
        rejected = True
        delay = 0
        requests.clear()
        worker = remote.RemoteWorker(link)
        until(lambda: worker.ready)
        worker.submit('left')
        until(lambda: worker.error is not None)
        worker.close()
        assert sum(path == '/manual' for path,_,_ in requests) == 1
        assert requests[-1][0] == '/stop'
    finally:
        if worker:
            worker.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    print('PASS: hold/release, focus/stop latch, four HTTP directions, renewable hold, stale UI stop, old firmware rejection, failed action locks without retry')


if __name__ == '__main__':
    main()
