"""Capture original sprite poses through the dev game's TCP server (owner ROM required).
The private output contains decoded game art and must not be committed.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
from PIL import Image, ImageDraw


class Client:
    def __init__(self, port):
        self.port = port

    def call(self, cmd, **values):
        with socket.create_connection(("127.0.0.1", self.port), 10) as sock:
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

    def advance(self, frames, button=None):
        if button is not None:
            self.call("press", buttons=button, frames=6)
        target = self.call("run_frames", frames=frames)["target"]
        deadline = time.monotonic() + 30
        while self.call("get_registers")["frame"] < target:
            if time.monotonic() > deadline:
                raise RuntimeError("frame timeout")
            time.sleep(0.002)

    def read(self, address, size):
        return b"".join(
            bytes.fromhex(
                self.call("read_ram", addr=address + i, len=min(4096, size - i))["hex"]
            )
            for i in range(0, size, 4096)
        )


def fnv(data):
    h = 2166136261
    for b in data:
        h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return h


def capture_portraits(client, output):
    chars = client.read(0x78000, 32768)
    cells = struct.unpack("<4096H", client.read(0x22000, 8192))
    portraits = []
    for c in range(7):
        pixels = []
        for y in range(32):
            for x in range(32):
                xx = c * 48 + x
                yy = 48 + y
                desc = cells[yy // 8 * 64 + xx // 8]
                u = (xx & 7) ^ (7 if desc & 8192 else 0)
                v = (yy & 7) ^ (7 if desc & 4096 else 0)
                pixels.append(
                    (
                        struct.unpack_from("<H", chars, (desc & 2047) * 16 + v * 2)[0]
                        >> (u * 2)
                    )
                    & 3
                )
        portraits.append(pixels)
    (output / "portraits.json").write_text(json.dumps(portraits), encoding="utf-8")


def collect(client, output, seen):
    ids = struct.unpack("<4H", client.read(0x0500203A, 8))
    capture = output.parent / "current.src"
    visible = [{} for _ in range(4)]
    for eye in (0, 1):
        client.call("source_dump", path=capture.as_posix(), eye=eye)
        sources = struct.iter_unpack("<IHHHBBBBBB", capture.read_bytes()[24:])
        for h, x, y, t, u, v, m, k, r, w in sources:
            if w and m == 0 and 384 <= y < 512 and x < 512:
                visible[x // 128][(x % 128, y - 384)] = (h, u, v, r)
    chr_data = client.read(0x78000, 32768)
    byhash = {
        fnv(chr_data[t : t + 16]): chr_data[t : t + 16] for t in range(0, 32768, 16)
    }
    for slot, character in enumerate(ids):
        if character > 6 or len(visible[slot]) < 20:
            continue
        for size in (128,):
            pixels = bytearray(size * size)
            tiles = []
            for ty in range(size // 8):
                for tx in range(size // 8):
                    samples = [
                        (x, y, visible[slot][x, y])
                        for y in range(ty * 8, ty * 8 + 8)
                        for x in range(tx * 8, tx * 8 + 8)
                        if (x, y) in visible[slot]
                    ]
                    if not samples:
                        continue
                    x, y, (h, u, v, r) = samples[0]
                    hflip = (x % 8) != u
                    vflip = (y % 8) != v
                    raw = byhash.get(h)
                    rows = struct.unpack("<8H", raw) if raw is not None else (0,) * 8
                    tiles.append([tx, ty, h, hflip, vflip])
                    for y in range(8):
                        for x in range(8):
                            pixels[(ty * 8 + y) * size + tx * 8 + x] = (
                                rows[y ^ (7 if vflip else 0)]
                                >> (2 * (x ^ (7 if hflip else 0)))
                            ) & 3
                    # Source records retain displayed raw texels even when the
                    # guest has already replaced that CHR tile for its next pose.
                    for x, y, (_, u, v, r) in samples:
                        pixels[y * size + x] = r
            if sum(bool(p) for p in pixels) < 15:
                continue
            identity = pixels + json.dumps(tiles, separators=(",", ":")).encode()
            key = f"c{character}-{size}-{hashlib.sha256(identity).hexdigest()[:16]}"
            if key in seen:
                continue
            seen.add(key)
            data = dict(
                character=character,
                size=size,
                pixels=base64.b64encode(pixels).decode(),
                tiles=tiles,
            )
            temporary = output / (key + f".{os.getpid()}.tmp")
            temporary.write_text(json.dumps(data), encoding="utf-8")
            temporary.replace(output / (key + ".json"))
            shades = [0, 255, 170, 85]
            Image.frombytes("L", (size, size), bytes(shades[p] for p in pixels)).save(
                output / (key + ".png")
            )


def sheets(output):
    for character in range(7):
        for size in (128,):
            paths = sorted(output.glob(f"c{character}-{size}-*.png"))
            if not paths:
                continue
            sheet = Image.new(
                "RGB", (8 * 144, ((len(paths) + 7) // 8) * 150), (28, 32, 40)
            )
            draw = ImageDraw.Draw(sheet)
            for i, p in enumerate(paths):
                x = (i % 8) * 144
                y = (i // 8) * 150
                im = Image.open(p).resize((128, 128), Image.Resampling.NEAREST)
                sheet.paste(im, (x, y))
                draw.text((x, y + 130), f"{i}: {p.stem[-5:]}", fill="white")
            sheet.save(output.parent / f"sheet-c{character}-{size}.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exe", type=Path)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--characters", default="0,1,2,3,4,5,6")
    parser.add_argument("--samples", type=int, default=220)
    parser.add_argument("--frame-step", type=int, default=4)
    parser.add_argument("--port", type=int, default=4495)
    parser.add_argument("--opponent", type=int, choices=range(7))
    args = parser.parse_args()
    output = args.output.resolve()
    poses = output / "poses"
    poses.mkdir(parents=True, exist_ok=True)
    seen = {p.stem for p in poses.glob("*.json")}
    client = Client(args.port)
    for character in map(int, args.characters.split(",")):
        process = subprocess.Popen(
            [
                str(args.exe.resolve()),
                "--rom",
                str(args.rom.resolve()),
                "--headless",
                "--paused",
                "--port",
                str(args.port),
                "--config",
                str(output / "settings.cfg"),
                "--mods-dir",
                str(output / "mods"),
            ],
            cwd=output,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            for _ in range(200):
                if process.poll() is not None:
                    raise RuntimeError("Runtime exited")
                try:
                    client.call("get_registers")
                    break
                except OSError:
                    time.sleep(0.05)
            client.advance(180)
            for b in (4096, 4096, 256, 4096, 4096, 4096):
                client.advance(90, b)
            client.call(
                "screenshot", path=(output / f"select-{character}.png").as_posix()
            )
            if not (output / "portraits.json").exists():
                capture_portraits(client, output)
            for _ in range(3):
                client.advance(24, 1024)
            for _ in range(character):
                client.advance(24, 256)
            client.call(
                "screenshot", path=(output / f"chosen-{character}.png").as_posix()
            )
            client.advance(120, 4096)
            client.call(
                "screenshot", path=(output / f"started-{character}.png").as_posix()
            )
            ids = struct.unpack("<4H", client.read(0x0500203A, 8))
            for extra in range(3):
                if any(ids):
                    break
                client.advance(120, 4)
                client.call(
                    "screenshot",
                    path=(output / f"extra-{character}-{extra}.png").as_posix(),
                )
                if extra == 0 and args.opponent is not None:
                    if args.opponent == character:
                        raise ValueError("Choose a different opponent")
                    cursor = character + 1 if character < 6 else 5
                    while cursor != args.opponent:
                        client.advance(24, 512)
                        cursor = (cursor - 1) % 7
                        if cursor == character:
                            cursor = (cursor - 1) % 7
                ids = struct.unpack("<4H", client.read(0x0500203A, 8))
            assert ids[0] == character, ids
            if args.opponent is not None:
                assert ids[3] == args.opponent, ids
            print("character", character, "slots", ids, flush=True)
            (output / f"slots-{character}.json").write_text(
                json.dumps(ids), encoding="utf-8"
            )
            # Run, serve, swing forehand/backhand and move both axes. Repeated
            # strokes exercise animation while the CPU opponent responds normally.
            directions = [0, 256, 512, 2048, 1024, 256 | 2048, 512 | 1024, 0]
            for sample in range(args.samples):
                direction = directions[(sample // 12) % len(directions)]
                stroke = (4 if (sample // 10) % 2 == 0 else 8) if sample % 10 < 4 else 0
                client.call("set_input", pad=direction | stroke)
                client.advance(args.frame_step)
                collect(client, poses, seen)
                if sample % 40 == 0:
                    print("sample", sample, "unique poses", len(seen), flush=True)
                    client.call(
                        "screenshot",
                        path=(output / f"play-{character}-{sample}.png").as_posix(),
                    )
                    client.call(
                        "source_dump",
                        path=(output / f"play-{character}-{sample}.src").as_posix(),
                    )
        finally:
            if process.poll() is None:
                try:
                    client.call("quit")
                    process.wait(timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    process.terminate()
                    process.wait(timeout=10)
        sheets(poses)
    print("Captured", len(seen), "unique character/LOD poses", flush=True)


if __name__ == "__main__":
    main()
