#!/usr/bin/env python3
"""colorize_tiles.py — author a colored override pack from a capture.

Reads a vbrecomp capture directory, selects the OBJ tiles that make up a
chosen text line (by screen-Y band) in a chosen frame, recolors each tile's
lit 2bpp pixels into a Mario red/yellow palette, and writes:

  overrides/graphics/<hash>.png      RGBA, stored-block deflate (so the
                                     runtime's self-contained png_read.c reads
                                     it with no zlib dependency)
  overrides/graphics/manifest.json   one replacement per distinct tile, keyed
                                     by content hash

This is a deliberately reproducible, programmatic colorization (no external
image model) to prove the replacement pipeline. The same manifest can later
point `image` at an externally-authored / AI-generated PNG instead.

Usage:
  python tools/colorize_tiles.py CAPTURE_DIR OVERRIDES_DIR
      [--frame N] [--y-band LO HI] [--all]
  # default: newest frame, y-band 36..44 (the "MARIO 0" scoreboard line)
"""
from __future__ import annotations
import argparse, glob, json, os, struct, sys, zlib

# 2bpp value -> RGBA. Value 0 is transparent (matches OBJ value-0 = clear).
# 1/2/3 -> Mario dark-red / red / yellow, giving colored letters with hilites.
PALETTE = {
    0: (0, 0, 0, 0),
    1: (140, 0, 0, 255),
    2: (220, 32, 32, 255),
    3: (255, 208, 40, 255),
}


def write_png_stored(path, w, h, rgba):
    """Write an 8-bit RGBA PNG whose IDAT uses only stored (uncompressed)
    deflate blocks — the format runtime/src/png_read.c parses."""
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter None
        raw += rgba[y * w * 4:(y + 1) * w * 4]
    # zlib stream: header + stored blocks + adler32
    body = bytearray([0x78, 0x01])
    MAX = 65535
    i, n = 0, len(raw)
    while True:
        blk = raw[i:i + MAX]
        i += len(blk)
        final = 1 if i >= n else 0
        body.append(final)
        body += struct.pack("<H", len(blk))
        body += struct.pack("<H", (~len(blk)) & 0xFFFF)
        body += blk
        if final:
            break
    body += struct.pack(">I", zlib.adler32(bytes(raw)))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + \
            struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)))
        f.write(chunk(b"IDAT", bytes(body)))
        f.write(chunk(b"IEND", b""))


def decode_2bpp(pixels16):
    """16 raw bytes -> 8x8 list of 2bpp values (low bits = leftmost px)."""
    out = []
    for row in range(8):
        bits = pixels16[row * 2] | (pixels16[row * 2 + 1] << 8)
        out.append([(bits >> (x * 2)) & 3 for x in range(8)])
    return out


def colorize(values):
    rgba = bytearray(8 * 8 * 4)
    for y in range(8):
        for x in range(8):
            r, g, b, a = PALETTE[values[y][x]]
            i = (y * 8 + x) * 4
            rgba[i:i + 4] = bytes((r, g, b, a))
    return rgba


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capdir")
    ap.add_argument("overrides_dir")
    ap.add_argument("--frame", type=int, default=None)
    ap.add_argument("--y-band", type=int, nargs=2, default=[36, 44])
    ap.add_argument("--all", action="store_true",
                    help="colorize every OBJ tile in the frame, not just the band")
    args = ap.parse_args()

    layouts = sorted(glob.glob(os.path.join(args.capdir, "layouts", "frame_*.json")))
    if not layouts:
        sys.exit("no layouts in " + args.capdir)
    path = (layouts[-1] if args.frame is None
            else os.path.join(args.capdir, "layouts", "frame_%06d.json" % args.frame))
    layout = json.load(open(path))
    lo, hi = args.y_band

    sel = {}
    for u in layout["uses"]:
        if u["ctx"] != "obj" or u["tile"] == "00000000":
            continue
        if not args.all and not (lo <= u["y"] <= hi):
            continue
        sel[u["tile"]] = u  # distinct by content hash

    gfx = os.path.join(args.overrides_dir, "graphics")
    os.makedirs(gfx, exist_ok=True)

    reps = []
    for h, u in sorted(sel.items()):
        tj = os.path.join(args.capdir, "tiles", h + ".json")
        if not os.path.exists(tj):
            print("skip (no tile json):", h); continue
        pixels = json.load(open(tj))["pixels_2bpp"]
        rgba = colorize(decode_2bpp(pixels))
        write_png_stored(os.path.join(gfx, h + ".png"), 8, 8, rgba)
        reps.append({"id": "tile_%s" % h,
                     "match": {"tile_hash": h},
                     "image": "%s.png" % h,
                     "anchor_x": 0, "anchor_y": 0})

    manifest = {
        "_comment": "Colored override pack (experiment). Faithful by default; "
                    "active only when VBRECOMP_OVERRIDES points at this "
                    "overrides/ dir. Each entry recolors one captured OBJ tile "
                    "by content hash.",
        "source_frame": layout["frame"],
        "replacements": reps,
    }
    with open(os.path.join(gfx, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print("wrote %d colored tiles + manifest -> %s" % (len(reps), gfx))
    print("hashes:", ", ".join(sorted(sel)))


if __name__ == "__main__":
    main()
