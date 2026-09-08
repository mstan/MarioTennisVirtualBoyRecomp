"""Validate material coverage and capture actual color animation through TCP.
Owner ROM required. Output screenshots/source dumps are private game artwork.
"""

import argparse
import collections
import json
import socket
import struct
import subprocess
import time
from pathlib import Path
from PIL import Image
from color_capture import Client
from validation_package import install_args


def catalog(path):
    data = path.read_bytes()
    assert data[:8] == b"VBMAT002"
    count = struct.unpack_from("<I", data, 8)[0]
    assert len(data) == 12 + 7 * 1024 + 72 * count
    result = {}
    for offset in range(12 + 7 * 1024, len(data), 72):
        c, n, x, y, h = struct.unpack_from("<BBBBI", data, offset)
        assert n == 128
        result[c, x, y, h] = data[offset + 8 : offset + 72]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("exe", "rom", "package", "materials", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--characters", default="0,1,2,3,4,5,6")
    parser.add_argument("--samples", type=int, default=360)
    parser.add_argument("--port", type=int, default=4497)
    parser.add_argument("--opponent", type=int, choices=range(7))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    table = catalog(args.materials)
    client = Client(args.port)
    report = []
    try:
        with socket.create_connection(("127.0.0.1", args.port), 0.2):
            raise RuntimeError("Validation port is already in use")
    except OSError:
        pass
    for character in map(int, args.characters.split(",")):
        folder = output / f"character-{character}"
        folder.mkdir(exist_ok=True)
        config = folder / "settings.cfg"
        mods = folder / "mods"
        command = [
            str(args.exe.resolve()),
            "--rom",
            str(args.rom.resolve()),
            "--headless",
            "--paused",
            "--port",
            str(args.port),
            "--config",
            str(config),
            "--mods-dir",
            str(mods),
        ]
        command += install_args(mods, args.package.resolve())
        command += ["--enable-mod", "marios-tennis.full-color:full-color"]
        log = (folder / "runtime.log").open("wb")
        process = subprocess.Popen(
            command,
            cwd=folder,
            stdout=log,
            stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        frames = []
        coverage = []
        missing = collections.Counter()
        near_worlds = set()
        try:
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"Runtime exited; see {folder}/runtime.log")
                try:
                    if client.call("get_registers")["frame"] == 0:
                        break
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("Startup timeout")
                time.sleep(0.05)
            client.advance(180)
            for button in (4096, 4096, 256, 4096, 4096, 4096):
                client.advance(90, button)
            client.call(
                "screenshot", path=(folder / "portraits.png").as_posix(), presented=1
            )
            for _ in range(3):
                client.advance(24, 1024)
            for _ in range(character):
                client.advance(24, 256)
            client.advance(120, 4096)
            ids = struct.unpack("<4H", client.read(0x0500203A, 8))
            for extra in range(3):
                if any(ids):
                    break
                client.advance(120, 4)
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
            directions = [0, 256, 512, 2048, 1024, 256 | 2048, 512 | 1024, 0]
            for sample in range(args.samples):
                direction = directions[(sample // 12) % len(directions)]
                stroke = (4 if (sample // 10) % 2 == 0 else 8) if sample % 10 < 4 else 0
                client.call("set_input", pad=direction | stroke)
                client.advance(4)
                for eye in range(2):
                    dump = folder / "current.src"
                    client.call("source_dump", path=dump.as_posix(), eye=eye)
                    known = total = 0
                    for h, x, y, t, u, v, m, k, r, w in struct.iter_unpack(
                        "<IHHHBBBBBB", dump.read_bytes()[24:]
                    ):
                        if not w or m != 0 or x >= 512 or not 384 <= y < 512:
                            continue
                        c = ids[x // 128]
                        total += 1
                        key = (c, x % 128 // 8, (y - 384) // 8, h)
                        if x // 128 == 0:
                            near_worlds.add(w)
                        mask = table.get(key)
                        if mask and mask[v * 8 + u]:
                            known += 1
                        else:
                            missing[key] += 1
                    if total:
                        ratio = known / total
                        if ratio < min(coverage, default=1):
                            (folder / "worst.src").write_bytes(dump.read_bytes())
                            (folder / "worst.json").write_text(
                                json.dumps(
                                    dict(
                                        sample=sample,
                                        eye=eye,
                                        coverage=ratio,
                                        slots=ids,
                                    )
                                ),
                                encoding="utf-8",
                            )
                            client.call(
                                "screenshot",
                                path=(folder / "worst.png").as_posix(),
                                eye=eye,
                                presented=1,
                            )
                        coverage.append(ratio)
                    if sample % 12 == 0:
                        screenshot = folder / f"frame-{sample:04}-{eye}.png"
                        before = client.call("get_registers")
                        client.call(
                            "screenshot",
                            path=screenshot.as_posix(),
                            eye=eye,
                            presented=1,
                        )
                        assert client.call("get_registers") == before, (
                            "Screenshot advanced guest state"
                        )
                        if eye == 0:
                            frames.append(Image.open(screenshot).convert("RGB").copy())
                if sample % 60 == 0:
                    print(
                        character,
                        sample,
                        "minimum coverage",
                        round(min(coverage) * 100, 3),
                        flush=True,
                    )
            item = dict(
                character=character,
                slots=ids,
                samples=args.samples,
                eyes=2,
                minimum_coverage=min(coverage),
                mean_coverage=sum(coverage) / len(coverage),
                near_worlds=sorted(near_worlds),
                missing=[
                    dict(character=k[0], x=k[1], y=k[2], hash=f"{k[3]:08x}", pixels=v)
                    for k, v in missing.most_common()
                ],
            )
            report.append(item)
            if frames:
                frames[0].save(
                    folder / "animation.gif",
                    save_all=True,
                    append_images=frames[1:],
                    duration=180,
                    loop=0,
                )
                selected = frames[:: max(1, len(frames) // 8)][:8]
                sheet = Image.new("RGB", (384 * 4, 224 * 2))
                for i, im in enumerate(selected):
                    sheet.paste(im, (i % 4 * 384, i // 4 * 224))
                sheet.save(folder / "contact.png")
            (output / "validation.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
        finally:
            if process.poll() is None:
                try:
                    client.call("quit")
                    process.wait(timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    process.terminate()
                    process.wait(timeout=10)
            log.close()
    assert all(r["minimum_coverage"] >= 0.99 for r in report), (
        "Uncatalogued animation pixels; inspect validation.json"
    )
    print(
        "PASS: both eyes, material coverage and paused TCP screenshots; inspect saved animation/contact sheets",
        flush=True,
    )


if __name__ == "__main__":
    main()
