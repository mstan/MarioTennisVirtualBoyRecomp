"""Owner-ROM integration check: deterministic stock/color A/B and both eyes.

Usage: python tools/validate_color.py EXE ROM VBMOD OUTPUT_DIR
Requires a debug-tools build. Never writes to the supplied ROM.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import zipfile

exe, rom, package, output = map(lambda p: Path(p).resolve(), sys.argv[1:])
output.mkdir(parents=True, exist_ok=True)
port = 4491
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
rom_before = digest(rom)


def call(cmd, **values):
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall((json.dumps(dict(cmd=cmd, **values)) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(1048576)
            if not chunk:
                raise RuntimeError("Debugger disconnected")
            data += chunk
    reply = json.loads(data)
    if not reply.get("ok"):
        raise RuntimeError(reply)
    return reply


def advance(frames, button=None):
    if button is not None:
        call("press", buttons=button, frames=6)
    target = call("run_frames", frames=frames)["target"]
    deadline = time.monotonic() + 30
    while call("get_registers")["frame"] < target:
        if time.monotonic() > deadline:
            raise RuntimeError("Guest did not reach frame target")
        time.sleep(.02)


def run(name, enabled, archive=package):
    folder = output / name
    folder.mkdir(exist_ok=True)
    args = [str(exe), "--rom", str(rom), "--headless", "--paused", "--port", str(port),
            "--mods-dir", str(folder / "mods"), "--config", str(folder / "settings.cfg")]
    if not (folder / "mods/packages/marios-tennis.full-color/0.1.0").exists():
        args += ["--install-mod", str(archive)]
    args += ["--enable-mod" if enabled else "--disable-mod", "marios-tennis.full-color:full-color"]
    env = os.environ.copy()
    # Legacy experimental overrides are not part of the package renderer.
    env.pop("VBRECOMP_OVERRIDES", None)
    env["VBRECOMP_CAPTURE"] = "1"
    process = subprocess.Popen(args, cwd=folder, env=env,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        deadline = time.monotonic() + 20
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"Runtime exited: {process.returncode}")
            try:
                if call("get_registers")["frame"] == 0:
                    break
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError("Debugger startup timeout")
            time.sleep(.05)
        advance(180)
        for button in [4096, 4096, 256, 4096, 4096]:
            advance(90, button)
        call("screenshot", path=str(folder / "title.png"), presented=1)
        for _ in range(2):
            advance(120, 4096)
        worlds = call("world_map")["worlds"]
        assert any(w["world"] == 22 for w in worlds), worlds
        (folder / "worlds.json").write_text(json.dumps([call("world_map",eye=e) for e in range(2)],indent=2))
        registers = call("get_registers")
        ram = bytes.fromhex("".join(call("read_ram", addr=0x05000000+i, len=4096)["hex"]
                                   for i in range(0,65536,4096)))
        (folder / "wram.bin").write_bytes(ram)
        for eye in range(2):
            call("screenshot", path=str(folder / f"stock-{eye}.png"), eye=eye)
            call("screenshot", path=str(folder / f"presented-{eye}.png"), eye=eye, presented=1)
        assert call("get_registers") == registers, "Presentation advanced guest state"
        (folder / "registers.json").write_text(json.dumps(registers, indent=2))
        # Continue play to cover moving player/ball and guest frame hooks.
        advance(60, 4)
        advance(60, 4)
        advance(90, 256)
        (folder / "rally-worlds.json").write_text(json.dumps([call("world_map",eye=e) for e in range(2)],indent=2))
        registers_after = call("get_registers")
        ram_after = bytes.fromhex("".join(call("read_ram", addr=0x05000000+i, len=4096)["hex"]
                                         for i in range(0,65536,4096)))
        call("screenshot", path=str(folder / "rally.png"), presented=1)
        return dict(registers=registers, wram=hashlib.sha256(ram).hexdigest(),
                    after=registers_after, after_wram=hashlib.sha256(ram_after).hexdigest(),
                    raw=[digest(folder / f"stock-{eye}.png") for eye in range(2)])
    finally:
        if process.poll() is None:
            try:
                call("quit")
                process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                # This process was created by this test and owns no Ghidra data.
                process.terminate()
                process.wait(timeout=10)


stock = run("disabled", False)
color = run("enabled", True)
assert stock == color, "Color changed guest state or native output"
for eye in range(2):
    assert digest(output / "disabled" / f"presented-{eye}.png") == stock["raw"][eye]
    assert digest(output / "enabled" / f"presented-{eye}.png") != stock["raw"][eye]
assert digest(rom) == rom_before
# A data-only palette variant must change presentation through the same trusted
# renderer, without a new executable or ROM changes. Use an isolated catalog.
variant = output / "palette-variant.vbmod"
with zipfile.ZipFile(package) as source, zipfile.ZipFile(variant, "w", zipfile.ZIP_DEFLATED) as target:
    for entry in source.infolist():
        data = source.read(entry.filename)
        if entry.filename == "palette.txt":
            data = data.replace(b"sky 64bfea", b"sky ef65cc")
        target.writestr(entry.filename, data)
palette_variant = run("palette-variant", True, variant)
assert palette_variant == stock
assert digest(output / "palette-variant/presented-0.png") != digest(output / "enabled/presented-0.png")
(output / "validation.json").write_text(json.dumps(dict(rom_sha256=rom_before, identical_guest=stock), indent=2))
print("PASS: both eyes and data-only palette variant recolored; ROM, native output, WRAM, registers and subsequent play unchanged")
