"""Avoid accidentally validating a stale installed revision of a dev package."""

import tomllib
import zipfile


def install_args(mods, package):
    with zipfile.ZipFile(package) as archive:
        manifest = tomllib.loads(archive.read("manifest.toml").decode("utf-8"))
        installed = mods / "packages" / manifest["id"] / manifest["version"]
        if not installed.exists():
            return ["--install-mod", str(package)]
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            file = installed / entry.filename
            if not file.is_file() or file.read_bytes() != archive.read(entry):
                raise RuntimeError(
                    f"{installed} contains a different package revision; choose a fresh validation output directory"
                )
    return []
