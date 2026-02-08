from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal, QEvent, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


_QSS_POPUP = """
QWidget#PopupCard {
    background: rgba(18, 20, 24, 245);
    border: 2px solid rgba(88, 135, 255, 220);
    border-radius: 12px;
    color: #ffffff;
    font-family: "Microsoft YaHei UI";
    font-size: 12px;
}
QLineEdit {
    background: rgba(10, 12, 16, 255);
    border: 1px solid rgba(255, 255, 255, 60);
    border-radius: 10px;
    padding: 8px 10px;
    color: #ffffff;
    selection-background-color: rgba(88, 135, 255, 160);
}
QLabel {
    padding: 6px 10px;
    color: #ffffff;
}
QLabel#PopupTitle {
    font-size: 14px;
    font-weight: 600;
    padding: 6px 10px;
}
QPushButton {
    background: rgba(25, 28, 36, 255);
    border: 1px solid rgba(255, 255, 255, 60);
    border-radius: 8px;
    padding: 6px 10px;
    color: #ffffff;
}
QPushButton:hover {
    background: rgba(35, 40, 52, 255);
}
"""


def _clamp_to_screen(pos: QPoint, size, margin: int = 8) -> QPoint:
    screen = QGuiApplication.screenAt(pos)
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    geom = screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)
    x = max(geom.left() + margin, min(pos.x(), geom.right() - size.width() - margin))
    y = max(geom.top() + margin, min(pos.y(), geom.bottom() - size.height() - margin))
    return QPoint(x, y)


class _ClickAwayFilter(QObject):
    def __init__(self, widget: QWidget) -> None:
        super().__init__(widget)
        self._widget = widget

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            try:
                gp = event.globalPosition().toPoint()
            except Exception:
                return False
            if not self._widget.isVisible():
                return False
            if not self._widget.geometry().contains(gp):
                self._widget.close()
        return False

class _ImeAwareLineEdit(QLineEdit):
    submitted = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._composing = False

    def is_composing(self) -> bool:
        return bool(self._composing)

    def inputMethodEvent(self, event) -> None:
        try:
            self._composing = bool(event.preeditString())
        except Exception:
            self._composing = False
        super().inputMethodEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._composing:
                super().keyPressEvent(event)
                return
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class FloatingPopup(QWidget):
    dismissed = Signal()
    f2_confirmed = Signal(str)
    f2_canceled_with_paste = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._card = QWidget(self)
        self._card.setObjectName("PopupCard")
        outer.addWidget(self._card)

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.title_label = QLabel("翻译", self._card)
        self.title_label.setObjectName("PopupTitle")

        self.input_edit = _ImeAwareLineEdit(self._card)
        self.input_edit.setPlaceholderText("输入要翻译的内容，回车翻译，Esc 取消")

        self.source_label = QLabel(self._card)
        self.source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.source_label.setWordWrap(True)
        self.source_label.setMinimumWidth(260)

        self.target_label = QLabel(self._card)
        self.target_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.target_label.setWordWrap(True)
        self.target_label.setMinimumWidth(260)

        layout.addWidget(self.title_label)
        layout.addWidget(self.input_edit)
        layout.addWidget(self.source_label)
        layout.addWidget(self.target_label)
        self.setStyleSheet(_QSS_POPUP)

        self._mode = "idle"
        self._enter_callback = None
        self._click_filter: _ClickAwayFilter | None = None
        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.timeout.connect(self._fire_typing_translate)
        self._last_sent = ""
        self._auto_commit = False

        self.input_edit.submitted.connect(self._on_enter)
        self.input_edit.textChanged.connect(self._on_text_changed)

    def open_f1(self, anchor: QPoint, source: str, translated: str) -> None:
        self._mode = "F1"
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.title_label.setText("划词翻译")
        self.input_edit.hide()
        self.source_label.show()
        self.source_label.setText((source or "").strip())
        self.target_label.setText((translated or "").strip() or "未获得翻译结果")
        self._show_at(anchor, activate=False)

    def open_f2(self, anchor: QPoint, enter_callback) -> None:
        self._mode = "F2"
        self._enter_callback = enter_callback
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.title_label.setText("打字翻译")
        self.input_edit.show()
        self.input_edit.setReadOnly(False)
        self.input_edit.clear()
        self._last_sent = ""
        self._auto_commit = False
        self.source_label.hide()
        self.target_label.setText("")
        self._show_at(anchor, activate=True)
        self.input_edit.setFocus()

    def show_f2_inline(self, anchor: QPoint, source: str, translated: str) -> None:
        self._mode = "F2_INLINE"
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.title_label.setText("打字翻译")
        self.input_edit.hide()
        self.source_label.show()
        self.source_label.setText((source or "").strip())
        self.target_label.setText((translated or "").strip())
        self._show_at(anchor, activate=False)

    def set_f2_translating(self) -> None:
        if self._mode != "F2":
            return
        self.target_label.setText("翻译中...")
        self.adjustSize()

    def set_f2_result(self, translated: str) -> None:
        if self._mode != "F2":
            return
        result = (translated or "").strip() or "未获得翻译结果"
        self.target_label.setText(result)
        self.adjustSize()
        self._auto_commit = False

    def show_error(self, anchor: QPoint, title: str, message: str) -> None:
        self._mode = "ERR"
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.title_label.setText(title or "错误")
        self.input_edit.hide()
        self.source_label.hide()
        self.target_label.setText(message or "")
        self._show_at(anchor, activate=False)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            if self._mode == "F2":
                self.f2_canceled_with_paste.emit(self.input_edit.text())
                return
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self._uninstall_click_filter()
        self._typing_timer.stop()
        self.dismissed.emit()
        super().closeEvent(event)

    def _on_enter(self) -> None:
        if self._mode != "F2":
            return
        if self.input_edit.is_composing():
            return
        self._typing_timer.stop()
        text = (self.input_edit.text() or "").strip()
        if not text:
            return
        self.f2_confirmed.emit(text)

    def _on_text_changed(self) -> None:
        if self._mode != "F2" or self._enter_callback is None:
            return
        if self.input_edit.is_composing():
            return
        self._typing_timer.start(260)

    def _fire_typing_translate(self, force: bool = False) -> None:
        if self._mode != "F2" or self._enter_callback is None:
            return
        if self.input_edit.is_composing():
            return
        text = (self.input_edit.text() or "").strip()
        if not text:
            self._last_sent = ""
            self.target_label.setText("")
            self.adjustSize()
            return
        if not force and text == self._last_sent:
            return
        self._last_sent = text
        self._enter_callback(text)

    def _show_at(self, anchor: QPoint, activate: bool) -> None:
        self.adjustSize()
        screen = QGuiApplication.screenAt(anchor)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        geom = screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)

        w = self.size().width()
        h = self.size().height()

        x = anchor.x() + 6
        y_below = anchor.y() + 24
        y_above = anchor.y() - h - 24
        y = y_below if (y_below + h) <= geom.bottom() else y_above

        self.move(_clamp_to_screen(QPoint(x, y), self.size()))
        self.show()
        self.raise_()
        if activate:
            self.activateWindow()
        self._install_click_filter()

    def _install_click_filter(self) -> None:
        if self._click_filter is not None:
            return
        app = QGuiApplication.instance()
        if app is None:
            return
        self._click_filter = _ClickAwayFilter(self)
        app.installEventFilter(self._click_filter)

    def _uninstall_click_filter(self) -> None:
        if self._click_filter is None:
            return
        app = QGuiApplication.instance()
        if app is not None:
            app.removeEventFilter(self._click_filter)
        self._click_filter = None



class ScreenshotResultOverlay(QWidget):
    dismissed = Signal()
    extract_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._card = QWidget(self)
        self._card.setObjectName("PopupCard")
        outer.addWidget(self._card)

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.label = QLabel(self._card)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.label)

        self.extract_button = QPushButton("提取文字到仪表盘", self._card)
        self.extract_button.clicked.connect(self.extract_requested.emit)
        layout.addWidget(self.extract_button, 0, Qt.AlignRight)

        self.setStyleSheet(_QSS_POPUP)
        self._click_filter: _ClickAwayFilter | None = None

    def open_for_rect(self, rect: QRect, text: str) -> None:
        self.label.setText(text or "")
        self.extract_button.setEnabled(bool(text and text not in ("识别中...", "翻译中...")))
        self.adjustSize()

        size = self.size()
        target = QRect(0, 0, max(260, size.width()), max(80, size.height()))
        x = rect.left()
        y_below = rect.bottom() + 10
        target.moveTo(x, y_below)
        
        screen = QGuiApplication.screenAt(target.center())
        if screen is None:
            screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        
        if screen is not None:
            screen_geom = screen.availableGeometry()

            if not screen_geom.contains(target):
                if not screen_geom.intersects(target):
                    target.moveCenter(screen_geom.center())
                else:
                    if target.bottom() > screen_geom.bottom():
                        target.moveTop(rect.top() - target.height() - 10)
                    if target.right() > screen_geom.right():
                        target.moveRight(screen_geom.right() - 10)
                    if target.bottom() > screen_geom.bottom():
                        target.moveBottom(screen_geom.bottom() - 10)
                    if target.left() < screen_geom.left():
                        target.moveLeft(screen_geom.left() + 10)
                    if target.top() < screen_geom.top():
                        target.moveTop(screen_geom.top() + 10)
        
        self.setGeometry(target)
        self.show()
        self.raise_()
        self.activateWindow()
        self._install_click_filter()

    def closeEvent(self, event) -> None:
        self._uninstall_click_filter()
        self.dismissed.emit()
        super().closeEvent(event)

    def _install_click_filter(self) -> None:
        if self._click_filter is not None:
            return
        app = QGuiApplication.instance()
        if app is None:
            return
        self._click_filter = _ClickAwayFilter(self)
        app.installEventFilter(self._click_filter)

    def _uninstall_click_filter(self) -> None:
        if self._click_filter is None:
            return
        app = QGuiApplication.instance()
        if app is not None:
            app.removeEventFilter(self._click_filter)
        self._click_filter = None
