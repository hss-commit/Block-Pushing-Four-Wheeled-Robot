"""USB serial link for the ESP32 SIM_ONLY firmware.

The class can later be called by a real motion executor. This CLI only sends
commands entered by a person and never assumes a simulated DRIVE moved a car.
"""

import argparse
import math
import time

import serial


class Esp32Link:
    def __init__(self, port: str, baudrate: int = 115200):
        self.serial = serial.Serial(port, baudrate, timeout=0.2, write_timeout=1)
        self.sequence = 0
        # Opening the USB serial port commonly resets an ESP32 development board.
        time.sleep(2)
        self.serial.reset_input_buffer()

    def command(self, verb: str, *args: object) -> str:
        self.sequence += 1
        sequence = self.sequence
        message = f"{verb} {sequence}"
        if args:
            message += " " + " ".join(str(arg) for arg in args)
        self.serial.write((message + "\n").encode("ascii"))
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            line = self.serial.readline().decode("ascii", errors="replace").strip()
            parts = line.split()
            if len(parts) >= 2 and parts[1] == str(sequence) and parts[0] in {"OK", "PONG", "STATUS", "ERR"}:
                if parts[0] == "ERR":
                    raise RuntimeError(line)
                return line
        raise TimeoutError(f"ESP32 did not answer {verb} #{sequence}")

    def close(self) -> None:
        if self.serial.is_open:
            try:
                self.command("STOP")
            except (OSError, RuntimeError, TimeoutError, serial.SerialException):
                pass
            self.serial.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="ESP32 USB serial dry-run console")
    parser.add_argument("--port", default="COM3", help="Serial port, previously COM3")
    parser.add_argument("--check", action="store_true", help="Run one serial/odometry/watchdog check")
    args = parser.parse_args()
    help_text = "ping | drive LEFT RIGHT | geom DIAMETER_MM TRACK_MM | ticks LEFT RIGHT | status | stop | quit"
    print(help_text)
    try:
        with Esp32Link(args.port) as link:
            print(link.command("PING"))
            if args.check:
                print(link.command("GEOM", 40, 100))
                print(link.command("SIMTICKS", 1560, 1560))
                pose = link.command("STATUS").split()
                assert pose[2] == "SIM_ONLY" and pose[5:7] == ["1560", "1560"]
                assert math.isclose(float(pose[7]), math.pi * 40, abs_tol=0.01)
                assert abs(float(pose[8])) < 0.01 and abs(float(pose[9])) < 0.001
                print("One simulated wheel revolution:", " ".join(pose[7:10]))
                print(link.command("DRIVE", 100, 100))
                time.sleep(0.4)
                stopped = link.command("STATUS").split()
                assert stopped[3:5] == ["0", "0"]
                print("300 ms command timeout: stopped")
                return
            while True:
                try:
                    entry = input("esp32> ").strip().split()
                except EOFError:
                    break
                if not entry:
                    continue
                verb = entry[0].lower()
                if verb in {"quit", "exit"}:
                    break
                commands = {"ping": ("PING", 0), "stop": ("STOP", 0),
                            "status": ("STATUS", 0), "drive": ("DRIVE", 2),
                            "geom": ("GEOM", 2), "ticks": ("SIMTICKS", 2)}
                if verb not in commands or len(entry) - 1 != commands[verb][1]:
                    print(help_text)
                    continue
                wire_verb = commands[verb][0]
                try:
                    print(link.command(wire_verb, *entry[1:]))
                except (RuntimeError, TimeoutError, serial.SerialException) as exc:
                    print(exc)
    except (OSError, serial.SerialException) as exc:
        raise SystemExit(f"Cannot open {args.port}: {exc}") from exc


if __name__ == "__main__":
    main()
