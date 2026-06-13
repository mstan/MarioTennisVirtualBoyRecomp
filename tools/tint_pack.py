#!/usr/bin/env python3
"""tint_pack.py — emit a debug recolor pack that tints each on-screen tile a
distinct hue, for visual identification of which content-hash = which element.

Queries the runtime's `attr_hashes` command (needs attribution active, i.e.
VBRECOMP_CAPTURE=1 or a recolor pack loaded), assigns every distinct
(hash) a unique hue, and writes <overrides_dir>/recolor/palette.json. Re-launch
the runtime with VBRECOMP_OVERRIDES=<overrides_dir> and screenshot {recolor:1}
to see every element in its own color → map hue back to element.

Usage:
  python tools/tint_pack.py OVERRIDES_DIR [--port 4390] [--eye 0] [--top 64]
"""
from __future__ import annotations
import argparse, colorsys, json, os, socket


def cmd(port, c, **kw):
    req = {"cmd": c, "id": 1}; req.update(kw)
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        s.sendall((json.dumps(req) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            ch = s.recv(65536)
            if not ch:
                break
            data += ch
    return json.loads(data.decode())


def ramp_for_hue(h):
    """4-level brightness ramp at hue h (0..1): black, then 45/72/100% value."""
    out = ["#000000"]
    for val in (0.45, 0.72, 1.0):
        r, g, b = colorsys.hsv_to_rgb(h, 0.95, val)
        out.append("#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("overrides_dir")
    ap.add_argument("--port", type=int, default=4390)
    ap.add_argument("--eye", type=int, default=0)
    ap.add_argument("--top", type=int, default=64)
    args = ap.parse_args()

    resp = cmd(args.port, "attr_hashes", eye=args.eye, top=args.top)
    tiles = resp.get("tiles", [])
    if not tiles:
        raise SystemExit("no on-screen tiles — is attribution active and a "
                         "scene drawn? (run with VBRECOMP_CAPTURE=1)")

    # distinct hashes in count order; assign evenly-spaced hues
    seen, order = set(), []
    for t in tiles:
        if t["hash"] not in seen:
            seen.add(t["hash"]); order.append(t)
    entries = []
    n = len(order)
    for i, t in enumerate(order):
        entries.append({
            "hash": t["hash"],
            "label": "tile_%s_c%d_p%d_n%d" % (t["hash"], t["char"],
                                              t["palette"], t["count"]),
            "bbox": [t["x0"], t["y0"], t["x1"], t["y1"]],
            "ramp": ramp_for_hue(i / max(1, n)),
        })

    out_dir = os.path.join(args.overrides_dir, "recolor")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "palette.json")
    with open(path, "w") as f:
        json.dump({"_comment": "DEBUG tint pack — each tile a distinct hue for "
                               "identification (tools/tint_pack.py).",
                   "entries": entries}, f, indent=2)
    print("wrote %d tinted entries -> %s" % (len(entries), path))
    for e in entries[:20]:
        print("  %s  %s  bbox=%s" % (e["hash"], e["ramp"][3], e["bbox"]))


if __name__ == "__main__":
    main()
