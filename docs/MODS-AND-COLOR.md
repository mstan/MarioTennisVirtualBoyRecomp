# Mods, shared UI, and the full-color renderer

The game now uses recomp-ui for ROM selection, video/audio settings, both native
D-pads, keyboard/controller bindings, and a versioned mod catalog. Press Escape
in-game (or the controller Guide button) to pause and open settings. The Mods
section can switch installed features live. Full package installation, version
selection, and option editing live in the preboot launcher.

Settings are saved beside the executable in `vbrecomp.cfg`; packages and feature
selections are under `mods/`. Use `--config` and `--mods-dir` for isolated profiles.
`--no-launcher` starts with saved settings; `--launcher` always opens the launcher.
The original 524,288-byte ROM is verified by exact SHA-256 before mod activation.
No ROM, generated code, or guest-memory patch is installed by the color package.

## Build and try it

Build the executable and the optional package:

```powershell
cmake --build build --target vb-runtime mario-tennis-mods
.\build\vbrecomp\runtime\MarioTennisVirtualBoyRecomp.exe --rom roms\marios_tennis.vb
```

In **Mods**, install
`build/mod-packages/marios-tennis-full-color-0.2.0.vbmod`, enable **Full-color
renderer**, and Play. It defaults off when first installed. To do the
same from the command line:

```powershell
.\build\vbrecomp\runtime\MarioTennisVirtualBoyRecomp.exe --rom roms\marios_tennis.vb --install-mod build\mod-packages\marios-tennis-full-color-0.2.0.vbmod --enable-mod marios-tennis.full-color:full-color
```

Use `--install-mod` only once per version. Later runs retain the selection.
Disable it through the menu or `--disable-mod marios-tennis.full-color:full-color`
to restore the original presentation. **Solid sky and court** controls background
fills; **Color saturation** ranges from grayscale to full saturation.

## What the renderer does

![Full-color rally captured from the native game](color-rally.png)

`src/tennis_color.cpp` uses source texels captured by the native rasterizer, along
with the game's four player-slot identities. Character materials are keyed by
original CHR content fingerprint and source atlas position, with unflipped
pixel masks. Moving world numbers, stereo parallax, and affine scaling do not
change a material's identity. The previous world guesses and screen-height body
bands are gone; Mario's hair no longer becomes a beige strip during animation.

The package includes material labels for all seven characters and their selection
portraits. Caps, hair, skin, garments, gloves, shoes, rackets, Yoshi's spines,
Toad's spots and Koopa's shell can use different colors. The masks preserve the
original pixel shapes and native occlusion. Original ROM/CHR pixels are not
included in the package; the supplied ROM remains the source of the artwork.

![Character selection portraits captured through the development TCP server](color-select.png)

An uncatalogued tile retains native ink and its character's base color rather
than adopting another layer's palette. This is still a visual reconstruction:
finite animation captures do not prove every match, doubles setup or pose is
covered. Court fills infer projected edges, and title/HUD decoration still uses
a general UI palette. Native detail remains 384 by 224 per eye.

## Make a data-only palette mod

Copy `mods/full-color`, give it a new package ID/version in `manifest.toml`, and
edit the named hexadecimal RGB values in `palette.txt`. Keep the game target and
trusted plugin ID. Package it using:

```powershell
python vbrecomp/tools/pack_mod.py path/to/my-palette my-palette.vbmod
```

The ZIP contains metadata, palette values and material annotations. It cannot load a DLL or script.
Two enabled packages claiming `video.renderer` produce a conflict before launch;
disable one to use the other. A genuinely new rendering implementation is linked
into the game and registered under its own trusted ID. Other framework consumers
can use the same API without putting game-specific rules into VIP emulation.

The framework package runtime is adapted from snesrecomp, retaining its PolyForm
Noncommercial license. The game-owned color code and palette remain under this
repository's MIT license. See `vbrecomp/docs/MODS.md` for package authoring and the
framework's retained third-party notices.

Additional palette keys use `material.NAME`, where NAME is `background`, `ink`,
`cap`, `skin`, `trousers`, `brown`, `white`, `yellow`, `green`, `pink`, `hair`,
`mouth`, `cyan`, `dark_hair`, `navy`, `pupil`, `racket`, `gold`, `shell`, or `shirt`.
These override that material's RGB independently of the original palette aliases.

## Capture and author materials

The development game already provides a loopback TCP screenshot server. Launch
with `--paused --port 4495` and send newline-delimited JSON. `screenshot` takes
`path`, `eye` and `presented: 1`; omit `presented` for original pixels.
`source_dump` captures the displayed source coordinates, raw texels and hashes.
See `vbrecomp/docs/MODS.md` for the wire format and deterministic stepping.

The authoring tools require Python 3.11+ and Pillow. A reproducible capture route
selects each character using native controller input, then moves, serves and
swings while collecting displayed artwork. Use a private output directory:

```powershell
python tools/color_capture.py build/vbrecomp/runtime/MarioTennisVirtualBoyRecomp.exe roms/marios_tennis.vb private-capture --samples 360
python tools/color_materials.py private-capture private-capture/portraits.json mods/full-color/materials.bin
```

`--opponent 0 --characters 1` captures Mario as the distant opponent. Merge such
a second corpus with `color_materials.py --extra-capture other-capture`. Inspect
the emitted color contact sheets, update the authoring rules/material annotations,
rebuild the package, and validate it in the actual runtime. Captures contain
decoded owner-ROM artwork and must not be committed or bundled.

`materials.bin` uses magic `VBMAT002`, a little-endian uint32 tile count, seven
32x32 portrait material masks, then 72-byte tile records. Each record is
`<BBBBI` (character 0..6, atlas size 128, tile x/y, CHR FNV-1a), followed by 64
unflipped material bytes. Bits 0..4 select the material; bits 5..6 select one of
four shades; bit 7 is reserved. The loader rejects invalid sizes, IDs, shades,
duplicate keys, truncation and trailing data before replacing an active catalog.

## Validation

Run the owner-ROM integration checks against a debug-tools build:

```powershell
python tools/validate_color.py build/vbrecomp/runtime/MarioTennisVirtualBoyRecomp.exe roms/marios_tennis.vb build/mod-packages/marios-tennis-full-color-0.2.0.vbmod build/color-check
python tools/validate_ui_windows.py build/vbrecomp/runtime/MarioTennisVirtualBoyRecomp.exe roms/marios_tennis.vb build/mod-packages/marios-tennis-full-color-0.2.0.vbmod build/ui-check
python tools/validate_materials.py build/vbrecomp/runtime/MarioTennisVirtualBoyRecomp.exe roms/marios_tennis.vb build/mod-packages/marios-tennis-full-color-0.2.0.vbmod mods/full-color/materials.bin build/material-check
```

The first follows a deterministic boot/service/rally route, compares both raw
eyes, CPU registers and all 64 KiB WRAM with color disabled/enabled, and checks a
data-only alternate palette. Presented images differ while the native outputs
and subsequent game state remain identical. It also verifies the ROM file hash.
The second drives only its own Windows process: rebinds A to C in the launcher,
verifies saved settings and actual input-register behavior, checks menu pause,
and toggles color off/on without advancing or changing the displayed game state.
Both leave their evidence in the requested output directory.

The material check replays each character's animation route, measures catalog
coverage in both eyes, verifies that screenshots do not advance the paused guest,
and saves actual PNG contact sheets and animated GIFs for visual inspection. It
fails below 99% coverage in any sampled frame. Use fresh output directories when
changing a package without changing its version; validators reject stale installs.
CTest includes ROM-free material-file rejection tests, native source/occlusion
tests, and the package lifecycle/security integration test.

The 0.2.0 pass was checked with 360 animation samples per character in both eyes:
all sampled character pixels had material coverage. A separate 360-sample match
checks Mario as the distant opponent. The catalog contains 12,713 tile material
records from 646 captured poses. These are finite route checks, not a claim of
exhaustive game coverage; use the same tools when extending the artwork catalog.

Also validated: 77 Python recompiler tests (5 oracle-dependent skips), unchanged
regenerated C, package lifecycle/security tests, shared-UI profile/assets/runtime
tests, and builds with UI off, debug tools off, and SDL absent. These checks do
not constitute a new full-game Beetle oracle comparison or physical-gamepad test.
Linux/macOS packaging scripts were updated for the executable name, launcher
assets, mod archive, notices, and writable profiles; their shell syntax was
checked on Windows, but native Linux/macOS builds were not run.
