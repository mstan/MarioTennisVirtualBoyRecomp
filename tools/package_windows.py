"""Package an already-built production runtime using an explicit file list."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sdl", type=Path, required=True)
    parser.add_argument("--sdl-license", type=Path, required=True)
    parser.add_argument("--git", default="git")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    build = args.build.resolve()
    cache = (build / "CMakeCache.txt").read_text(encoding="utf-8")
    assert "VBRECOMP_DEBUG_TOOLS:BOOL=OFF" in cache
    assert "MARIO_TENNIS_UI:BOOL=ON" in cache
    assert "CMAKE_BUILD_TYPE:STRING=Release" in cache
    version = "0.2.2"
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="windows-stage-", dir=output))
    runtime = build / "vbrecomp/runtime"
    exe = "MarioTennisVirtualBoyRecomp.exe"
    shutil.copy2(runtime / exe, stage / exe)
    shutil.copy2(args.sdl, stage / "SDL2.dll")
    shutil.copytree(runtime / "assets", stage / "assets")
    package = f"marios-tennis-full-color-{version}.vbmod"
    shutil.copy2(build / "mod-packages" / package, stage / package)
    shutil.copy2(stage / package, output / package)
    licenses = stage / "licenses"
    licenses.mkdir()
    sources = {
        "game-MIT.txt": repo / "LICENSE.md",
        "vbrecomp-license.txt": repo / "vbrecomp/LICENSE",
        "recomp-ui-license.txt": repo / "recomp-ui/LICENSE",
        "imgui-license.txt": repo / "recomp-ui/src/third_party/imgui/LICENSE.txt",
        "snes-mod-runtime.txt": repo / "vbrecomp/runtime/licenses/snes-mod-runtime.txt",
        "SDL2-license.txt": args.sdl_license,
        "font-notices.md": repo / "recomp-ui/assets/common/fonts/NOTICE.md",
        "boxart-notice.md": repo / "assets/NOTICE.md",
    }
    for name, source in sources.items():
        shutil.copy2(source, licenses / name)
    for source in (repo / "assets/licenses").glob("*.txt"):
        shutil.copy2(source, licenses / source.name)
    (licenses / "Lato-notice.txt").write_text(
        "Copyright (c) 2011-2015 by tyPoland Lukasz Dziedzic "
        '(http://www.typoland.com/) with Reserved Font Name "Lato". '
        "Licensed under the SIL Open Font License, Version 1.1.\n",
        encoding="utf-8",
    )
    (stage / "README.txt").write_text(
        f"Mario's Tennis Recompiled {version} - Windows x64\n\n"
        "Extract the entire ZIP. Run MarioTennisVirtualBoyRecomp.exe and select your own ROM.\n"
        "Required ROM: 524288 bytes, CRC32 7CE7460D. No ROM is included or modified.\n\n"
        f"Optional color: use Mods to import {package}, then enable Full-color renderer.\n"
        "Color is experimental and OFF by default. Disable it to return to native red/black.\n"
        "Keyboard: arrows move, X/Z are A/B, Enter is Start, Esc opens settings.\n"
        "Controls can be rebound in the launcher. Settings/mod state use a writable user profile.\n"
        "This production build has no TCP debugger or private pose recorder.\n\n"
        "Source and documentation: https://github.com/mstan/MarioTennisVirtualBoyRecomp\n"
        "Third-party notices and licenses are in licenses/ and assets/BOXART-NOTICE.md.\n",
        encoding="utf-8",
    )

    def commit(path):
        return subprocess.check_output(
            [args.git, "-C", str(path), "rev-parse", "HEAD"], text=True
        ).strip()

    (stage / "build-info.json").write_text(
        json.dumps(
            dict(
                version=version,
                game_commit=commit(repo),
                vbrecomp_commit=commit(repo / "vbrecomp"),
                recomp_ui_commit=commit(repo / "recomp-ui"),
                debug_tools=False,
                default_color_enabled=False,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    archive = output / "MarioTennisVirtualBoyRecomp-windows-x64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                assert path.suffix.lower() not in (".vb", ".vboy", ".cfg", ".src")
                z.write(path, path.relative_to(stage).as_posix())
    artifacts = [archive, output / package]
    (output / "SHA256SUMS.txt").write_text(
        "".join(
            f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n"
            for p in artifacts
        ),
        encoding="ascii",
    )
    print(
        json.dumps(
            dict(stage=str(stage), artifacts=[str(p) for p in artifacts]), indent=2
        )
    )


if __name__ == "__main__":
    main()
