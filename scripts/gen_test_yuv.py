"""Generate synthetic raw YUV test patterns for automated tests and manual QA.

Usage:
    python scripts/gen_test_yuv.py out.yuv --format I420 --width 64 --height 48

Produces deterministic, colorful frames (a moving gradient + color bars) so
that visual inspection and ffmpeg cross-checks have interesting, reproducible
content, not just flat fields.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from yuvviewer.formats import PixelFormat, YuvFormat  # noqa: E402


def make_rgb_frame(width: int, height: int, frame_idx: int) -> np.ndarray:
    """Deterministic RGB test pattern: color bars with a per-frame moving stripe."""
    bar_colors = np.array(
        [
            [235, 235, 235],  # white
            [235, 235, 16],  # yellow
            [16, 235, 235],  # cyan
            [16, 235, 16],  # green
            [235, 16, 235],  # magenta
            [235, 16, 16],  # red
            [16, 16, 235],  # blue
            [16, 16, 16],  # black
        ],
        dtype=np.uint8,
    )
    bar_width = max(1, width // len(bar_colors))
    rgb = np.zeros((height, width, 3), dtype=np.uint8)
    for i, color in enumerate(bar_colors):
        x0 = i * bar_width
        x1 = width if i == len(bar_colors) - 1 else (i + 1) * bar_width
        rgb[:, x0:x1] = color

    # A moving vertical stripe so successive frames differ (useful for playback tests).
    stripe_x = (frame_idx * 4) % width
    stripe_w = max(1, width // 32)
    x0 = stripe_x
    x1 = min(width, stripe_x + stripe_w)
    rgb[:, x0:x1] = [128, 128, 128]

    return rgb


def rgb_to_yuv444_bt601_limited(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reference forward conversion (RGB -> YUV), BT.601 limited range, for generating test inputs."""
    rgb_f = rgb.astype(np.float64)
    r, g, b = rgb_f[..., 0], rgb_f[..., 1], rgb_f[..., 2]
    y = 16 + 0.257 * r + 0.504 * g + 0.098 * b
    u = 128 - 0.148 * r - 0.291 * g + 0.439 * b
    v = 128 + 0.439 * r - 0.368 * g - 0.071 * b
    clip = lambda a: np.clip(np.rint(a), 0, 255).astype(np.uint8)  # noqa: E731
    return clip(y), clip(u), clip(v)


def downsample_chroma(plane: np.ndarray, h_factor: int, v_factor: int) -> np.ndarray:
    """Box-filter downsample by averaging h_factor x v_factor blocks."""
    h, w = plane.shape
    ch, cw = h // v_factor, w // h_factor
    reshaped = plane[: ch * v_factor, : cw * h_factor].astype(np.float64)
    reshaped = reshaped.reshape(ch, v_factor, cw, h_factor)
    return np.rint(reshaped.mean(axis=(1, 3))).astype(np.uint8)


def pack_frame(y: np.ndarray, u: np.ndarray, v: np.ndarray, fmt: YuvFormat) -> bytes:
    pf = fmt.pixel_format
    if pf == PixelFormat.I420 or pf == PixelFormat.I422 or pf == PixelFormat.I444:
        return y.tobytes() + u.tobytes() + v.tobytes()
    if pf == PixelFormat.YV12:
        return y.tobytes() + v.tobytes() + u.tobytes()
    if pf == PixelFormat.NV12:
        interleaved = np.stack([u, v], axis=-1)
        return y.tobytes() + interleaved.tobytes()
    if pf == PixelFormat.NV21:
        interleaved = np.stack([v, u], axis=-1)
        return y.tobytes() + interleaved.tobytes()
    raise ValueError(f"unhandled pixel format: {pf}")


def generate(fmt: YuvFormat, num_frames: int) -> bytes:
    h_sub, v_sub = fmt.chroma_subsampling
    out = bytearray()
    for i in range(num_frames):
        rgb = make_rgb_frame(fmt.width, fmt.height, i)
        y, u_full, v_full = rgb_to_yuv444_bt601_limited(rgb)
        if (h_sub, v_sub) == (1, 1):
            u, v = u_full, v_full
        else:
            u = downsample_chroma(u_full, h_sub, v_sub)
            v = downsample_chroma(v_full, h_sub, v_sub)
        if fmt.bit_depth == 10:
            y = y.astype("<u2") * 4
            u = u.astype("<u2") * 4
            v = v.astype("<u2") * 4
        out += pack_frame(y, u, v, fmt)
    return bytes(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--format", choices=[f.value for f in PixelFormat], default="I420")
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--height", type=int, default=48)
    parser.add_argument("--bit-depth", type=int, choices=[8, 10], default=8)
    parser.add_argument("--num-frames", type=int, default=5)
    args = parser.parse_args()

    fmt = YuvFormat(
        pixel_format=PixelFormat(args.format),
        width=args.width,
        height=args.height,
        bit_depth=args.bit_depth,
    )
    data = generate(fmt, args.num_frames)
    args.output.write_bytes(data)
    print(f"Wrote {len(data)} bytes ({args.num_frames} frames) to {args.output}")


if __name__ == "__main__":
    main()
