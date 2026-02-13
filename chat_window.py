from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_CHAT_QSS = """
QWidget {
    background: #14161a;
    color: #e7eaf0;
    font-family: "Microsoft YaHei UI";
    font-size: 12px;
}
QPlainTextEdit {
    background: #0f1114;
    border: 1px solid #2a2f37;
    border-radius: 10px;
    padding: 10px;
    selection-background-color: #2b6cb0;
}
QPushButton {
    background: #1e2228;
    border: 1px solid #2a2f37;
    border-radius: 8px;
    padding: 7px 12px;
}
QPushButton:hover { background: #242a33; }
QPushButton:pressed { background: #1a1f26; }
QLabel#SectionTitle {
    color: #c7cdd8;
    font-weight: 600;
}
"""


class ChatWindow(QDialog):
    message_submitted = Signal(object)
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("FlashTrans - F4 对话")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.resize(720, 520)
        self.setStyleSheet(_CHAT_QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self._think_btn = QPushButton("显示思考过程", self)
        self._think_btn.setCheckable(True)
        self._think_btn.setVisible(False)
        root.addWidget(self._think_btn)

        self._think_view = QPlainTextEdit(self)
        self._think_view.setReadOnly(True)
        self._think_view.setMaximumHeight(160)
        self._think_view.setVisible(False)
        root.addWidget(self._think_view)

        self._transcript = QPlainTextEdit(self)
        self._transcript.setReadOnly(True)
        root.addWidget(self._transcript, 1)

        self._input = QPlainTextEdit(self)
        self._input.setPlaceholderText("输入问题，Ctrl+Enter 发送")
        self._input.setMaximumHeight(120)
        root.addWidget(self._input)

        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        self._btn_save = QPushButton("保存记录", row)
        self._btn_clear = QPushButton("清除记录", row)
        self._btn_send = QPushButton("发送", row)
        self._btn_close = QPushButton("关闭", row)
        row_layout.addStretch(1)
        row_layout.addWidget(self._btn_save)
        row_layout.addWidget(self._btn_clear)
        row_layout.addWidget(self._btn_send)
        row_layout.addWidget(self._btn_close)
        root.addWidget(row)

        self._btn_save.clicked.connect(self._save_transcript)
        self._btn_clear.clicked.connect(self._clear_transcript)
        self._btn_send.clicked.connect(self._send)
        self._btn_close.clicked.connect(self.close)
        self._think_btn.toggled.connect(self._toggle_think)

    def set_input_text(self, text: str) -> None:
        text = str(text or "")
        self._input.setPlainText(text)
        self._input.setFocus()
        cursor = self._input.textCursor()
        cursor.select(cursor.Document)
        self._input.setTextCursor(cursor)

    def append_user(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._transcript.appendPlainText(f"你：{text}\n")

    def append_assistant(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        think = ""
        m = re.search(r"<think>([\s\S]*?)</think>", text, flags=re.IGNORECASE)
        if m:
            think = (m.group(1) or "").strip()
            visible = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
        else:
            visible = text

        if think:
            self._think_view.setPlainText(think)
            self._think_btn.setChecked(False)
            self._think_btn.setVisible(True)
            self._think_view.setVisible(False)
        else:
            self._think_btn.setVisible(False)
            self._think_view.setVisible(False)
            self._think_view.setPlainText("")
            self._think_btn.setChecked(False)

        if visible:
            self._transcript.appendPlainText(f"助手：{visible}\n")

    def append_status(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._transcript.appendPlainText(f"{text}\n")

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and (event.modifiers() & Qt.ControlModifier):
            self._send()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.dismissed.emit()
        super().closeEvent(event)

    def _send(self) -> None:
        question = (self._input.toPlainText() or "").strip()
        if not question:
            return
        self._input.clear()
        self.message_submitted.emit({"question": question})

    def _toggle_think(self, checked: bool) -> None:
        self._think_view.setVisible(bool(checked))
        self._think_btn.setText("隐藏思考过程" if checked else "显示思考过程")

    def _clear_transcript(self) -> None:
        self._transcript.clear()
        self._think_view.clear()
        self._think_btn.setVisible(False)

    def _save_transcript(self) -> None:
        from datetime import datetime
        
        text = self._transcript.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "无内容", "没有可保存的对话记录。")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"FlashTrans_对话_{timestamp}.txt"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存对话记录",
            default_name,
            "文本文件 (*.txt);;所有文件 (*.*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(text)
                QMessageBox.information(self, "保存成功", f"对话记录已保存到:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "保存失败", f"保存文件时出错:\n{str(e)}")
