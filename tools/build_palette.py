#!/usr/bin/env python3
"""build_palette.py — author a canonical recolor pack with logic, not hand work.

Queries the runtime's `attr_hashes` for the current scene and assigns each
on-screen tile a real color ramp by rule: scene elements (sky / skyline / court
/ net / HUD) by screen region, and characters by palette + position using
canonical Mario-universe colors (refs: Super Mario Wiki). Writes
<overrides_dir>/recolor/palette.json; reload in the runtime to apply.

Rules are intentionally simple/heuristic ("use logic on what you extract") and
easy to tweak per scene via --scene. Unmatched tiles are left faithful.

Usage:
  python tools/build_palette.py OVERRIDES_DIR --scene match [--port 4390] [--eye 0]
"""
from __future__ import annotations
import argparse, json, os, socket


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


def ramp(base, dark=0.30, mid=0.62):
    """4-level ramp (value 0 transparent-ish black, then dark/mid/full)."""
    r, g, b = base
    def sc(f):
        return "#%02x%02x%02x" % (int(r * f), int(g * f), int(b * f))
    return ["#000000", sc(dark), sc(mid), sc(1.0)]


# canonical colors (0..255), refs: Super Mario Wiki
C = {
    "mario_red":   (0xE0, 0x10, 0x10),
    "mario_blue":  (0x20, 0x40, 0xD0),
    "luigi_green": (0x18, 0xB0, 0x20),
    "skin":        (0xF0, 0xC0, 0x90),
    "sky":         (0x30, 0x70, 0xE0),
    "skyline":     (0x50, 0x60, 0x90),
    "court":       (0x30, 0xA0, 0x40),
    "court_line":  (0xF0, 0xF0, 0xF0),
    "net":         (0xF0, 0xF0, 0xF0),
    "hud":         (0xF0, 0xC0, 0x20),
    "ball":        (0xF0, 0xE0, 0x40),
    "shoes":       (0x80, 0x50, 0x20),
    "opponent":    (0x8a, 0x5a, 0x2a),   # Donkey Kong Jr. brown
}


def classify_match(t):
    """Return a color name (or None = leave faithful) for a match-scene tile,
    by on-screen region. Wide tiles are scene layers; compact tiles in the
    lower-center play area are the near player, sub-colored by vertical
    position into Mario's body parts (cap/shirt red, overalls blue, shoes)."""
    cx = (t["x0"] + t["x1"]) // 2
    cy = (t["y0"] + t["y1"]) // 2
    w  = t["x1"] - t["x0"]
    h  = t["y1"] - t["y0"]

    # Leave the HUD scoreboard + player-name banner faithful (top band).
    if cy < 100 and (cx > 264 or w > 120):
        return None
    # Sky + skyline (upper background)
    if cy < 70:
        return "skyline" if w > 120 else "sky"
    # Net: thin wide band around the middle
    if 78 <= cy <= 104 and w > 150:
        return "net"
    # Court: wide tiles across the lower half
    if cy >= 100 and w > 140:
        return "court"

    # Near player (Mario): compact tiles clustered bottom-center.
    if cx >= 110 and cx <= 270 and cy >= 104 and w <= 110 and h <= 110:
        if cy < 138:  return "mario_red"     # cap + upper
        if cy < 168:  return "skin"          # face / hands band
        if cy < 192:  return "mario_blue"    # overalls
        return "shoes"
    # Far player (opponent): compact tiles upper-mid of the court
    if cy < 104 and w <= 110 and h <= 90:
        return "opponent"

    # small fast-moving compact tile high up = ball
    if w <= 24 and h <= 24:
        return "ball"
    return "court_line"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("overrides_dir")
    ap.add_argument("--scene", default="match")
    ap.add_argument("--port", type=int, default=4390)
    ap.add_argument("--eye", type=int, default=0)
    ap.add_argument("--top", type=int, default=96)
    args = ap.parse_args()

    resp = cmd(args.port, "attr_hashes", eye=args.eye, top=args.top)
    tiles = resp.get("tiles", [])
    if not tiles:
        raise SystemExit("no on-screen tiles (attribution active? scene drawn?)")

    classify = {"match": classify_match}[args.scene]
    entries, seen = [], set()
    for t in tiles:
        if t["hash"] in seen:
            continue
        seen.add(t["hash"])
        name = classify(t)
        if name is None:
            continue          # leave this tile faithful (no entry)
        entries.append({"hash": t["hash"], "label": name,
                        "bbox": [t["x0"], t["y0"], t["x1"], t["y1"]],
                        "ramp": ramp(C[name])})

    out_dir = os.path.join(args.overrides_dir, "recolor")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "palette.json"), "w") as f:
        json.dump({"_comment": "Canonical recolor pack (build_palette.py, scene=%s)."
                              % args.scene, "entries": entries}, f, indent=2)
    from collections import Counter
    print("wrote %d entries -> %s" % (len(entries), out_dir))
    print("by element:", dict(Counter(e["label"] for e in entries)))


if __name__ == "__main__":
    main()
