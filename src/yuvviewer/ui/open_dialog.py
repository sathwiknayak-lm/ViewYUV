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

CUSTOM_RESOLUTION = "Custom..."

# (label, width, height) -- common raw/test-video resolutions, roughly smallest to largest.
RESOLUTION_PRESETS = [
    ("176x144 (QCIF)", 176, 144),
    ("320x240 (QVGA)", 320, 240),
    ("352x288 (CIF)", 352, 288),
    ("640x360 (nHD)", 640, 360),
    ("640x480 (VGA)", 640, 480),
    ("720x480 (NTSC DV)", 720, 480),
    ("720x576 (PAL DV)", 720, 576),
    ("800x600 (SVGA)", 800, 600),
    ("1024x768 (XGA)", 1024, 768),
    ("1280x720 (HD 720p)", 1280, 720),
    ("1280x960", 1280, 960),
    ("1366x768", 1366, 768),
    ("1600x1200 (UXGA)", 1600, 1200),
    ("1920x1080 (Full HD 1080p)", 1920, 1080),
    ("2560x1440 (QHD 1440p)", 2560, 1440),
    ("3840x2160 (4K UHD)", 3840, 2160),
    ("4096x2160 (DCI 4K)", 4096, 2160),
    ("7680x4320 (8K UHD)", 7680, 4320),
]


class OpenFormatDialog(QDialog):
    """Prompts for width/height/pixel-format/bit-depth/matrix/range for a raw YUV file.

    Remembers the last-used values (per QSettings) as defaults for next time,
    unless explicit `initial_*` values are passed (used to re-open this dialog
    pre-filled with a source's current settings for in-place editing).
    """

    def __init__(
        self,
        file_path: str,
        parent=None,
        slot: str = "A",
        initial_fmt: YuvFormat | None = None,
        initial_matrix: ColorMatrix | None = None,
        initial_range: ColorRange | None = None,
    ):
        super().__init__(parent)
        self.file_path = file_path
        self.slot = slot
        self._syncing = False
        self.setWindowTitle(f"{'Edit format' if initial_fmt else 'Open'} {slot}: {os.path.basename(file_path)}")

        settings = QSettings(_ORG, _APP)

        default_width = initial_fmt.width if initial_fmt else int(settings.value("last_width", 1920))
        default_height = initial_fmt.height if initial_fmt else int(settings.value("last_height", 1080))

        self.resolution_combo = QComboBox()
        self.resolution_combo.addItem(CUSTOM_RESOLUTION, None)
        for label, w, h in RESOLUTION_PRESETS:
            self.resolution_combo.addItem(label, (w, h))
        self.resolution_combo.currentIndexChanged.connect(self._on_resolution_preset_changed)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 16384)
        self.width_spin.setValue(default_width)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 16384)
        self.height_spin.setValue(default_height)

        self._sync_resolution_combo_to_spins()

        self.format_combo = QComboBox()
        for pf in PixelFormat:
            self.format_combo.addItem(pf.value, pf)
        last_format = initial_fmt.pixel_format.value if initial_fmt else settings.value("last_format", PixelFormat.I420.value)
        idx = self.format_combo.findText(last_format)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)

        self.bit_depth_combo = QComboBox()
        self.bit_depth_combo.addItems(["8", "10"])
        last_bit_depth = str(initial_fmt.bit_depth if initial_fmt else settings.value("last_bit_depth", "8"))
        idx = self.bit_depth_combo.findText(last_bit_depth)
        if idx >= 0:
            self.bit_depth_combo.setCurrentIndex(idx)

        self.matrix_combo = QComboBox()
        self.matrix_combo.addItem("BT.601", ColorMatrix.BT601)
        self.matrix_combo.addItem("BT.709", ColorMatrix.BT709)
        last_matrix = initial_matrix.value if initial_matrix else settings.value("last_matrix", ColorMatrix.BT601.value)
        self.matrix_combo.setCurrentIndex(0 if last_matrix == ColorMatrix.BT601.value else 1)

        self.range_combo = QComboBox()
        self.range_combo.addItem("Limited (16-235/240)", ColorRange.LIMITED)
        self.range_combo.addItem("Full (0-255)", ColorRange.FULL)
        last_range = initial_range.value if initial_range else settings.value("last_range", ColorRange.LIMITED.value)
        self.range_combo.setCurrentIndex(0 if last_range == ColorRange.LIMITED.value else 1)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.width_spin.valueChanged.connect(self._on_spin_changed)
        self.height_spin.valueChanged.connect(self._on_spin_changed)
        self.format_combo.currentIndexChanged.connect(self._update_info)
        self.bit_depth_combo.currentIndexChanged.connect(self._update_info)

        form = QFormLayout()
        form.addRow("Resolution:", self.resolution_combo)
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

    # ------------------------------------------------------- resolution combo

    def _sync_resolution_combo_to_spins(self) -> None:
        """Select the preset matching the current width/height, or 'Custom...'."""
        w, h = self.width_spin.value(), self.height_spin.value()
        self._syncing = True
        for i, (_label, pw, ph) in enumerate(RESOLUTION_PRESETS, start=1):
            if (pw, ph) == (w, h):
                self.resolution_combo.setCurrentIndex(i)
                self._syncing = False
                return
        self.resolution_combo.setCurrentIndex(0)  # Custom...
        self._syncing = False

    def _on_resolution_preset_changed(self, _index: int) -> None:
        if self._syncing:
            return
        size = self.resolution_combo.currentData()
        if size is None:
            return  # "Custom..." selected -- leave width/height as-is for manual typing
        w, h = size
        self._syncing = True
        self.width_spin.setValue(w)
        self.height_spin.setValue(h)
        self._syncing = False
        self._update_info()

    def _on_spin_changed(self, _value: int) -> None:
        if not self._syncing:
            self._sync_resolution_combo_to_spins()
        self._update_info()

    # ------------------------------------------------------------------ misc

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

    @staticmethod
    def edit_existing(parent, slot: str, file_path: str, fmt: YuvFormat, matrix: ColorMatrix, color_range: ColorRange):
        """Re-opens the format dialog pre-filled with a loaded source's current settings.

        Returns (YuvFormat, ColorMatrix, ColorRange) or None if cancelled.
        """
        dialog = OpenFormatDialog(
            file_path, parent, slot=slot, initial_fmt=fmt, initial_matrix=matrix, initial_range=color_range
        )
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.result_format(), dialog.result_matrix(), dialog.result_range()
