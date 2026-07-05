# YUView-lite

A small cross-platform (Windows / Linux / macOS) desktop tool for viewing and
comparing raw, headerless YUV video files -- built to validate a custom YUV
downscaling algorithm by inspecting pixel-exact output and A/B metrics.

Not a fork of YUView or any other viewer; built from scratch in Python.

## Features

- Raw YUV decoding: I420, YV12, NV12, NV21, I422, I444, 8-bit and 10-bit
  (unpacked little-endian).
- BT.601 / BT.709 color matrices, limited or full range.
- Frame navigation (slider, prev/next, jump-to-frame), play/pause with
  adjustable FPS. Decoding runs on a worker thread and drops frames under
  load rather than blocking the UI.
- Channel isolation: full color / Y / U / V.
- Zoom (mouse wheel), pan (click-drag), fit-to-window, 100%, and a status
  bar showing cursor position + raw Y/U/V values.
- Compare two files (independent resolutions/formats): side-by-side, a
  false-color diff/heatmap, and a draggable A/B wipe view. Spacebar
  toggles A/B in single view.
- Live PSNR/SSIM per frame, plus a whole-clip pass with min/max/average
  and a per-frame line chart.
- Export the current view as PNG.

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Run

```bash
python -m yuvviewer
```

## Building an installer

One script, same command on every OS:

```bash
pip install pyinstaller
python scripts/build_all.py
```

It detects the OS it's running on and produces that OS's installer under
`installers/`:

| Platform | Output | Built via |
|---|---|---|
| Windows | `installers/windows/viewYUV-Setup.exe` | PyInstaller + [Inno Setup](https://jrsoftware.org/isinfo.php) |
| macOS | `installers/macos/viewYUV.dmg` | PyInstaller + `hdiutil` |
| Linux | `installers/linux/viewYUV-x86_64.AppImage` | PyInstaller + [appimagetool](https://github.com/AppImage/AppImageKit) |

Each is a normal installer for that OS -- Start Menu/Applications
entry, an icon, and (Windows/macOS) an uninstaller. If the optional
packaging tool (Inno Setup / `hdiutil` / `appimagetool`) isn't
installed, the script falls back to producing a portable binary/archive
instead of failing outright, and tells you what to install for the full
installer.

**Important: there's no cross-compiling.** PyInstaller bundles a native
binary for whatever OS it runs on, so a Windows machine can only ever
produce the Windows installer, a Mac only the macOS one, and so on.
Run `python scripts/build_all.py` once on each OS you want to support
and collect the results from `installers/` -- the command itself is
identical everywhere, you just need to run it three times on three
different machines to get all three installers.

`build/`, `dist/`, and `installers/` are all gitignored; rebuild
locally rather than committing binaries.

If you only want the portable single-file exe without an installer
wrapper (e.g. for a quick internal test), the underlying PyInstaller
command scripts/build_all.py runs is also documented at the top of
that file.

## Test

```bash
pytest
```

`tests/test_against_ffmpeg.py` cross-checks the YUV->RGB conversion and
PSNR/SSIM against ffmpeg's own decode and `psnr`/`ssim` filters. It's
skipped automatically if `ffmpeg` isn't on `PATH` -- it is a dev/test-only
dependency, never required at runtime.

## Generating test clips

```bash
python scripts/gen_test_yuv.py sample.yuv --format I420 --width 320 --height 240 --num-frames 30
```

## Project layout

```
src/yuvviewer/
  formats.py       raw YUV layouts, frame-size math, byte parsing
  colorconvert.py  YUV -> RGB (BT.601/709, limited/full range)
  metrics.py       PSNR, SSIM
  yuv_file.py      file + format -> frame(N) -> numpy planes
  render.py        frame -> displayable RGB, diff heatmap, wipe composite
  ui/              PySide6 widgets (main window, viewers, dialogs, workers)
tests/             pytest suite, incl. ffmpeg cross-checks
scripts/           synthetic YUV test-pattern generator
```

## Notes

- 10-bit support assumes unpacked little-endian 16-bit samples (0-1023),
  the common raw-test-stream convention. Packed formats (v210 etc.) are
  out of scope.
- No video codec (h264/hevc) support -- raw YUV only.
- Chroma upsampling for display/compare uses nearest-neighbor (matches
  `ffmpeg -sws_flags neighbor`), not bilinear -- fast and exactly
  reproducible for the accuracy tests.
