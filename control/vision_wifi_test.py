"""One-shot camera -> Wi-Fi -> ESP32 pulse test. SPACE is required for every run."""

import argparse
import json
import math
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vision.robot_vision import detect_robot, draw_robot

PROTOCOL = "vision-pulse-v1"
OUTPUT = Path(__file__).resolve().parent.parent / "vision" / "results"


class WifiLink:
    def __init__(self, host):
        host = host.strip()
        if host.startswith('http://'):
            host = 'http://' + host[7:].strip()
        if any(c.isspace() for c in host):
            raise ValueError('IP地址中间不能有空格，请重新输入完整地址')
        parsed = urlsplit(host)
        if parsed.scheme != "http" or not parsed.hostname or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("--host 必须是 http://地址，例如 http://192.168.4.1")
        self.host = host.rstrip("/")
        # A local car must never be reached through the PC's web proxy.
        self.opener = build_opener(ProxyHandler({}))

    def request(self, path, data=None):
        payload = None if data is None else urlencode(data).encode("ascii")
        request = Request(self.host+path, data=payload,
                          headers={"Content-Type":"application/x-www-form-urlencoded"})
        with self.opener.open(request, timeout=.18) as response:
            result = json.loads(response.read(4096).decode("utf-8"))
        if not isinstance(result,dict) or result.get("protocol") != PROTOCOL:
            raise ValueError("ESP32 程序不匹配，请烧录视觉无线联动测试工程")
        return result

    def connect(self):
        result = self.request("/status")
        if result.get("pulse_ms") != 250 or result.get("result") != "ready":
            raise ValueError("ESP32 测试协议或动作时长不匹配")
        self.stop()

    def pulse(self):
        result = self.request("/pulse", {"id":uuid.uuid4().hex})
        if result.get("result") != "pulse_queued":
            raise ValueError("ESP32 未接受短动作: " + str(result))
        return result

    def stop(self):
        result = self.request("/stop", {})
        if result.get("result") != "stop_queued":
            raise ValueError("ESP32 未确认停止请求")
        return result


class PulseGate:
    """A new stable observation and a new SPACE press are needed for each pulse."""
    def __init__(self):
        self.since = None
        self.reference = None
        self.running_until = None
        self.ready = False
        self.message = "WAIT FOR STABLE ROBOT"
        self.last_now = None
        self.consumed = False

    def reset(self, message):
        self.since = self.reference = self.running_until = None
        self.ready = False
        self.message = message

    @staticmethod
    def pose(robot):
        if not robot.get("detected") or not robot.get("heading_valid"):
            return None
        try:
            center = np.asarray(robot["center_px"], dtype=float)
            heading = float(robot["heading_rad"])
            base = float(np.linalg.norm(np.asarray(robot["front_px"])-robot["rear_px"]))
            if center.shape != (2,) or not np.isfinite(center).all() or not math.isfinite(heading) or not math.isfinite(base) or base <= 0:
                return None
            return center, heading, base
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def difference(a, b):
        return abs((a-b+math.pi)%(2*math.pi)-math.pi)

    def update(self, robot, captured_at, now, arm=False, stop=False):
        running = self.running_until is not None
        clock_ok = (math.isfinite(now) and math.isfinite(captured_at) and
                    (self.last_now is None or now >= self.last_now) and 0 <= now-captured_at <= .2)
        self.last_now = now
        pose = self.pose(robot) if clock_ok else None
        if stop or pose is None:
            self.reset("STOP / NEED FRESH ROBOT" if not stop else "MANUAL STOP")
            return "stop" if running or stop else None
        if running:
            center, heading, base = pose
            previous_center, previous_heading, previous_base = self.reference
            if (self.difference(heading, previous_heading) > math.radians(25) or
                    np.linalg.norm(center-previous_center) > previous_base*.6 or
                    not .65 < base/previous_base < 1.5):
                self.reset("STOP / ROBOT CHANGED")
                return "stop"
            if now >= self.running_until:
                self.reset("PULSE FINISHED / WAIT TO REARM")
                return "stop"
            return None
        if self.consumed:
            self.ready = False
            self.message = "DONE / R: PREPARE NEXT TEST"
            return None
        if (self.reference is None or
                np.linalg.norm(pose[0]-self.reference[0]) > pose[2]*.08 or
                self.difference(pose[1], self.reference[1]) > math.radians(12)):
            self.reference, self.since = pose, now
        self.ready = now-self.since >= .5
        self.message = "READY / SPACE: ONE SHORT PULSE" if self.ready else "WAIT FOR STABLE ROBOT (0.5s)"
        if arm and self.ready:
            self.consumed = True
            self.running_until = now+.3
            self.message = "PULSE REQUEST / X: STOP"
            return "pulse"
        return None


def main():
    parser = argparse.ArgumentParser(description="电脑视觉识别后，经 ESP32 热点触发一次 250ms 低速直行。空格触发，X 停止。")
    parser.add_argument("--camera",type=int,default=0)
    parser.add_argument("--host",default="http://192.168.4.1")
    parser.add_argument("--bluetooth-port",help="改用已配对蓝牙设备的传出串口，例如 COM7")
    parser.add_argument("--dry-run",action="store_true",help="仅检查识别与触发逻辑，不连接或控制小车")
    args = parser.parse_args()
    if args.camera < 0:
        parser.error("摄像头编号不能为负数")
    if args.bluetooth_port:
        from control.bluetooth_link import BluetoothLink
    link = None if args.dry_run else (BluetoothLink(args.bluetooth_port) if args.bluetooth_port else WifiLink(args.host))
    capture = None
    gate = PulseGate()
    folder = OUTPUT / (("bt-pulse-" if args.bluetooth_port else "wifi-pulse-") + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    folder.mkdir(parents=True)
    mode = "DRY RUN / NO NETWORK" if args.dry_run else ("LIVE BLUETOOTH" if args.bluetooth_port else "LIVE WIFI") + " / SPACE MOVES CAR"
    name = "Vision WiFi test | SPACE pulse | R rearm | X stop | N/P camera | S save | Esc quit"

    def record(event, **data):
        entry = {"event":event,"time":datetime.now().isoformat(timespec="milliseconds"),
                 "monotonic_s":time.monotonic(),"dry_run":args.dry_run,**data}
        with (folder/"events.jsonl").open("a",encoding="utf-8") as stream:
            stream.write(json.dumps(entry,ensure_ascii=False)+"\n")
        print(event, data)

    def send(action):
        response = None
        if link:
            try:
                response = link.pulse() if action == "pulse" else link.stop()
            except (OSError,ValueError) as error:
                record("communication_error",action=action,error=str(error))
                raise
        record(action,response=response)

    try:
        if link:
            print("连接 ESP32：",args.bluetooth_port or args.host)
            link.connect()
        record("start",mode=mode)
        print("先架空车轮。画面识别稳定后，空格触发一次低速250毫秒动作；R准备下一次，X停止，S保存，N/P切换摄像头。")
        print("ESP32 回应只表示已接收请求，不证明电机实际移动。结果目录：",folder)
        cv2.namedWindow(name,cv2.WINDOW_AUTOSIZE)
        while True:
            if capture is None:
                print(f"使用摄像头 {args.camera}；请关闭其他占用摄像头的预览窗口，N/P可切换。")
                capture = cv2.VideoCapture(args.camera)
                capture.set(cv2.CAP_PROP_BUFFERSIZE,1)
                gate.reset("CAMERA CHANGED / WAIT FOR STABLE ROBOT")
            captured_at = time.monotonic()
            ok,frame = capture.read()
            if not ok or frame is None:
                robot = {"detected":False,"heading_valid":False,"reason":"NO CAMERA"}
                action = gate.update(robot,captured_at,time.monotonic())
                if action:
                    send(action)
                gate.message = f"NO CAMERA {args.camera} / CLOSE OTHER PREVIEW / N/P"
                preview = np.zeros((400,850,3),np.uint8)
            else:
                factor = min(960/frame.shape[1],720/frame.shape[0],1)
                preview = cv2.resize(frame,None,fx=factor,fy=factor)
                robot = detect_robot(preview)
                action = gate.update(robot,captured_at,time.monotonic())
                if action:
                    send(action)
                draw_robot(preview,robot)
            cv2.rectangle(preview,(0,0),(preview.shape[1],88),(25,25,25),-1)
            for row,text in enumerate((mode,gate.message,"SPACE: pulse | R: rearm | X: stop | N/P | S: save | Esc")):
                cv2.putText(preview,text,(10,23+26*row),cv2.FONT_HERSHEY_SIMPLEX,
                            min(.6,preview.shape[1]/1000),(0,220,255),1,cv2.LINE_AA)
            cv2.imshow(name,preview)
            key = cv2.waitKey(15)&0xff
            if key == 27 or cv2.getWindowProperty(name,cv2.WND_PROP_VISIBLE)<1:
                break
            if key in (ord("x"),ord("X")):
                gate.consumed = True
                gate.reset("MANUAL STOP")
                send("stop")
            if key in (ord("r"),ord("R")):
                send("stop")
                gate.reset("WAIT FOR STABLE ROBOT")
                gate.consumed = False
                record("rearm")
            if key == 32:
                action = gate.update(robot,captured_at,time.monotonic(),arm=True)
                if action:
                    # A pulse request is sent once; there are no movement retries.
                    record("visual_trigger",robot=robot)
                    send(action)
            if key in (ord("n"),ord("N"),ord("p"),ord("P")):
                send("stop")
                gate.reset("CAMERA CHANGED")
                args.camera = max(0,args.camera+(1 if key in (ord("n"),ord("N")) else -1))
                capture.release()
                capture = None
            if key in (ord("s"),ord("S")) and ok:
                stamp = datetime.now().strftime("%H%M%S-%f")
                for label,img in (("source",frame),("preview",preview)):
                    success,encoded = cv2.imencode(".png",img)
                    if not success:
                        raise ValueError("保存现场图失败")
                    encoded.tofile(folder/(stamp+"-"+label+".png"))
                record("snapshot",robot=robot,coordinate_unit="preview pixels",camera=args.camera)
    finally:
        if link:
            try:
                send("stop")
            except (OSError,ValueError) as error:
                print("停止请求未确认，车端独立250ms限时仍生效；请核对实车：",error)
            finally:
                if args.bluetooth_port:
                    link.close()
        if capture is not None:
            capture.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except (OSError,ValueError,cv2.error,KeyboardInterrupt) as error:
        print("测试已结束：",error)
        raise SystemExit(1)
