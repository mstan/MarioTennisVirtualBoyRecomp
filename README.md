# MarioTennisVirtualBoyRecomp

Static V810→C recompilation of Mario's Tennis (Virtual Boy, 1995) on top of the
[`vbrecomp`](https://github.com/mstan/vbrecomp) framework.

## Status

- Title-screen warning ("READ INSTRUCTION AND PRECAUTION BOOKLETS BEFORE
  OPERATING" + Japanese variant) renders pixel-position-equivalent to the
  Beetle VB oracle: **1762 / 86,016 lit pixels at zero-tolerance bounding-box
  match**. See `baseline-title-screen.png`.
- All 236 reachable functions / 27,882 V810 instructions emitted from the cart
  ROM compile cleanly. The recompiled cart runs through reset trampoline →
  BSS clear → VIP / IRQ controller / timer setup → game-state dispatcher
  loop, and stays in the dispatcher forever per real hardware (no premature
  unwind).
- VIP renderer, brightness pipeline (cache), column state machine,
  CHR-RAM aliasing, framebuffer pack/unpack, BMP screenshot — all wired into
  the runtime.
- Beetle VB oracle is built as a sibling process for register-level and
  framebuffer cross-checking via a shared TCP wire protocol.

Known gaps:
- Brightness scale differs by a constant offset from Beetle (runtime R=0xC7
  vs Beetle R=0xE3 at level 3 with brta=12 brtb=40 brtc=48). Pixel positions
  match exactly; this is a `recalc_brt_cache` tuning task, not a recompiler
  issue.
- vb-runtime is still TCP-headless (no SDL window). Screenshots over TCP
  are the visual interface. Live SDL window is the next milestone.

## Repo layout

```
MarioTennisVirtualBoyRecomp/   (this repo)
├── CMakeLists.txt             — top-level entry; forces VBRECOMP_GAME=marios_tennis
├── README.md                  — this file
├── LICENSE.md                 — game-repo licence
├── baseline-title-screen.png  — known-good render (regression baseline)
├── debug.ini.example          — sample debug.ini for vb-runtime / vb-beetle ports
├── .gitignore
├── roms/                      — Mario's Tennis ROM goes here (gitignored)
├── generated/                 — V810→C output from the recompiler (gitignored, regenerate)
├── beetle-vb/                 — Beetle VB libretro-core clone (gitignored, see BRINGUP.md)
├── build/                     — CMake build dir (gitignored)
└── vbrecomp/                  — framework (separate repo: mstan/vbrecomp)
```

The `vbrecomp/` directory is a **separate git repo**, cloned in as a
subdirectory. It is intentionally NOT included in this repo's history —
gameplay-agnostic recompiler + runtime code lives upstream; this repo only
holds the Mario's-Tennis-specific build wiring.

## Build from scratch

This is a Windows + MinGW (mingw-w64-x86_64) setup. PowerShell only — MSYS2
bash silently fails to spawn `cc1.exe` on this machine (see
`vbrecomp/docs/BRINGUP.md` for the diagnosis).

```powershell
$env:PATH = "C:\msys64\mingw64\bin;$env:PATH"
cd F:\Projects\virtualboyrecomp\MarioTennisVirtualBoyRecomp

# 1. Clone the framework + Beetle VB oracle (one-time)
git clone git@github.com:mstan/vbrecomp.git vbrecomp
git clone https://github.com/libretro/beetle-vb-libretro.git beetle-vb
# Build the oracle's static archive (see vbrecomp/docs/BRINGUP.md).

# 2. Drop the ROM into roms/
#    sha256: 5dc5e6b5d5f538f56b3b9727db1c7931d9dfe1bbd0743f698897e0fd90e70101
mkdir roms
cp <wherever>\marios_tennis.vb roms\marios_tennis.vb

# 3. Run the recompiler — generates V810→C
python -m recompiler.cli.vbrecomp_codegen `
    --rom roms\marios_tennis.vb `
    --module marios_tennis `
    --out generated\

# 4. Configure CMake (creates build/)
cmake -S . -B build -G "Ninja"

# 5. Build vb-runtime (the recompiled cart) + vb-beetle (oracle)
cmake --build build --target vb-runtime
cmake --build build --target vb-beetle
```

## Run

```powershell
# Launch the recompiled runtime (TCP debug server on 4390)
.\build\runtime\vb-runtime.exe --rom roms\marios_tennis.vb --port 4390

# In another terminal: launch the Beetle oracle (TCP on 4391, headless)
.\build\runtime\vb-beetle.exe --rom roms\marios_tennis.vb --port 4391 --headless

# Pull a screenshot from the recompiled runtime
python vbrecomp\tools\_ping.py --port 4390 --cmd screenshot --arg eye=0
# → writes vb-runtime-eye0.bmp; should match baseline-title-screen.png at
# the pixel-position level

# Cross-process pixel diff
python vbrecomp\tools\_framebuf_diff.py
```

See `vbrecomp/TCP.md` for the full debug command surface (wtrace, fntrace,
read_ram, get_registers, vip_state, etc.).

## Licence

The recompiler + runtime + tooling are MIT (see `vbrecomp/LICENSE`).
This repo's build wiring is MIT (see `LICENSE.md`).

The Mario's Tennis ROM and any derived data are © Nintendo and not
included or distributable. You must dump the cart yourself.
