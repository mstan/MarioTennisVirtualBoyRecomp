"""Record missing materials on every presented frame using native Windows input.

Private output contains decoded owner-ROM artwork. Do not commit or distribute it.
The test window is hidden; input is posted only to that process's SDL window.
"""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import time

from color_capture import Client
from validation_package import install_args


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("exe", "rom", "package", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--samples", type=int, default=280)
    parser.add_argument("--step", type=int, default=12)
    parser.add_argument("--character", type=int, choices=range(7), default=0)
    parser.add_argument("--opponent", type=int, choices=range(7), default=1)
    parser.add_argument("--port", type=int, default=4498)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.character == args.opponent:
        parser.error("Choose two different characters")
    output = args.output.resolve()
    poses = output / "poses"
    poses.mkdir(parents=True, exist_ok=True)
    if any(poses.iterdir()):
        raise ValueError("Use a fresh capture directory")
    config = output / "settings.cfg"
    config.write_text("fullscreen 0\nscale 1\nsource 1\n", encoding="utf-8")
    env = os.environ.copy()
    env["VB_TENNIS_CAPTURE_MISSING"] = str(poses)
    mods = output / "mods"
    command = [
        str(args.exe.resolve()),
        "--rom",
        str(args.rom.resolve()),
        "--no-launcher",
        "--paused",
        "--stereo",
        "--port",
        str(args.port),
        "--config",
        str(config),
        "--mods-dir",
        str(mods),
    ]
    command += install_args(mods, args.package.resolve())
    command += ["--enable-mod", "marios-tennis.full-color:full-color"]
    client = Client(args.port)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.PostMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    held = set()
    mapping = {
        4: (88, 45, False),
        8: (90, 44, False),
        256: (39, 77, True),
        512: (37, 75, True),
        1024: (40, 80, True),
        2048: (38, 72, True),
        4096: (13, 28, False),
        65536: (9, 15, False),
    }
    window = None
    with (output / "runtime.log").open("wb") as log:
        process = subprocess.Popen(
            command,
            cwd=output,
            env=env,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        def key(button, down):
            vk, scan, extended = mapping[button]
            flags = 1 | (scan << 16) | (int(extended) << 24)
            if not down:
                flags |= 0xC0000000
            if not user32.PostMessageW(window, 0x100 if down else 0x101, vk, flags):
                raise ctypes.WinError(ctypes.get_last_error())
            (held.add if down else held.discard)(button)
            time.sleep(0.01)

        def tap(button, frames=90):
            key(button, True)
            client.advance(12)
            key(button, False)
            client.advance(frames - 12)

        try:
            deadline = time.monotonic() + 30
            # SDL may recreate its initial HWND while choosing an OpenGL
            # renderer. A serviced TCP command means startup has finished.
            while True:
                try:
                    client.call("get_registers")
                    break
                except OSError:
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise
                    time.sleep(0.05)
            while window is None:
                windows = []

                @callback_type
                def visit(hwnd, data):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    name = ctypes.create_unicode_buffer(100)
                    user32.GetClassNameW(hwnd, name, 100)
                    if pid.value == process.pid and name.value == "SDL_app":
                        windows.append(hwnd)
                    return True

                user32.EnumWindows(visit, 0)
                if windows:
                    window = windows[0]
                    user32.ShowWindow(window, 0)
                    break
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Game window did not start; inspect runtime.log")
                time.sleep(0.05)
            key(65536, True)  # Turbo, confined to the hidden test window.
            client.advance(180)
            for button in (4096, 4096, 256, 4096, 4096, 4096):
                tap(button)
            for _ in range(3):
                tap(1024, 36)
            for _ in range(args.character):
                tap(256, 36)
            tap(4096, 120)
            for extra in range(3):
                if any(client.read(0x0500203A, 8)):
                    break
                tap(4, 120)
                if extra == 0:
                    cursor = args.character + 1 if args.character < 6 else 5
                    while cursor != args.opponent:
                        tap(512, 36)
                        cursor = (cursor - 1) % 7
                        if cursor == args.character:
                            cursor = (cursor - 1) % 7
            ids = list(client.read(0x0500203A, 8)[::2])
            assert ids[0] == args.character and ids[3] == args.opponent, ids
            directions = [0, 256, 512, 2048, 1024, 256 | 2048, 512 | 1024, 0]
            for sample in range(args.samples):
                stroke = (4 if (sample // 10) % 2 == 0 else 8) if sample % 10 < 4 else 0
                pad = directions[(sample // 12) % len(directions)] | stroke
                for button in mapping:
                    if button == 65536:
                        continue
                    if bool(button & pad) != (button in held):
                        key(button, bool(button & pad))
                client.advance(args.step)
                if sample % 20 == 0:
                    for eye in (0, 1):
                        client.call(
                            "screenshot",
                            path=(output / f"frame-{sample:04}-{eye}.png").as_posix(),
                            eye=eye,
                            presented=1,
                        )
                    print(
                        "sample",
                        sample,
                        "captured",
                        len(list(poses.glob("c*.json"))),
                        flush=True,
                    )
        finally:
            if process.poll() is None:
                for button in list(held):
                    try:
                        key(button, False)
                    except OSError:
                        pass
                try:
                    client.call("quit")
                except OSError:
                    process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=10)
    summary = json.loads((poses / "capture-summary.json").read_text())
    print(summary, flush=True)
    assert not summary["failed"] and not summary["limit_reached"], summary
    assert summary["eye_frames"] >= args.samples, (
        "Insufficient presented-frame coverage"
    )
    if args.check:
        assert summary["unknown_eye_frames"] == 0, (
            "Uncatalogued transition frames captured"
        )


if __name__ == "__main__":
    main()
