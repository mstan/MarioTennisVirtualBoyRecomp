#!/usr/bin/env python3
"""build_palette.py — author a world-based recolor pack (animation-stable).

Queries the runtime's `world_map` (per-world on-screen bbox) for the current
scene, classifies each VIP world by its footprint (sky / skyline / court / net /
HUD / near-player / opponent), and emits <overrides_dir>/recolor/palette.json:
scene layers get a flat canonical ramp; characters get vertical "body bands"
(cap / face / shirt / overalls / shoes) so the whole character is colored
consistently across every animation frame (world index is stable; tiles are
not). Reload in the runtime (recolor_reload) to apply.

Colors reference Super Mario Wiki. Unmatched worlds stay faithful.

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


# Flat element ramps (value 0 = black, then 3 brightness shades).
FLAT = {
    "court":   ["#000000", "#0a4018", "#1c7a30", "#34c050"],
    "skyline": ["#000000", "#1a2240", "#34406a", "#5a6aa0"],
    "sky":     ["#000000", "#102050", "#2848a0", "#4070e0"],
    "net":     ["#000000", "#505050", "#a8a8a8", "#f4f4f4"],
    "opponent":["#000000", "#3a2410", "#7a5020", "#b88030"],   # DK Jr. brown
}

# Mario body bands by vertical fraction of the player's bbox (hi in 0..256).
MARIO_BANDS = [
    {"hi": 60,  "ramp": ["#000000", "#7a0000", "#c81010", "#ff3030"]},  # cap (red)
    {"hi": 96,  "ramp": ["#000000", "#8a5a30", "#d59a60", "#f0c090"]},  # face (skin)
    {"hi": 150, "ramp": ["#000000", "#7a0000", "#c81010", "#ff3030"]},  # shirt (red)
    {"hi": 208, "ramp": ["#000000", "#101878", "#2030b0", "#3048e0"]},  # overalls (blue)
    {"hi": 256, "ramp": ["#000000", "#3a2410", "#6a4420", "#8a5a2a"]},  # shoes (brown)
]


def classify(w):
    """Return ('flat', name) | ('mario', None) | None (leave faithful)."""
    if w["count"] < 24:
        return None
    cx = (w["x0"] + w["x1"]) // 2
    cy = (w["y0"] + w["y1"]) // 2
    ww = w["x1"] - w["x0"]
    hh = w["y1"] - w["y0"]

    # HUD scoreboard / banner (top, right or wide) — leave faithful.
    if cy < 72 and (cx > 264 or ww > 150):
        # sky/skyline is wide too; distinguish: HUD is small-area, top-right
        if cx > 240 and ww < 170:
            return None
        return ("flat", "skyline")
    if cy < 72:
        return ("flat", "sky")
    if 74 <= cy <= 112 and ww > 150:
        return ("flat", "net")
    if cy >= 100 and ww > 200:
        return ("flat", "court")
    # near player: compact, lower-center
    if 90 <= cx <= 290 and cy >= 96 and ww <= 150 and hh >= 24:
        return ("mario", None)
    # far player: compact, upper-mid
    if cy < 112 and ww <= 150:
        return ("flat", "opponent")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("overrides_dir")
    ap.add_argument("--scene", default="match")
    ap.add_argument("--port", type=int, default=4390)
    ap.add_argument("--eye", type=int, default=0)
    args = ap.parse_args()

    worlds = cmd(args.port, "world_map", eye=args.eye).get("worlds", [])
    if not worlds:
        raise SystemExit("no on-screen worlds (attribution active? scene drawn?)")

    entries = []
    for w in worlds:
        kind = classify(w)
        if kind is None:
            continue
        if kind[0] == "mario":
            entries.append({"world": w["world"], "label": "mario",
                            "bbox": [w["x0"], w["y0"], w["x1"], w["y1"]],
                            "bands": MARIO_BANDS})
        else:
            name = kind[1]
            entries.append({"world": w["world"], "label": name,
                            "bbox": [w["x0"], w["y0"], w["x1"], w["y1"]],
                            "ramp": FLAT[name]})

    out_dir = os.path.join(args.overrides_dir, "recolor")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "palette.json"), "w") as f:
        json.dump({"_comment": "World-based recolor pack (build_palette.py, scene=%s); "
                              "animation-stable." % args.scene,
                   "worlds": entries}, f, indent=2)
    print("wrote %d world rules -> %s" % (len(entries), out_dir))
    for e in entries:
        print("  world %-2d %-9s %s" % (e["world"], e["label"],
                                        "bands" if "bands" in e else e["ramp"][3]))


if __name__ == "__main__":
    main()
