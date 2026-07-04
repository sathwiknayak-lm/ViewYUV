"""PSNR and SSIM metrics for comparing two frames/planes."""

from __future__ import annotations

import numpy as np
from skimage.metrics import structural_similarity


def psnr(a: np.ndarray, b: np.ndarray, max_val: float = 255.0) -> float:
    """Peak signal-to-noise ratio in dB. Returns inf when a == b exactly."""
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    mse = np.mean((a - b) ** 2)
    if mse == 0:
        return float("inf")
    return 10.0 * np.log10((max_val**2) / mse)


def ssim(a: np.ndarray, b: np.ndarray, max_val: float = 255.0) -> float:
    """Structural similarity index between two 2D (grayscale) or 3D (H,W,C) arrays."""
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    channel_axis = -1 if a.ndim == 3 else None
    return float(
        structural_similarity(a, b, data_range=max_val, channel_axis=channel_axis)
    )
