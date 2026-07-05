"""Single cross-platform build entry point.

Run this SAME command on Windows, macOS, and Linux:

    python scripts/build_all.py

It detects the OS it's running on and produces that OS's installer.
There is no cross-compiling -- PyInstaller bundles native binaries for
whichever OS it runs on, so a Windows machine can only ever produce the
Windows installer, a Mac only the macOS one, a Linux box only the Linux
one. This script just means you don't need to remember three different
sets of commands; run it once per target OS and collect the results.

Output (always under installers/, regardless of platform):
    installers/windows/viewYUV-Setup.exe        (via PyInstaller + Inno Setup)
    installers/macos/viewYUV.dmg                (via PyInstaller + hdiutil)
    installers/linux/viewYUV-x86_64.AppImage    (via PyInstaller + appimagetool)

Falls back to a plain portable binary/archive on macOS/Linux if hdiutil /
appimagetool aren't installed, rather than failing outright.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
INSTALLERS = ROOT / "installers"
RESOURCES = ROOT / "resources"
APP_NAME = "viewYUV"
DISPLAY_NAME = "YUView-lite"


def run(cmd: list, **kwargs) -> None:
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, **kwargs)


def clean() -> None:
    for d in (DIST, BUILD):
        if d.exists():
            shutil.rmtree(d)


def run_pyinstaller(bundle_icon: Path | None) -> None:
    """bundle_icon controls PyInstaller's --icon (the OS's file/bundle icon,
    e.g. Explorer/Finder/Dock) -- format must match the OS (.ico/.icns).
    The runtime window/taskbar icon is separate: __main__.py loads
    resources/icon.ico via Qt, which reads .ico fine on every OS, so that
    file is always bundled as a data file regardless of platform.
    """
    system = platform.system()
    data_sep = ";" if system == "Windows" else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--windowed", "--name", APP_NAME,
        "-p", str(ROOT / "src"),
        "--add-data", f"{RESOURCES / 'icon.ico'}{data_sep}resources",
    ]
    if bundle_icon:
        cmd += ["--icon", str(bundle_icon)]
    if system != "Darwin":  # macOS wants a .app directory bundle, not a single file
        cmd.append("--onefile")
    cmd.append(str(ROOT / "scripts" / "pyinstaller_entry.py"))
    run(cmd, cwd=ROOT)


def build_windows() -> None:
    run_pyinstaller(RESOURCES / "icon.ico")
    out_dir = INSTALLERS / "windows"
    out_dir.mkdir(parents=True, exist_ok=True)

    iscc_candidates = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe",
        shutil.which("ISCC.exe") or "",
    ]
    iscc = next((p for p in iscc_candidates if p and Path(p).exists()), None)
    if iscc is None:
        print("Inno Setup (ISCC.exe) not found -- copying the portable .exe instead of building an installer.")
        print("Install it with: winget install JRSoftware.InnoSetup")
        shutil.copy2(DIST / f"{APP_NAME}.exe", out_dir / f"{APP_NAME}.exe")
        return

    run([str(iscc), str(ROOT / "scripts" / "build_installer.iss")])
    shutil.copy2(DIST / f"{APP_NAME}-Setup.exe", out_dir / f"{APP_NAME}-Setup.exe")
    print(f"\nWindows installer ready: {out_dir / f'{APP_NAME}-Setup.exe'}")


def build_macos() -> None:
    run_pyinstaller(RESOURCES / "icon.icns")
    app_bundle = DIST / f"{APP_NAME}.app"
    if not app_bundle.exists():
        raise SystemExit(f"expected {app_bundle} -- PyInstaller did not produce a .app bundle")

    out_dir = INSTALLERS / "macos"
    out_dir.mkdir(parents=True, exist_ok=True)

    if shutil.which("hdiutil") is None:
        dest = out_dir / f"{APP_NAME}.app"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(app_bundle, dest)
        print(f"hdiutil not found -- left the uncompressed .app bundle instead: {dest}")
        return

    dmg_path = out_dir / f"{APP_NAME}.dmg"
    dmg_path.unlink(missing_ok=True)
    staging = out_dir / "_dmg_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    shutil.copytree(app_bundle, staging / f"{DISPLAY_NAME}.app")
    (staging / "Applications").symlink_to("/Applications")

    run([
        "hdiutil", "create", "-volname", DISPLAY_NAME, "-srcfolder", str(staging),
        "-ov", "-format", "UDZO", str(dmg_path),
    ])
    shutil.rmtree(staging)
    print(f"\nmacOS installer ready: {dmg_path}")


def build_linux() -> None:
    run_pyinstaller(None)  # PyInstaller doesn't support --icon for plain ELF binaries
    binary = DIST / APP_NAME
    if not binary.exists():
        raise SystemExit(f"expected {binary} -- PyInstaller did not produce a Linux binary")

    out_dir = INSTALLERS / "linux"
    out_dir.mkdir(parents=True, exist_ok=True)

    appimagetool = shutil.which("appimagetool")
    if appimagetool is None:
        archive = out_dir / f"{APP_NAME}-linux-x86_64.tar.gz"
        run(["tar", "-czf", str(archive), "-C", str(DIST), APP_NAME])
        print(f"appimagetool not found -- wrote a plain archive instead: {archive}")
        print("Install appimagetool (https://github.com/AppImage/AppImageKit) for a double-clickable AppImage.")
        return

    appdir = out_dir / "AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    (appdir / "usr" / "bin").mkdir(parents=True)
    shutil.copy2(binary, appdir / "usr" / "bin" / APP_NAME)
    shutil.copy2(RESOURCES / "viewYUV.desktop", appdir / f"{APP_NAME}.desktop")
    shutil.copy2(ROOT / "logo" / "viewYUV.png", appdir / f"{APP_NAME}.png")
    (appdir / "AppRun").symlink_to(Path("usr/bin") / APP_NAME)

    appimage_path = out_dir / f"{APP_NAME}-x86_64.AppImage"
    run([appimagetool, str(appdir), str(appimage_path)])
    shutil.rmtree(appdir)
    print(f"\nLinux installer ready: {appimage_path}")


def main() -> None:
    clean()
    system = platform.system()
    if system == "Windows":
        build_windows()
    elif system == "Darwin":
        build_macos()
    elif system == "Linux":
        build_linux()
    else:
        raise SystemExit(f"unsupported platform: {system}")


if __name__ == "__main__":
    main()
