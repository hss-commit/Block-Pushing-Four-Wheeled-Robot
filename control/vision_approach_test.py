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
from control.multi_push_control import MultiPushControl, MovingBlocks
from control.straight_push_control import StraightPush, FrameBlocks
from vision.photo_vision import (select_corners, rectify, detect_midline, segment,
                                 classify_regions, annotated, sample_colour, write_png, ClickedBlock)
from vision.latest_camera import LatestCamera
from vision.robot_vision import detect_robot, draw_robot, exclude_robot_regions, retain_contact_target

DRIVE_LEASE_MS = 350
DRIVE_RENEW_S = .12
LIVE_EDGE_MARGIN_MM = 60


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


class GentleLink(DirectionLink):
    # The reply may arrive after the independent 80ms motor step has ended.
    # This only extends acknowledgement waiting, never the motor action itself.
    request_timeout = .6

    def connect(self):
        super().connect()
        status=self.request('/status')
        self.reverse_step=status.get('reverse_step') is True
        self.gentle_straight_speed=status.get('gentle_straight_speed')
        self.drive_hold_ms=status.get('drive_hold_ms',0)
        self.medium_turn_ms=status.get('medium_turn_ms',0)
        self.fine_turn_ms=status.get('fine_turn_ms',0)
        if self.medium_turn_ms!=60 or self.fine_turn_ms!=35:
            print('ESP32: legacy turns; test 8 uses visual breakaway correction with existing 120ms steps.')
        if status.get('gentle_step_ms') != 80:
            raise ValueError('多块测试需要新版80ms低速动作，请重新上传手机热点联动固件。')

    def step(self, direction, *, gentle=True, turn_profile=None):
        if direction not in ('forward','backward','left','right'):
            raise ValueError('Invalid direction')
        payload={'id':uuid.uuid4().hex,'direction':direction}
        if gentle:
            payload['gentle']='1'
        if turn_profile is not None:
            if direction not in ('left','right') or turn_profile not in ('medium','fine'):
                raise ValueError('Invalid turn profile')
            payload['turn_profile']=turn_profile
        result=self.request('/step',payload)
        if result.get('result')!='step_queued':
            raise ValueError('ESP32未接受低速动作：'+str(result))
        return result

    def drive(self, left, right, hold_ms):
        result=self.request('/drive',{'id':uuid.uuid4().hex,'left':left,'right':right,
                                      'hold_ms':hold_ms})
        if result.get('result')!='drive_queued':
            raise ValueError('ESP32 rejected continuous drive: '+str(result))
        return result


class TurnFeedback:
    """Check commanded turn signs against fresh marker headings."""

    def __init__(self, inverted=False):
        self.inverted=inverted
        self.reference=None
        self.opposite_count=0
        self.stalled_count=0
        self.last_direction=None

    def reset(self):
        self.reference=None
        self.opposite_count=0
        self.stalled_count=0
        self.last_direction=None

    def use_normal_step(self, direction, plan, *, profiles):
        """Use available breakaway torque, bounded by the checked turn sweep."""
        if direction!=self.last_direction:
            self.stalled_count=0
        if not plan.get('normal_turn_clear',False):
            return False
        error=abs(plan.get('heading_error_deg',0))
        # Old 0.025 steps often cannot start a loaded skid-steer chassis.
        # Near the goal try gentle correction first; boost after two measured
        # failures, including errors below the old 15-degree boost cutoff.
        return (not profiles and error>=25) or self.stalled_count>=2

    def sent(self, direction, heading, observe_after):
        if direction!=self.last_direction:
            self.stalled_count=0
        self.last_direction=direction
        self.reference=(direction,heading,observe_after)

    def observe(self, heading, captured_at):
        if self.reference is None:
            return False
        direction,before,after=self.reference
        if captured_at<after:
            return False
        self.reference=None
        if captured_at-after>.6:
            self.stalled_count=0
            return False
        change=(heading-before+math.pi)%(2*math.pi)-math.pi
        self.stalled_count=self.stalled_count+1 if abs(change)<math.radians(1) else 0
        if not math.radians(2)<=abs(change)<=math.radians(20):
            return False
        opposite=change*(1 if direction=='left' else -1)<0
        self.opposite_count=self.opposite_count+1 if opposite else 0
        if self.opposite_count<2:
            return False
        self.inverted=not self.inverted
        self.opposite_count=0
        self.stalled_count=0
        return True


def calibration(index):
    capture=None
    name='Camera | N/P switch | Enter calibrate | Esc quit'
    calibration_error=None
    try:
        while True:
            if capture is None:
                capture=LatestCamera(index)
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


def show_stopped_error(name, error, allow_reconnect=False, image=None, *, allow_start=True):
    panel=cv2.resize(image,(900,900)).copy() if image is not None else np.zeros((300,900,3),np.uint8)
    cv2.rectangle(panel,(0,0),(900,280),(25,25,25),-1)
    lines=('STOPPED - '+type(error).__name__,
           str(error).encode('ascii',errors='replace').decode('ascii')[:100],
           (('R: reconnect only | SPACE: reconnect and request start' if allow_start else
             'R: reconnect | After reconnect, press SPACE to start') if allow_reconnect else
            'Motion is locked. Fix the problem, then restart the test.'),
           ('Start requires valid fresh vision. X cancels. Esc exits.' if allow_reconnect else
            'Esc / close window: exit. No automatic restart.'))
    for row,text in enumerate(lines):
        cv2.putText(panel,text,(15,45+55*row),cv2.FONT_HERSHEY_SIMPLEX,.55,
                    (0,100,255) if row<2 else (0,230,255),1,cv2.LINE_AA)
    cv2.namedWindow(name,cv2.WINDOW_AUTOSIZE)
    while True:
        cv2.imshow(name,panel)
        key=cv2.waitKey(100)&255
        if allow_reconnect and key in (ord('r'),ord('R')):
            return True
        if allow_reconnect and allow_start and key==32:
            return 'start'
        if key==27 or cv2.getWindowProperty(name,cv2.WND_PROP_VISIBLE)<1:
            return


def main():
    parser=argparse.ArgumentParser(description='视觉接近测试；加 --single-push 可进行识别稳定后自动开始的单块直线推送。')
    parser.add_argument('--camera',type=int,default=0)
    parser.add_argument('--host',default='http://192.168.4.1')
    parser.add_argument('--bluetooth-port',help='已配对蓝牙设备的传出串口，例如 COM7')
    parser.add_argument('--dry-run',action='store_true',help='显示方向和路线，不发送网络指令')
    parser.add_argument('--invert-turns',action='store_true',help='仅当实测左右转反向时交换发送的转向命令')
    parser.add_argument('--single-push',action='store_true',help='单块直线推送：识别稳定倒计时3秒后自动开始，按视觉位移停车')
    parser.add_argument('--multi-push',action='store_true',help='逐个将方块送入黄色区，退开核验后再选下一个；空格启动')
    parser.add_argument('--straight-push',action='store_true',help='Manually aligned push into yellow and return; Space starts')
    parser.add_argument('--midfield',action='store_true',help='Drive each push to the middle of the yellow half before reversing')
    parser.add_argument('--one-delivery',action='store_true',help='Stop after one verified delivery in automatic push mode')
    parser.add_argument('--push-distance',type=float,default=100,help='单块模式目标位移，20～150mm，默认100mm')
    args=parser.parse_args()
    stepped_push=args.multi_push or args.straight_push
    if (args.one_delivery or args.midfield) and not args.multi_push:
        parser.error('--one-delivery and --midfield require --multi-push')
    if (args.multi_push and args.straight_push) or (stepped_push and (args.single_push or args.bluetooth_port)):
        parser.error('Push modes are mutually exclusive; stepped push requires Wi-Fi')
    if args.camera<0:
        parser.error('摄像头编号须非负')
    config=Config.load(Path(__file__).resolve().parent.parent/'strategy'/'config.json')
    if args.straight_push:
        controller=StraightPush(config)
        tracker_type=FrameBlocks
    elif stepped_push:
        controller=MultiPushControl(config,one_delivery=args.one_delivery,field_guided=True,midfield=args.midfield)
        tracker_type=MovingBlocks
    else:
        controller=SinglePushControl(config,args.push_distance) if args.single_push else ApproachControl(config)
        tracker_type=StationaryBlocks
    tracker=tracker_type()
    if args.bluetooth_port:
        from control.bluetooth_link import BluetoothLink
    link=None if args.dry_run else (BluetoothLink(args.bluetooth_port) if args.bluetooth_port else GentleLink(args.host) if stepped_push else DirectionLink(args.host))
    capture=None
    folder=OUTPUT/(('straight-push-' if args.straight_push else 'auto-one-delivery-' if args.one_delivery else 'multi-push-' if stepped_push else 'single-push-' if args.single_push else 'approach-')+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir(parents=True)
    name=('PUSH AND RETURN | SPACE start | X stop | R rearm | Esc exit' if args.straight_push else ('AUTO ONE DELIVERY' if args.one_delivery else 'MULTI BLOCK')+' | SPACE start | X stop | R rearm | S save | Esc exit' if stepped_push else 'AUTO ONE BLOCK | 3s countdown | X stop | R rearm | S save | Esc exit' if args.single_push else
          'Approach | click block colour | SPACE start | X stop | R rearm | S save | Esc exit')
    sample=None
    pending=None
    clicked_block=None
    image=None
    last_receipt=last_send=-math.inf
    observe_after=-math.inf
    drive_until=-math.inf
    drive_replan_at=-math.inf
    drive_segment=None
    drive_observation=None
    drive_sent_frame=-math.inf
    drive_renew_at=-math.inf
    last_command='stop'
    turn_feedback=TurnFeedback(args.invert_turns)
    start_requested=False
    link_healthy=True
    status_retry_at=0.
    field_cache=None
    field_checked_at=-math.inf
    timing_logged_at=-math.inf
    request_ms=0.

    def record(event,**data):
        with (folder/'events.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'event':event,'time':datetime.now().isoformat(),
                'dry_run':args.dry_run,**data},ensure_ascii=False)+'\n')

    def drive_enabled():
        return (args.multi_push and not (args.one_delivery or args.midfield) and
                (args.dry_run or getattr(link,'drive_hold_ms',0)==2000))

    def send(command, wheels=None, *, renew=False):
        nonlocal last_receipt,last_send,last_command,observe_after,request_ms
        nonlocal drive_until,drive_replan_at,drive_segment,drive_observation,drive_sent_frame,drive_renew_at
        plan=controller.last_plan
        wire={'left':'right','right':'left'}.get(command,command) if turn_feedback.inverted else command
        standard_step=(args.multi_push and
                       (controller.last_plan.get('normal_turn_step',False) if command in ('left','right') else
                        controller.last_plan.get('standard_step',False)))
        if (args.midfield or drive_enabled()) and wire in ('forward','backward'):
            standard_step=False
        profiles=(getattr(link,'medium_turn_ms',0)==60 and getattr(link,'fine_turn_ms',0)==35)
        if args.multi_push and not wheels and wire in ('left','right'):
            standard_step=standard_step or turn_feedback.use_normal_step(
                command,controller.last_plan,profiles=profiles)
            controller.last_plan['normal_turn_step']=bool(standard_step)
            controller.last_plan['turn_stalled_observations']=turn_feedback.stalled_count
        startup_pulse=(args.multi_push and not args.midfield and wire=='forward' and
                       controller.last_plan.get('startup_pulse',False))
        step_duration=.25 if startup_pulse else .12 if standard_step else .08
        turn_profile=None
        if (args.multi_push and not wheels and not standard_step and wire in ('left','right') and
                profiles):
            turn_profile=('fine' if abs(controller.last_plan.get('heading_error_deg',180))<15 else 'medium')
            step_duration=.035 if turn_profile=='fine' else .06
        request_started=time.monotonic()
        if link:
            if wire=='stop':
                response=link.stop()
            elif wheels:
                response=link.drive(*(wheels[::-1] if turn_feedback.inverted else wheels),
                                    DRIVE_LEASE_MS)
            elif startup_pulse:
                response=link.pulse()
            elif turn_profile:
                response=link.step(wire,turn_profile=turn_profile)
            elif standard_step:
                response=link.step(wire,gentle=False)
            else:
                response=link.step(wire)
        else:
            response={'dry_run':True}
        last_receipt=last_send=time.monotonic()
        request_ms=(last_receipt-request_started)*1000
        drive_until=request_started+DRIVE_LEASE_MS/1000 if wheels else -math.inf
        drive_renew_at=request_started+DRIVE_RENEW_S if wheels else -math.inf
        drive_sent_frame=acquired if wheels else -math.inf
        if wheels and not renew:
            drive_replan_at=request_started+plan['drive_replan_s']
            # Inverted wiring still follows the same visual arc.
            origin=np.asarray(robot['center_px'],float)*config.field_mm/1199
            origin[1]=config.field_mm-origin[1]
            endpoint=np.asarray(plan['drive_end_mm'])
            drive_segment=(origin,endpoint,np.float32(plan['drive_sweep']),plan['drive_ignored_id'])
            drive_observation=(acquired,origin)
        elif not wheels:
            drive_segment=None
            drive_observation=None
        if startup_pulse and not wheels:
            controller.startup_pulse_used=True
        if stepped_push:
            # Judge the step from a frame acquired after its firmware time limit.
            observe_after=(request_started if wheels else last_receipt+.02 if wire=='stop'
                           else last_receipt+step_duration+.02)
            if not wheels and wire in ('left','right') and robot.get('heading_valid'):
                turn_feedback.sent(command,robot['heading_rad'],observe_after)
            else:
                turn_feedback.reset()
        last_command=command
        record('command',command=command,wire_command=wire,drive_wheels=wheels,
               drive_renewal=renew,drive_lease_ms=DRIVE_LEASE_MS if wheels else None,response=response,
               request_ms=round(request_ms,1),turn_profile=turn_profile,
               step_ms=round(step_duration*1000) if wire!='stop' and not wheels else None,
               plan=controller.last_plan)

    def mouse(event,x,y,flags,param):
        nonlocal pending
        if event==cv2.EVENT_LBUTTONDOWN:
            pending=(min(1199,max(0,int(x*1200/700))),min(1199,max(0,int(y*1200/700))))

    retrying=False
    try:
        while True:
            try:
                if link:
                    link.connect()
                    if args.midfield and link.gentle_straight_speed != .05:
                        raise ValueError('菜单8需要固定0.05直行档，请重新上传手机热点联动固件。')
                    if (args.straight_push or args.midfield) and not link.reverse_step:
                        raise ValueError('车端固件未提供倒退短步，无法执行往返。')
                if retrying:
                    completed=controller.completed
                    controller.rearm()
                    controller.completed=completed
                    tracker=tracker_type()
                    pending=None
                    last_command='stop';last_send=-math.inf
                    record('reconnected',completed=completed,requires_space=True)
                    print('重新连接成功。已保留标定、取色及完成数量；小车保持停车，场景稳定后按空格重新开始。')
                    retrying=False
                last_receipt=time.monotonic()
                link_healthy=True;status_retry_at=0.
                print('电脑使用蓝牙串口 '+args.bluetooth_port if args.bluetooth_port else '连接小车地址：'+args.host)
                print('手机保持 USB DroidCam。先架空核对轮子映射，再低速落地测试。')
                if args.single_push:
                    print('Enter四角标定，再点击唯一方块取色。车头须对准方块，场景稳定3秒后自动前进，不需空格。')
                    print(f'方块视觉位移达到{args.push_distance:g}mm后停止，只执行一次。X停止，R重新倒计时，S保存，Esc退出。')
                elif args.straight_push:
                    print('只放一块，靠近分界，摆正车头并清空前后通道。标定取色后等 READY，按一次空格执行直推、倒退、停车。')
                elif args.one_delivery:
                    print('单块自动推送：四角标定，点击方块取色，按空格启动。自动接近、对准，推到对面半区中部，再退开核验。')
                elif args.midfield:
                    print('多块完整推送：四角标定，点击同色方块取色，按一次空格。每块推到黄区中部后退开核验，再自动选下一块。X停车。')
                elif stepped_push:
                    print('多块实车测试：Enter标定，点击方块取色，场景稳定后按空格开始。逐个推入黄区、退开核验，再选下一块。X停车。')
                else:
                    print('Enter 四角标定，点击方块取色。空格启动一次自动接近，X停止，R重新准备，S保存。')
                print('结果：',folder)
                if capture is None:
                    selected=calibration(args.camera)
                    if selected is None:
                        return
                    capture,corners,turns,frame_size=selected
                cv2.namedWindow(name,cv2.WINDOW_AUTOSIZE)
                cv2.setMouseCallback(name,mouse)
                last_reason=None
                while True:
                    poll_interval=.22 if args.multi_push and controller.active else .15
                    if (stepped_push and link and not controller.finished and
                            time.monotonic()>=drive_until and
                            time.monotonic()-last_receipt>poll_interval and
                            time.monotonic()>=status_retry_at):
                        try:
                            status_started=time.monotonic()
                            link.request('/status')
                            request_ms=(time.monotonic()-status_started)*1000
                        except OSError as status_error:
                            if controller.active and not args.multi_push:
                                raise
                            if link_healthy:
                                record('idle_link_wait',error=str(status_error))
                                print('停车准备中：暂未收到小车状态，窗口保持打开，自动重新查询。')
                            link_healthy=False
                            status_retry_at=time.monotonic()+1
                        else:
                            if not link_healthy:
                                record('idle_link_recovered')
                                print('小车状态已恢复，继续检查画面。')
                            link_healthy=True
                            last_receipt=time.monotonic()
                    acquired=time.monotonic()
                    try:
                        ok,frame=capture.read()
                    except OSError as camera_error:
                        raise ValueError('摄像头读取失败，需要重新标定：'+str(camera_error)) from camera_error
                    acquired=capture.captured_at
                    if not ok or frame is None or frame.shape[:2]!=frame_size:
                        controller.stop('CAMERA LOST / SIZE CHANGED')
                        send('stop')
                        raise ValueError('摄像头断开或分辨率改变，请重新启动并标定。')
                    processing_started=time.monotonic()
                    image=np.rot90(rectify(frame,corners),turns).copy()
                    if pending is not None:
                        if not stepped_push or controller.active or last_command!='stop':
                            send('stop')
                        sample=sample_colour(image,*pending)
                        if args.one_delivery:
                            clicked_block=ClickedBlock(pending)
                        if args.multi_push:
                            clicked_hsv=sample
                            # Use one stable red band across the OpenCV hue wrap.
                            if sample[0]<=12 or sample[0]>=160:
                                # Cover purple-red shadows without extending
                                # the upper red edge into the orange floor.
                                sample=[176,*sample[1:]]
                            record('colour_sample',point_px=pending,hsv=clicked_hsv,segmentation_hsv=sample)
                        pending=None
                        controller.rearm();tracker=tracker_type()
                        print('方块取色 HSV:',sample)
                    robot=detect_robot(image,retry_low_contrast=args.multi_push)
                    robot_done=time.monotonic()
                    if (args.multi_push and robot.get('detected') and
                            robot.get('heading_valid') and robot.get('geometry_valid')):
                        if turn_feedback.observe(robot['heading_rad'],acquired):
                            record('turn_mapping_corrected',inverted=turn_feedback.inverted)
                            print('连续两次观察到反向转动，已自动交换左右转向。')
                    # Floor geometry is stationary after calibration. A lower
                    # resolution refresh avoids stalling marker/block control.
                    if (not stepped_push or field_cache is None or
                            not field_cache.get('valid') or acquired-field_checked_at>=2):
                        field_cache=(detect_midline(image,max_dimension=450) if stepped_push else
                                     detect_midline(image))
                        field_checked_at=acquired
                    field=field_cache
                    field_done=time.monotonic()
                    regions=[]
                    obstacle_regions=[]
                    mask=np.zeros(image.shape[:2],np.uint8)
                    blocks=()
                    recent_obstacles=()
                    association_hints={}
                    contact_hint=(getattr(controller,'contact_estimate',lambda pose:None)(robot)
                                  if args.multi_push else None)
                    track_error=None
                    if sample is not None:
                        if args.multi_push:
                            hue_tolerance=16 if sample[0]==176 else 10
                            mask,regions=segment(image,sample,h_tol=hue_tolerance,
                                                 min_area=90,field=field,
                                                 square_side_mm=2*config.block_half_mm,
                                                 allow_blurred_square=True)
                        else:
                            mask,regions=segment(image,sample,h_tol=18,min_area=90,field=field)
                        detected_regions=regions
                        outside_regions=exclude_robot_regions(detected_regions,robot)
                        regions=outside_regions
                        locked=getattr(controller,'target_lock',None)
                        tracking_contact=(args.multi_push and controller.active and
                            ((controller.task is not None and controller.state in ('APPROACH','ALIGN','PUSH','RELEASE')) or
                             locked is not None))
                        if clicked_block is not None:
                            candidates=regions
                            if clicked_block.last_region is not None and tracking_contact:
                                contact_px=2*config.block_half_mm*1199/config.field_mm
                                if contact_hint is not None or (clicked_block.last_seen is not None and acquired-clicked_block.last_seen<=.6):
                                    candidates=retain_contact_target(detected_regions,robot,
                                        clicked_block.last_region,block_side_px=contact_px,
                                        expected_point_mm=contact_hint)
                            expected_px=(None if contact_hint is None else
                                (contact_hint[0]*1199/config.field_mm,(config.field_mm-contact_hint[1])*1199/config.field_mm))
                            regions=clicked_block.update(candidates,acquired,expected_point=expected_px)
                            if regions:
                                obstacle_regions=[region for region in outside_regions if region is not regions[0]]
                        elif tracking_contact:
                            target_id=controller.task.target_ids[0] if controller.task is not None else locked['id']
                            previous=tracker.previous.get(target_id)
                            if contact_hint is not None or (previous is not None and acquired-tracker.last_seen[target_id]<=.6):
                                contact_px=2*config.block_half_mm*1199/config.field_mm
                                other_tracks=[point for key,point in tracker.previous.items()
                                    if key!=target_id and acquired-tracker.last_seen[key]<=tracker.TRACK_WINDOW_SECONDS]
                                regions=retain_contact_target(detected_regions,robot,
                                    tracker.regions.get(target_id),block_side_px=contact_px,
                                    other_points_mm=other_tracks,expected_point_mm=contact_hint)
                                if contact_hint is not None:
                                    association_hints={target_id:contact_hint}
                        classify_regions(regions,field)
                        if args.single_push or stepped_push:
                            for region in regions:
                                region.pop('direction_arrow_px',None)
                        try:
                            if args.single_push:
                                if any(max(r['bbox_px'][2:])>40 for r in regions):
                                    raise ValueError('MERGED / OVERSIZE BLOCK')
                                blocks=tuple(Block(f'single-{i}',r['x_mm'],r['y_mm']) for i,r in enumerate(regions))
                            elif clicked_block is not None:
                                blocks=tuple(Block('selected',r['x_mm'],r['y_mm']) for r in regions)
                                blocks+=tracker.update(obstacle_regions)
                            elif args.multi_push:
                                blocks=tracker.update(regions,acquired,association_hints=association_hints)
                                recent_obstacles=tuple(Block(key,*point) for key,point in tracker.previous.items()
                                    if 0<acquired-tracker.last_seen[key]<=.6)
                            else:
                                blocks=tracker.update(regions)
                        except ValueError as error:
                            track_error=str(error)
                    if not stepped_push and link and time.monotonic()-last_receipt>.15:
                        link.request('/status')
                        last_receipt=time.monotonic()
                    now=time.monotonic()
                    planning_started=time.perf_counter()
                    perception_ms=(now-processing_started)*1000
                    if args.dry_run:
                        last_receipt=now
                    driving=now<drive_until
                    drive_guard=(robot.get('detected') and robot.get('heading_valid') and
                                 robot.get('geometry_valid') and field.get('valid') and
                                 0<=now-acquired<=.2 and not track_error)
                    edge_stop=False
                    if args.multi_push and controller.active and drive_guard:
                        body=np.asarray(robot['body_polygon_px'],float)*config.field_mm/1199
                        edge_stop=(not np.isfinite(body).all() or np.any(body<LIVE_EDGE_MARGIN_MM) or
                                   np.any(body>config.field_mm-LIVE_EDGE_MARGIN_MM))
                    segment_blocked=False
                    segment_done=False
                    excessive_motion=False
                    if driving and drive_guard:
                        origin,endpoint,sweep,ignored=drive_segment
                        center=np.asarray(robot['center_px'],float)*config.field_mm/1199
                        center[1]=config.field_mm-center[1]
                        travel=endpoint-origin
                        segment_done=(acquired>drive_sent_frame and np.dot(center-endpoint,travel)>=0)
                        previous_frame,previous_center=drive_observation
                        if acquired>previous_frame:
                            elapsed=acquired-previous_frame
                            excessive_motion=math.dist(center,previous_center)>12+160*elapsed
                            drive_observation=(acquired,center)
                        margin=15+math.sqrt(2)*config.block_half_mm
                        body=np.asarray(robot['body_polygon_px'],float)*config.field_mm/1199
                        segment_blocked=(not np.isfinite(body).all() or np.any(body<10) or
                            np.any(body>config.field_mm-10) or any(
                            b.id!=ignored and cv2.pointPolygonTest(sweep,(float(b.x),float(b.y)),True)>=-margin
                            for b in blocks))
                    holding_drive=(driving and drive_guard and not segment_blocked and
                                   not excessive_motion and not segment_done and now<drive_replan_at)
                    waiting_for_step_frame=(stepped_push and controller.active and link_healthy and
                                            drive_segment is None and acquired<observe_after)
                    if edge_stop:
                        plan=controller.stop('TOO CLOSE TO FIELD EDGE / LOCKED STOP')
                        send('stop')
                    elif stepped_push and not link_healthy:
                        reason='WAITING FOR CAR STATUS / AUTO RECHECK'
                        if args.multi_push and controller.active:
                            plan=controller._waiting(reason)
                        else:
                            plan=controller._invalid(reason)
                    elif drive_segment is not None and (not driving or not drive_guard or
                                                        segment_blocked or excessive_motion):
                        reason=('DRIVE PATH BLOCKED' if segment_blocked else
                                'CAR MOVED TOO FAST FOR ROLLING CONTROL' if excessive_motion else
                                'DRIVE LEASE EXPIRED' if not driving else
                                track_error or 'ROBOT MARKER / BODY OR FIELD LOST DURING DRIVE')
                        plan=controller.stop(reason+' / LOCKED STOP')
                    elif holding_drive or waiting_for_step_frame:
                        plan={**controller.last_plan,'command':last_command if holding_drive else 'stop',
                              'reason':('EXECUTING DRIVE SEGMENT' if holding_drive else
                                        'WAIT FOR FRAME AFTER STEP'),'can_start':False}
                    elif track_error:
                        if args.multi_push and not args.one_delivery and not controller.finished:
                            plan=controller._missing_vision(track_error,now)
                        elif args.multi_push and not controller.finished:
                            plan=controller._reselect(track_error)
                            tracker=tracker_type()
                        elif stepped_push and not controller.active and not controller.finished:
                            plan=controller._invalid(track_error)
                            tracker=tracker_type()
                        else:
                            plan=controller.stop(track_error)
                    elif sample is None:
                        plan=controller._waiting('CLICK A BLOCK TO SAMPLE COLOUR')
                    elif args.one_delivery:
                        plan=controller.update(robot,blocks,field,acquired,now,last_receipt,
                                               target_block_id='selected')
                    elif args.multi_push:
                        drive_options={'continuous_drive':True} if drive_enabled() else {}
                        if drive_segment is not None:
                            drive_options['after_drive_segment']=True
                        plan=controller.update(robot,blocks,field,acquired,now,last_receipt,
                                               recent_obstacles=recent_obstacles,**drive_options)
                    else:
                        plan=controller.update(robot,blocks,field,acquired,now,last_receipt)
                    if stepped_push and start_requested:
                        if controller.finished or (args.straight_push and not plan.get('can_start')):
                            start_requested=False
                            record('start_cancelled',reason=plan['reason'])
                            print('启动请求已取消，保持停车：',plan['reason'])
                        elif plan.get('can_start') and controller.start():
                            start_requested=False
                            record('start_accepted')
                            print('条件满足，开始推送。')
                    planning_ms=(time.perf_counter()-planning_started)*1000
                    link_age_ms=(now-last_receipt)*1000
                    command=plan['command'] if controller.active else 'stop'
                    wheels=plan.get('drive_wheels') if drive_enabled() and command!='stop' else None
                    if holding_drive:
                        if now>=drive_renew_at and acquired>drive_sent_frame:
                            send(command,wheels,renew=True)
                    elif waiting_for_step_frame:
                        pass
                    elif drive_segment is not None and not wheels:
                        # End a rolling command explicitly before a short step or reversal.
                        send('stop')
                    elif command=='stop':
                        if last_command!='stop':
                            if (args.multi_push and not (args.one_delivery or args.midfield) and not driving and
                                    link_healthy and acquired>=observe_after):
                                last_command='stop'
                                turn_feedback.reset()
                            else:
                                send('stop')
                    elif args.multi_push or now-last_send>=.22:
                        send(command,wheels)
                    elif command!=last_command and last_command!='stop':
                        send('stop')
                    if args.multi_push and now-timing_logged_at>=1:
                        record('timing',frame_age_ms=round((now-acquired)*1000,1),
                               processing_ms=round(perception_ms,1),
                               robot_and_warp_ms=round((robot_done-processing_started)*1000,1),
                               field_ms=round((field_done-robot_done)*1000,1),
                               blocks_ms=round((now-field_done)*1000,1),
                               planning_ms=round(planning_ms,1),
                               request_ms=round(request_ms,1))
                        timing_logged_at=now
                    result=annotated(image,regions,field,calibrated=True)
                    for obstacle in obstacle_regions:
                        x,y,w,h=obstacle['bbox_px']
                        cv2.rectangle(result,(x,y),(x+w,y+h),(0,165,255),2)
                    if clicked_block is not None and not regions and clicked_block.recently_seen(acquired):
                        x,y,w,h=clicked_block.last_region['bbox_px']
                        cv2.rectangle(result,(x,y),(x+w,y+h),(0,165,255),2)
                        cv2.putText(result,'LAST SEEN',(x,max(105,y-5)),cv2.FONT_HERSHEY_SIMPLEX,
                                    .45,(0,165,255),1,cv2.LINE_AA)
                    draw_robot(result,robot,calibrated=True)
                    if plan.get('goal_mm') and robot.get('detected'):
                        goal=np.array([plan['goal_mm'][0],1200-plan['goal_mm'][1]])*1199/1200
                        cv2.arrowedLine(result,tuple(np.rint(robot['center_px']).astype(int)),
                                        tuple(np.rint(goal).astype(int)),(255,255,0),3,tipLength=.1)
                        cv2.circle(result,tuple(np.rint(goal).astype(int)),15,(255,0,255),3)
                    mode='DRY RUN' if args.dry_run else 'LIVE BLUETOOTH' if args.bluetooth_port else 'LIVE WIFI'
                    state=controller.state if args.single_push or stepped_push else 'RUNNING' if controller.active else 'READY' if plan.get('can_start') else 'STOPPED'
                    if stepped_push and plan.get('can_start'):
                        state='READY'
                    cv2.rectangle(result,(0,0),(1200,100),(25,25,25),-1)
                    detail=plan['reason']
                    if stepped_push:
                        detail+=f' | VERIFIED: {controller.completed}'
                        if start_requested:
                            detail+=' | START REQUESTED / X CANCEL'
                    if args.single_push and controller.active:
                        detail+=f' | BLOCK: {plan.get("block_progress_mm",0):.0f}/{args.push_distance:g} mm'
                    for row,text in enumerate((f'{mode} | {state} | NEXT: {plan["command"].upper()}',
                                               detail,('AUTO START | X stop | R rearm | S save | Esc' if args.single_push else
                                                               'SPACE start | X stop | R rearm | S save | Esc exit'))):
                        cv2.putText(result,text,(12,25+30*row),cv2.FONT_HERSHEY_SIMPLEX,.65,(0,230,255),1,cv2.LINE_AA)
                    if args.multi_push:
                        cv2.putText(result,f'VISION {now-acquired:.3f}s | PROCESS {perception_ms:.0f}ms | HTTP {request_ms:.0f}ms',
                                    (12,1190),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,230,255),2,cv2.LINE_AA)
                    if last_reason!=plan['reason']:
                        if stepped_push:
                            record('plan',plan=plan,robot_reason=robot.get('reason'),
                                   obstacle_regions=obstacle_regions,
                                   recent_obstacles_mm=[(b.x,b.y) for b in recent_obstacles],
                                   field_reason=field.get('reason'),
                                   field_point_px=field.get('point_px'),
                                   yellow_normal=field.get('yellow_normal'),
                                   frame_age_ms=round((now-acquired)*1000),
                                   link_age_ms=round(link_age_ms),
                                   regions=[{key: region.get(key) for key in ('x_mm','y_mm','half')}
                                            for region in regions])
                        else:
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
                        start_requested=False
                        controller.stop('MANUAL STOP');send('stop')
                    if key in (ord('r'),ord('R')):
                        start_requested=False
                        send('stop');controller.rearm();tracker=tracker_type()
                    if key==32:
                        if ((args.midfield and controller.finished) or
                                (args.straight_push and not controller.active and not plan.get('can_start'))):
                            record('start_rejected',reason=plan['reason'])
                            print('Not ready. Press R to reset a finished run, or check the current status:',plan['reason'])
                        elif stepped_push:
                            if not controller.active:
                                if controller.finished:
                                    completed=controller.completed
                                    controller.rearm()
                                    if not args.one_delivery:
                                        controller.completed=completed
                                    tracker=tracker_type()
                                start_requested=True
                                record('start_requested',reason=controller.last_plan['reason'])
                                print('已收到启动请求：条件满足后开始；X取消。当前状态：',controller.last_plan['reason'])
                        elif not args.single_push:
                            if controller.start():
                                record('start_accepted')
                            else:
                                record('start_rejected',reason=controller.last_plan['reason'])
                                print('暂不能启动：',controller.last_plan['reason'])
                                print('若提示MERGED/OVERSIZE或AMBIGUOUS：先分开方块、检查轮子误识别，再按R准备。显示READY后，点击识别窗口按空格。')
                    if key in (ord('s'),ord('S')):
                        stamp=datetime.now().strftime('%H%M%S-%f')
                        write_png(folder/(stamp+'-source.png'),frame)
                        write_png(folder/(stamp+'-result.png'),result)
                        record('snapshot',robot=robot,regions=regions,field=field,plan=plan,
                               corners=corners,rotation_ccw=turns,sample_hsv=sample)
                break
            except (OSError,ValueError,cv2.error) as error:
                start_requested=False
                controller.stop('ERROR / MOTION LOCKED: '+str(error))
                record('error',error_type=type(error).__name__,error=str(error))
                try:
                    send('stop')
                except (OSError,ValueError) as stop_error:
                    record('stop_unconfirmed',error=str(stop_error))
                print('测试已暂停，保持停车：',error)
                print('错误已记录：',folder/'events.jsonl')
                if stepped_push and isinstance(error,OSError):
                    print('窗口保持打开。网络恢复后按R重连，成功后还须按空格重新启动。Esc退出。')
                    recovery=show_stopped_error(name,error,allow_reconnect=True,image=image,
                                                allow_start=not args.midfield)
                    if recovery:
                        start_requested=recovery=='start'
                        record('reconnect_requested')
                        retrying=True
                        continue
                else:
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
