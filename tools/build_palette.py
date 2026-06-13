#!/usr/bin/env python3
"""build_palette.py — author/merge one scene of a scene-aware recolor pack.

Queries the runtime's `world_map` (per-world on-screen bbox) for the current
scene, classifies each VIP world by its footprint, and merges a scene entry
into <overrides_dir>/recolor/palette.json. The pack is scene-aware: each scene
carries a detection signature (the set of world indices that must be present /
absent on screen) plus its world rules. The runtime selects the first matching
scene each frame; rules are animation-stable (keyed on world index, not tile
content). Reload in the runtime (recolor_reload) to apply.

The detection signature must be given explicitly (the author knows which worlds
discriminate the scene): --detect-all 22 (and optional --detect-none 29).
Re-running with the same --scene name replaces that scene in place.

Colors reference Super Mario Wiki. Unmatched worlds stay faithful.

Usage:
  python tools/build_palette.py OVERRIDES_DIR --scene match \
      --detect-all 22 [--detect-none 29] [--port 4390] [--eye 0]
  python tools/build_palette.py OVERRIDES_DIR --scene title \
      --detect-all 25,26 --detect-none 22,29
  python tools/build_palette.py OVERRIDES_DIR --scene mode_select \
      --detect-all 29 --detect-none 22
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
    "court":    ["#000000", "#0a4018", "#1c7a30", "#34c050"],
    "skyline":  ["#000000", "#1a2240", "#34406a", "#5a6aa0"],
    "sky":      ["#000000", "#102050", "#2848a0", "#4070e0"],
    "net":      ["#000000", "#505050", "#a8a8a8", "#f4f4f4"],
    "opponent": ["#000000", "#3a2410", "#7a5020", "#b88030"],  # DK Jr. brown
    "logo":     ["#000000", "#a01800", "#e85820", "#ffd040"],  # fiery red->yellow
    "menu_text":["#000000", "#404040", "#909090", "#e8e8e8"],  # white
    "selected": ["#000000", "#806000", "#c0a000", "#ffe040"],  # yellow highlight
    "unselected":["#000000", "#404040", "#909090", "#e0e0e0"], # dim white
    "cursor":   ["#000000", "#7a0000", "#c81010", "#ff3030"],  # red
    "dim":      ["#000000", "#303030", "#606060", "#909090"],  # dim grey
    "faces":    ["#000000", "#7a4a28", "#c08850", "#f0c090"],  # warm skin (roster)
    "frame":    ["#000000", "#1a2240", "#34406a", "#5a6aa0"],  # blue frame
}

# Mario body bands by vertical fraction of the player's bbox (hi in 0..256).
MARIO_BANDS = [
    {"hi": 60,  "ramp": ["#000000", "#7a0000", "#c81010", "#ff3030"]},  # cap (red)
    {"hi": 96,  "ramp": ["#000000", "#8a5a30", "#d59a60", "#f0c090"]},  # face (skin)
    {"hi": 150, "ramp": ["#000000", "#7a0000", "#c81010", "#ff3030"]},  # shirt (red)
    {"hi": 208, "ramp": ["#000000", "#101878", "#2030b0", "#3048e0"]},  # overalls (blue)
    {"hi": 256, "ramp": ["#000000", "#3a2410", "#6a4420", "#8a5a2a"]},  # shoes (brown)
]


def classify_match(w):
    """Return ('flat', name) | ('mario', None) | None for the in-match scene."""
    if w["count"] < 24:
        return None
    cx = (w["x0"] + w["x1"]) // 2
    cy = (w["y0"] + w["y1"]) // 2
    ww = w["x1"] - w["x0"]
    hh = w["y1"] - w["y0"]
    if cy < 72 and (cx > 264 or ww > 150):
        if cx > 240 and ww < 170:
            return None
        return ("flat", "skyline")
    if cy < 72:
        return ("flat", "sky")
    if 74 <= cy <= 112 and ww > 150:
        return ("flat", "net")
    if cy >= 100 and ww > 200:
        return ("flat", "court")
    if 90 <= cx <= 290 and cy >= 96 and ww <= 150 and hh >= 24:
        return ("mario", None)
    if cy < 112 and ww <= 150:
        return ("flat", "opponent")
    return None


def classify_title(w):
    """MARIO'S TENNIS title + SINGLES/DOUBLES mode select."""
    if w["count"] < 24:
        return None
    cx = (w["x0"] + w["x1"]) // 2
    cy = (w["y0"] + w["y1"]) // 2
    ww = w["x1"] - w["x0"]
    if cy < 100 and ww > 120:
        return ("flat", "logo")           # big MARIO'S TENNIS logo
    if 108 <= cy <= 132 and ww > 120:
        return ("flat", "net")            # horizon / net line
    if cy >= 100 and ww > 200:
        return ("flat", "court")
    if ww < 40:
        return ("flat", "cursor")         # selection ball
    if cy >= 200:
        return ("flat", "dim")            # copyright
    if 140 <= cy <= 162:
        return ("flat", "selected")       # SINGLES (highlighted)
    if cy > 162:
        return ("flat", "unselected")     # DOUBLES
    return None


def classify_mode_select(w):
    """MODE / LEVEL / MATCH options + roster strip."""
    if w["count"] < 24:
        return None
    cy = (w["y0"] + w["y1"]) // 2
    ww = w["x1"] - w["x0"]
    hh = w["y1"] - w["y0"]
    if cy < 40 and ww < 120:
        return ("flat", "selected")       # MODE highlight box
    if cy >= 150 and hh < 24:
        return ("flat", "frame")          # roster frame / name row
    if cy >= 150:
        return ("flat", "faces")          # roster portraits
    return ("flat", "menu_text")          # everything else (labels/options)


CLASSIFIERS = {
    "match": classify_match,
    "title": classify_title,
    "mode_select": classify_mode_select,
}


def parse_mask(s):
    return [int(x) for x in s.split(",") if x.strip() != ""] if s else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("overrides_dir")
    ap.add_argument("--scene", default="match", choices=list(CLASSIFIERS))
    ap.add_argument("--detect-all", default="",
                    help="comma list of world indices that must all be present")
    ap.add_argument("--detect-none", default="",
                    help="comma list of world indices that must be absent")
    ap.add_argument("--port", type=int, default=4390)
    ap.add_argument("--eye", type=int, default=0)
    args = ap.parse_args()

    worlds = cmd(args.port, "world_map", eye=args.eye).get("worlds", [])
    if not worlds:
        raise SystemExit("no on-screen worlds (recolor/capture active? scene drawn?)")

    classify = CLASSIFIERS[args.scene]
    rules = []
    for w in worlds:
        kind = classify(w)
        if kind is None:
            continue
        if kind[0] == "mario":
            rules.append({"world": w["world"], "label": "mario",
                          "bbox": [w["x0"], w["y0"], w["x1"], w["y1"]],
                          "bands": MARIO_BANDS})
        else:
            name = kind[1]
            rules.append({"world": w["world"], "label": name,
                          "bbox": [w["x0"], w["y0"], w["x1"], w["y1"]],
                          "ramp": FLAT[name]})

    detect = {}
    da, dn = parse_mask(args.detect_all), parse_mask(args.detect_none)
    if da:
        detect["all"] = da
    if dn:
        detect["none"] = dn
    scene = {"name": args.scene, "detect": detect, "worlds": rules}

    out_dir = os.path.join(args.overrides_dir, "recolor")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "palette.json")
    pack = {"scenes": []}
    if os.path.exists(path):
        with open(path) as f:
            pack = json.load(f)
        if "scenes" not in pack:               # migrate legacy flat form
            pack = {"scenes": [{"name": "default", "detect": {},
                                "worlds": pack.get("worlds", [])}]}
    # replace same-named scene in place, else append
    scenes = pack["scenes"]
    for i, s in enumerate(scenes):
        if s.get("name") == args.scene:
            scenes[i] = scene
            break
    else:
        scenes.append(scene)
    pack.setdefault("_comment", "Scene-aware world recolor pack (build_palette.py); "
                                "animation-stable.")
    with open(path, "w") as f:
        json.dump(pack, f, indent=2)

    print("scene '%s' -> %d world rules (detect %s) in %s"
          % (args.scene, len(rules), detect or "always", path))
    for e in rules:
        print("  world %-2d %-10s %s" % (e["world"], e["label"],
                                         "bands" if "bands" in e else e["ramp"][3]))


if __name__ == "__main__":
    main()
