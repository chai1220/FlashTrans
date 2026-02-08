from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, Signal, QObject, QEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


_QSS_DARK = """
QWidget {
    background: #14161a;
    color: #e7eaf0;
    font-family: "Microsoft YaHei UI";
    font-size: 12px;
}
#TitleBar {
    background: #0f1114;
}
QPushButton {
    background: #1e2228;
    border: 1px solid #2a2f37;
    border-radius: 6px;
    padding: 6px 10px;
}
QPushButton:hover {
    background: #272d36;
}
QPushButton:pressed {
    background: #1a1f26;
}
QTextEdit {
    background: #0f1114;
    border: 1px solid #2a2f37;
    border-radius: 10px;
    padding: 10px;
    selection-background-color: #2b6cb0;
}
QLabel#AppTitle {
    font-size: 14px;
    font-weight: 600;
}
QPushButton#WindowButton {
    min-width: 34px;
    max-width: 34px;
    min-height: 26px;
    max-height: 26px;
    border-radius: 6px;
    padding: 0px;
}
QPushButton#CloseButton {
    min-width: 34px;
    max-width: 34px;
    min-height: 26px;
    max-height: 26px;
    border-radius: 6px;
    padding: 0px;
}
QPushButton#CloseButton:hover {
    background: #b42318;
    border-color: #b42318;
}
"""


_QSS_LIGHT = """
QWidget {
    background: #f6f7fb;
    color: #1f2329;
    font-family: "Microsoft YaHei UI";
    font-size: 12px;
}
#TitleBar {
    background: #ffffff;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #d7dbe5;
    border-radius: 6px;
    padding: 6px 10px;
}
QPushButton:hover {
    background: #f0f2f7;
}
QPushButton:pressed {
    background: #e8ebf3;
}
QTextEdit {
    background: #ffffff;
    border: 1px solid #d7dbe5;
    border-radius: 10px;
    padding: 10px;
    selection-background-color: #2b6cb0;
}
QLabel#AppTitle {
    font-size: 14px;
    font-weight: 600;
}
QPushButton#WindowButton {
    min-width: 34px;
    max-width: 34px;
    min-height: 26px;
    max-height: 26px;
    border-radius: 6px;
    padding: 0px;
}
QPushButton#CloseButton {
    min-width: 34px;
    max-width: 34px;
    min-height: 26px;
    max-height: 26px;
    border-radius: 6px;
    padding: 0px;
}
QPushButton#CloseButton:hover {
    background: #d92d20;
    border-color: #d92d20;
    color: #ffffff;
}
"""


class _SourceEditFilter(QObject):
    ctrl_enter = Signal()

    def eventFilter(self, obj, event):  # type: ignore[override]
        if event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and (event.modifiers() & Qt.ControlModifier):
                self.ctrl_enter.emit()
                return True
        return False


class DashboardWindow(QWidget):
    translate_requested = Signal()
    copy_source_requested = Signal()
    copy_target_requested = Signal()
    settings_requested = Signal()
    clear_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FlashTrans 仪表盘")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setMinimumSize(760, 420)

        self._theme = "dark"
        self._drag_active = False
        self._drag_offset = QPoint()

        self._build_ui()
        self.apply_theme(self._theme)

    @property
    def source_edit(self) -> QTextEdit:
        return self._source_edit

    @property
    def target_edit(self) -> QTextEdit:
        return self._target_edit

    def apply_theme(self, theme: str) -> None:
        theme = theme.lower().strip()
        if theme not in ("dark", "light"):
            theme = "dark"
        self._theme = theme
        self.setStyleSheet(_QSS_DARK if theme == "dark" else _QSS_LIGHT)

    def toggle_theme(self) -> None:
        self.apply_theme("light" if self._theme == "dark" else "dark")

    def set_source_text(self, text: str) -> None:
        self._source_edit.setPlainText(text or "")

    def set_target_text(self, text: str) -> None:
        self._target_edit.setPlainText(text or "")

    def get_source_text(self) -> str:
        return self._source_edit.toPlainText() or ""

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self._is_in_title_bar(event.position().toPoint()):
            self._drag_active = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_active and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self._drag_active = False
        super().mouseReleaseEvent(event)

    def _is_in_title_bar(self, pos: QPoint) -> bool:
        return pos.y() <= self._title_bar.height()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        self._title_bar = QWidget(self)
        self._title_bar.setObjectName("TitleBar")
        title_layout = QHBoxLayout(self._title_bar)
        title_layout.setContentsMargins(10, 8, 10, 8)
        title_layout.setSpacing(8)

        title = QLabel("FlashTrans 仪表盘", self._title_bar)
        title.setObjectName("AppTitle")

        title_layout.addWidget(title)
        title_layout.addStretch(1)

        btn_min = QPushButton("-", self._title_bar)
        btn_min.setObjectName("WindowButton")
        btn_min.setAccessibleName("最小化")

        btn_close = QPushButton("×", self._title_bar)
        btn_close.setObjectName("CloseButton")
        btn_close.setAccessibleName("关闭")

        btn_min.clicked.connect(self.showMinimized)
        btn_close.clicked.connect(self.close)

        title_layout.addWidget(btn_min)
        title_layout.addWidget(btn_close)

        root.addWidget(self._title_bar)

        toolbar = QWidget(self)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)

        btn_translate = QPushButton("翻译", toolbar)
        btn_copy_src = QPushButton("复制原文", toolbar)
        btn_copy_tgt = QPushButton("复制译文", toolbar)
        btn_clear = QPushButton("清空", toolbar)
        btn_settings = QPushButton("设置", toolbar)

        btn_translate.setToolTip("将左侧原文翻译到右侧（快捷键：Ctrl+Enter）")
        btn_copy_src.setToolTip("复制左侧识别结果")
        btn_copy_tgt.setToolTip("复制右侧翻译结果")
        btn_clear.setToolTip("清空原文和译文")
        btn_settings.setToolTip("切换主题（暗色/亮色）")

        btn_translate.clicked.connect(self.translate_requested.emit)
        btn_copy_src.clicked.connect(self.copy_source_requested.emit)
        btn_copy_tgt.clicked.connect(self.copy_target_requested.emit)
        btn_clear.clicked.connect(self.clear_requested.emit)
        btn_settings.clicked.connect(self.settings_requested.emit)

        toolbar_layout.addWidget(btn_translate)
        toolbar_layout.addWidget(btn_copy_src)
        toolbar_layout.addWidget(btn_copy_tgt)
        toolbar_layout.addWidget(btn_clear)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(btn_settings)

        root.addWidget(toolbar)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setChildrenCollapsible(False)

        self._source_edit = QTextEdit(splitter)
        self._source_edit.setReadOnly(False)
        self._source_edit.setPlaceholderText("原文（可编辑，支持手动翻译）")

        self._target_edit = QTextEdit(splitter)
        self._target_edit.setReadOnly(True)
        self._target_edit.setPlaceholderText("译文（离线翻译结果）")

        splitter.addWidget(self._source_edit)
        splitter.addWidget(self._target_edit)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter, 1)

        self._source_filter = _SourceEditFilter(self)
        self._source_filter.ctrl_enter.connect(self.translate_requested.emit)
        self._source_edit.installEventFilter(self._source_filter)


MainWindow = DashboardWindow
