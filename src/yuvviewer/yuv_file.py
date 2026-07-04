"""Wraps a raw YUV file + its format spec, exposing per-frame plane access."""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from .formats import YuvFormat, frame_count_for_file, parse_frame


@dataclass(frozen=True)
class Frame:
    index: int
    y: np.ndarray
    u: np.ndarray
    v: np.ndarray


class YuvFile:
    """Random-access reader over a raw YUV file."""

    def __init__(self, path: str, fmt: YuvFormat):
        self.path = path
        self.fmt = fmt
        self._file_size = os.path.getsize(path)
        self.frame_count, self.is_truncated = frame_count_for_file(self._file_size, fmt)
        self._fh = open(path, "rb", buffering=0)

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> "YuvFile":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def read_frame(self, index: int) -> Frame:
        if index < 0 or index >= self.frame_count:
            raise IndexError(f"frame {index} out of range (0..{self.frame_count - 1})")
        offset = index * self.fmt.frame_size
        self._fh.seek(offset)
        data = self._fh.read(self.fmt.frame_size)
        y, u, v = parse_frame(data, self.fmt)
        return Frame(index=index, y=y, u=u, v=v)
