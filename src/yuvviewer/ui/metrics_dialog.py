"""Dialog showing whole-clip PSNR/SSIM summary stats and per-frame line graphs."""

from __future__ import annotations

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QDialog, QLabel, QTabWidget, QVBoxLayout


def _make_chart_view(values: list[float], title: str, y_label: str) -> QChartView:
    series = QLineSeries()
    finite_values = [v if v != float("inf") else 0.0 for v in values]
    for i, v in enumerate(finite_values):
        series.append(i, v)

    chart = QChart()
    chart.addSeries(series)
    chart.setTitle(title)
    chart.legend().hide()

    axis_x = QValueAxis()
    axis_x.setTitleText("Frame")
    axis_x.setLabelFormat("%d")
    chart.addAxis(axis_x, Qt.AlignBottom)
    series.attachAxis(axis_x)

    axis_y = QValueAxis()
    axis_y.setTitleText(y_label)
    if finite_values:
        lo, hi = min(finite_values), max(finite_values)
        pad = (hi - lo) * 0.1 or 1.0
        axis_y.setRange(lo - pad, hi + pad)
    chart.addAxis(axis_y, Qt.AlignLeft)
    series.attachAxis(axis_y)

    view = QChartView(chart)
    view.setRenderHint(QPainter.Antialiasing)
    return view


class ClipMetricsDialog(QDialog):
    def __init__(self, result: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Clip Metrics")
        self.resize(720, 480)

        layout = QVBoxLayout(self)

        note = " (cancelled -- partial results)" if result.get("cancelled") else ""
        summary = QLabel(
            f"<b>PSNR (dB):</b> min {result['psnr_min']:.2f}  max {result['psnr_max']:.2f}  "
            f"avg {result['psnr_avg']:.2f}<br>"
            f"<b>SSIM:</b> min {result['ssim_min']:.4f}  max {result['ssim_max']:.4f}  "
            f"avg {result['ssim_avg']:.4f}{note}"
        )
        layout.addWidget(summary)

        tabs = QTabWidget()
        tabs.addTab(_make_chart_view(result["psnr_values"], "PSNR per frame (Y plane)", "PSNR (dB)"), "PSNR")
        tabs.addTab(_make_chart_view(result["ssim_values"], "SSIM per frame (Y plane)", "SSIM"), "SSIM")
        layout.addWidget(tabs)
