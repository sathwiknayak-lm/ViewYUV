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

## Building a standalone executable

For sharing with people who don't have Python installed, build a
double-clickable binary with [PyInstaller](https://pyinstaller.org):

```bash
pip install pyinstaller
# Windows:
pyinstaller --noconfirm --windowed --onefile --name viewYUV -p src ^
  --icon resources/icon.ico --add-data "resources/icon.ico;resources" ^
  scripts/pyinstaller_entry.py
# Linux/macOS (data-file separator is ':' instead of ';'):
pyinstaller --noconfirm --windowed --onefile --name viewYUV -p src \
  --icon resources/icon.ico --add-data "resources/icon.ico:resources" \
  scripts/pyinstaller_entry.py
```

The result is `dist/viewYUV.exe` (or the platform equivalent) -- a single
file with no Python/PySide6 install required on the target machine, with
the app icon baked into both the .exe file itself and the window/taskbar
icon at runtime. Zip it up and send it directly, or attach it to a
GitHub Release.

### Making it a "real" install (Start Menu shortcut, uninstaller)

Double-clicking `viewYUV.exe` just runs it directly (it's a portable
app, nothing is "installed"). If you want a proper installer -- Start
Menu entry, optional Desktop shortcut, and an uninstall entry in
Windows Settings -- see `scripts/build_installer.iss` (requires
[Inno Setup](https://jrsoftware.org/isinfo.php)):

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" scripts\build_installer.iss
```

This produces `dist/viewYUV-Setup.exe`, a normal Windows installer.

This has to be built separately on each OS you want to support -- a
Windows build only runs on Windows, a macOS build only on macOS, etc.
(no cross-compiling). `build/`, `dist/`, and `*.spec` are gitignored;
rebuild locally rather than committing the binary.

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
