"""Package an already-built production runtime using an explicit file list."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import re
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
    assert "VBRECOMP_CPUHOOK:BOOL=OFF" in cache
    assert "MARIO_TENNIS_UI:BOOL=ON" in cache
    assert "CMAKE_BUILD_TYPE:STRING=Release" in cache
    for key, expected in (("CMAKE_HOME_DIRECTORY", repo),
                          ("VBRECOMP_ROOT", repo / "vbrecomp"),
                          ("RECOMP_UI_ROOT", repo / "recomp-ui")):
        match = re.search(rf"^{key}:[^=]+=(.+)$", cache, re.MULTILINE)
        assert match and Path(match[1]).resolve() == expected.resolve(), key
    version = (repo / "VERSION").read_text().strip()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="windows-stage-", dir=output))
    runtime = build / "vbrecomp/runtime"
    exe = "MarioTennisVirtualBoyRecomp.exe"
    shutil.copy2(runtime / exe, stage / exe)
    shutil.copy2(args.sdl, stage / "SDL2.dll")
    # Include the complete non-system DLL closure, including alternate native
    # toolchains that link the C++ runtime dynamically.
    queue = [runtime / exe, args.sdl.resolve()]
    copied = {"sdl2.dll"}
    toolchain = args.sdl.resolve().parent
    while queue:
        binary = queue.pop()
        imports = subprocess.check_output([str(toolchain / "objdump.exe"), "-p", str(binary)], text=True)
        for name in re.findall(r"DLL Name:\s*(\S+)", imports):
            if name.lower() in copied:
                continue
            candidate = next((folder / name for folder in (runtime, toolchain) if (folder / name).is_file()), None)
            if candidate:
                copied.add(name.lower())
                shutil.copy2(candidate, stage / name)
                queue.append(candidate)
            elif not (Path(os.environ["SystemRoot"]) / "System32" / name).is_file() and not name.lower().startswith(("api-ms-", "ext-ms-")):
                raise RuntimeError("Unresolved dependency: " + name)
    shutil.copytree(runtime / "assets", stage / "assets")
    shutil.copy2(repo / "README.md", stage / "README.md")
    shutil.copytree(repo / "docs", stage / "docs")
    package = "marios-tennis-full-color-0.2.2.vbmod"
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
        assert not subprocess.check_output([args.git, "-C", str(path), "status", "--porcelain"], text=True).strip(), path
        return subprocess.check_output(
            [args.git, "-C", str(path), "rev-parse", "HEAD"], text=True
        ).strip()

    for name in ("vbrecomp", "recomp-ui"):
        assert subprocess.check_output([args.git, "-C", str(repo), "rev-parse", "HEAD:" + name], text=True).strip() == commit(repo / name)
    (stage / "build-info.json").write_text(
        json.dumps(
            dict(
                version=version,
                game_commit=commit(repo),
                vbrecomp_commit=commit(repo / "vbrecomp"),
                recomp_ui_commit=commit(repo / "recomp-ui"),
                debug_tools=False,
                default_color_enabled=False,
                executable_sha256=hashlib.sha256((stage / exe).read_bytes()).hexdigest(),
                dlls={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.glob("*.dll")},
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
