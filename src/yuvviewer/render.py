"""Shared rendering helpers: frame -> displayable RGB array, diff heatmaps, colormaps."""

from __future__ import annotations

from enum import Enum

import numpy as np

from .colorconvert import ColorMatrix, ColorRange, chroma_to_grayscale, y_to_grayscale, yuv_to_rgb
from .yuv_file import Frame


class ChannelMode(Enum):
    FULL = "Full color"
    Y = "Y only"
    U = "U only"
    V = "V only"


def render_frame_rgb(
    frame: Frame,
    bit_depth: int,
    matrix: ColorMatrix,
    color_range: ColorRange,
    channel_mode: ChannelMode,
) -> np.ndarray:
    """Render a decoded Frame to an (H, W, 3) uint8 RGB array for display."""
    if channel_mode is ChannelMode.FULL:
        return yuv_to_rgb(frame.y, frame.u, frame.v, bit_depth=bit_depth, matrix=matrix, color_range=color_range)
    if channel_mode is ChannelMode.Y:
        return y_to_grayscale(frame.y, bit_depth=bit_depth, color_range=color_range)
    if channel_mode is ChannelMode.U:
        return chroma_to_grayscale(frame.u, frame.y.shape, bit_depth=bit_depth)
    if channel_mode is ChannelMode.V:
        return chroma_to_grayscale(frame.v, frame.y.shape, bit_depth=bit_depth)
    raise ValueError(f"unhandled channel mode: {channel_mode}")


# "Inferno"-style colormap: a short set of anchor colors interpolated to 256 entries.
_INFERNO_ANCHORS = np.array(
    [
        [0, 0, 4],
        [40, 11, 84],
        [101, 21, 110],
        [159, 42, 99],
        [212, 72, 66],
        [245, 125, 21],
        [250, 193, 39],
        [252, 255, 164],
    ],
    dtype=np.float32,
)


def _build_colormap(anchors: np.ndarray, size: int = 256) -> np.ndarray:
    positions = np.linspace(0, size - 1, len(anchors))
    xs = np.arange(size)
    r = np.interp(xs, positions, anchors[:, 0])
    g = np.interp(xs, positions, anchors[:, 1])
    b = np.interp(xs, positions, anchors[:, 2])
    return np.clip(np.stack([r, g, b], axis=-1), 0, 255).astype(np.uint8)


INFERNO_LUT = _build_colormap(_INFERNO_ANCHORS)


def resize_nearest(plane: np.ndarray, target_shape: tuple[int, int]) -> np.ndarray:
    """Nearest-neighbor resize a 2D (or H,W,C) array to target (h, w)."""
    h, w = plane.shape[:2]
    th, tw = target_shape
    if (h, w) == (th, tw):
        return plane
    row_idx = np.minimum((np.arange(th) * h // th), h - 1)
    col_idx = np.minimum((np.arange(tw) * w // tw), w - 1)
    return plane[row_idx][:, col_idx]


def diff_heatmap(a: np.ndarray, b: np.ndarray, colormap: np.ndarray = INFERNO_LUT) -> np.ndarray:
    """Per-pixel absolute difference rendered as a false-color heatmap.

    `a` and `b` must already be the same shape (resize before calling, and
    surface a "resized" notice in the UI when they weren't originally).
    Inputs may be 2D (single plane) or (H, W, C) -- multi-channel inputs are
    collapsed to a per-pixel magnitude (mean abs diff across channels) first.
    """
    a = a.astype(np.int32)
    b = b.astype(np.int32)
    diff = np.abs(a - b)
    if diff.ndim == 3:
        diff = diff.mean(axis=-1)
    max_val = max(int(diff.max()), 1)
    scaled = np.clip((diff.astype(np.float32) * 255.0 / max_val), 0, 255).astype(np.uint8)
    return colormap[scaled]


def wipe_composite(rgb_a: np.ndarray, rgb_b: np.ndarray, split_x: int) -> np.ndarray:
    """Composite A (left of split_x) and B (right of split_x) into one image."""
    h, w, _ = rgb_a.shape
    split_x = max(0, min(w, split_x))
    out = np.empty_like(rgb_a)
    out[:, :split_x] = rgb_a[:, :split_x]
    out[:, split_x:] = rgb_b[:, split_x:]
    return out
