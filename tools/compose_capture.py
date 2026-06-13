#!/usr/bin/env python3
"""compose_capture.py — reconstruct larger composites from a vbrecomp capture.

Reads a capture directory produced by the runtime `capture_dump` TCP command
(tiles/<hash>.png + layouts/frame_*.json) and renders, per requested eye, the
OBJ tiles of one frame into a transparent 384x224 canvas at their original
relative positions — a "frame-layout sheet" that makes an assembled
metasprite (e.g. a character portrait) human-recognizable even though each
individual 8x8 tile is not.

It also offers a simple grouping heuristic that clusters OBJ uses sharing
context/parallax/proximity into candidate metasprites, prints them, and emits
a deterministic cluster_hash per group (hash over the sorted set of
(rel_x, rel_y, tile_hash, hflip, vflip, palette)).

Usage:
  python tools/compose_capture.py CAPTURE_DIR [--frame N] [--eye 0|1]
      [--scale S] [--out PATH] [--clusters] [--crop]
  # default: newest frame, eye 0, scale 4, writes <CAPTURE_DIR>/composite.png
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import zlib
import struct
import hashlib


# ---- minimal PNG reader (RGBA, 8-bit, the format png_write.c emits) ----
def read_png_rgba(path):
    with open(path, "rb") as f:
        data = f.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG: " + path
    pos = 8
    w = h = 0
    idat = b""
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            w, h, bitd, colt = struct.unpack(">IIBB", chunk[:10])
            assert bitd == 8 and colt == 6, "expected 8-bit RGBA"
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
        pos += 12 + length
    raw = zlib.decompress(idat)
    stride = w * 4
    out = bytearray(w * h * 4)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        ftype = raw[p]; p += 1
        line = bytearray(raw[p:p + stride]); p += stride
        if ftype == 0:
            pass
        elif ftype == 1:  # Sub
            for i in range(4, stride):
                line[i] = (line[i] + line[i - 4]) & 0xFF
        elif ftype == 2:  # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:  # Average
            for i in range(stride):
                a = line[i - 4] if i >= 4 else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:  # Paeth
            for i in range(stride):
                a = line[i - 4] if i >= 4 else 0
                b = prev[i]
                c = prev[i - 4] if i >= 4 else 0
                pp = a + b - c
                pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        else:
            raise ValueError("bad filter %d" % ftype)
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, bytes(out)


def write_png_rgba(path, w, h, px):
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)
        raw += px[y * stride:(y + 1) * stride]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(t, d):
        return (struct.pack(">I", len(d)) + t + d +
                struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)))
        f.write(chunk(b"IDAT", comp))
        f.write(chunk(b"IEND", b""))


def blit(dst, dw, dh, tile_px, tx, ty, hflip, vflip):
    """Alpha-over blit an 8x8 RGBA tile at (tx,ty), optionally mirrored."""
    for row in range(8):
        sy = 7 - row if vflip else row
        oy = ty + row
        if oy < 0 or oy >= dh:
            continue
        for col in range(8):
            sx = 7 - col if hflip else col
            ox = tx + col
            if ox < 0 or ox >= dw:
                continue
            si = (sy * 8 + sx) * 4
            a = tile_px[si + 3]
            if a == 0:
                continue
            di = (oy * dw + ox) * 4
            # source is opaque where alpha!=0 (tiles are 0/255), so overwrite
            dst[di:di + 4] = tile_px[si:si + 4]


def load_layout(capdir, frame):
    layouts = sorted(glob.glob(os.path.join(capdir, "layouts", "frame_*.json")))
    if not layouts:
        sys.exit("no layouts in " + capdir)
    if frame is None:
        path = layouts[-1]
    else:
        path = os.path.join(capdir, "layouts", "frame_%06d.json" % frame)
        if not os.path.exists(path):
            sys.exit("no such frame; available: " +
                     ", ".join(os.path.basename(p) for p in layouts))
    return json.load(open(path)), path


def tile_cache(capdir):
    cache = {}

    def get(h):
        if h not in cache:
            p = os.path.join(capdir, "tiles", h + ".png")
            cache[h] = read_png_rgba(p)[2] if os.path.exists(p) else None
        return cache[h]
    return get


def compose(capdir, layout, eye, scale, crop):
    dw, dh = 384, 224
    px = bytearray(dw * dh * 4)  # transparent
    get = tile_cache(capdir)
    objs = [u for u in layout["uses"]
            if u["ctx"] == "obj" and u["tile"] != "00000000"]
    visk = "vis_l" if eye == 0 else "vis_r"
    xk = "x_l" if eye == 0 else "x_r"
    drawn = 0
    minx = miny = 10 ** 9
    maxx = maxy = -10 ** 9
    for u in objs:
        if not u[visk]:
            continue
        tp = get(u["tile"])
        if tp is None:
            continue
        blit(px, dw, dh, tp, u[xk], u["y"], u["hflip"], u["vflip"])
        drawn += 1
        minx = min(minx, u[xk]); maxx = max(maxx, u[xk] + 8)
        miny = min(miny, u["y"]); maxy = max(maxy, u["y"] + 8)
    if scale != 1:
        sw, sh = dw * scale, dh * scale
        sp = bytearray(sw * sh * 4)
        for y in range(sh):
            for x in range(sw):
                si = ((y // scale) * dw + (x // scale)) * 4
                di = (y * sw + x) * 4
                sp[di:di + 4] = px[si:si + 4]
        px, dw, dh = sp, sw, sh
        minx *= scale; miny *= scale; maxx *= scale; maxy *= scale
    bbox = (minx, miny, maxx, maxy) if drawn else None
    return px, dw, dh, drawn, bbox


def make_clusters(layout):
    """Group OBJ uses by (context, parallax bucket, proximity). Returns list
    of clusters with a deterministic cluster_hash."""
    objs = [u for u in layout["uses"]
            if u["ctx"] == "obj" and u["tile"] != "00000000"]
    # bucket by parallax (x_r - x_l) then flood by 16px proximity
    clusters = []
    used = [False] * len(objs)
    for i, u in enumerate(objs):
        if used[i]:
            continue
        par = u["x_r"] - u["x_l"]
        group = [i]
        used[i] = True
        changed = True
        while changed:
            changed = False
            for j, v in enumerate(objs):
                if used[j] or (v["x_r"] - v["x_l"]) != par:
                    continue
                for gi in group:
                    g = objs[gi]
                    if (abs(v["x_l"] - g["x_l"]) <= 16 and
                            abs(v["y"] - g["y"]) <= 16):
                        group.append(j); used[j] = True; changed = True
                        break
        members = [objs[k] for k in group]
        ax = min(m["x_l"] for m in members)
        ay = min(m["y"] for m in members)
        key = sorted((m["x_l"] - ax, m["y"] - ay, m["tile"],
                      m["hflip"], m["vflip"], m["palette"]) for m in members)
        ch = hashlib.sha1(repr(key).encode()).hexdigest()[:12]
        clusters.append({"cluster_hash": ch, "anchor_x": ax, "anchor_y": ay,
                         "parallax": par, "count": len(members),
                         "members": members})
    clusters.sort(key=lambda c: -c["count"])
    return clusters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capdir")
    ap.add_argument("--frame", type=int, default=None)
    ap.add_argument("--eye", type=int, default=0, choices=(0, 1))
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--out", default=None)
    ap.add_argument("--clusters", action="store_true")
    args = ap.parse_args()

    layout, path = load_layout(args.capdir, args.frame)
    print("frame", layout["frame"], "from", os.path.basename(path),
          "use_count", layout.get("use_count"))

    px, dw, dh, drawn, bbox = compose(args.capdir, layout, args.eye,
                                      args.scale, True)
    out = args.out or os.path.join(args.capdir,
                                   "composite_f%06d_eye%d.png" %
                                   (layout["frame"], args.eye))
    write_png_rgba(out, dw, dh, px)
    print("composited %d OBJ tiles -> %s (bbox %s)" % (drawn, out, bbox))

    if args.clusters:
        cl = make_clusters(layout)
        print("\n%d clusters:" % len(cl))
        for c in cl[:20]:
            print("  hash=%s n=%-3d anchor=(%d,%d) parallax=%d" %
                  (c["cluster_hash"], c["count"], c["anchor_x"],
                   c["anchor_y"], c["parallax"]))


if __name__ == "__main__":
    main()
