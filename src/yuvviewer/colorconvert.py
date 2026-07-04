"""YUV -> RGB color conversion.

Matrix coefficients (BT.601 / BT.709, limited / full range) are the
standard ITU-R coefficients as used by ffmpeg's swscale and documented in
ITU-R BT.601-7 / BT.709-6:

    Limited range (Y: 16-235, Cb/Cr: 16-240, at 8-bit):
        BT.601: R = 1.164*(Y-16)                 + 1.596*(Cr-128)
                G = 1.164*(Y-16) - 0.392*(Cb-128) - 0.813*(Cr-128)
                B = 1.164*(Y-16) + 2.017*(Cb-128)
        BT.709: R = 1.164*(Y-16)                 + 1.793*(Cr-128)
                G = 1.164*(Y-16) - 0.213*(Cb-128) - 0.533*(Cr-128)
                B = 1.164*(Y-16) + 2.112*(Cb-128)

    Full range (Y/Cb/Cr: 0-255, at 8-bit):
        BT.601: R = Y                 + 1.402*(Cr-128)
                G = Y - 0.344*(Cb-128) - 0.714*(Cr-128)
                B = Y + 1.772*(Cb-128)
        BT.709: R = Y                 + 1.5748*(Cr-128)
                G = Y - 0.1873*(Cb-128) - 0.4681*(Cr-128)
                B = Y + 1.8556*(Cb-128)

For bit depths above 8, samples are unpacked 16-bit little-endian with the
same 0-1023 (10-bit) range convention; the offsets/scale above are simply
scaled by 2**(bit_depth-8) since they are affine in the raw sample value.

Chroma upsampling uses nearest-neighbor (pixel repeat) rather than
bilinear, matching `ffmpeg -sws_flags neighbor` -- this keeps our output
exactly reproducible against ffmpeg for the accuracy-validation tests, and
is fast (a pure numpy repeat, no interpolation).
"""

from __future__ import annotations

from enum import Enum

import numpy as np

# (Kr, Kg_cb, Kg_cr, Kb) coefficients per matrix, at 8-bit limited-range scale.
_LIMITED_COEFFS = {
    "601": (1.596, -0.392, -0.813, 2.017),
    "709": (1.793, -0.213, -0.533, 2.112),
}
_LUMA_GAIN_LIMITED = 1.164

_FULL_COEFFS = {
    "601": (1.402, -0.344, -0.714, 1.772),
    "709": (1.5748, -0.1873, -0.4681, 1.8556),
}


class ColorMatrix(Enum):
    BT601 = "601"
    BT709 = "709"


class ColorRange(Enum):
    LIMITED = "limited"
    FULL = "full"


def _upsample_chroma(plane: np.ndarray, target_shape: tuple[int, int]) -> np.ndarray:
    """Nearest-neighbor upsample a chroma plane to target (h, w)."""
    h, w = plane.shape
    th, tw = target_shape
    if (h, w) == (th, tw):
        return plane
    v_factor = th // h
    h_factor = tw // w
    out = np.repeat(np.repeat(plane, v_factor, axis=0), h_factor, axis=1)
    return out[:th, :tw]


def yuv_to_rgb(
    y: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    bit_depth: int = 8,
    matrix: ColorMatrix = ColorMatrix.BT601,
    color_range: ColorRange = ColorRange.LIMITED,
) -> np.ndarray:
    """Convert YUV planes (chroma may be subsampled) to an 8-bit RGB image.

    Returns an (H, W, 3) uint8 array. Chroma planes are upsampled to Y's
    resolution first if needed.
    """
    scale = 1 << (bit_depth - 8)  # 1 for 8-bit, 4 for 10-bit
    h, w = y.shape

    u_full = _upsample_chroma(u, (h, w)).astype(np.float32)
    v_full = _upsample_chroma(v, (h, w)).astype(np.float32)
    y_f = y.astype(np.float32)

    matrix_key = matrix.value
    if color_range is ColorRange.LIMITED:
        y_off = 16 * scale
        c_off = 128 * scale
        kr, kg_cb, kg_cr, kb = _LIMITED_COEFFS[matrix_key]
        y_term = _LUMA_GAIN_LIMITED * (y_f - y_off)
        r = y_term + kr * (v_full - c_off)
        g = y_term + kg_cb * (u_full - c_off) + kg_cr * (v_full - c_off)
        b = y_term + kb * (u_full - c_off)
    else:
        c_off = 128 * scale
        kr, kg_cb, kg_cr, kb = _FULL_COEFFS[matrix_key]
        r = y_f + kr * (v_full - c_off)
        g = y_f + kg_cb * (u_full - c_off) + kg_cr * (v_full - c_off)
        b = y_f + kb * (u_full - c_off)

    rgb = np.stack([r, g, b], axis=-1) / scale
    return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)


def y_to_grayscale(y: np.ndarray, bit_depth: int = 8, color_range: ColorRange = ColorRange.LIMITED) -> np.ndarray:
    """Render the Y plane alone as an 8-bit grayscale RGB image."""
    scale = 1 << (bit_depth - 8)
    y_f = y.astype(np.float32) / scale
    if color_range is ColorRange.LIMITED:
        y_f = (y_f - 16) * (255.0 / 219.0)
    gray = np.clip(np.rint(y_f), 0, 255).astype(np.uint8)
    return np.stack([gray, gray, gray], axis=-1)


def chroma_to_grayscale(plane: np.ndarray, target_shape: tuple[int, int], bit_depth: int = 8) -> np.ndarray:
    """Render a U or V plane alone as an 8-bit grayscale RGB image (raw sample value, no offset)."""
    scale = 1 << (bit_depth - 8)
    full = _upsample_chroma(plane, target_shape).astype(np.float32) / scale
    gray = np.clip(np.rint(full), 0, 255).astype(np.uint8)
    return np.stack([gray, gray, gray], axis=-1)
