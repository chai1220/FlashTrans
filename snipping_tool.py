from __future__ import annotations

import time

from PySide6.QtCore import QRect, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QWidget


class SnippingOverlay(QWidget):
    captured = Signal(QPixmap, QRect)
    canceled = Signal()

    def __init__(self) -> None:
        super().__init__()

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.CrossCursor)

        self._start: QPoint | None = None
        self._end: QPoint | None = None
        self._dragging = False

    def begin(self) -> None:
        screens = QGuiApplication.screens()
        if not screens:
            return

        virtual_geom = QRect()
        for screen in screens:
            virtual_geom = virtual_geom.united(screen.geometry())

        if virtual_geom.isEmpty():
            return

        self.setGeometry(virtual_geom)
        self._start = None
        self._end = None
        self._dragging = False
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        rect = self._selection_rect()
        if rect is None:
            return

        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(rect, QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        pen = QPen(QColor(0, 180, 255, 220), 2)
        painter.setPen(pen)
        painter.drawRect(rect)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        if hasattr(event, "globalPosition"):
            self._start = event.globalPosition().toPoint()
        else:
            self._start = event.globalPos()
        self._end = self._start
        self._dragging = True
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return
        if hasattr(event, "globalPosition"):
            self._end = event.globalPosition().toPoint()
        else:
            self._end = event.globalPos()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        self._dragging = False

        global_rect = self._global_selection_rect()
        if global_rect is None or global_rect.width() < 8 or global_rect.height() < 8:
            self._reset_and_hide()
            self.canceled.emit()
            return

        self.hide()
        QApplication.processEvents()
        time.sleep(0.06)

        pixmap = self._grab_virtual_rect(global_rect)

        self._reset_and_hide()
        if pixmap.isNull():
            self.canceled.emit()
            return
        self.captured.emit(pixmap, global_rect)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._reset_and_hide()
            self.canceled.emit()
            return
        super().keyPressEvent(event)

    def _selection_rect(self) -> QRect | None:
        if self._start is None or self._end is None:
            return None
        local_start = self.mapFromGlobal(self._start)
        local_end = self.mapFromGlobal(self._end)
        return QRect(local_start, local_end).normalized()
    
    def _global_selection_rect(self) -> QRect | None:
        if self._start is None or self._end is None:
            return None
        return QRect(self._start, self._end).normalized()

    def _reset_and_hide(self) -> None:
        self._start = None
        self._end = None
        self._dragging = False
        self.hide()

    def _grab_virtual_rect(self, global_rect: QRect) -> QPixmap:
        screens = QGuiApplication.screens() or []
        if not screens:
            return QPixmap()

        parts: list[tuple[QImage, int, int]] = []
        max_w = 0
        max_h = 0

        for screen in screens:
            sg = screen.geometry()
            inter = global_rect.intersected(sg)
            if inter.isEmpty():
                continue
            full = screen.grabWindow(0)
            if full.isNull():
                continue
            img = full.toImage()
            if img.isNull() or sg.width() <= 0 or sg.height() <= 0:
                continue
            sx = img.width() / float(sg.width())
            sy = img.height() / float(sg.height())

            px_x = int(round((inter.x() - sg.x()) * sx))
            px_y = int(round((inter.y() - sg.y()) * sy))
            px_w = int(round(inter.width() * sx))
            px_h = int(round(inter.height() * sy))
            if px_w <= 0 or px_h <= 0:
                continue
            crop = img.copy(px_x, px_y, px_w, px_h)
            if crop.isNull():
                continue

            off_x = int(round((inter.x() - global_rect.x()) * sx))
            off_y = int(round((inter.y() - global_rect.y()) * sy))
            parts.append((crop, off_x, off_y))
            max_w = max(max_w, off_x + crop.width())
            max_h = max(max_h, off_y + crop.height())

        if not parts or max_w <= 0 or max_h <= 0:
            return QPixmap()

        canvas = QImage(max_w, max_h, QImage.Format_RGBA8888)
        canvas.fill(QColor(0, 0, 0, 0))
        painter = QPainter(canvas)
        try:
            for img, x, y in parts:
                painter.drawImage(x, y, img)
        finally:
            painter.end()
        return QPixmap.fromImage(canvas)
