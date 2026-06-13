# Mario's Tennis — macOS (Apple Silicon) build

Native arm64 macOS build of Mario's Tennis, attached to release **v0.1.0** as
`MarioTennisVirtualBoyRecomp-macos-arm64.zip`.

## What this is
- The original game statically recompiled to native arm64 (no emulator core shipped).
- Self-contained `.app`: SDL2 bundled via `@executable_path`, ad-hoc codesigned.
- Verified by manual play on Apple Silicon (looks/sounds correct on the golden path).


## Install
1. Download `MarioTennisVirtualBoyRecomp-macos-arm64.zip` from the **v0.1.0** release and unzip.
2. First launch: right-click `Mario's Tennis.app` -> Open (ad-hoc signed), or
   `xattr -dr com.apple.quarantine "Mario's Tennis.app"`.
3. ROM not included — supply your own dump: Mario's Tennis (Virtual Boy) .vb dump
4. Run: `"Mario's Tennis.app/Contents/MacOS/Mario's Tennis" /path/to/rom`

## Build it yourself
`scripts/release-mac.sh` reproduces this artifact (build -> .app -> zip);
`scripts/release-mac.sh --publish` re-attaches it to the latest release.
Requires: `brew install cmake ninja sdl2 dylibbundler` on Apple Silicon.
