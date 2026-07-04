import numpy as np

from yuvviewer.metrics import psnr, ssim


def test_psnr_identical_is_infinite():
    a = np.random.default_rng(0).integers(0, 256, (32, 32), dtype=np.uint8)
    assert psnr(a, a) == float("inf")


def test_psnr_known_value():
    a = np.zeros((10, 10), dtype=np.uint8)
    b = np.full((10, 10), 10, dtype=np.uint8)  # constant error of 10 -> MSE = 100
    expected = 10.0 * np.log10((255.0**2) / 100.0)
    assert abs(psnr(a, b) - expected) < 1e-9


def test_psnr_decreases_with_more_noise():
    rng = np.random.default_rng(1)
    a = rng.integers(0, 256, (64, 64), dtype=np.uint8)
    small_noise = np.clip(a.astype(int) + rng.integers(-2, 3, a.shape), 0, 255).astype(np.uint8)
    big_noise = np.clip(a.astype(int) + rng.integers(-40, 41, a.shape), 0, 255).astype(np.uint8)
    assert psnr(a, small_noise) > psnr(a, big_noise)


def test_ssim_identical_is_one():
    a = np.random.default_rng(2).integers(0, 256, (32, 32), dtype=np.uint8)
    assert abs(ssim(a, a) - 1.0) < 1e-9


def test_ssim_decreases_with_more_noise():
    rng = np.random.default_rng(3)
    a = rng.integers(0, 256, (64, 64), dtype=np.uint8)
    small_noise = np.clip(a.astype(int) + rng.integers(-2, 3, a.shape), 0, 255).astype(np.uint8)
    big_noise = np.clip(a.astype(int) + rng.integers(-80, 81, a.shape), 0, 255).astype(np.uint8)
    assert ssim(a, small_noise) > ssim(a, big_noise)


def test_ssim_accepts_rgb():
    a = np.random.default_rng(4).integers(0, 256, (32, 32, 3), dtype=np.uint8)
    assert abs(ssim(a, a) - 1.0) < 1e-9
