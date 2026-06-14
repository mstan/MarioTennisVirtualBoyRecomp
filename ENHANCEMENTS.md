# Enhancements — opt-in runtime recolorization (WIP)

This branch adds an **optional, faithful-by-default** color-enhancement layer on
top of the Mario's Tennis static recompilation. The Virtual Boy is a red-only
console; this layer recolors selected on-screen elements (court, net, crowd, the
near player per character, menu/score text) into full color **without ever
changing the faithful output**.

> **Status: WIP, not merge-ready.** Parked on remote for collaboration. The
> default build is byte-identical to the oracle; the enhancement is purely
> additive and gated behind an environment variable. See *Known limitations*.

---

## Cardinal rule: faithful is the product

The recompiled game must remain a bit-exact reproduction of the real hardware.
Therefore every enhancement here is:

- **Opt-in.** Nothing activates unless `VBRECOMP_OVERRIDES` points at a pack.
- **Default-OFF and byte-identical.** With no overrides set, the runtime renders
  exactly as before. This is verified after every change by screenshotting
  headless with no overrides and `cmp`-ing both eyes against
  `.tmp/baseline_eye{0,1}.png`.
- **Fail-faithful.** A missing, malformed, or partially-parsed pack falls back to
  faithful rendering — it never aborts and never corrupts the frame.
- **Out of the oracle path.** `vb_vip_render_framebuffer` (the screenshot/oracle
  path) is untouched. Recoloring runs in a separate, attribution-aware render.

If an enhancement cannot satisfy all four, it does not ship.

---

## Enabling it

```sh
# Faithful (default) — no overrides, byte-identical to the oracle:
vb-runtime.exe --rom roms/marios_tennis.vb --port 4390

# Enhanced — point at the pack, then run:
set VBRECOMP_OVERRIDES=...\MarioTennisVirtualBoyRecomp\overrides
vb-runtime.exe --rom roms/marios_tennis.vb --port 4390
```

The pack lives at `overrides/recolor/palette.json` and is generated
deterministically by `tools/make_match_palette.py` (never hand-edit the JSON —
edit the generator and regenerate).

---

## How it works

### Engine (in the `vbrecomp` runtime repo)

The recolor engine is generic and game-agnostic; all Mario's-Tennis-specific
values live in the pack, never in the runtime.

- `runtime/src/recolor.c` / `include/recolor.h` — the scene model and per-pixel
  recolor (`vb_recolor_world_pixel`).
- `runtime/src/vip.c` — an opt-in attribution-aware render pass that records,
  per displayed frame, which **VIP world** drew each pixel (plus per-world
  on-screen bounding boxes). This is what makes "color only the net" possible.
- `runtime/src/debug_server.c` — TCP commands for inspection (below).

### Scene model

The VB composites the screen from up to 32 **worlds** (draw layers). Each game
screen uses a recognizable set of worlds, so the pack is organized as **scenes**:

```jsonc
{
  "scenes": [
    {
      "name": "match_mario",
      "detect": { "all": [28], "none": [29, 31],
                  "ram": { "addr": "0x0500203A", "eq": 0 } },
      "worlds": [
        { "world": 28, "label": "court", "ramp": ["#000000","#0a4018","#1c7a30","#34c050"] },
        { "world": 22, "label": "mario",
          "bands": [ { "hi": 150, "ramp": [...] }, { "hi": 256, "ramp": [...] } ] }
      ]
    }
  ]
}
```

- **Detection.** Each frame the runtime builds a bitmask of present worlds and
  selects the **first** scene whose `detect` matches:
  `(mask & all) == all && (mask & none) == 0`, plus an optional `ram` byte
  predicate. Scene **order matters** — more specific scenes go first. A scene
  with no `detect` matches always (catch-all, order last). No match ⇒ faithful.
- **RAM predicates.** World index alone can't tell characters apart (the near
  player is always world 22). The pack gates per-character scenes on a game RAM
  byte (`0x0500203A` = P1 character index 0..6). The address is game-specific
  and lives only in the pack.
- **Ramps.** Each world rule maps the 4 VB red intensities to 4 target colors.
- **Vertical bands.** A rule may split its on-screen bbox into horizontal bands
  (`hi` = rel-y 0..256) to color e.g. cap / torso / legs differently.
- **Horizontal columns.** A rule may first split into vertical columns (`hx` =
  rel-x 0..256), each with its own ramp or bands — used for the menu roster strip
  where 7 portraits share one world.
- **Hysteresis.** The VB redraws sprites on alternating frames, so a world drops
  out of ~10% of frames. To avoid flicker, a no-match frame holds the previous
  scene for a few frames before reverting to faithful.

---

## Current coverage

| Scene | Detect signature | What's colored |
|---|---|---|
| `title` | worlds 25,26,31 | logo, court, net, singles/doubles text, cursor |
| `mode_select` | world 29, no 22 | menu text, mode box, roster frame, **7 roster portraits** (per-character columns) |
| `match_<char>` (×7 + fallback) | world 28, no 29/31, RAM=char | court, net, skyline, intro names, **near player per character** (back-view body bands) |
| `change_service` (×7 + fallback) | worlds 19,20, no 17/18/27/29/31, RAM=char | **score header (gold), CHANGE-SERVICE/ENDS prompts (cyan), serve icon, standing player per character**, court/net/skyline |

Proof screenshots are under `docs/proof/recolor_*.png` (before/after pairs).

The shared court/net/skyline rules are defined once as constants in the
generator and reused by both the match and change-service scenes so their colors
can never drift apart.

---

## Observability

All inspection goes through the TCP debug server (port 4390) — **no printf, no
log files** (project rule). Helper client: `vbrecomp/tools/_ping.py`.

| Command | Purpose |
|---|---|
| `recolor_state` | active scene, loaded scene/entry counts |
| `world_map` | per-world on-screen bbox + pixel count for the current frame |
| `world_trace` / `wram_anchors` | session-spanning rings (walk after the fact, never arm-and-capture) |
| `screenshot ... attr=1` | false-color **world attribution** view — the key "which world owns this pixel" diagnostic |
| `screenshot ... recolor=1` | the enhanced (recolored) frame |
| `recolor_reload` | hot-reload the pack JSON without restarting |
| `recolor_trace` | per-frame scene-selection decision ring |

Authoring a new scene is: capture `attr=1` + `world_map` on the target screen →
read off the world→element mapping → add a scene to `make_match_palette.py` with
a bleed-free `detect` signature → regenerate → `recolor_reload` → verify against
the attribution map → re-confirm faithful byte-identity.

> **Ring-buffer discipline:** the world/anchor rings are always-on and
> session-spanning. Probes *query* the ring for the window of interest; they
> never arm a trace then run a workload (LLM/tool latency loses the event).

---

## Build, run, verify

```sh
# Build (mingw via PowerShell, not MSYS bash):
cmake --build build --target vb-runtime

# Regenerate the pack after editing the generator:
python tools/make_match_palette.py

# Verify faithful byte-identity (must pass after every engine/pack change):
#   run headless with NO overrides, screenshot both eyes, cmp vs baseline.
```

---

## Known limitations (WIP)

- **CPU opponent is not separately colorable.** It is drawn inside the court
  world (28) rather than its own world, so the world-keyed engine can't isolate
  it. Coloring it would require per-CHR-tile sub-world attribution — a large
  subsystem, shelved by decision.
- **Scored screens require human play.** Headless input can't complete a serve,
  and the windowed instance's per-frame keyboard read clobbers TCP input — so
  score/results screens are reached by a human playing the focused window, not by
  scripted navigation.
- **Band/column fractions are approximate.** Per-character body bands and the
  roster column boundaries are hand-tuned estimates; some jitter as poses change.
- **Score header color is generic.** World 21 carries the winner's name, which
  varies and can't be known ahead of time, so it gets a neutral gold rather than
  the winner's signature hue.
- **Coverage is partial.** OPTIONS, the VB boot splash, doubles, and several
  transition screens are not yet colored (they render faithfully).

---

## Scope guardrails

Allowed on this branch: extend the opt-in recolor/capture layer, the per-game
pack and its generator, per-game proofs, and observability tooling. **Not**
allowed: interpreter/HLE/stubs, editing `generated/`, hardcoding game-specific
values into the generic runtime, printf/log files, or anything that changes the
faithful default. The faithful build stays byte-identical to the oracle — always.
