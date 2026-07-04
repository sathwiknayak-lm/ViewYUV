"""Background frame decoding so the Qt event loop is never blocked.

A single FrameDecoder QObject lives on a worker QThread. The main thread
never reads files or does YUV->RGB math directly -- it emits a
`requestDecode` signal (cross-thread emit -> automatically queued by Qt)
and receives results via `frameDecoded`.

Frame-dropping: MainWindowController tracks one "pending" decode per
source at a time. If the user scrubs/plays faster than decoding can keep
up, newer requests simply overwrite the "latest wanted" frame for that
source instead of queuing up -- once the in-flight decode finishes, only
the latest wanted frame (if different) is decoded next.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from ..yuv_file import Frame, YuvFile


class FrameDecoder(QObject):
    frameDecoded = Signal(str, int, object)  # source_id, frame_index, Frame
    decodeError = Signal(str, str)  # source_id, message

    def __init__(self):
        super().__init__()
        self._sources: dict[str, YuvFile] = {}

    @Slot(str, object)
    def set_source(self, source_id: str, yuv_file: YuvFile | None) -> None:
        old = self._sources.pop(source_id, None)
        if old is not None:
            old.close()
        if yuv_file is not None:
            self._sources[source_id] = yuv_file

    @Slot(str, int)
    def decode(self, source_id: str, frame_index: int) -> None:
        yuv_file = self._sources.get(source_id)
        if yuv_file is None:
            return
        try:
            frame: Frame = yuv_file.read_frame(frame_index)
        except Exception as exc:  # noqa: BLE001 - report any decode failure to the UI
            self.decodeError.emit(source_id, str(exc))
            return
        self.frameDecoded.emit(source_id, frame_index, frame)
