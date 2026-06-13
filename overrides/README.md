# Override layer (optional graphics enhancements)

This folder is an **opt-in plugin layer** that recolors/replaces graphics
Mario's Tennis decodes at runtime. It mirrors the snesrecomp `overrides/`
pattern (`SuperMarioWorldRecomp/overrides/README.md`).

**Nothing here changes vbrecomp's defaults.** The layer is active only when the
runtime is launched with `VBRECOMP_OVERRIDES` pointing at this `overrides/`
directory. With it unset the original 2bpp render runs unchanged and the output
is byte-for-byte faithful (verified: boot frame `cmp`-identical to a pre-change
baseline). A missing/empty/malformed manifest, or an entry whose image is
missing, falls back to the faithful render for that item and never aborts.

## How it works

1. The runtime captures the game's decoded 8×8 OBJ tiles by **content hash**
   (address-independent) — see `vbrecomp/docs/ASSET_CAPTURE.md`.
2. `graphics/manifest.json` maps a tile's content hash to a colored RGBA PNG.
3. At each drawing frame the runtime matches on-screen OBJ tiles against the
   manifest, suppresses the original 2bpp pixels for a match, and composites the
   RGBA image at the original position **per eye** (preserving flip, priority,
   and per-eye parallax/visibility).

## manifest.json

```json
{
  "replacements": [
    { "id": "tile_097eec65",
      "match": { "tile_hash": "097eec65" },
      "image": "097eec65.png",
      "anchor_x": 0, "anchor_y": 0 }
  ]
}
```

- `match.tile_hash` — FNV-1a of the unflipped 8×8 tile (the `<hash>` filename in a
  `capture_dump`).
- `image` — RGBA PNG resolved relative to `graphics/`. Must be a **stored-block**
  PNG (what `tools/colorize_tiles.py` and the runtime's `png_read.c` use).
- `anchor_x/y` — optional draw offset from the tile's top-left.

## Regenerating this pack

```bash
# 1. capture (runtime built from vbrecomp, headless):
VBRECOMP_CAPTURE=1 vb-runtime.exe --rom roms/marios_tennis.vb --headless
#    drive into a live match (see tools/), then TCP: capture_dump {dir:captures}
# 2. reconstruct + pick an asset:
python tools/compose_capture.py captures --clusters
# 3. colorize the chosen tiles -> overrides/graphics/:
python tools/colorize_tiles.py captures overrides --y-band 36 44
```

## Known behavior

This pack replaces **per tile by content hash**, so a shared font glyph is
recolored everywhere it appears (e.g. recoloring the "MARIO" scoreboard glyphs
also recolors "DONKEY", which shares font tiles). Replacing a single word/logo as
a unit needs cluster matching — see the next-iteration notes in
`vbrecomp/docs/ASSET_CAPTURE.md`.
