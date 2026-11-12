"""One entry for existing camera and car tests; no motion during connection checks."""
import importlib.util
import ipaddress
import json
from pathlib import Path
import subprocess
import sys
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / 'control' / 'launcher.local.json'
MODES = {
    '1': ('直接推块测试（自动接近、推移10厘米后停车）', 'control/vision_approach_test.py', ['--single-push']),
    '2': ('只看视觉识别（不控制小车）', 'vision/photo_vision.py', []),
    '3': ('短动作测试（空格触发）', 'control/vision_wifi_test.py', []),
    '4': ('进阶：只自动接近（含转向，先验轮向）', 'control/vision_approach_test.py', []),
    '5': ('键盘遥控（按住持续走，松开停车）', 'control/keyboard_remote.py', []),
    '6': ('多块入区测试（逐个送入黄区，空格启动）', 'control/vision_approach_test.py', ['--multi-push']),
}


def address(value):
    value = value.strip().removeprefix('http://').rstrip('/')
    return str(ipaddress.IPv4Address(value))


def load_settings():
    defaults = {'ip': '10.112.135.116', 'camera': 1, 'mode': '2'}
    try:
        saved = json.loads(SETTINGS.read_text(encoding='utf-8'))
        defaults['ip'] = address(saved['ip'])
        if type(saved['camera']) is not int or saved['camera'] < 0 or saved['mode'] not in MODES:
            raise ValueError('invalid settings')
        defaults.update(camera=saved['camera'], mode=saved['mode'])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return defaults


def save_settings(settings):
    SETTINGS.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')


def check_connection(ip, needs_steps):
    # Only GET /status here. Existing test programs retain all motion/stop guards.
    with build_opener(ProxyHandler({})).open('http://' + address(ip) + '/status', timeout=2) as response:
        status = json.loads(response.read(4096).decode('utf-8'))
    if not isinstance(status, dict) or status.get('protocol') != 'vision-pulse-v1' or status.get('result') != 'ready' or status.get('pulse_ms') != 250:
        raise ValueError('小车程序不匹配，请使用手机热点联动测试固件')
    if needs_steps and status.get('step_ms') != 120:
        raise ValueError('小车固件不支持当前接近/推送测试')


def command(settings, mode):
    _, script, extra = MODES[mode]
    args = [sys.executable, '-X', 'utf8', str(ROOT / script), *extra]
    if mode != '5':
        args += ['--camera', str(settings['camera'])]
    if mode != '2':
        args += ['--host', 'http://' + address(settings['ip'])]
    return args


def configure(settings):
    try:
        ip = input(f"小车IP [{settings['ip']}]，回车保留：").strip()
        camera = input(f"摄像头编号 [{settings['camera']}]，回车保留：").strip()
        updated = dict(settings)
        if ip:
            updated['ip'] = address(ip)
        if camera:
            updated['camera'] = int(camera)
            if updated['camera'] < 0:
                raise ValueError('摄像头编号不能小于0')
        settings.update(updated)
        save_settings(settings)
    except ValueError:
        print('输入无效：IP应为四段数字，摄像头编号应为非负整数。设置未更改。')


def configure_marker():
    sys.path.insert(0, str(ROOT))
    from vision.robot_vision import CONFIG_PATH, load_config, validate_config
    config = load_config()
    print('单位为厘米；回车保留。长度沿车头方向，宽度含轮胎，长度含推板。')
    print('尽量把码贴在车体中心，上边朝车头。偏移表示从码中心到车体中心，向右/向前为正。')
    fields = [('marker_size_mm', '黑色码正方形边长（不含白边）'),
              ('body_length_mm', '整车最大长度'), ('body_width_mm', '整车最大宽度'),
              ('center_offset_right_mm', '码中心到车体中心的向右偏移'),
              ('center_offset_forward_mm', '码中心到车体中心的向前偏移')]
    updated = dict(config)
    try:
        for key, label in fields:
            current = config[key]
            value = input(f"{label} [{current/10 if current is not None else '未量'}]：").strip()
            if value:
                updated[key] = float(value)*10
        validate_config(updated)
        CONFIG_PATH.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding='utf-8')
        print('标记设置已保存；下次打开测试时生效。尺寸未填全时只允许查看定位。')
    except ValueError:
        print('尺寸输入无效，设置未更改。')


def main():
    missing = [name for name in ('cv2', 'numpy') if importlib.util.find_spec(name) is None]
    if missing:
        print('缺少视觉运行组件：' + ', '.join(missing) + '。请使用项目自带的启动入口。')
        return 1
    settings = load_settings()
    print('统一测试入口；键盘遥控不需要摄像头，视觉模式需先连好DroidCam。')
    print('实车模式需要电脑和ESP32连接同一手机热点。')
    while True:
        print('\n========== 机器人测试 ==========')
        print(f"摄像头：{settings['camera']}  小车IP：{settings['ip']}（会自动记住）")
        for key, (label, _, _) in MODES.items():
            print(f'{key}. {label}')
        print('S. 修改IP / 摄像头    M. 贴码尺寸 / 车体尺寸    Q. 退出')
        mode = input(f"回车启动上次模式 [{settings['mode']}]，或输入选项：").strip().lower()
        if mode == 'q':
            return 0
        if mode == 's':
            configure(settings)
            continue
        if mode == 'm':
            configure_marker()
            continue
        mode = mode or settings['mode']
        if mode not in MODES:
            print('请输入1～6、S、M或Q。')
            continue
        if mode != '2':
            if mode != '5':
                sys.path.insert(0, str(ROOT))
                from vision.robot_vision import load_config
                marker = load_config()
                if marker['body_length_mm'] is None or marker['body_width_mm'] is None:
                    print('尚未填写车体长宽：先选2查看ArUco定位；量好后选M填写，再做实车测试。')
                    continue
            print('正在检查小车连接（不会发送运动指令）……')
            try:
                check_connection(settings['ip'], mode in ('1', '4', '5', '6'))
            except (OSError, ValueError) as error:
                print(f'未能连接：{error}')
                print('请确认电脑和小车均已加入Robot-Test热点，小车已供电。')
                print('IP可能因重新联网而变化；输入S修改，或选2先看画面。')
                continue
            print('连接检查通过。测试程序仍会按原时限检查通信。')
        settings['mode'] = mode
        save_settings(settings)
        print('正在打开：' + MODES[mode][0])
        if mode != '5':
            print('关闭其他占用摄像头的测试窗口；DroidCam客户端保留。')
        if mode == '1':
            print('只留一个方块并提前摆正小车；完成四角标定和取色后自动倒计时3秒运动，X停车。')
        result = subprocess.run(command(settings, mode), cwd=ROOT)
        print('测试已退出。' if result.returncode == 0 else f'测试异常退出（{result.returncode}），可查看上方提示后重试。')
        if mode == '5':
            print('已回到主菜单：W/S/A/D此时不能遥控；输入5并回车，点击新弹出的遥控窗口，等待CONNECTED后再操作。')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (EOFError, KeyboardInterrupt):
        print('\n已退出启动入口。')
    except OSError as error:
        print('启动失败：', error)
        raise SystemExit(1)
