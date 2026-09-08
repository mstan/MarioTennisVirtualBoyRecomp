# Mods, shared UI, and the full-color spike

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
`build/mod-packages/marios-tennis-full-color-0.1.0.vbmod`, enable **Full-color
renderer (spike)**, and Play. It defaults off when first installed. To do the
same from the command line:

```powershell
.\build\vbrecomp\runtime\MarioTennisVirtualBoyRecomp.exe --rom roms\marios_tennis.vb --install-mod build\mod-packages\marios-tennis-full-color-0.1.0.vbmod --enable-mod marios-tennis.full-color:full-color
```

Use `--install-mod` only once per version. Later runs retain the selection.
Disable it through the menu or `--disable-mod marios-tennis.full-color:full-color`
to restore the original presentation. **Solid sky and court** controls background
fills; **Color saturation** ranges from grayscale to full saturation.

## What the spike does

![Full-color rally captured from the native game](color-rally.png)

`src/tennis_color.cpp` is game-owned code using the framework's read-only
presentation callback: native 2bpp levels, per-pixel VIP world attribution, eye,
and displayed frame sequence. It colors the players, ball, net, scenery, court,
and text; fills sky, scenery silhouettes and court surfaces; and preserves native
stereo geometry. Service introduction and rally use different player/net layers,
and the eyes use separate scenery worlds. The renderer handles those cases.

This is an experimental visual reconstruction, not finished replacement artwork.
Player colors use vertical body bands, with approximate Mario and Donkey Kong
palettes. Other characters, doubles, every camera/animation state, and a complete
match have not been exhaustively validated. Menus use a generic color palette.
Court fills infer projected edges from visible native pixels, so unusual views
may expose artifacts. Native sprite/line detail remains at 384 by 224 per eye.

## Make a data-only palette mod

Copy `mods/full-color`, give it a new package ID/version in `manifest.toml`, and
edit the named hexadecimal RGB values in `palette.txt`. Keep the game target and
trusted plugin ID. Package it using:

```powershell
python vbrecomp/tools/pack_mod.py path/to/my-palette my-palette.vbmod
```

The ZIP contains metadata and palette data only. It cannot load a DLL or script.
Two enabled packages claiming `video.renderer` produce a conflict before launch;
disable one to use the other. A genuinely new rendering implementation is linked
into the game and registered under its own trusted ID. Other framework consumers
can use the same API without putting game-specific rules into VIP emulation.

The framework package runtime is adapted from snesrecomp, retaining its PolyForm
Noncommercial license. The game-owned color code and palette remain under this
repository's MIT license. See `vbrecomp/docs/MODS.md` for package authoring and the
framework's retained third-party notices.

## Validation

Run the owner-ROM integration checks against a debug-tools build:

```powershell
python tools/validate_color.py build/vbrecomp/runtime/MarioTennisVirtualBoyRecomp.exe roms/marios_tennis.vb build/mod-packages/marios-tennis-full-color-0.1.0.vbmod build/color-check
python tools/validate_ui_windows.py build/vbrecomp/runtime/MarioTennisVirtualBoyRecomp.exe roms/marios_tennis.vb build/mod-packages/marios-tennis-full-color-0.1.0.vbmod build/ui-check
```

The first follows a deterministic boot/service/rally route, compares both raw
eyes, CPU registers and all 64 KiB WRAM with color disabled/enabled, and checks a
data-only alternate palette. Presented images differ while the native outputs
and subsequent game state remain identical. It also verifies the ROM file hash.
The second drives only its own Windows process: rebinds A to C in the launcher,
verifies saved settings and actual input-register behavior, checks menu pause,
and toggles color off/on without advancing or changing the displayed game state.
Both leave their evidence in the requested output directory.

Also validated: 77 Python recompiler tests (5 oracle-dependent skips), unchanged
regenerated C, package lifecycle/security tests, shared-UI profile/assets/runtime
tests, and builds with UI off, debug tools off, and SDL absent. These checks do
not constitute a new full-game Beetle oracle comparison or physical-gamepad test.
Linux/macOS packaging scripts were updated for the executable name, launcher
assets, mod archive, notices, and writable profiles; their shell syntax was
checked on Windows, but native Linux/macOS builds were not run.
