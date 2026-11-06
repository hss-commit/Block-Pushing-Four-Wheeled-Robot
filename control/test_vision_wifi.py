"""Offline gate checks plus real loopback HTTP; never contacts a car."""

import json
import math
import threading
import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import cv2
import numpy as np

from vision_wifi_test import PROTOCOL, PulseGate, WifiLink, detect_robot
import vision_wifi_test as wifi_test


def missing_camera_checks():
    link=Mock()
    link.stop.return_value={'result':'stop_queued'}
    link.connect.side_effect=lambda: link.stop()
    capture=Mock()
    capture.read.return_value=(False,None)
    with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()), \
         patch.object(wifi_test,'OUTPUT',Path(folder)), \
         patch.object(wifi_test.sys,'argv',['vision_wifi_test.py','--host','http://127.0.0.1']), \
         patch.object(wifi_test,'WifiLink',return_value=link), \
         patch.object(cv2,'VideoCapture',return_value=capture), \
         patch.object(cv2,'namedWindow'), patch.object(cv2,'imshow'), \
         patch.object(cv2,'getWindowProperty',return_value=1), \
         patch.object(cv2,'waitKey',side_effect=[32,0,0,ord('x'),0,27]), \
         patch.object(cv2,'destroyAllWindows'):
        wifi_test.main()
    assert link.stop.call_count==3, f'Missing camera flooded STOP: {link.stop.call_count}'
    link.pulse.assert_not_called()
    capture.release.assert_called_once()
    print('PASS: repeated missing camera does not flood STOP; SPACE cannot move; startup, X and exit still send STOP')


def observation():
    image=np.full((800,800,3),210,np.uint8)
    for x,y in ((260,260),(260,540),(500,240),(500,560)):
        cv2.circle(image,(x,y),27,(0,0,230),-1)
        cv2.circle(image,(x,y),13,(15,15,15),-1)
    result=detect_robot(image)
    assert result['heading_valid']
    return result


def ready_gate(robot):
    gate=PulseGate()
    assert gate.update(robot,0,0,arm=True) is None
    assert gate.update(robot,.3,.3) is None
    assert gate.update(robot,.6,.6) is None
    assert gate.ready
    return gate


def main():
    missing_camera_checks()
    robot=observation()
    missing={'detected':False,'heading_valid':False}
    uncertain={**robot,'heading_valid':False}
    for bad in (missing,uncertain):
        gate=PulseGate()
        for now in (0,.3,.6,1):
            assert gate.update(bad,now,now,arm=True) is None
        assert not gate.ready
    gate=ready_gate(robot)
    assert gate.update(robot,.61,.61,arm=True)=='pulse'
    assert gate.update(robot,.7,.7,arm=True) is None
    assert gate.update(robot,.92,.92)=='stop'
    for now in (1,2,3):
        assert gate.update(robot,now,now,arm=True) is None
    assert gate.consumed and not gate.ready
    for bad in (missing,uncertain,{**robot,'heading_rad':math.pi}):
        gate=ready_gate(robot)
        assert gate.update(robot,.61,.61,arm=True)=='pulse'
        assert gate.update(bad,.7,.7)=='stop'
    gate=ready_gate(robot)
    assert gate.update(robot,.61,.61,arm=True)=='pulse'
    assert gate.update(robot,.5,.75)=='stop', 'stale frame did not stop'
    gate=ready_gate(robot)
    assert gate.update(robot,.61,.61,arm=True)=='pulse'
    assert gate.update(robot,.62,.62,stop=True)=='stop'
    gate=ready_gate(robot)
    assert gate.update(robot,.1,.1,arm=True) is None
    assert not gate.ready, 'backwards clock left controller ready'
    print('PASS: stable vision, manual trigger, one pulse, lost/uncertain/stale/changed robot, manual stop, clock reversal')

    received=[]
    fail_pulse=False
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def handle_request(self):
            received.append((self.command,self.path,self.rfile.read(int(self.headers.get('Content-Length',0)))))
            result={'/status':'ready','/stop':'stop_queued','/pulse':'pulse_queued'}[self.path]
            self.send_response(500 if fail_pulse and self.path=='/pulse' else 200)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'protocol':PROTOCOL,'pulse_ms':250,'result':result,'busy':False}).encode())

        do_GET=handle_request
        do_POST=handle_request

    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    try:
        link=WifiLink(' \t http:// 127.0.0.1:'+str(server.server_port)+'  \t ')
        link.connect()
        gate=ready_gate(robot)
        action=gate.update(robot,.61,.61,arm=True)
        assert action=='pulse'
        link.pulse()
        action=gate.update(missing,.7,.7)
        assert action=='stop'
        link.stop()
        assert [(method,path) for method,path,_ in received]==[
            ('GET','/status'),('POST','/stop'),('POST','/pulse'),('POST','/stop')]
        token=parse_qs(received[2][2].decode())['id'][0]
        assert len(token)==32 and all(c in '0123456789abcdef' for c in token)
        fail_pulse=True
        try:
            link.pulse()
        except OSError:
            link.stop()
        else:
            raise AssertionError('Rejected movement request was ignored')
        assert len([entry for entry in received if entry[1]=='/pulse'])==2, 'movement retried'
        assert received[-1][1]=='/stop'
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
    print('PASS: actual OpenCV detection -> gate -> real local HTTP handshake/pulse/stop, unique token, failed request with no movement retry')


if __name__=='__main__':
    main()
