"""Zoom/pan pixel-accurate image view, and pixel-probe support."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QImage, QPixmap, QWheelEvent
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView


def numpy_to_qpixmap(rgb: np.ndarray) -> QPixmap:
    """Convert an (H, W, 3) uint8 RGB array to a QPixmap."""
    rgb = np.ascontiguousarray(rgb)
    h, w, _ = rgb.shape
    qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


class ZoomPanGraphicsView(QGraphicsView):
    """A QGraphicsView with wheel-zoom, drag-to-pan, and a pixel-hover signal."""

    pixelHovered = Signal(int, int)  # image-space x, y (-1, -1) when off-image
    zoomChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setMouseTracking(True)
        self._zoom = 1.0
        self._image_size = (0, 0)

    def set_pixmap(self, pixmap: QPixmap) -> None:
        was_empty = self._pixmap_item.pixmap().isNull()
        self._pixmap_item.setPixmap(pixmap)
        self._scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())
        self._image_size = (pixmap.width(), pixmap.height())
        if was_empty:
            self.fit_to_window()

    def fit_to_window(self) -> None:
        if self._image_size == (0, 0):
            return
        self.resetTransform()
        self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self.zoomChanged.emit(self._zoom)

    def zoom_100(self) -> None:
        self.resetTransform()
        self._zoom = 1.0
        self.zoomChanged.emit(self._zoom)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._image_size == (0, 0):
            return
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        new_zoom = self._zoom * factor
        new_zoom = max(0.02, min(64.0, new_zoom))
        factor = new_zoom / self._zoom
        self._zoom = new_zoom
        self.scale(factor, factor)
        self.zoomChanged.emit(self._zoom)

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        scene_pos: QPointF = self.mapToScene(event.pos())
        x, y = int(scene_pos.x()), int(scene_pos.y())
        w, h = self._image_size
        if 0 <= x < w and 0 <= y < h:
            self.pixelHovered.emit(x, y)
        else:
            self.pixelHovered.emit(-1, -1)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.pixelHovered.emit(-1, -1)
