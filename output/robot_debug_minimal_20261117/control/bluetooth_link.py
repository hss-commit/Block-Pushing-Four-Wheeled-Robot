"""Bluetooth SPP link for the timed vision test; no automatic motion retries."""
import argparse
import json
import time
import uuid

import serial
from serial.tools import list_ports

from control.vision_wifi_test import WifiLink


class BluetoothLink(WifiLink):
    def __init__(self, port):
        self.port = port
        self.serial = None

    def request(self, path, data=None):
        if path not in ('/status', '/stop', '/pulse', '/step'):
            raise ValueError('未知蓝牙指令')
        direction = '-' if path == '/pulse' else (data or {}).get('direction')
        if path == '/step' and direction not in ('forward', 'left', 'right'):
            raise ValueError('无效转向')
        suffix = ''
        if path in ('/pulse', '/step'):
            # Expiry uses the device clock, avoiding dependence on Windows clock sync.
            status = self.request('/status')
            uptime = status.get('uptime_ms')
            if type(uptime) is not int or not 0 <= uptime <= 0xffffffff:
                raise ValueError('蓝牙固件未提供有效动作期限')
            suffix = f' {direction} {(uptime + 200) & 0xffffffff}'
        token = uuid.uuid4().hex
        if self.serial is None:
            self.serial = serial.Serial(self.port, 115200, timeout=.02, write_timeout=.18)
        message = f'{token} {path}{suffix}\n'.encode('ascii')
        started = time.monotonic()
        if self.serial.write(message) != len(message):
            raise OSError('蓝牙指令发送不完整；不会重试动作')
        buffer = bytearray()
        while time.monotonic() - started < .18:
            buffer.extend(self.serial.read_until(b'\n', 2048 - len(buffer)))
            if len(buffer) >= 2048:
                raise ValueError('蓝牙回复过长')
            if not buffer.endswith(b'\n'):
                continue
            try:
                result = json.loads(buffer.decode('ascii'))
            except (UnicodeError, json.JSONDecodeError) as error:
                raise ValueError('蓝牙回复无法解析') from error
            buffer.clear()
            if not isinstance(result, dict):
                raise ValueError('蓝牙回复格式错误')
            if result.get('id') != token:
                continue
            if result.get('protocol') != 'vision-bt-v1':
                raise ValueError('请烧录视觉蓝牙联动测试工程')
            return result
        raise TimeoutError('蓝牙回复超时；不会重试动作。请核对配对和蓝牙传出 COM 端口。')

    def connect(self):
        super().connect()
        if self.request('/status').get('step_ms') != 120:
            raise ValueError('蓝牙固件不支持120ms方向动作')

    def step(self, direction):
        result = self.request('/step', {'direction': direction})
        if result.get('result') != 'step_queued':
            raise ValueError('ESP32 未接受方向指令：' + str(result))
        return result

    def close(self):
        if self.serial is not None:
            self.serial.close()
            self.serial = None


def main():
    parser = argparse.ArgumentParser(description='检查蓝牙连接，只查询状态和发送停止，不驱动车轮。')
    parser.add_argument('--port')
    args = parser.parse_args()
    if not args.port:
        for port in list_ports.comports():
            print(port.device, port.description)
        print('先在 Windows 配对 ESP32-Vision-BT，再用 --port COM端口 检查连接。')
        return
    link = BluetoothLink(args.port)
    try:
        link.connect()
        print('蓝牙通信成功，已发送停止请求；这不代表电机或停车已经实测。')
    finally:
        try:
            if link.serial is not None:
                link.stop()
        finally:
            link.close()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, serial.SerialException) as error:
        print('蓝牙检查停止：', error)
        raise SystemExit(1)
