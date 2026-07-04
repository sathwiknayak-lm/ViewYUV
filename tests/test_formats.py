import numpy as np
import pytest

from yuvviewer.formats import PixelFormat, YuvFormat, frame_count_for_file, parse_frame


@pytest.mark.parametrize(
    "pixel_format,width,height,bit_depth,expected",
    [
        (PixelFormat.I420, 4, 2, 8, 4 * 2 * 3 // 2),
        (PixelFormat.YV12, 4, 2, 8, 4 * 2 * 3 // 2),
        (PixelFormat.NV12, 4, 2, 8, 4 * 2 * 3 // 2),
        (PixelFormat.NV21, 4, 2, 8, 4 * 2 * 3 // 2),
        (PixelFormat.I422, 4, 2, 8, 4 * 2 * 2),
        (PixelFormat.I444, 4, 2, 8, 4 * 2 * 3),
        (PixelFormat.I420, 4, 2, 10, 4 * 2 * 3),  # doubled for 16-bit samples
    ],
)
def test_frame_size(pixel_format, width, height, bit_depth, expected):
    fmt = YuvFormat(pixel_format=pixel_format, width=width, height=height, bit_depth=bit_depth)
    assert fmt.frame_size == expected


def test_frame_count_exact():
    fmt = YuvFormat(pixel_format=PixelFormat.I420, width=4, height=2)
    count, truncated = frame_count_for_file(fmt.frame_size * 3, fmt)
    assert count == 3
    assert not truncated


def test_frame_count_truncated_warns():
    fmt = YuvFormat(pixel_format=PixelFormat.I420, width=4, height=2)
    count, truncated = frame_count_for_file(fmt.frame_size * 3 + 5, fmt)
    assert count == 3
    assert truncated


def test_invalid_dimensions_for_subsampling():
    with pytest.raises(ValueError):
        YuvFormat(pixel_format=PixelFormat.I420, width=3, height=2)


def test_parse_frame_i420_planar_layout():
    w, h = 4, 2
    fmt = YuvFormat(pixel_format=PixelFormat.I420, width=w, height=h)
    y_plane = np.arange(w * h, dtype=np.uint8)
    u_plane = np.full((h // 2, w // 2), 100, dtype=np.uint8)
    v_plane = np.full((h // 2, w // 2), 200, dtype=np.uint8)
    data = y_plane.tobytes() + u_plane.tobytes() + v_plane.tobytes()

    y, u, v = parse_frame(data, fmt)
    assert np.array_equal(y, y_plane.reshape(h, w))
    assert np.all(u == 100)
    assert np.all(v == 200)


def test_parse_frame_yv12_swaps_u_and_v_vs_i420():
    w, h = 4, 2
    fmt = YuvFormat(pixel_format=PixelFormat.YV12, width=w, height=h)
    y_plane = np.zeros(w * h, dtype=np.uint8)
    v_plane = np.full((h // 2, w // 2), 111, dtype=np.uint8)
    u_plane = np.full((h // 2, w // 2), 222, dtype=np.uint8)
    data = y_plane.tobytes() + v_plane.tobytes() + u_plane.tobytes()

    y, u, v = parse_frame(data, fmt)
    assert np.all(u == 222)
    assert np.all(v == 111)


def test_parse_frame_nv12_interleaved():
    w, h = 4, 2
    fmt = YuvFormat(pixel_format=PixelFormat.NV12, width=w, height=h)
    y_plane = np.zeros(w * h, dtype=np.uint8)
    interleaved = np.empty((h // 2, w // 2, 2), dtype=np.uint8)
    interleaved[..., 0] = 10  # U
    interleaved[..., 1] = 20  # V
    data = y_plane.tobytes() + interleaved.tobytes()

    y, u, v = parse_frame(data, fmt)
    assert np.all(u == 10)
    assert np.all(v == 20)


def test_parse_frame_nv21_interleaved_swapped():
    w, h = 4, 2
    fmt = YuvFormat(pixel_format=PixelFormat.NV21, width=w, height=h)
    y_plane = np.zeros(w * h, dtype=np.uint8)
    interleaved = np.empty((h // 2, w // 2, 2), dtype=np.uint8)
    interleaved[..., 0] = 30  # V
    interleaved[..., 1] = 40  # U
    data = y_plane.tobytes() + interleaved.tobytes()

    y, u, v = parse_frame(data, fmt)
    assert np.all(u == 40)
    assert np.all(v == 30)


def test_parse_frame_too_short_raises():
    fmt = YuvFormat(pixel_format=PixelFormat.I420, width=4, height=2)
    with pytest.raises(ValueError):
        parse_frame(b"\x00" * (fmt.frame_size - 1), fmt)


def test_10bit_uses_little_endian_u16():
    w, h = 2, 2
    fmt = YuvFormat(pixel_format=PixelFormat.I444, width=w, height=h, bit_depth=10)
    y_plane = np.array([1000, 512, 0, 1023], dtype="<u2").reshape(h, w)
    u_plane = np.full((h, w), 512, dtype="<u2")
    v_plane = np.full((h, w), 512, dtype="<u2")
    data = y_plane.tobytes() + u_plane.tobytes() + v_plane.tobytes()

    y, u, v = parse_frame(data, fmt)
    assert np.array_equal(y, y_plane)
