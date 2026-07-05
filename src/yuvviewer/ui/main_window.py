"""Main application window: orchestrates sources, playback, view modes, and metrics."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QThread, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStyle,
    QToolBar,
    QWidget,
)

from ..colorconvert import ColorMatrix, ColorRange
from ..formats import YuvFormat
from ..render import ChannelMode, diff_heatmap, render_frame_rgb, resize_nearest, wipe_composite
from ..metrics import psnr, ssim
from ..yuv_file import Frame, YuvFile
from .compare_widget import ViewArea, ViewMode
from .decode_worker import FrameDecoder
from .metrics_dialog import ClipMetricsDialog
from .metrics_worker import ClipMetricsWorker
from .open_dialog import OpenFormatDialog
from .viewer_widget import numpy_to_qpixmap

SLOTS = ("A", "B")


@dataclass
class SourceInfo:
    path: str
    fmt: YuvFormat
    matrix: ColorMatrix
    color_range: ColorRange
    frame_count: int
    is_truncated: bool
    last_frame: Frame | None = field(default=None, compare=False)
    last_frame_index: int = -1


def _sample_yuv(frame: Frame, fmt: YuvFormat, x: int, y: int) -> tuple[int, int, int] | None:
    if frame is None or not (0 <= x < fmt.width and 0 <= y < fmt.height):
        return None
    h_sub, v_sub = fmt.chroma_subsampling
    cx, cy = min(x // h_sub, frame.u.shape[1] - 1), min(y // v_sub, frame.u.shape[0] - 1)
    return int(frame.y[y, x]), int(frame.u[cy, cx]), int(frame.v[cy, cx])


class MainWindow(QMainWindow):
    requestDecode = Signal(str, int)
    requestSetSource = Signal(str, object)
    requestCancelMetrics = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("YUView-lite")
        self.resize(1280, 820)

        self.sources: dict[str, SourceInfo | None] = {"A": None, "B": None}
        self._pending_decode = {"A": False, "B": False}
        self._wanted_frame = {"A": 0, "B": 0}
        self._playhead = 0
        self._channel_mode = ChannelMode.FULL
        self._view_mode = ViewMode.SINGLE
        self._active_single = "A"
        self._playing = False
        self._updating_controls = False
        self._exportable_rgb = None
        self._resize_notice = ""
        self._hover: tuple[str, int, int] | None = None
        self._metrics_thread: QThread | None = None

        self._setup_decoder_thread()
        self._build_ui()
        self._update_view_mode_availability()
        self._update_controls_enabled()

    # ---------------------------------------------------------------- setup

    def _setup_decoder_thread(self) -> None:
        self._decoder_thread = QThread(self)
        self._decoder = FrameDecoder()
        self._decoder.moveToThread(self._decoder_thread)
        self.requestDecode.connect(self._decoder.decode)
        self.requestSetSource.connect(self._decoder.set_source)
        self._decoder.frameDecoded.connect(self._on_frame_decoded)
        self._decoder.decodeError.connect(self._on_decode_error)
        self._decoder_thread.start()

    def _build_ui(self) -> None:
        self.view_area = ViewArea()
        self.setCentralWidget(self.view_area)
        for view in (
            self.view_area.single_view,
            self.view_area.side_by_side.view_a,
            self.view_area.side_by_side.view_b,
            self.view_area.diff_view,
            self.view_area.wipe_view,
        ):
            view.pixelHovered.connect(self._make_hover_handler(view))
        self.view_area.wipe_view.splitFractionChanged.connect(lambda _f: self._update_display())

        self._build_menu()
        self._build_toolbar()
        self._build_statusbar()

        play_action = QAction(self)
        play_action.setShortcut(Qt.Key_Space)
        play_action.triggered.connect(self._toggle_active_or_play)
        self.addAction(play_action)

    def _build_menu(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("&File")

        open_a = QAction("Open A...", self)
        open_a.triggered.connect(lambda: self._open_source("A"))
        file_menu.addAction(open_a)

        open_b = QAction("Open B...", self)
        open_b.triggered.connect(lambda: self._open_source("B"))
        file_menu.addAction(open_b)

        file_menu.addSeparator()

        export_action = QAction("Export current view as PNG...", self)
        export_action.triggered.connect(self._export_png)
        file_menu.addAction(export_action)

        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        format_menu = menu.addMenu("F&ormat")
        self.edit_format_actions = {}
        for slot in SLOTS:
            action = QAction(f"Edit Format {slot}...", self)
            action.triggered.connect(lambda checked=False, s=slot: self._edit_format(s))
            action.setEnabled(False)
            format_menu.addAction(action)
            self.edit_format_actions[slot] = action

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        style = self.style()

        self.open_buttons = {}
        self.edit_format_buttons = {}
        for slot in SLOTS:
            open_button = QPushButton(f"Open {slot}...")
            open_button.setToolTip(f"Open a raw YUV file into slot {slot}")
            open_button.clicked.connect(lambda checked=False, s=slot: self._open_source(s))
            toolbar.addWidget(open_button)
            self.open_buttons[slot] = open_button

            edit_button = QPushButton(f"Edit {slot}...")
            edit_button.setToolTip(f"Edit resolution/format/matrix/range for the file already loaded in {slot}")
            edit_button.setEnabled(False)
            edit_button.clicked.connect(lambda checked=False, s=slot: self._edit_format(s))
            toolbar.addWidget(edit_button)
            self.edit_format_buttons[slot] = edit_button

            if slot != SLOTS[-1]:
                toolbar.addSeparator()

        toolbar.addSeparator()

        self.play_button = QPushButton()
        self.play_button.setIcon(style.standardIcon(QStyle.SP_MediaPlay))
        self.play_button.setToolTip("Play/pause (Space)")
        self.play_button.clicked.connect(self._toggle_play)
        toolbar.addWidget(self.play_button)

        prev_button = QPushButton()
        prev_button.setIcon(style.standardIcon(QStyle.SP_MediaSkipBackward))
        prev_button.setToolTip("Previous frame")
        prev_button.clicked.connect(lambda: self._seek(self._playhead - 1))
        toolbar.addWidget(prev_button)

        next_button = QPushButton()
        next_button.setIcon(style.standardIcon(QStyle.SP_MediaSkipForward))
        next_button.setToolTip("Next frame")
        next_button.clicked.connect(lambda: self._seek(self._playhead + 1))
        toolbar.addWidget(next_button)

        toolbar.addWidget(QLabel(" FPS: "))
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 240)
        self.fps_spin.setValue(25)
        self.fps_spin.valueChanged.connect(self._on_fps_changed)
        toolbar.addWidget(self.fps_spin)

        toolbar.addSeparator()

        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimumWidth(220)
        self.frame_slider.valueChanged.connect(self._on_slider_changed)
        toolbar.addWidget(self.frame_slider)

        self.frame_spin = QSpinBox()
        self.frame_spin.setMinimumWidth(80)
        self.frame_spin.valueChanged.connect(self._on_spin_changed)
        toolbar.addWidget(self.frame_spin)

        self.frame_count_label = QLabel(" / 0")
        toolbar.addWidget(self.frame_count_label)

        toolbar.addSeparator()

        fit_button = QPushButton("Fit")
        fit_button.setToolTip("Fit to window")
        fit_button.clicked.connect(self._fit_to_window)
        toolbar.addWidget(fit_button)

        zoom_100_button = QPushButton("100%")
        zoom_100_button.clicked.connect(self._zoom_100)
        toolbar.addWidget(zoom_100_button)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel(" Channel: "))
        self.channel_combo = QComboBox()
        for mode in ChannelMode:
            self.channel_combo.addItem(mode.value, mode)
        self.channel_combo.currentIndexChanged.connect(self._on_channel_changed)
        toolbar.addWidget(self.channel_combo)

        toolbar.addWidget(QLabel(" View: "))
        self.view_mode_combo = QComboBox()
        for mode in ViewMode:
            self.view_mode_combo.addItem(mode.value, mode)
        self.view_mode_combo.currentIndexChanged.connect(self._on_view_mode_changed)
        toolbar.addWidget(self.view_mode_combo)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        self.compute_clip_button = QPushButton("Compute metrics for whole clip...")
        self.compute_clip_button.clicked.connect(self._compute_clip_metrics)
        toolbar.addWidget(self.compute_clip_button)

    def _build_statusbar(self) -> None:
        status = self.statusBar()
        self.format_label = QLabel("No file loaded")
        self.pixel_label = QLabel("")
        self.metrics_label = QLabel("")
        status.addWidget(self.format_label, 3)
        status.addWidget(self.pixel_label, 3)
        status.addPermanentWidget(self.metrics_label, 2)

    # ------------------------------------------------------------- opening

    def _open_source(self, slot: str) -> None:
        result = OpenFormatDialog.get_file_and_format(self, slot=slot)
        if result is None:
            return
        path, fmt, matrix, color_range = result
        self._load_source(slot, path, fmt, matrix, color_range)

    def _edit_format(self, slot: str) -> None:
        """Re-opens the format dialog pre-filled with this source's current settings.

        Available regardless of the current view mode (Single or
        Side-by-side) -- whichever of A/B is loaded can be corrected in
        place without re-picking the file.
        """
        info = self.sources[slot]
        if info is None:
            return
        result = OpenFormatDialog.edit_existing(self, slot, info.path, info.fmt, info.matrix, info.color_range)
        if result is None:
            return
        fmt, matrix, color_range = result
        self._load_source(slot, info.path, fmt, matrix, color_range, reset_playhead=False)

    def _load_source(
        self,
        slot: str,
        path: str,
        fmt: YuvFormat,
        matrix: ColorMatrix,
        color_range: ColorRange,
        reset_playhead: bool = True,
    ) -> None:
        try:
            probe = YuvFile(path, fmt)
        except OSError as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return

        info = SourceInfo(
            path=path,
            fmt=fmt,
            matrix=matrix,
            color_range=color_range,
            frame_count=probe.frame_count,
            is_truncated=probe.is_truncated,
        )
        self.sources[slot] = info
        self._wanted_frame[slot] = 0
        self.requestSetSource.emit(slot, probe)

        if info.is_truncated:
            QMessageBox.warning(
                self,
                "Truncated file",
                f"{path}\n\nFile size doesn't divide evenly by the frame size for "
                f"{fmt.pixel_format.value} {fmt.width}x{fmt.height} ({fmt.bit_depth}-bit).\n"
                f"The last partial frame will be ignored ({info.frame_count} whole frames available).",
            )

        if slot == "A" and reset_playhead:
            self._active_single = "A"
        self._update_view_mode_availability()
        self._update_controls_enabled()
        self._update_frame_range()
        self._update_format_label()
        self._seek(0 if reset_playhead else self._playhead)

    # --------------------------------------------------------- frame flow

    def _max_frame_count(self) -> int:
        counts = [s.frame_count for s in self.sources.values() if s is not None]
        return max(counts) if counts else 0

    def _update_frame_range(self) -> None:
        total = self._max_frame_count()
        self._updating_controls = True
        self.frame_slider.setRange(0, max(total - 1, 0))
        self.frame_spin.setRange(0, max(total - 1, 0))
        self.frame_count_label.setText(f" / {total}")
        self._updating_controls = False

    def _needed_slots(self) -> tuple[str, ...]:
        if self._view_mode is ViewMode.SINGLE:
            return (self._active_single,) if self.sources[self._active_single] else ()
        return tuple(s for s in SLOTS if self.sources[s] is not None)

    def _mapped_frame_index(self, slot: str) -> int:
        info = self.sources[slot]
        total = self._max_frame_count()
        if info is None or total <= 1:
            return 0
        return round(self._playhead * (info.frame_count - 1) / (total - 1))

    def _request_frame(self, slot: str) -> None:
        info = self.sources[slot]
        if info is None:
            return
        wanted = self._mapped_frame_index(slot)
        self._wanted_frame[slot] = wanted
        if self._pending_decode[slot]:
            return  # already decoding; latest "wanted" will be picked up on completion
        self._pending_decode[slot] = True
        self.requestDecode.emit(slot, wanted)

    def _on_frame_decoded(self, slot: str, frame_index: int, frame: Frame) -> None:
        self._pending_decode[slot] = False
        info = self.sources[slot]
        if info is None:
            return  # source was closed/replaced while decode was in flight
        info.last_frame = frame
        info.last_frame_index = frame_index
        if self._wanted_frame[slot] != frame_index:
            self._request_frame(slot)  # stale result -- user moved on; go again (drops this frame)
            return
        self._update_display()

    def _on_decode_error(self, slot: str, message: str) -> None:
        self._pending_decode[slot] = False
        self.statusBar().showMessage(f"Decode error ({slot}): {message}", 5000)

    def _seek(self, frame_index: int) -> None:
        total = self._max_frame_count()
        if total == 0:
            return
        frame_index = max(0, min(total - 1, frame_index))
        self._playhead = frame_index
        self._updating_controls = True
        self.frame_slider.setValue(frame_index)
        self.frame_spin.setValue(frame_index)
        self._updating_controls = False
        for slot in self._needed_slots():
            self._request_frame(slot)

    # ------------------------------------------------------------ display

    def _render_slot(self, slot: str):
        info = self.sources[slot]
        if info is None or info.last_frame is None:
            return None
        return render_frame_rgb(info.last_frame, info.fmt.bit_depth, info.matrix, info.color_range, self._channel_mode)

    def _update_display(self) -> None:
        self._resize_notice = ""
        if self._view_mode is ViewMode.SINGLE:
            rgb = self._render_slot(self._active_single)
            if rgb is not None:
                self.view_area.single_view.set_pixmap(numpy_to_qpixmap(rgb))
                self._exportable_rgb = rgb
        elif self._view_mode is ViewMode.SIDE_BY_SIDE:
            rgb_a, rgb_b = self._render_slot("A"), self._render_slot("B")
            if rgb_a is not None:
                self.view_area.side_by_side.view_a.set_pixmap(numpy_to_qpixmap(rgb_a))
            if rgb_b is not None:
                self.view_area.side_by_side.view_b.set_pixmap(numpy_to_qpixmap(rgb_b))
            self._exportable_rgb = rgb_a
        elif self._view_mode is ViewMode.DIFF:
            rgb_a, rgb_b = self._render_slot("A"), self._render_slot("B")
            if rgb_a is not None and rgb_b is not None:
                if rgb_a.shape != rgb_b.shape:
                    rgb_b = resize_nearest(rgb_b, rgb_a.shape[:2])
                    self._resize_notice = "B resized to A's resolution for diff"
                heatmap = diff_heatmap(rgb_a, rgb_b)
                self.view_area.diff_view.set_pixmap(numpy_to_qpixmap(heatmap))
                self._exportable_rgb = heatmap
        elif self._view_mode is ViewMode.WIPE:
            rgb_a, rgb_b = self._render_slot("A"), self._render_slot("B")
            if rgb_a is not None and rgb_b is not None:
                if rgb_a.shape != rgb_b.shape:
                    rgb_b = resize_nearest(rgb_b, rgb_a.shape[:2])
                    self._resize_notice = "B resized to A's resolution for wipe"
                split_x = int(self.view_area.wipe_view.split_fraction() * rgb_a.shape[1])
                composite = wipe_composite(rgb_a, rgb_b, split_x)
                self.view_area.wipe_view.set_pixmap(numpy_to_qpixmap(composite))
                self._exportable_rgb = composite

        self._update_metrics_label()
        self._update_pixel_label()

    def _update_metrics_label(self) -> None:
        info_a, info_b = self.sources["A"], self.sources["B"]
        if info_a is None or info_b is None or info_a.last_frame is None or info_b.last_frame is None:
            self.metrics_label.setText("")
            return
        y_a, y_b = info_a.last_frame.y, info_b.last_frame.y
        if y_a.shape != y_b.shape:
            y_b = resize_nearest(y_b, y_a.shape)
        p = psnr(y_a, y_b)
        s = ssim(y_a, y_b)
        p_text = "inf" if p == float("inf") else f"{p:.2f} dB"
        notice = f"  [{self._resize_notice}]" if self._resize_notice else ""
        self.metrics_label.setText(f"PSNR: {p_text}   SSIM: {s:.4f}{notice}")

    def _update_format_label(self) -> None:
        parts = []
        for slot in SLOTS:
            info = self.sources[slot]
            if info is None:
                continue
            parts.append(
                f"{slot}: {info.fmt.pixel_format.value} {info.fmt.width}x{info.fmt.height} "
                f"{info.fmt.bit_depth}-bit ({info.frame_count} frames)"
            )
        self.format_label.setText("   |   ".join(parts) if parts else "No file loaded")

    # ---------------------------------------------------------- pixel probe

    def _make_hover_handler(self, view):
        def handler(x: int, y: int) -> None:
            pane = {
                self.view_area.single_view: "single",
                self.view_area.side_by_side.view_a: "A",
                self.view_area.side_by_side.view_b: "B",
                self.view_area.diff_view: "diff",
                self.view_area.wipe_view: "wipe",
            }[view]
            self._hover = None if x < 0 else (pane, x, y)
            self._update_pixel_label()

        return handler

    def _update_pixel_label(self) -> None:
        if self._hover is None:
            self.pixel_label.setText("")
            return
        pane, x, y = self._hover
        pane_to_slot = {"single": self._active_single, "A": "A", "B": "B", "diff": "A", "wipe": "A"}
        slot = pane_to_slot.get(pane)
        info = self.sources.get(slot) if slot else None
        if info is None or info.last_frame is None:
            self.pixel_label.setText(f"({x}, {y})")
            return
        sample = _sample_yuv(info.last_frame, info.fmt, x, y)
        if sample is None:
            self.pixel_label.setText(f"({x}, {y})")
            return
        y_v, u_v, v_v = sample
        self.pixel_label.setText(f"({x}, {y})  Y={y_v} U={u_v} V={v_v}")

    # -------------------------------------------------------------- zoom

    def _current_views(self):
        if self._view_mode is ViewMode.SINGLE:
            return [self.view_area.single_view]
        if self._view_mode is ViewMode.SIDE_BY_SIDE:
            return [self.view_area.side_by_side.view_a, self.view_area.side_by_side.view_b]
        if self._view_mode is ViewMode.DIFF:
            return [self.view_area.diff_view]
        return [self.view_area.wipe_view]

    def _fit_to_window(self) -> None:
        for view in self._current_views():
            view.fit_to_window()

    def _zoom_100(self) -> None:
        for view in self._current_views():
            view.zoom_100()

    # ------------------------------------------------------------ controls

    def _on_slider_changed(self, value: int) -> None:
        if not self._updating_controls:
            self._seek(value)

    def _on_spin_changed(self, value: int) -> None:
        if not self._updating_controls:
            self._seek(value)

    def _on_fps_changed(self, value: int) -> None:
        if self._playing:
            self._play_timer.setInterval(int(1000 / value))

    def _on_channel_changed(self, _index: int) -> None:
        self._channel_mode = self.channel_combo.currentData()
        self._update_display()

    def _on_view_mode_changed(self, _index: int) -> None:
        self._view_mode = self.view_mode_combo.currentData()
        self.view_area.set_mode(self._view_mode)
        for slot in self._needed_slots():
            self._request_frame(slot)
        self._update_display()

    def _update_view_mode_availability(self) -> None:
        both_loaded = self.sources["A"] is not None and self.sources["B"] is not None
        model = self.view_mode_combo.model()
        for i, mode in enumerate(ViewMode):
            enabled = mode is ViewMode.SINGLE or both_loaded
            item = model.item(i)
            if item is not None:
                item.setEnabled(enabled)
        if not both_loaded and self._view_mode is not ViewMode.SINGLE:
            self.view_mode_combo.setCurrentIndex(0)

    def _update_controls_enabled(self) -> None:
        any_loaded = any(s is not None for s in self.sources.values())
        both_loaded = self.sources["A"] is not None and self.sources["B"] is not None
        for widget in (self.play_button, self.frame_slider, self.frame_spin, self.fps_spin):
            widget.setEnabled(any_loaded)
        self.compute_clip_button.setEnabled(both_loaded)
        for slot in SLOTS:
            loaded = self.sources[slot] is not None
            self.edit_format_actions[slot].setEnabled(loaded)
            self.edit_format_buttons[slot].setEnabled(loaded)

    def _toggle_active_or_play(self) -> None:
        # Space bar: A/B toggle in Single mode (if both loaded), else play/pause.
        if self._view_mode is ViewMode.SINGLE and self.sources["A"] is not None and self.sources["B"] is not None:
            self._active_single = "B" if self._active_single == "A" else "A"
            self._request_frame(self._active_single)
            self._update_display()
        else:
            self._toggle_play()

    # ------------------------------------------------------------ playback

    def _toggle_play(self) -> None:
        self._playing = not self._playing
        style = self.style()
        if self._playing:
            self.play_button.setIcon(style.standardIcon(QStyle.SP_MediaPause))
            self._play_timer = getattr(self, "_play_timer", None) or QTimer(self)
            self._play_timer.timeout.connect(self._on_play_tick)
            self._play_timer.start(int(1000 / self.fps_spin.value()))
        else:
            self.play_button.setIcon(style.standardIcon(QStyle.SP_MediaPlay))
            if getattr(self, "_play_timer", None):
                self._play_timer.stop()

    def _on_play_tick(self) -> None:
        total = self._max_frame_count()
        if total == 0:
            return
        if self._playhead >= total - 1:
            self._toggle_play()
            return
        self._seek(self._playhead + 1)

    # -------------------------------------------------------------- export

    def _export_png(self) -> None:
        if self._exportable_rgb is None:
            QMessageBox.information(self, "Nothing to export", "Open a file and display a frame first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "", "PNG images (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        numpy_to_qpixmap(self._exportable_rgb).save(path, "PNG")
        self.statusBar().showMessage(f"Exported {path}", 4000)

    # ------------------------------------------------------- clip metrics

    def _compute_clip_metrics(self) -> None:
        info_a, info_b = self.sources["A"], self.sources["B"]
        if info_a is None or info_b is None:
            return

        thread = QThread(self)
        worker = ClipMetricsWorker(info_a.path, info_a.fmt, info_b.path, info_b.fmt)
        worker.moveToThread(thread)
        self._metrics_thread = thread
        self._metrics_worker = worker

        progress = QProgressDialog("Computing PSNR/SSIM for whole clip...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        thread.started.connect(worker.run)
        worker.progress.connect(lambda cur, total: progress.setValue(int(cur * 100 / total)))
        progress.canceled.connect(worker.request_cancel)

        def on_finished(result: dict) -> None:
            progress.close()
            thread.quit()
            thread.wait()
            self._metrics_thread = None
            if not result.get("cancelled"):
                dialog = ClipMetricsDialog(result, self)
                dialog.exec()

        worker.finished.connect(on_finished)
        thread.start()

    # ---------------------------------------------------------------- misc

    def closeEvent(self, event) -> None:
        if self._playing:
            self._toggle_play()
        if self._metrics_thread is not None:
            self._metrics_worker.request_cancel()
            self._metrics_thread.quit()
            self._metrics_thread.wait()
        self.requestSetSource.emit("A", None)
        self.requestSetSource.emit("B", None)
        self._decoder_thread.quit()
        self._decoder_thread.wait()
        super().closeEvent(event)
