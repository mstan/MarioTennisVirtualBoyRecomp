"""Windows owner-ROM UI check. Usage: python validate_ui_windows.py EXE ROM VBMOD OUTPUT.

Drives only the test process's window. Checks launcher rebind persistence,
actual guest input, menu pause and reversible presentation toggles.
Requires a UI/debug-tools build; leaves screenshots and an isolated profile.
"""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from validation_package import install_args

exe, rom, package, output = [Path(p).resolve() for p in sys.argv[1:]]
output.mkdir(parents=True, exist_ok=True)
config = output / "settings.cfg"
config.write_text("fullscreen 0\nscale 2\nsource 1\n")
env = os.environ.copy()
env.pop("VBRECOMP_OVERRIDES", None)
env["LNG_SCRIPT"] = ";".join([
    "wait:10", "view:controller", "capbtn:8", "wait:5", "key:c", "wait:5",
    f"shot:{(output / 'controller.png').as_posix()}", "view:dashboard", "wait:5",
    "click:968,819", "wait:30"])
args = [str(exe), "--launcher", "--paused", "--port", "4492", "--rom", str(rom),
        "--config", str(config), "--mods-dir", str(output / "mods")]
args += install_args(output/'mods',package)
args += ["--enable-mod", "marios-tennis.full-color:full-color"]
process = subprocess.Popen(args, cwd=output, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def call(cmd, **values):
    with socket.create_connection(("127.0.0.1", 4492), timeout=5) as sock:
        sock.sendall((json.dumps(dict(cmd=cmd, **values))+"\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(1048576)
            if not chunk:
                raise RuntimeError("Debugger disconnected")
            data += chunk
    reply = json.loads(data)
    assert reply.get("ok"), reply
    return reply


def key(vk, scan, down=True, extended=False):
    flags = 1 | (scan << 16) | (int(extended) << 24)
    if not down:
        flags |= 0xc0000000
    assert user32.PostMessageW(window, 0x100 if down else 0x101, vk, flags)
    time.sleep(.03)


def tap(vk, scan, extended=False):
    key(vk, scan, extended=extended)
    key(vk, scan, down=False, extended=extended)


def advance(frames, button=None):
    if button:
        key(*button)
    target = call("run_frames", frames=frames)["target"]
    deadline = time.monotonic()+30
    while call("get_registers")["frame"] < target:
        if time.monotonic() > deadline:
            raise RuntimeError("Guest frame timeout")
        time.sleep(.01)
    if button:
        key(*button, down=False)


try:
    deadline = time.monotonic()+30
    while True:
        assert process.poll() is None, f"Runtime exited: {process.returncode}"
        try:
            call("get_registers")
            break
        except OSError:
            assert time.monotonic() < deadline, "Launcher did not launch"
            time.sleep(.1)
    assert "key8 6\n" in config.read_text(), "Launcher rebind was not returned and saved"
    windows = []

    @callback_type
    def find_window(handle, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if pid.value == process.pid and user32.IsWindowVisible(handle):
            windows.append(handle)
        return True

    user32.EnumWindows(find_window, 0)
    assert len(windows) == 1, windows
    window = windows[0]
    key(0x43, 0x2e)  # The newly bound C key must set native A.
    assert int(call("read_ram", addr=0x02000010, len=1)["hex"],16) & 4
    key(0x43, 0x2e, down=False)
    key(0x58, 0x2d)  # Old X must no longer set A.
    assert not int(call("read_ram", addr=0x02000010, len=1)["hex"],16) & 4
    key(0x58, 0x2d, down=False)
    key(9, 0x0f)  # Turbo avoids waiting on presentation pacing during the route.
    advance(180)
    for button in [(13,0x1c),(13,0x1c),(0x27,0x4d),(13,0x1c),(13,0x1c)]:
        # Right is an extended key; send it explicitly.
        key(*button, extended=button[0]==0x27)
        advance(12)
        key(*button, down=False, extended=button[0]==0x27)
        advance(78)
    for _ in range(2):
        advance(12,(13,0x1c)); advance(108)
    key(9,0x0f,down=False)
    assert any(w["world"] in (21,22) for w in call("world_map")["worlds"])
    call("screenshot", path=str(output / "color.png"), presented=1)
    call("screenshot", path=str(output / "stock.png"))
    tap(27,1)
    registers = call("get_registers")
    call("continue")  # Menu must itself stop simulation, without debugger pause.
    time.sleep(.2)
    assert call("get_registers") == registers, "Open menu did not pause simulation"
    call("pause")
    for _ in range(4): tap(0x28,0x50,True)
    tap(13,0x1c)
    call("screenshot", path=str(output / "menu-on.png"), host=1)
    tap(13,0x1c)
    call("screenshot", path=str(output / "menu-off.png"), host=1)
    call("screenshot", path=str(output / "disabled.png"), presented=1)
    assert (output / "disabled.png").read_bytes() == (output / "stock.png").read_bytes()
    assert "enabled = false" in (output / "mods/state.toml").read_text()
    tap(13,0x1c)
    call("screenshot", path=str(output / "reenabled.png"), presented=1)
    assert (output / "reenabled.png").read_bytes() == (output / "color.png").read_bytes()
    assert call("get_registers") == registers
    assert "enabled = true" in (output / "mods/state.toml").read_text()
    (output / "validation.json").write_text(json.dumps(dict(
        rebind="C -> native A; X inactive", menu_pauses=True,
        toggle_reversible=True, registers=registers,
        rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest()),indent=2))
    print("PASS: launcher rebind, saved settings, native input, menu pause, reversible live mod toggle")
finally:
    if process.poll() is None:
        try:
            call("quit"); process.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            process.terminate(); process.wait(timeout=10)
