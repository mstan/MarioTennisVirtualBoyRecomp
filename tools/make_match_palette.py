#!/usr/bin/env python3
"""make_match_palette.py — emit the full scene-aware recolor pack for Mario's
Tennis (overrides/recolor/palette.json), deterministically.

The in-match near player is always VIP world 22 regardless of which character
was chosen, so world-keying alone can't tell Mario from Luigi. P1's selected
character is held in WRAM at PLAYER_CHAR_ADDR (0..6, found by diffing in-match
WRAM across characters; verified Mario=0, Luigi=1, Princess=2, Yoshi=3 against
the on-screen "X vs Y" intro). Each character gets its own match scene gated by
a ram predicate {"addr": PLAYER_CHAR_ADDR, "eq": index}; the runtime reads the
byte each frame and selects the matching scene. A generic Mario-colored match
scene (no ram predicate) is emitted last as a fallback for any unknown index.

The non-player layers (court / sky / skyline / opponent) are identical across
characters, so they're defined once here and repeated into every match scene
(each scene must be self-contained — only one is active per frame). The title
and mode_select scenes are emitted unchanged.

Colors reference Super Mario Wiki character palettes. Band fractions (hi in
0..256, vertical position within the player's on-screen bbox) approximate
cap/face/torso/legs/feet; refine per character as needed.

Usage:  python tools/make_match_palette.py [overrides_dir]
"""
from __future__ import annotations
import json, os, sys

PLAYER_CHAR_ADDR = "0x0500203A"   # WRAM: P1 selected character index 0..6

# Shared in-match scenery (same for every character).
MATCH_SCENERY = [
    {"world": 30, "label": "skyline", "ramp": ["#000000", "#1a2240", "#34406a", "#5a6aa0"]},
    {"world": 28, "label": "court",   "ramp": ["#000000", "#0a4018", "#1c7a30", "#34c050"]},
    {"world": 21, "label": "sky",     "ramp": ["#000000", "#102050", "#2848a0", "#4070e0"]},
    {"world": 20, "label": "opponent","ramp": ["#000000", "#3a2410", "#7a5020", "#b88030"]},
    {"world": 19, "label": "opponent","ramp": ["#000000", "#3a2410", "#7a5020", "#b88030"]},
    {"world": 26, "label": "opponent","ramp": ["#000000", "#3a2410", "#7a5020", "#b88030"]},
]

# Per-character world-22 vertical body bands (cap/face/torso/legs/feet).
RED    = ["#000000", "#7a0000", "#c81010", "#ff3030"]
SKIN   = ["#000000", "#8a5a30", "#d59a60", "#f0c090"]
BLUE   = ["#000000", "#101878", "#2030b0", "#3048e0"]
BROWN  = ["#000000", "#3a2410", "#6a4420", "#8a5a2a"]
GREEN  = ["#000000", "#0a5a18", "#18a030", "#30d048"]
NAVY   = ["#000000", "#0a1858", "#1828a0", "#2840d0"]
BLONDE = ["#000000", "#806000", "#d0a830", "#f0d860"]
PINK   = ["#000000", "#a02858", "#e060a0", "#ff90c8"]
CREAM  = ["#000000", "#806040", "#c0a070", "#f0e0b0"]
ORANGE = ["#000000", "#8a3a00", "#d06010", "#ff8020"]
WHITE  = ["#000000", "#505050", "#a8a8a8", "#f4f4f4"]
YELLOW = ["#000000", "#806000", "#c0a000", "#f0d020"]

# (index, name, [ (hi, ramp), ... ])
CHARACTERS = [
    (0, "mario", [(60, RED), (96, SKIN), (150, RED), (208, BLUE), (256, BROWN)]),
    (1, "luigi", [(60, GREEN), (96, SKIN), (150, GREEN), (208, NAVY), (256, BROWN)]),
    (2, "princess", [(50, BLONDE), (90, SKIN), (210, PINK), (256, SKIN)]),
    (3, "yoshi", [(45, GREEN), (80, CREAM), (150, GREEN), (200, RED), (256, ORANGE)]),
    (4, "toad", [(70, WHITE), (100, SKIN), (150, BLUE), (210, WHITE), (256, BROWN)]),
    (5, "koopa", [(55, YELLOW), (90, YELLOW), (200, GREEN), (256, YELLOW)]),
    (6, "dkjr", [(55, BROWN), (95, CREAM), (256, BROWN)]),
]


def match_scene(index, name, bands):
    rules = list(MATCH_SCENERY)
    rules.append({"world": 22, "label": name,
                  "bands": [{"hi": hi, "ramp": ramp} for hi, ramp in bands]})
    return {"name": "match_" + name,
            "detect": {"all": [22], "ram": {"addr": PLAYER_CHAR_ADDR, "eq": index}},
            "worlds": rules}


def build():
    scenes = [match_scene(i, n, b) for i, n, b in CHARACTERS]
    # fallback: any unknown P1 index still gets a colored (Mario) match
    fallback = match_scene(0, "mario", CHARACTERS[0][2])
    fallback["name"] = "match"
    fallback["detect"] = {"all": [22]}
    scenes.append(fallback)
    # mode_select + title (unchanged layouts)
    scenes.append({
        "name": "mode_select", "detect": {"all": [29], "none": [22]},
        "worlds": [
            {"world": 31, "label": "menu_text", "ramp": ["#000000", "#404040", "#909090", "#e8e8e8"]},
            {"world": 28, "label": "mode_box",  "ramp": ["#000000", "#806000", "#c0a000", "#ffe040"]},
            {"world": 29, "label": "roster_frame", "ramp": ["#000000", "#1a2240", "#34406a", "#5a6aa0"]},
            {"world": 30, "label": "roster_faces", "ramp": ["#000000", "#7a4a28", "#c08850", "#f0c090"]},
        ]})
    scenes.append({
        "name": "title", "detect": {"all": [25, 26], "none": [22, 29]},
        "worlds": [
            {"world": 28, "label": "logo",     "ramp": ["#000000", "#a01800", "#e85820", "#ffd040"]},
            {"world": 31, "label": "court",    "ramp": ["#000000", "#0a4018", "#1c7a30", "#34c050"]},
            {"world": 30, "label": "net",      "ramp": ["#000000", "#505050", "#a8a8a8", "#f4f4f4"]},
            {"world": 26, "label": "singles",  "ramp": ["#000000", "#806000", "#c0a000", "#ffe040"]},
            {"world": 25, "label": "doubles",  "ramp": ["#000000", "#404040", "#909090", "#e0e0e0"]},
            {"world": 24, "label": "cursor",   "ramp": ["#000000", "#7a0000", "#c81010", "#ff3030"]},
            {"world": 23, "label": "copyright","ramp": ["#000000", "#303030", "#606060", "#909090"]},
        ]})
    return {"_comment": "Scene-aware recolor pack for Mario's Tennis "
                        "(generated by tools/make_match_palette.py). Per-character "
                        "match scenes are gated on the P1-character WRAM byte %s; "
                        "world index alone can't tell characters apart. "
                        "Animation-stable." % PLAYER_CHAR_ADDR,
            "scenes": scenes}


def main():
    overrides = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "overrides")
    out_dir = os.path.join(overrides, "recolor")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "palette.json")
    with open(path, "w") as f:
        json.dump(build(), f, indent=2)
    print("wrote", path)
    for s in build()["scenes"]:
        print("  %-14s detect=%s" % (s["name"], s["detect"]))


if __name__ == "__main__":
    main()
