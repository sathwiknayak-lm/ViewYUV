"""Whole-clip PSNR/SSIM computation, run on a worker thread with progress reporting."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..formats import YuvFormat
from ..metrics import psnr, ssim
from ..render import resize_nearest
from ..yuv_file import YuvFile


class ClipMetricsWorker(QObject):
    progress = Signal(int, int)  # current, total
    finished = Signal(dict)

    def __init__(self, path_a: str, fmt_a: YuvFormat, path_b: str, fmt_b: YuvFormat):
        super().__init__()
        self._path_a = path_a
        self._fmt_a = fmt_a
        self._path_b = path_b
        self._fmt_b = fmt_b
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        # Independent file handles from the live-preview ones to avoid cross-thread contention.
        file_a = YuvFile(self._path_a, self._fmt_a)
        file_b = YuvFile(self._path_b, self._fmt_b)
        try:
            total = max(file_a.frame_count, file_b.frame_count)
            psnr_values: list[float] = []
            ssim_values: list[float] = []
            for i in range(total):
                if self._cancel_requested:
                    break
                idx_a = round(i * (file_a.frame_count - 1) / (total - 1)) if total > 1 else 0
                idx_b = round(i * (file_b.frame_count - 1) / (total - 1)) if total > 1 else 0
                frame_a = file_a.read_frame(idx_a)
                frame_b = file_b.read_frame(idx_b)
                y_a, y_b = frame_a.y, frame_b.y
                if y_a.shape != y_b.shape:
                    y_b = resize_nearest(y_b, y_a.shape)
                psnr_values.append(psnr(y_a, y_b))
                ssim_values.append(ssim(y_a, y_b))
                if i % 5 == 0 or i == total - 1:
                    self.progress.emit(i + 1, total)

            finite_psnr = [v for v in psnr_values if v != float("inf")]
            result = {
                "cancelled": self._cancel_requested,
                "psnr_values": psnr_values,
                "ssim_values": ssim_values,
                "psnr_min": min(finite_psnr) if finite_psnr else float("inf"),
                "psnr_max": max(finite_psnr) if finite_psnr else float("inf"),
                "psnr_avg": sum(finite_psnr) / len(finite_psnr) if finite_psnr else float("inf"),
                "ssim_min": min(ssim_values) if ssim_values else 0.0,
                "ssim_max": max(ssim_values) if ssim_values else 0.0,
                "ssim_avg": sum(ssim_values) / len(ssim_values) if ssim_values else 0.0,
            }
        finally:
            file_a.close()
            file_b.close()
        self.finished.emit(result)
