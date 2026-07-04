"""View-mode widgets for comparison: side-by-side, and the A/B wipe view.

Single and Diff modes reuse ZoomPanGraphicsView directly; this module adds
the two widgets that need extra structure (two panes, or a draggable
split line).
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsLineItem, QHBoxLayout, QSplitter, QStackedWidget, QWidget

from .viewer_widget import ZoomPanGraphicsView


class ViewMode(Enum):
    SINGLE = "Single"
    SIDE_BY_SIDE = "Side-by-side"
    DIFF = "Diff / Heatmap"
    WIPE = "Wipe"


class SideBySideView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.view_a = ZoomPanGraphicsView()
        self.view_b = ZoomPanGraphicsView()
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.view_a)
        splitter.addWidget(self.view_b)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)


class WipeGraphicsView(ZoomPanGraphicsView):
    """Shows a single composited A/B image with a draggable vertical split line."""

    splitFractionChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._split_fraction = 0.5
        self._dragging = False
        self._line = QGraphicsLineItem()
        pen = QPen(QColor(255, 220, 0))
        pen.setWidth(0)  # cosmetic: always 1 device pixel regardless of zoom
        self._line.setPen(pen)
        self._line.setZValue(10)
        self._scene.addItem(self._line)

    def set_split_fraction(self, fraction: float) -> None:
        self._split_fraction = max(0.0, min(1.0, fraction))
        self._update_line()

    def split_fraction(self) -> float:
        return self._split_fraction

    def set_pixmap(self, pixmap) -> None:
        super().set_pixmap(pixmap)
        self._update_line()

    def _update_line(self) -> None:
        w, h = self._image_size
        if (w, h) == (0, 0):
            return
        x = self._split_fraction * w
        self._line.setLine(x, 0, x, h)

    def _line_x(self) -> float:
        w, _ = self._image_size
        return self._split_fraction * w

    def mousePressEvent(self, event) -> None:
        if self._image_size != (0, 0):
            scene_x = self.mapToScene(event.pos()).x()
            if abs(scene_x - self._line_x()) < 8 / max(self._zoom, 0.01):
                self._dragging = True
                self.setDragMode(ZoomPanGraphicsView.NoDrag)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            w, _ = self._image_size
            scene_x = self.mapToScene(event.pos()).x()
            fraction = max(0.0, min(1.0, scene_x / w)) if w else 0.5
            self.set_split_fraction(fraction)
            self.splitFractionChanged.emit(fraction)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging:
            self._dragging = False
            self.setDragMode(ZoomPanGraphicsView.ScrollHandDrag)
        super().mouseReleaseEvent(event)


class ViewArea(QStackedWidget):
    """Switches between Single / Side-by-side / Diff / Wipe presentation widgets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.single_view = ZoomPanGraphicsView()
        self.side_by_side = SideBySideView()
        self.diff_view = ZoomPanGraphicsView()
        self.wipe_view = WipeGraphicsView()

        self._pages = {
            ViewMode.SINGLE: self.single_view,
            ViewMode.SIDE_BY_SIDE: self.side_by_side,
            ViewMode.DIFF: self.diff_view,
            ViewMode.WIPE: self.wipe_view,
        }
        for page in self._pages.values():
            self.addWidget(page)

    def set_mode(self, mode: ViewMode) -> None:
        self.setCurrentWidget(self._pages[mode])
