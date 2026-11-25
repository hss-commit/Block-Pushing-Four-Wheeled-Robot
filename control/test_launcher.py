"""Launcher checks without opening a camera or connecting to a real vehicle."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from control import launcher
from vision.test_robot_vision import TEST_CONFIG


def main():
    with tempfile.TemporaryDirectory() as folder:
        with patch.object(launcher, 'SETTINGS', Path(folder) / 'settings.json'), patch('vision.robot_vision.load_config', return_value=TEST_CONFIG):
            settings = launcher.load_settings()
            assert settings == {'ip': '10.112.135.116', 'camera': 1, 'mode': '2'}
            with patch('builtins.input', side_effect=['http://192.168.1.8/', '3']):
                launcher.configure(settings)
            assert launcher.load_settings() == {'ip': '192.168.1.8', 'camera': 3, 'mode': '2'}
            before = dict(settings)
            with patch('builtins.input', side_effect=['1.2.3.4 & calc', '0']):
                launcher.configure(settings)
            assert settings == before
            launcher.SETTINGS.write_text('broken', encoding='utf-8')
            assert launcher.load_settings()['mode'] == '2'
            for mode in launcher.MODES:
                args = launcher.command(settings, mode)
                assert ('--camera' in args) == (mode != '5')
                if mode != '5':
                    assert args[args.index('--camera') + 1] == '3'
                assert ('--host' in args) == (mode != '2')
                assert '--single-push' not in args
                assert ('--multi-push' in args) == (mode == '8')
                assert ('--midfield' in args) == (mode == '8')
                assert '--one-delivery' not in args
                assert Path(args[3]).is_file()
            launcher.save_settings({'ip': '192.168.1.8', 'camera': 3, 'mode': '7'})
            assert launcher.load_settings() == {'ip': '192.168.1.8', 'camera': 3, 'mode': '8'}
            for choice in ('', '1', '6', '7'):
                with patch('builtins.input', side_effect=[choice, 'q']), patch.object(launcher, 'check_connection'), patch.object(launcher.subprocess, 'run') as run:
                    run.return_value.returncode = 0
                    assert launcher.main() == 0
                    assert run.call_args.args[0] == launcher.command(settings, '8')
            for status in ({'drive_hold_ms': 2000}, {}):
                output = io.StringIO()
                with (patch('builtins.input', side_effect=['8', 'q']),
                      patch.object(launcher, 'check_connection', return_value=status),
                      patch.object(launcher.subprocess, 'run') as run, redirect_stdout(output)):
                    run.return_value.returncode = 0
                    assert launcher.main() == 0
                    assert run.call_args.args[0] == launcher.command(settings, '8')
                    assert '多块推送使用车端限时短步' in output.getvalue()
            launcher.SETTINGS.write_text('broken', encoding='utf-8')
            # A failed connection must not open the motion program.
            with patch('builtins.input', side_effect=['1', 'q']), patch('vision.robot_vision.load_config', return_value={**TEST_CONFIG, 'body_length_mm': None}), patch.object(launcher, 'check_connection') as check, patch.object(launcher.subprocess, 'run') as run:
                assert launcher.main() == 0
                check.assert_not_called()
                run.assert_not_called()
            # One-time centimetre entry is persisted in millimetres.
            marker_path = Path(folder) / 'marker.json'
            with patch('vision.robot_vision.CONFIG_PATH', marker_path), patch('builtins.input', side_effect=['5', '20', '18', '0', '-1']):
                launcher.configure_marker()
            marker = json.loads(marker_path.read_text(encoding='utf-8'))
            assert marker['body_length_mm'] == 200 and marker['body_width_mm'] == 180
            assert marker['center_offset_forward_mm'] == -10
            with patch('builtins.input', side_effect=['1', 'q']), patch.object(launcher, 'check_connection', side_effect=OSError('offline')), patch.object(launcher.subprocess, 'run') as run:
                assert launcher.main() == 0
                run.assert_not_called()
            # Preview needs no vehicle; quitting a child returns to the menu.
            with patch('builtins.input', side_effect=['5', 'q']), patch('vision.robot_vision.load_config', side_effect=AssertionError('Remote must not need body dimensions')), patch.object(launcher, 'check_connection') as check, patch.object(launcher.subprocess, 'run') as run:
                run.return_value.returncode = 0
                assert launcher.main() == 0
                check.assert_called_once_with('10.112.135.116', True)
                assert '--camera' not in run.call_args.args[0]
            with patch('builtins.input', side_effect=['2', 'q']), patch.object(launcher, 'check_connection') as check, patch.object(launcher.subprocess, 'run') as run:
                run.return_value.returncode = 0
                assert launcher.main() == 0
                check.assert_not_called()
                assert '--host' not in run.call_args.args[0]
            # Enter reuses the saved mode and address, with preflight first.
            settings['mode'] = '1'
            launcher.save_settings(settings)
            assert launcher.load_settings()['mode'] == '8'
            with patch('builtins.input', side_effect=['', 'q']), patch.object(launcher, 'check_connection') as check, patch.object(launcher.subprocess, 'run') as run:
                run.return_value.returncode = 1
                assert launcher.main() == 0
                check.assert_called_once_with('192.168.1.8', True)
                assert run.call_args.args[0] == launcher.command(settings, '8')
    status = {'protocol': 'vision-pulse-v1', 'result': 'ready', 'pulse_ms': 250, 'step_ms': 120}
    class Opener:
        def open(self, url, timeout):
            assert url == 'http://192.168.1.8/status'
            assert timeout == 2
            return io.BytesIO(json.dumps(status).encode())
    with patch.object(launcher, 'build_opener', return_value=Opener()):
        launcher.check_connection('192.168.1.8', True)
        status['protocol'] = 'other'
        try:
            launcher.check_connection('192.168.1.8', True)
        except ValueError:
            pass
        else:
            raise AssertionError('wrong firmware accepted')
    print('Launcher checks passed: settings, mode aliases, camera-free remote, GET-only preflight, failure/retry and remembered start.')


if __name__ == '__main__':
    main()
