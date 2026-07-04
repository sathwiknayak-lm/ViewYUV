"""File-open + raw YUV format dialog."""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from ..colorconvert import ColorMatrix, ColorRange
from ..formats import PixelFormat, YuvFormat

_ORG, _APP = "yuvviewer", "yuvviewer"


class OpenFormatDialog(QDialog):
    """Prompts for width/height/pixel-format/bit-depth/matrix/range for a raw YUV file.

    Remembers the last-used values (per QSettings) as defaults for next time.
    """

    def __init__(self, file_path: str, parent=None, slot: str = "A"):
        super().__init__(parent)
        self.file_path = file_path
        self.slot = slot
        self.setWindowTitle(f"Open {slot}: {os.path.basename(file_path)}")

        settings = QSettings(_ORG, _APP)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 16384)
        self.width_spin.setValue(int(settings.value("last_width", 1920)))

        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 16384)
        self.height_spin.setValue(int(settings.value("last_height", 1080)))

        self.format_combo = QComboBox()
        for pf in PixelFormat:
            self.format_combo.addItem(pf.value, pf)
        last_format = settings.value("last_format", PixelFormat.I420.value)
        idx = self.format_combo.findText(last_format)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)

        self.bit_depth_combo = QComboBox()
        self.bit_depth_combo.addItems(["8", "10"])
        last_bit_depth = str(settings.value("last_bit_depth", "8"))
        idx = self.bit_depth_combo.findText(last_bit_depth)
        if idx >= 0:
            self.bit_depth_combo.setCurrentIndex(idx)

        self.matrix_combo = QComboBox()
        self.matrix_combo.addItem("BT.601", ColorMatrix.BT601)
        self.matrix_combo.addItem("BT.709", ColorMatrix.BT709)
        last_matrix = settings.value("last_matrix", ColorMatrix.BT601.value)
        self.matrix_combo.setCurrentIndex(0 if last_matrix == ColorMatrix.BT601.value else 1)

        self.range_combo = QComboBox()
        self.range_combo.addItem("Limited (16-235/240)", ColorRange.LIMITED)
        self.range_combo.addItem("Full (0-255)", ColorRange.FULL)
        last_range = settings.value("last_range", ColorRange.LIMITED.value)
        self.range_combo.setCurrentIndex(0 if last_range == ColorRange.LIMITED.value else 1)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.width_spin.valueChanged.connect(self._update_info)
        self.height_spin.valueChanged.connect(self._update_info)
        self.format_combo.currentIndexChanged.connect(self._update_info)
        self.bit_depth_combo.currentIndexChanged.connect(self._update_info)

        form = QFormLayout()
        form.addRow("Width:", self.width_spin)
        form.addRow("Height:", self.height_spin)
        form.addRow("Pixel format:", self.format_combo)
        form.addRow("Bit depth:", self.bit_depth_combo)
        form.addRow("Color matrix:", self.matrix_combo)
        form.addRow("Range:", self.range_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"File: {file_path}"))
        layout.addLayout(form)
        layout.addWidget(self.info_label)
        layout.addWidget(buttons)

        self._update_info()

    def _current_format(self) -> YuvFormat | None:
        try:
            return YuvFormat(
                pixel_format=self.format_combo.currentData(),
                width=self.width_spin.value(),
                height=self.height_spin.value(),
                bit_depth=int(self.bit_depth_combo.currentText()),
            )
        except ValueError:
            return None

    def _update_info(self) -> None:
        fmt = self._current_format()
        if fmt is None:
            self.info_label.setText("Invalid dimensions for this format's chroma subsampling.")
            return
        try:
            file_size = os.path.getsize(self.file_path)
        except OSError:
            file_size = 0
        frame_size = fmt.frame_size
        count = file_size // frame_size if frame_size else 0
        truncated = frame_size and file_size % frame_size != 0
        text = f"Frame size: {frame_size:,} bytes  |  Frames: {count}"
        if truncated:
            text += "  (warning: file size doesn't divide evenly -- last frame is truncated)"
        self.info_label.setText(text)

    def _on_accept(self) -> None:
        if self._current_format() is None:
            return
        settings = QSettings(_ORG, _APP)
        settings.setValue("last_width", self.width_spin.value())
        settings.setValue("last_height", self.height_spin.value())
        settings.setValue("last_format", self.format_combo.currentText())
        settings.setValue("last_bit_depth", self.bit_depth_combo.currentText())
        settings.setValue("last_matrix", self.matrix_combo.currentData().value)
        settings.setValue("last_range", self.range_combo.currentData().value)
        self.accept()

    def result_format(self) -> YuvFormat:
        return self._current_format()

    def result_matrix(self) -> ColorMatrix:
        return self.matrix_combo.currentData()

    def result_range(self) -> ColorRange:
        return self.range_combo.currentData()

    @staticmethod
    def get_file_and_format(parent, slot: str = "A"):
        """Runs the full Open flow: file picker, then format dialog.

        Returns (file_path, YuvFormat, ColorMatrix, ColorRange) or None if cancelled.
        """
        file_path, _ = QFileDialog.getOpenFileName(parent, f"Open YUV file ({slot})", "", "All files (*.*)")
        if not file_path:
            return None
        dialog = OpenFormatDialog(file_path, parent, slot=slot)
        if dialog.exec() != QDialog.Accepted:
            return None
        return file_path, dialog.result_format(), dialog.result_matrix(), dialog.result_range()
