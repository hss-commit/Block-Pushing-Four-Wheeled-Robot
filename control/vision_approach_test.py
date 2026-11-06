"""Calibrated approach test, with an opt-in automatic single-block straight push."""
import argparse
import json
import math
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from control.approach_control import ApproachControl, StationaryBlocks
from control.vision_wifi_test import WifiLink, OUTPUT
from strategy.planner import Block, Config
from control.single_push_control import SinglePushControl
from vision.photo_vision import (select_corners, rectify, detect_midline, segment,
                                 classify_regions, annotated, sample_colour, write_png)
from vision.robot_vision import detect_robot, draw_robot, exclude_robot_regions


class DirectionLink(WifiLink):
    def connect(self):
        super().connect()
        if self.request('/status').get('step_ms') != 120:
            raise ValueError('固件还不支持转向。请重新烧录更新后的视觉无线联动测试工程。')

    def step(self,direction):
        if direction not in ('forward','left','right'):
            raise ValueError('Invalid direction')
        result=self.request('/step',{'id':uuid.uuid4().hex,'direction':direction})
        if result.get('result') != 'step_queued':
            raise ValueError('ESP32未接受方向指令: '+str(result))
        return result


def calibration(index):
    capture=None
    name='Camera | N/P switch | Enter calibrate | Esc quit'
    calibration_error=None
    try:
        while True:
            if capture is None:
                capture=cv2.VideoCapture(index)
                capture.set(cv2.CAP_PROP_BUFFERSIZE,1)
            ok,frame=capture.read()
            if ok and frame is not None:
                factor=min(1000/frame.shape[1],700/frame.shape[0],1)
                preview=cv2.resize(frame,None,fx=factor,fy=factor)
            else:
                preview=np.zeros((400,800,3),np.uint8)
            cv2.putText(preview,f'Camera {index} | N/P | Enter: corners | Esc: exit',(10,25),
                        cv2.FONT_HERSHEY_SIMPLEX,.55,(0,230,255),1)
            if calibration_error:
                cv2.rectangle(preview,(0,35),(preview.shape[1],105),(25,25,25),-1)
                cv2.putText(preview,'CALIBRATION FAILED: '+calibration_error,(10,55),
                            cv2.FONT_HERSHEY_SIMPLEX,.42,(0,100,255),1)
                cv2.putText(preview,'Show all FOUR real field corners. Enter: select again.',(10,80),
                            cv2.FONT_HERSHEY_SIMPLEX,.45,(0,230,255),1)
            cv2.imshow(name,preview)
            key=cv2.waitKey(20)&255
            if key==27 or cv2.getWindowProperty(name,cv2.WND_PROP_VISIBLE)<1:
                return None
            if key in (ord('n'),ord('p')):
                index=max(0,index+(1 if key==ord('n') else -1))
                capture.release();capture=None
            if key in (10,13) and ok:
                cv2.destroyAllWindows()
                selected=select_corners(frame)
                if selected is None:
                    return None
                image,corners=selected
                field=detect_midline(image)
                if not field.get('valid'):
                    calibration_error=field.get('reason','Blue/yellow field not recognised')
                    print('场地标定未通过：',calibration_error,'。请完整拍到场地四个真实内角，按Enter重新选择。')
                    continue
                nx,ny=field['yellow_normal']
                # Canonical world: yellow bottom, +x right, +y up (no reflection).
                turns=int(np.argmax([ny,-nx,-ny,nx]))
                result=(capture,corners,turns,frame.shape[:2])
                capture=None
                return result
    finally:
        if capture is not None:
            capture.release()
        cv2.destroyAllWindows()


def show_stopped_error(name, error):
    panel=np.zeros((300,900,3),np.uint8)
    lines=('STOPPED - '+type(error).__name__,
           str(error).encode('ascii',errors='replace').decode('ascii')[:100],
           'Motion is locked. Fix the problem, then restart the test.',
           'Esc / close window: exit. No automatic restart.')
    for row,text in enumerate(lines):
        cv2.putText(panel,text,(15,45+55*row),cv2.FONT_HERSHEY_SIMPLEX,.55,
                    (0,100,255) if row<2 else (0,230,255),1,cv2.LINE_AA)
    cv2.namedWindow(name,cv2.WINDOW_AUTOSIZE)
    while True:
        cv2.imshow(name,panel)
        if cv2.waitKey(100)&255==27 or cv2.getWindowProperty(name,cv2.WND_PROP_VISIBLE)<1:
            return


def main():
    parser=argparse.ArgumentParser(description='视觉接近测试；加 --single-push 可进行识别稳定后自动开始的单块直线推送。')
    parser.add_argument('--camera',type=int,default=0)
    parser.add_argument('--host',default='http://192.168.4.1')
    parser.add_argument('--bluetooth-port',help='已配对蓝牙设备的传出串口，例如 COM7')
    parser.add_argument('--dry-run',action='store_true',help='显示方向和路线，不发送网络指令')
    parser.add_argument('--invert-turns',action='store_true',help='仅当实测左右转反向时交换发送的转向命令')
    parser.add_argument('--single-push',action='store_true',help='单块直线推送：识别稳定倒计时3秒后自动开始，按视觉位移停车')
    parser.add_argument('--push-distance',type=float,default=100,help='单块模式目标位移，20～150mm，默认100mm')
    args=parser.parse_args()
    if args.camera<0:
        parser.error('摄像头编号须非负')
    config=Config.load(Path(__file__).resolve().parent.parent/'strategy'/'config.json')
    controller=SinglePushControl(config,args.push_distance) if args.single_push else ApproachControl(config)
    tracker=StationaryBlocks()
    if args.bluetooth_port:
        from control.bluetooth_link import BluetoothLink
    link=None if args.dry_run else (BluetoothLink(args.bluetooth_port) if args.bluetooth_port else DirectionLink(args.host))
    capture=None
    folder=OUTPUT/(('single-push-' if args.single_push else 'approach-')+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir(parents=True)
    name=('AUTO ONE BLOCK | 3s countdown | X stop | R rearm | S save | Esc exit' if args.single_push else
          'Approach | click block colour | SPACE start | X stop | R rearm | S save | Esc exit')
    sample=None
    pending=None
    image=None
    last_receipt=last_send=-math.inf
    last_command='stop'

    def record(event,**data):
        with (folder/'events.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'event':event,'time':datetime.now().isoformat(),
                'dry_run':args.dry_run,**data},ensure_ascii=False)+'\n')

    def send(command):
        nonlocal last_receipt,last_send,last_command
        wire={'left':'right','right':'left'}.get(command,command) if args.invert_turns else command
        if link:
            response=link.stop() if wire=='stop' else link.step(wire)
        else:
            response={'dry_run':True}
        last_receipt=last_send=time.monotonic()
        last_command=command
        record('command',command=command,wire_command=wire,response=response,plan=controller.last_plan)

    def mouse(event,x,y,flags,param):
        nonlocal pending
        if event==cv2.EVENT_LBUTTONDOWN:
            pending=(min(1199,max(0,int(x*1200/700))),min(1199,max(0,int(y*1200/700))))

    try:
        if link:
            link.connect()
        last_receipt=time.monotonic()
        print('电脑使用蓝牙串口 '+args.bluetooth_port if args.bluetooth_port else '连接小车地址：'+args.host)
        print('手机保持 USB DroidCam。先架空核对轮子映射，再低速落地测试。')
        if args.single_push:
            print('Enter四角标定，再点击唯一方块取色。车头须对准方块，场景稳定3秒后自动前进，不需空格。')
            print(f'方块视觉位移达到{args.push_distance:g}mm后停止，只执行一次。X停止，R重新倒计时，S保存，Esc退出。')
        else:
            print('Enter 四角标定，点击方块取色。空格启动一次自动接近，X停止，R重新准备，S保存。')
        print('结果：',folder)
        selected=calibration(args.camera)
        if selected is None:
            return
        capture,corners,turns,frame_size=selected
        cv2.namedWindow(name,cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(name,mouse)
        last_reason=None
        while True:
            acquired=time.monotonic()
            ok,frame=capture.read()
            if not ok or frame is None or frame.shape[:2]!=frame_size:
                controller.stop('CAMERA LOST / SIZE CHANGED')
                send('stop')
                raise ValueError('摄像头断开或分辨率改变，请重新启动并标定。')
            image=np.rot90(rectify(frame,corners),turns).copy()
            if pending is not None:
                send('stop')
                sample=sample_colour(image,*pending)
                pending=None
                controller.rearm();tracker=StationaryBlocks()
                print('方块取色 HSV:',sample)
            robot=detect_robot(image)
            field=detect_midline(image)
            regions=[]
            mask=np.zeros(image.shape[:2],np.uint8)
            blocks=()
            track_error=None
            if sample is not None:
                mask,regions=segment(image,sample,h_tol=18,min_area=90,field=field)
                regions=exclude_robot_regions(regions,robot)
                classify_regions(regions,field)
                if args.single_push:
                    for region in regions:
                        region.pop('direction_arrow_px',None)
                try:
                    if args.single_push:
                        if any(max(r['bbox_px'][2:])>40 for r in regions):
                            raise ValueError('MERGED / OVERSIZE BLOCK')
                        blocks=tuple(Block(f'single-{i}',r['x_mm'],r['y_mm']) for i,r in enumerate(regions))
                    else:
                        blocks=tracker.update(regions)
                except ValueError as error:
                    track_error=str(error)
            if link and time.monotonic()-last_receipt>.15:
                link.request('/status')
                last_receipt=time.monotonic()
            now=time.monotonic()
            if args.dry_run:
                last_receipt=now
            if track_error:
                plan=controller.stop(track_error)
            elif sample is None:
                plan=controller._waiting('CLICK A BLOCK TO SAMPLE COLOUR')
            else:
                plan=controller.update(robot,blocks,field,acquired,now,last_receipt)
            # No motion while preparing. A stop/direction change interrupts the old step.
            command=plan['command'] if controller.active else 'stop'
            if command=='stop':
                if last_command!='stop':
                    send('stop')
            elif now-last_send>=.22:
                send(command)
            elif command!=last_command:
                send('stop')
            result=annotated(image,regions,field,calibrated=True)
            draw_robot(result,robot,calibrated=True)
            if plan.get('goal_mm') and robot.get('detected'):
                goal=np.array([plan['goal_mm'][0],1200-plan['goal_mm'][1]])*1199/1200
                cv2.arrowedLine(result,tuple(np.rint(robot['center_px']).astype(int)),
                                tuple(np.rint(goal).astype(int)),(255,255,0),3,tipLength=.1)
                cv2.circle(result,tuple(np.rint(goal).astype(int)),15,(255,0,255),3)
            mode='DRY RUN' if args.dry_run else 'LIVE BLUETOOTH' if args.bluetooth_port else 'LIVE WIFI'
            state=controller.state if args.single_push else 'RUNNING' if controller.active else 'READY' if plan.get('can_start') else 'STOPPED'
            cv2.rectangle(result,(0,0),(1200,100),(25,25,25),-1)
            detail=plan['reason']
            if args.single_push and controller.active:
                detail+=f' | BLOCK: {plan.get("block_progress_mm",0):.0f}/{args.push_distance:g} mm'
            for row,text in enumerate((f'{mode} | {state} | NEXT: {plan["command"].upper()}',
                                       detail,('AUTO START | X stop | R rearm | S save | Esc' if args.single_push else
                                                       'SPACE start | X stop | R rearm | S save | Esc exit'))):
                cv2.putText(result,text,(12,25+30*row),cv2.FONT_HERSHEY_SIMPLEX,.65,(0,230,255),1,cv2.LINE_AA)
            if last_reason!=plan['reason']:
                record('plan',plan=plan)
                last_reason=plan['reason']
            cv2.imshow(name,cv2.resize(result,(700,700)))
            key=cv2.waitKey(15)&255
            if key==27:
                record('exit',reason='escape_key')
                break
            if cv2.getWindowProperty(name,cv2.WND_PROP_VISIBLE)<1:
                record('exit',reason='window_closed')
                break
            if key in (ord('x'),ord('X')):
                controller.stop('MANUAL STOP');send('stop')
            if key in (ord('r'),ord('R')):
                send('stop');controller.rearm();tracker=StationaryBlocks()
            if key==32:
                if not args.single_push:
                    controller.start()
            if key in (ord('s'),ord('S')):
                stamp=datetime.now().strftime('%H%M%S-%f')
                write_png(folder/(stamp+'-source.png'),frame)
                write_png(folder/(stamp+'-result.png'),result)
                record('snapshot',robot=robot,regions=regions,plan=plan,corners=corners,rotation_ccw=turns)
    except (OSError,ValueError,cv2.error) as error:
        controller.stop('ERROR / MOTION LOCKED: '+str(error))
        record('error',error_type=type(error).__name__,error=str(error))
        try:
            send('stop')
        except (OSError,ValueError) as stop_error:
            record('stop_unconfirmed',error=str(stop_error))
        print('测试已暂停，画面会保留；请先排除问题后再重新启动：',error)
        print('错误已记录：',folder/'events.jsonl')
        show_stopped_error(name,error)
        return False
    finally:
        if link:
            try:
                send('stop')
            except (OSError,ValueError) as error:
                print('停止请求未确认；车端短动作限时仍有效，请核对实车：',error)
            finally:
                if args.bluetooth_port:
                    link.close()
        if capture is not None:
            capture.release()
        cv2.destroyAllWindows()


if __name__=='__main__':
    try:
        if main() is False:
            raise SystemExit(1)
    except (OSError,ValueError,cv2.error,KeyboardInterrupt) as error:
        print('接近测试停止：',error)
        raise SystemExit(1)
