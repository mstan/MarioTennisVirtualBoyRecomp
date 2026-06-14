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

# Shared court furniture, reused by both the match and change-service scenes so
# the colors never drift apart. world 30 = sky/skyline band, 28 = court, 24 =
# net tape (a horizontal band ~y118-129).
SKYLINE_RULE = {"world": 30, "label": "skyline", "ramp": ["#000000", "#1a2240", "#34406a", "#5a6aa0"]}
COURT_RULE   = {"world": 28, "label": "court",   "ramp": ["#000000", "#0a4018", "#1c7a30", "#34c050"]}
NET_RULE     = {"world": 24, "label": "net",     "ramp": ["#000000", "#606060", "#b0b0b0", "#f4f4f4"]}

# Shared in-match scenery (same for every character). Only worlds whose index
# reliably maps to the same element during a match are colored here. Worlds
# 19/20/21/26 are deliberately left faithful in the MATCH scene: they draw the
# far opponent and the sky during a rally but are reused for big
# score/CHANGE-SERVICE text on the between-points screens, so coloring them in
# the match scene bleeds onto that text (e.g. "PRINCESS" rendered blue). The
# dedicated change-service scene below colors those text worlds, gated so it
# only fires on the between-points screen (never during a rally).
MATCH_SCENERY = [
    SKYLINE_RULE,
    COURT_RULE,
    NET_RULE,
    # "1 SET MATCH  X vs Y" intro text. Worlds 17-20 appear ONLY on the pre-match
    # intro (the rally and CHANGE-SERVICE screens use different world indices),
    # so coloring them here is bleed-free. w18 (left = P1 name) is colored per
    # character in match_scene() below; the rest are shared neutral.
    {"world": 20, "label": "intro_title", "ramp": ["#000000", "#806000", "#c0a000", "#ffe040"]},
    {"world": 19, "label": "intro_vs",    "ramp": ["#000000", "#404040", "#808080", "#c0c0c0"]},
    {"world": 17, "label": "opp_name",    "ramp": ["#000000", "#505050", "#a8a8a8", "#f4f4f4"]},
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

# P1-name (intro, world 18) color per character — their signature hue.
NAME_COLOR = {0: RED, 1: GREEN, 2: PINK, 3: GREEN, 4: RED, 5: GREEN, 6: BROWN}

# Per-character vertical body bands (hi in 0..256 of the player's bbox).
# IMPORTANT: the near player is drawn FROM BEHIND, so there is no visible face —
# a "skin" band in the upper body lands on the back of the head/shoulders and
# reads as nonsensical flesh. Bands therefore use each character's iconic
# back-view colors only (cap/shell on top, torso, lower body, shoes), no face
# skin. Kept to 3-4 broad zones so the per-frame bbox jitter (the bbox shifts as
# the pose/racket changes) doesn't produce obvious thin stripes.
# (index, name, [ (hi, ramp), ... ])
CHARACTERS = [
    (0, "mario",    [(150, RED),    (212, BLUE),  (256, BROWN)]),   # red cap+shirt, blue overalls, shoes
    (1, "luigi",    [(150, GREEN),  (212, NAVY),  (256, BROWN)]),   # green cap+shirt, dark overalls
    (2, "princess", [(70,  BLONDE), (235, PINK),  (256, PINK)]),    # blonde hair, pink dress
    (3, "yoshi",    [(150, GREEN),  (205, RED),   (256, ORANGE)]),  # green body, red saddle, orange boots
    (4, "toad",     [(115, WHITE),  (185, BLUE),  (256, WHITE)]),   # white cap, blue vest, white pants
    (5, "koopa",    [(55,  YELLOW), (215, GREEN), (256, YELLOW)]),  # yellow head, green shell, yellow feet
    (6, "dkjr",     [(256, BROWN)]),                                # all-brown (coherent over striped)
]


# mode_select roster strip. The 7 character face-portraits (MARIO LUIGI PRINCESS
# YOSHI TOAD KOOPA DKJR, left->right) are all drawn under VIP world 30, so a
# single flat ramp tints them one uniform skin tone. World 30's on-screen bbox
# spans the whole strip (verified via world_map: x0=32..x1=351), so split it into
# 7 equal HORIZONTAL columns (hx in 0..256, rel-x within the bbox) and color each
# portrait its character's signature hue. Portrait order == character index, so
# column i uses CHARACTERS[i]. Humans get a cap/hair band over a face-skin band;
# Yoshi/Koopa/DK are flat. This is a static menu (bbox stable, no animation), so
# the per-column bands don't jitter. ROSTER_HX[i] is the right edge of column i.
ROSTER_HX = [37, 73, 110, 146, 183, 219, 256]
CAP_HI = 115   # cap/hair ends ~45% down the circular portrait
# (index -> vertical bands for that portrait: [(hi, ramp), ...])
ROSTER_BANDS = {
    0: [(CAP_HI, RED),    (256, SKIN)],    # mario:    red cap over face
    1: [(CAP_HI, GREEN),  (256, SKIN)],    # luigi:    green cap over face
    2: [(CAP_HI, BLONDE), (256, SKIN)],    # princess: blonde hair over face
    3: [(256, GREEN)],                     # yoshi:    green (flat)
    4: [(CAP_HI, WHITE),  (256, SKIN)],    # toad:     white mushroom cap over face
    5: [(256, GREEN)],                     # koopa:    green (flat)
    6: [(256, BROWN)],                     # dkjr:     brown fur (flat)
}

def roster_cols():
    """world 30 horizontal columns, one per roster portrait (left->right)."""
    cols = []
    for i, hx in enumerate(ROSTER_HX):
        bands = ROSTER_BANDS[i]
        if len(bands) == 1:
            cols.append({"hx": hx, "ramp": bands[0][1]})
        else:
            cols.append({"hx": hx,
                         "bands": [{"hi": h, "ramp": r} for h, r in bands]})
    return cols


# Match detection keys on the court (world 28, present every match frame) and
# excludes the menu/title (worlds 29/31 never appear during a match). Keying on
# the near player (world 22) is unreliable: the VB redraws it on alternating
# frames, so ~10% of frames lack it. With court-keying the scene stays selected
# through that dropout; the player's world-22 rule simply has no pixels to color
# on a frame where it isn't drawn (instead of the whole frame falling to red).
MATCH_DETECT_NONE = [29, 31]

def match_scene(index, name, bands):
    rules = list(MATCH_SCENERY)
    # P1 name (intro, left) in this character's signature color.
    rules.append({"world": 18, "label": "p1_name", "ramp": NAME_COLOR[index]})
    rules.append({"world": 22, "label": name,
                  "bands": [{"hi": hi, "ramp": ramp} for hi, ramp in bands]})
    return {"name": "match_" + name,
            "detect": {"all": [28], "none": MATCH_DETECT_NONE,
                       "ram": {"addr": PLAYER_CHAR_ADDR, "eq": index}},
            "worlds": rules}


# --- Between-points CHANGE-SERVICE / CHANGE-ENDS / score screen ------------
# After a game, play pauses on a screen showing "SET n", the running score
# ("DONKEY 1"), and the prompts "CHANGE SERVICE" / "CHANGE ENDS". Captured world
# map (attr=1 + world_map): world 21 = the big "SET n" + score header (center
# top), world 20 = "CHANGE SERVICE" (left), world 19 = "CHANGE ENDS" (right),
# world 26 = the small service icon between them; the court (28), net (24),
# skyline (30) and the standing near player (22) are still on screen.
#
# These same world indices mean different things during a rally (19/20 absent,
# 27 = live scoreboard present) and on the intro (17/18 = the "X vs Y" names
# present), so the scene is gated all:[19,20] none:[17,18,27,29,31]: 19 AND 20
# present excludes the rally (which has neither) and the menu/title; none:[17,18]
# excludes the intro; none:[27] is belt-and-suspenders against a live point.
# It must be ordered BEFORE the match scenes (which match on world 28 alone), so
# it wins selection on the score screen. The score header name varies with who
# won the game (we can't know it), so world 21 gets a neutral readable gold
# rather than a per-character hue; the CHANGE prompts get a calm UI cyan.
SCORE_GOLD = ["#000000", "#806000", "#c0a000", "#ffe040"]   # SET/score header (w21), icon (w26)
UI_CYAN    = ["#000000", "#106868", "#20b0b0", "#48e8e8"]   # CHANGE SERVICE/ENDS prompts (w19/w20)

SCORE_DETECT_ALL  = [19, 20]
SCORE_DETECT_NONE = [17, 18, 27, 29, 31]

def change_service_scene(index, name, bands):
    """Score / CHANGE-SERVICE screen, self-contained (court+player+text). When
    index is None, emits the no-ram fallback (any P1 character index)."""
    rules = [
        SKYLINE_RULE, COURT_RULE, NET_RULE,
        # standing near player, colored per character exactly as in the match
        {"world": 22, "label": name,
         "bands": [{"hi": hi, "ramp": ramp} for hi, ramp in bands]},
        {"world": 21, "label": "score_header",   "ramp": SCORE_GOLD},
        {"world": 20, "label": "change_service", "ramp": UI_CYAN},
        {"world": 19, "label": "change_ends",    "ramp": UI_CYAN},
        {"world": 26, "label": "serve_icon",     "ramp": SCORE_GOLD},
    ]
    detect = {"all": SCORE_DETECT_ALL, "none": SCORE_DETECT_NONE}
    if index is None:
        return {"name": "change_service", "detect": detect, "worlds": rules}
    detect["ram"] = {"addr": PLAYER_CHAR_ADDR, "eq": index}
    return {"name": "change_service_" + name, "detect": detect, "worlds": rules}


def build():
    # Change-service / score scenes FIRST: they must win over the match scenes
    # (which key on world 28 alone, present on the score screen too). Per
    # character (gated on the P1 RAM byte) so the standing player is colored
    # right, then a no-ram fallback for any unknown index.
    scenes = [change_service_scene(i, n, b) for i, n, b in CHARACTERS]
    scenes.append(change_service_scene(None, "mario", CHARACTERS[0][2]))
    scenes += [match_scene(i, n, b) for i, n, b in CHARACTERS]
    # fallback: any unknown P1 index still gets a colored (Mario) match
    fallback = match_scene(0, "mario", CHARACTERS[0][2])
    fallback["name"] = "match"
    fallback["detect"] = {"all": [28], "none": MATCH_DETECT_NONE}
    scenes.append(fallback)
    # mode_select + title (unchanged layouts)
    scenes.append({
        "name": "mode_select", "detect": {"all": [29], "none": [22]},
        "worlds": [
            {"world": 31, "label": "menu_text", "ramp": ["#000000", "#404040", "#909090", "#e8e8e8"]},
            {"world": 28, "label": "mode_box",  "ramp": ["#000000", "#806000", "#c0a000", "#ffe040"]},
            {"world": 29, "label": "roster_frame", "ramp": ["#000000", "#1a2240", "#34406a", "#5a6aa0"]},
            {"world": 30, "label": "roster_faces", "cols": roster_cols()},
        ]})
    scenes.append({
        "name": "title", "detect": {"all": [25, 26, 31], "none": [22, 29]},
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
