"""Raw YUV pixel format definitions and byte-layout parsing.

Raw YUV files have no header, so width/height/format/bit-depth must be
supplied by the caller. This module defines the supported layouts and
converts a raw frame's bytes into separate Y/U/V numpy planes, at their
*native* (possibly chroma-subsampled) resolution -- upsampling to full
resolution for display/RGB conversion happens in colorconvert.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class PixelFormat(Enum):
    I420 = "I420"  # planar Y, U(w/2,h/2), V(w/2,h/2)
    YV12 = "YV12"  # planar Y, V(w/2,h/2), U(w/2,h/2)
    NV12 = "NV12"  # planar Y, interleaved UV(w,h/2)
    NV21 = "NV21"  # planar Y, interleaved VU(w,h/2)
    I422 = "I422"  # planar Y, U(w/2,h), V(w/2,h)
    I444 = "I444"  # planar Y, U(w,h), V(w,h)


# Chroma subsampling factor (horizontal, vertical) relative to luma, per format.
_CHROMA_SUBSAMPLING = {
    PixelFormat.I420: (2, 2),
    PixelFormat.YV12: (2, 2),
    PixelFormat.NV12: (2, 2),
    PixelFormat.NV21: (2, 2),
    PixelFormat.I422: (2, 1),
    PixelFormat.I444: (1, 1),
}

BIT_DEPTHS = (8, 10)


@dataclass(frozen=True)
class YuvFormat:
    """Describes how to interpret a raw YUV file's bytes."""

    pixel_format: PixelFormat
    width: int
    height: int
    bit_depth: int = 8  # 8 or 10 (10-bit is unpacked, little-endian 16-bit samples)

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        if self.bit_depth not in BIT_DEPTHS:
            raise ValueError(f"unsupported bit depth: {self.bit_depth}")
        h_sub, v_sub = _CHROMA_SUBSAMPLING[self.pixel_format]
        if self.width % h_sub != 0 or self.height % v_sub != 0:
            raise ValueError(
                f"{self.pixel_format.value} requires width/height divisible by "
                f"{h_sub}/{v_sub} (got {self.width}x{self.height})"
            )

    @property
    def chroma_subsampling(self) -> tuple[int, int]:
        return _CHROMA_SUBSAMPLING[self.pixel_format]

    @property
    def chroma_width(self) -> int:
        h_sub, _ = self.chroma_subsampling
        return self.width // h_sub

    @property
    def chroma_height(self) -> int:
        _, v_sub = self.chroma_subsampling
        return self.height // v_sub

    @property
    def bytes_per_sample(self) -> int:
        return 1 if self.bit_depth == 8 else 2

    @property
    def frame_size(self) -> int:
        """Total bytes for one frame, per the formulas in PROMPT.md."""
        luma_samples = self.width * self.height
        chroma_samples = 2 * self.chroma_width * self.chroma_height
        return (luma_samples + chroma_samples) * self.bytes_per_sample

    @property
    def dtype(self) -> np.dtype:
        return np.dtype(np.uint8) if self.bit_depth == 8 else np.dtype("<u2")


def frame_count_for_file(file_size: int, fmt: YuvFormat) -> tuple[int, bool]:
    """Return (frame_count, is_truncated) for a file of the given size."""
    if fmt.frame_size == 0:
        return 0, False
    count, remainder = divmod(file_size, fmt.frame_size)
    return count, remainder != 0


def parse_frame(data: bytes, fmt: YuvFormat) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Parse one frame's raw bytes into (Y, U, V) planes at native resolution.

    Y is always (height, width). U/V are (chroma_height, chroma_width) except
    for formats with no subsampling, where they match Y's shape.
    """
    expected = fmt.frame_size
    if len(data) < expected:
        raise ValueError(f"frame data too short: got {len(data)} bytes, need {expected}")

    dtype = fmt.dtype
    w, h = fmt.width, fmt.height
    cw, ch = fmt.chroma_width, fmt.chroma_height

    samples = np.frombuffer(data, dtype=dtype, count=w * h + 2 * cw * ch)

    y = samples[: w * h].reshape(h, w)
    rest = samples[w * h :]

    pf = fmt.pixel_format
    if pf in (PixelFormat.I420, PixelFormat.I422, PixelFormat.I444):
        u_count = cw * ch
        u = rest[:u_count].reshape(ch, cw)
        v = rest[u_count : 2 * u_count].reshape(ch, cw)
    elif pf == PixelFormat.YV12:
        v_count = cw * ch
        v = rest[:v_count].reshape(ch, cw)
        u = rest[v_count : 2 * v_count].reshape(ch, cw)
    elif pf == PixelFormat.NV12:
        interleaved = rest.reshape(ch, cw, 2)
        u = interleaved[:, :, 0]
        v = interleaved[:, :, 1]
    elif pf == PixelFormat.NV21:
        interleaved = rest.reshape(ch, cw, 2)
        v = interleaved[:, :, 0]
        u = interleaved[:, :, 1]
    else:  # pragma: no cover - exhaustive over PixelFormat
        raise ValueError(f"unhandled pixel format: {pf}")

    return y, u, v
