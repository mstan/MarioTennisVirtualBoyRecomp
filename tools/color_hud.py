"""Author Lakitu materials from private VBSRC001 captures; export labels only."""

import argparse
import collections
from pathlib import Path
import struct

from color_materials import INK, WHITE, YELLOW, GREEN, BROWN, RACKET


def material(x, y, raw):
    # Coordinates in the original scoreboard artwork, before world movement,
    # eye displacement or flipping. Fingerprints restrict these annotations
    # to the reviewed source tiles, never arbitrary pixels in the HUD box.
    if raw == 3:
        return INK
    if 48 <= x < 64:
        return WHITE if x in (52, 53, 58, 59) else BROWN
    if x >= 64:
        x = 111 - x  # Separately stored opposite-facing referee artwork.
    if x >= 58:
        return WHITE if raw == 1 else RACKET
    if y >= 17:
        return WHITE if raw == 1 else RACKET | 96
    if x >= 44 and y < 8:
        return BROWN
    if x < 30 and y >= 10:
        return GREEN if raw == 1 else GREEN | 32
    if 31 <= x <= 39 and 7 <= y <= 11:
        return WHITE if raw == 1 else RACKET
    return YELLOW if raw == 1 else YELLOW | 32


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("sources", nargs="+", type=Path)
    args = parser.parse_args()
    records = collections.defaultdict(lambda: bytearray(64))
    for path in args.sources:
        data = path.read_bytes()
        if data[:8] != b"VBSRC001" or len(data) != 24 + 384 * 224 * 16:
            raise ValueError(f"Invalid source capture: {path}")
        for h, x, y, tile, u, v, m, k, raw, world in struct.iter_unpack(
            "<IHHHBBBBBB", data[24:]
        ):
            if world and m == 1 and k == 0 and 16 <= x < 112 and y < 35:
                records[x // 8, y // 8, h][v * 8 + u] = material(x, y, raw)
    # Reuse the checked material container; character 0 is the HUD namespace
    # in this separate asset. Portraits are unused and intentionally empty.
    with args.output.open("wb") as out:
        out.write(b"VBMAT002" + struct.pack("<I", len(records)))
        out.write(bytes(7 * 1024))
        for (x, y, h), mask in sorted(records.items()):
            out.write(struct.pack("<BBBBI", 0, 128, x, y, h) + mask)
    print(f"Lakitu material tiles: {len(records)}")


if __name__ == "__main__":
    main()
