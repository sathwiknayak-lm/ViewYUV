import numpy as np
import pytest

from yuvviewer.colorconvert import ColorMatrix, ColorRange, yuv_to_rgb


def _solid(value, shape=(2, 2)):
    return np.full(shape, value, dtype=np.uint8)


@pytest.mark.parametrize("matrix", [ColorMatrix.BT601, ColorMatrix.BT709])
def test_limited_range_black_and_white(matrix):
    black = yuv_to_rgb(_solid(16), _solid(128), _solid(128), matrix=matrix, color_range=ColorRange.LIMITED)
    white = yuv_to_rgb(_solid(235), _solid(128), _solid(128), matrix=matrix, color_range=ColorRange.LIMITED)
    assert np.all(black == 0)
    assert np.all(white == 255)


@pytest.mark.parametrize("matrix", [ColorMatrix.BT601, ColorMatrix.BT709])
def test_full_range_black_and_white(matrix):
    black = yuv_to_rgb(_solid(0), _solid(128), _solid(128), matrix=matrix, color_range=ColorRange.FULL)
    white = yuv_to_rgb(_solid(255), _solid(128), _solid(128), matrix=matrix, color_range=ColorRange.FULL)
    assert np.all(black == 0)
    assert np.all(white == 255)


def test_neutral_chroma_is_grayscale_regardless_of_matrix():
    for matrix in (ColorMatrix.BT601, ColorMatrix.BT709):
        rgb = yuv_to_rgb(_solid(128), _solid(128), _solid(128), matrix=matrix, color_range=ColorRange.LIMITED)
        assert rgb[..., 0].tolist() == rgb[..., 1].tolist() == rgb[..., 2].tolist()


def test_bt601_red_is_reddish():
    # Pure "red" chroma (max V, neutral U) should give a channel order R > G, R > B.
    rgb = yuv_to_rgb(_solid(81), _solid(90), _solid(240), matrix=ColorMatrix.BT601, color_range=ColorRange.LIMITED)
    r, g, b = int(rgb[0, 0, 0]), int(rgb[0, 0, 1]), int(rgb[0, 0, 2])
    assert r > g and r > b


def test_chroma_upsampling_nearest_neighbor_420():
    # 2x2 luma block should take on a single chroma value (nearest-neighbor, no blending).
    y = np.array([[16, 16], [16, 16]], dtype=np.uint8)
    u = np.array([[128]], dtype=np.uint8)
    v = np.array([[200]], dtype=np.uint8)
    rgb = yuv_to_rgb(y, u, v, matrix=ColorMatrix.BT601, color_range=ColorRange.LIMITED)
    assert rgb.shape == (2, 2, 3)
    # All 4 pixels should be identical since they share the same upsampled chroma.
    assert np.all(rgb == rgb[0, 0])


def test_10bit_matches_8bit_after_scaling():
    y8, u8, v8 = _solid(180), _solid(100), _solid(160)
    rgb8 = yuv_to_rgb(y8, u8, v8, bit_depth=8, matrix=ColorMatrix.BT601, color_range=ColorRange.LIMITED)

    y10 = (y8.astype("<u2")) * 4
    u10 = (u8.astype("<u2")) * 4
    v10 = (v8.astype("<u2")) * 4
    rgb10 = yuv_to_rgb(y10, u10, v10, bit_depth=10, matrix=ColorMatrix.BT601, color_range=ColorRange.LIMITED)

    assert np.abs(rgb8.astype(int) - rgb10.astype(int)).max() <= 1
