"""Cross-check our pixel math against ffmpeg's own decode + psnr/ssim filters.

Per PROMPT.md: for I420 and NV12, 8-bit, BT.601 limited range, our
YUV->RGB conversion and PSNR/SSIM must agree with ffmpeg within a small
tolerance. These tests shell out to ffmpeg (dev-machine only, never a
runtime dependency of the app) and are skipped if ffmpeg isn't on PATH.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gen_test_yuv import (  # noqa: E402
    downsample_chroma,
    make_rgb_frame,
    pack_frame,
    rgb_to_yuv444_bt601_limited,
)
from yuvviewer.colorconvert import ColorMatrix, ColorRange, yuv_to_rgb  # noqa: E402
from yuvviewer.formats import PixelFormat, YuvFormat  # noqa: E402
from yuvviewer.metrics import psnr as our_psnr  # noqa: E402
from yuvviewer.metrics import ssim as our_ssim  # noqa: E402

FFMPEG = shutil.which("ffmpeg")

pytestmark = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not available on PATH")


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return result


def _make_planes(fmt: YuvFormat, frame_idx: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rgb = make_rgb_frame(fmt.width, fmt.height, frame_idx)
    y, u_full, v_full = rgb_to_yuv444_bt601_limited(rgb)
    h_sub, v_sub = fmt.chroma_subsampling
    if (h_sub, v_sub) == (1, 1):
        return y, u_full, v_full
    return y, downsample_chroma(u_full, h_sub, v_sub), downsample_chroma(v_full, h_sub, v_sub)


@pytest.mark.parametrize("pixel_format", [PixelFormat.I420, PixelFormat.NV12])
def test_yuv_to_rgb_matches_ffmpeg(tmp_path: Path, pixel_format: PixelFormat):
    width, height = 64, 48
    fmt = YuvFormat(pixel_format=pixel_format, width=width, height=height, bit_depth=8)

    y, u, v = _make_planes(fmt, frame_idx=0)
    yuv_path = tmp_path / "frame.yuv"
    yuv_path.write_bytes(pack_frame(y, u, v, fmt))

    ffmpeg_pix_fmt = {"I420": "yuv420p", "NV12": "nv12"}[pixel_format.value]
    rgb_path = tmp_path / "frame.rgb"
    _run(
        [
            FFMPEG,
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            ffmpeg_pix_fmt,
            "-s",
            f"{width}x{height}",
            "-i",
            str(yuv_path),
            "-sws_flags",
            "neighbor",
            "-vf",
            "scale=in_color_matrix=bt601:in_range=tv",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            str(rgb_path),
        ]
    )
    ffmpeg_rgb = np.frombuffer(rgb_path.read_bytes(), dtype=np.uint8).reshape(height, width, 3)

    our_rgb = yuv_to_rgb(y, u, v, bit_depth=8, matrix=ColorMatrix.BT601, color_range=ColorRange.LIMITED)

    # ffmpeg's swscale uses internal fixed-point coefficient tables rather than
    # our floating-point ITU coefficients, so a few pixels land +-1-2 LSB apart
    # (rounding, not a wrong matrix) -- PSNR is the right way to bound that.
    diff = np.abs(ffmpeg_rgb.astype(int) - our_rgb.astype(int))
    assert diff.max() <= 3, f"max abs diff {diff.max()} exceeds tolerance"
    assert our_psnr(ffmpeg_rgb, our_rgb) >= 40.0


def test_psnr_matches_ffmpeg(tmp_path: Path):
    width, height = 64, 48
    fmt = YuvFormat(pixel_format=PixelFormat.I420, width=width, height=height, bit_depth=8)
    y_a, _, _ = _make_planes(fmt, frame_idx=0)
    y_b, _, _ = _make_planes(fmt, frame_idx=1)  # moving stripe -> genuine differences

    a_path, b_path = tmp_path / "a.gray", tmp_path / "b.gray"
    a_path.write_bytes(y_a.tobytes())
    b_path.write_bytes(y_b.tobytes())

    result = _run(
        [
            FFMPEG,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-s",
            f"{width}x{height}",
            "-i",
            str(a_path),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-s",
            f"{width}x{height}",
            "-i",
            str(b_path),
            "-lavfi",
            "psnr",
            "-f",
            "null",
            "-",
        ]
    )
    stderr = result.stderr.decode(errors="replace")
    match = re.search(r"PSNR.*?y:([\d.]+|inf)", stderr)
    assert match, f"could not parse ffmpeg psnr output:\n{stderr}"
    ffmpeg_psnr = float("inf") if match.group(1) == "inf" else float(match.group(1))

    mine = our_psnr(y_a, y_b)
    assert abs(mine - ffmpeg_psnr) < 0.1


def test_ssim_matches_ffmpeg(tmp_path: Path):
    width, height = 64, 48
    fmt = YuvFormat(pixel_format=PixelFormat.I420, width=width, height=height, bit_depth=8)
    y_a, _, _ = _make_planes(fmt, frame_idx=0)
    y_b, _, _ = _make_planes(fmt, frame_idx=1)

    a_path, b_path = tmp_path / "a.gray", tmp_path / "b.gray"
    a_path.write_bytes(y_a.tobytes())
    b_path.write_bytes(y_b.tobytes())

    result = _run(
        [
            FFMPEG,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-s",
            f"{width}x{height}",
            "-i",
            str(a_path),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-s",
            f"{width}x{height}",
            "-i",
            str(b_path),
            "-lavfi",
            "ssim",
            "-f",
            "null",
            "-",
        ]
    )
    stderr = result.stderr.decode(errors="replace")
    match = re.search(r"SSIM.*?Y:([\d.]+)", stderr)
    assert match, f"could not parse ffmpeg ssim output:\n{stderr}"
    ffmpeg_ssim = float(match.group(1))

    # ffmpeg's ssim filter uses non-overlapping 8x8 block averaging (the
    # codec-community convention popularized by x264/x265), while
    # skimage.metrics.structural_similarity uses a sliding Gaussian/uniform
    # window (the original Wang et al. image-quality convention). Both are
    # correct implementations of SSIM, they just use different windowing, so
    # we only check they land in the same ballpark rather than bit-match.
    mine = our_ssim(y_a, y_b)
    assert abs(mine - ffmpeg_ssim) < 0.06
