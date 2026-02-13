from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, QPoint, Signal, QObject, QEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from settings_store import ApiProfile, SettingsStore


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008


def _vk_to_key_name(vk: int) -> str:
    vk = int(vk)
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    names = {
        0x20: "Space",
        0x09: "Tab",
        0x1B: "Esc",
        0x0D: "Enter",
        0x2E: "Del",
        0x08: "Backspace",
        0x25: "Left",
        0x26: "Up",
        0x27: "Right",
        0x28: "Down",
    }
    return names.get(vk, f"VK_{vk}")


def _format_hotkey(mods: int, vk: int) -> str:
    parts: list[str] = []
    mods = int(mods)
    if mods & MOD_CONTROL:
        parts.append("Ctrl")
    if mods & MOD_ALT:
        parts.append("Alt")
    if mods & MOD_SHIFT:
        parts.append("Shift")
    if mods & MOD_WIN:
        parts.append("Win")
    parts.append(_vk_to_key_name(int(vk)))
    return "+".join(parts)


class _HotkeyEdit(QLineEdit):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vk = 0
        self._mods = 0
        self.setReadOnly(True)
        self.setPlaceholderText("点击后按组合键" if QApplication.instance().property("ui_lang") != "en" else "Click and press keys")

    def set_hotkey(self, mods: int, vk: int) -> None:
        self._mods = int(mods)
        self._vk = int(vk)
        self.setText(_format_hotkey(self._mods, self._vk))
        self.changed.emit()

    def hotkey(self) -> dict[str, int]:
        return {"vk": int(self._vk), "mods": int(self._mods)}

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            event.accept()
            return
        vk = int(getattr(event, "nativeVirtualKey")() or 0)
        if vk <= 0:
            event.accept()
            return
        mods = 0
        qt_mods = event.modifiers()
        if qt_mods & Qt.ControlModifier:
            mods |= MOD_CONTROL
        if qt_mods & Qt.AltModifier:
            mods |= MOD_ALT
        if qt_mods & Qt.ShiftModifier:
            mods |= MOD_SHIFT
        if qt_mods & Qt.MetaModifier:
            mods |= MOD_WIN
        self.set_hotkey(mods, vk)
        event.accept()


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
QLabel#BackendLabel {
    color: #6b7280;
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
    clear_requested = Signal()

    def __init__(self, on_hotkeys_changed: Callable[[], None] | None = None) -> None:
        super().__init__()
        self._store = SettingsStore()
        self._on_hotkeys_changed = on_hotkeys_changed
        self._ui_lang = self._store.get_ui_language()
        self.setWindowTitle(self._t("dashboard_title"))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.WindowStaysOnTopHint)
        self.setMinimumSize(760, 420)

        self._theme = "dark"
        self._drag_active = False
        self._drag_offset = QPoint()

        self._build_ui()
        self.apply_theme(self._theme)
        self._apply_ui_language()

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

        self._logo = QLabel(self._title_bar)
        self._logo.setFixedSize(32, 32)
        self._logo.setPixmap(QApplication.windowIcon().pixmap(32, 32))
        title_layout.addWidget(self._logo)

        self._title = QLabel(self._t("dashboard_title"), self._title_bar)
        self._title.setObjectName("AppTitle")
        title_layout.addWidget(self._title)

        self._backend_label = QLabel("", self._title_bar)
        self._backend_label.setObjectName("BackendLabel")
        title_layout.addWidget(self._backend_label)
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

        self._btn_translate = QPushButton(self._t("translate"), toolbar)
        self._btn_copy_src = QPushButton(self._t("copy_source"), toolbar)
        self._btn_copy_tgt = QPushButton(self._t("copy_target"), toolbar)
        self._btn_clear = QPushButton(self._t("clear"), toolbar)
        self._btn_theme = QPushButton(self._t("theme"), toolbar)
        self._btn_settings = QPushButton(self._t("settings"), toolbar)

        self._target_lang = QComboBox(toolbar)
        self._target_lang.addItem(self._t("lang_auto"), "auto")
        self._target_lang.addItem(self._t("lang_zh"), "zh")
        self._target_lang.addItem(self._t("lang_en"), "en")
        self._target_lang.addItem(self._t("lang_ja"), "ja")
        self._target_lang.addItem(self._t("lang_ko"), "ko")
        self._target_lang.addItem(self._t("lang_fr"), "fr")
        self._target_lang.addItem(self._t("lang_de"), "de")
        self._target_lang.addItem(self._t("lang_es"), "es")
        self._target_lang.addItem(self._t("lang_ru"), "ru")
        self._set_combo_by_data(self._target_lang, self._store.get_target_language())

        self._btn_translate.setToolTip(self._t("tip_translate"))
        self._btn_copy_src.setToolTip(self._t("tip_copy_source"))
        self._btn_copy_tgt.setToolTip(self._t("tip_copy_target"))
        self._btn_clear.setToolTip(self._t("tip_clear"))
        self._btn_theme.setToolTip(self._t("tip_theme"))
        self._btn_settings.setToolTip(self._t("tip_settings"))

        self._btn_translate.clicked.connect(self.translate_requested.emit)
        self._btn_copy_src.clicked.connect(self.copy_source_requested.emit)
        self._btn_copy_tgt.clicked.connect(self.copy_target_requested.emit)
        self._btn_clear.clicked.connect(self.clear_requested.emit)
        self._btn_theme.clicked.connect(self.toggle_theme)
        self._btn_settings.clicked.connect(self._open_settings_dialog)

        self._target_lang.currentIndexChanged.connect(lambda: self._store.set_target_language(self.get_target_language()))

        toolbar_layout.addWidget(self._btn_translate)
        toolbar_layout.addWidget(self._btn_copy_src)
        toolbar_layout.addWidget(self._btn_copy_tgt)
        toolbar_layout.addWidget(self._btn_clear)
        toolbar_layout.addWidget(self._target_lang)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self._btn_theme)
        toolbar_layout.addWidget(self._btn_settings)

        root.addWidget(toolbar)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setChildrenCollapsible(False)

        self._source_edit = QTextEdit(splitter)
        self._source_edit.setReadOnly(False)
        self._source_edit.setPlaceholderText(self._t("source_placeholder"))

        self._target_edit = QTextEdit(splitter)
        self._target_edit.setReadOnly(True)
        self._target_edit.setPlaceholderText(self._t("target_placeholder"))

        splitter.addWidget(self._source_edit)
        splitter.addWidget(self._target_edit)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter, 1)

        self._source_filter = _SourceEditFilter(self)
        self._source_filter.ctrl_enter.connect(self.translate_requested.emit)
        self._source_edit.installEventFilter(self._source_filter)

    def get_target_language(self) -> str:
        try:
            return str(self._target_lang.currentData() or "auto")
        except Exception:
            return "auto"

    def get_subject(self) -> str:
        return ""

    def get_ui_language(self) -> str:
        return self._ui_lang

    def set_backend_info(self, text: str) -> None:
        self._backend_label.setText(str(text or "").strip())

    def _t(self, key: str) -> str:
        zh = {
            "dashboard_title": "FlashTrans 仪表盘",
            "translate": "翻译",
            "copy_source": "复制原文",
            "copy_target": "复制译文",
            "clear": "清空",
            "settings": "设置",
            "theme": "主题",
            "lang_auto": "目标语言：自动",
            "lang_zh": "目标语言：中文",
            "lang_en": "目标语言：英文",
            "lang_ja": "目标语言：日文",
            "lang_ko": "目标语言：韩文",
            "lang_fr": "目标语言：法文",
            "lang_de": "目标语言：德文",
            "lang_es": "目标语言：西班牙文",
            "lang_ru": "目标语言：俄文",
            "tip_translate": "将左侧原文翻译到右侧（快捷键：Ctrl+Enter）",
            "tip_copy_source": "复制左侧识别结果",
            "tip_copy_target": "复制右侧翻译结果",
            "tip_clear": "清空原文和译文",
            "tip_settings": "配置 API / 界面语言 / 交互功能",
            "tip_theme": "切换主题（暗色/亮色）",
            "source_placeholder": "原文（可编辑，支持手动翻译）",
            "target_placeholder": "译文（翻译结果）",
            "dlg_title": "设置",
            "ui_lang": "界面语言",
            "ui_zh": "中文",
            "ui_en": "English",
            "llm_enable": "启用 F4 大模型交互（使用 API）",
            "backend": "翻译后端",
            "backend_offline": "离线（当前内置模型）",
            "backend_api": "API（用大模型翻译）",
            "api_profile": "配置名称",
            "api_base": "API Base URL",
            "api_model": "Model",
            "api_key": "API Key",
            "save": "保存",
            "delete": "删除",
            "ok": "确定",
        }
        en = {
            "dashboard_title": "FlashTrans Dashboard",
            "translate": "Translate",
            "copy_source": "Copy Source",
            "copy_target": "Copy Target",
            "clear": "Clear",
            "settings": "Settings",
            "theme": "Theme",
            "lang_auto": "Target: Auto",
            "lang_zh": "Target: Chinese",
            "lang_en": "Target: English",
            "lang_ja": "Target: Japanese",
            "lang_ko": "Target: Korean",
            "lang_fr": "Target: French",
            "lang_de": "Target: German",
            "lang_es": "Target: Spanish",
            "lang_ru": "Target: Russian",
            "tip_translate": "Translate left text to the right (Ctrl+Enter)",
            "tip_copy_source": "Copy source text",
            "tip_copy_target": "Copy translated text",
            "tip_clear": "Clear both panes",
            "tip_settings": "Configure API / UI language / interactions",
            "tip_theme": "Toggle theme",
            "source_placeholder": "Source text (editable)",
            "target_placeholder": "Translation result",
            "dlg_title": "Settings",
            "ui_lang": "UI Language",
            "ui_zh": "中文",
            "ui_en": "English",
            "llm_enable": "Enable F4 LLM (via API)",
            "backend": "Translation Backend",
            "backend_offline": "Offline (built-in)",
            "backend_api": "API (LLM translation)",
            "api_profile": "Profile Name",
            "api_base": "API Base URL",
            "api_model": "Model",
            "api_key": "API Key",
            "save": "Save",
            "delete": "Delete",
            "ok": "OK",
        }
        return (en if self._ui_lang == "en" else zh).get(key, key)

    def _apply_ui_language(self) -> None:
        self.setWindowTitle(self._t("dashboard_title"))
        self._title.setText(self._t("dashboard_title"))
        self._btn_translate.setText(self._t("translate"))
        self._btn_copy_src.setText(self._t("copy_source"))
        self._btn_copy_tgt.setText(self._t("copy_target"))
        self._btn_clear.setText(self._t("clear"))
        self._btn_theme.setText(self._t("theme"))
        self._btn_settings.setText(self._t("settings"))

        self._btn_translate.setToolTip(self._t("tip_translate"))
        self._btn_copy_src.setToolTip(self._t("tip_copy_source"))
        self._btn_copy_tgt.setToolTip(self._t("tip_copy_target"))
        self._btn_clear.setToolTip(self._t("tip_clear"))
        self._btn_theme.setToolTip(self._t("tip_theme"))
        self._btn_settings.setToolTip(self._t("tip_settings"))

        self._source_edit.setPlaceholderText(self._t("source_placeholder"))
        self._target_edit.setPlaceholderText(self._t("target_placeholder"))
        cur = self.get_target_language()
        self._target_lang.blockSignals(True)
        self._target_lang.clear()
        self._target_lang.addItem(self._t("lang_auto"), "auto")
        self._target_lang.addItem(self._t("lang_zh"), "zh")
        self._target_lang.addItem(self._t("lang_en"), "en")
        self._target_lang.addItem(self._t("lang_ja"), "ja")
        self._target_lang.addItem(self._t("lang_ko"), "ko")
        self._target_lang.addItem(self._t("lang_fr"), "fr")
        self._target_lang.addItem(self._t("lang_de"), "de")
        self._target_lang.addItem(self._t("lang_es"), "es")
        self._target_lang.addItem(self._t("lang_ru"), "ru")
        self._set_combo_by_data(self._target_lang, cur)
        self._target_lang.blockSignals(False)

    def _set_combo_by_data(self, combo: QComboBox, value: str) -> None:
        value = str(value or "")
        for i in range(combo.count()):
            if str(combo.itemData(i)) == value:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(0)

    def _open_settings_dialog(self) -> None:
        dlg = _SettingsDialog(self._store, self._ui_lang, self, on_hotkeys_changed=self._on_hotkeys_changed)
        if dlg.exec() == QDialog.Accepted:
            self._ui_lang = self._store.get_ui_language()
            self._apply_ui_language()


class _SettingsDialog(QDialog):
    def __init__(
        self,
        store: SettingsStore,
        ui_lang: str,
        parent: QWidget | None = None,
        on_hotkeys_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._ui_lang = ui_lang if ui_lang in ("zh-CN", "en") else "zh-CN"
        self._on_hotkeys_changed = on_hotkeys_changed
        self.setWindowTitle("设置" if self._ui_lang != "en" else "Settings")
        self.setModal(True)
        self.resize(560, 520)
        if parent is not None:
            try:
                self.setStyleSheet(parent.styleSheet())
            except Exception:
                pass

        root = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        root.addLayout(form)

        self._lang_combo = QComboBox(self)
        self._lang_combo.addItem("中文", "zh-CN")
        self._lang_combo.addItem("English", "en")
        self._set_combo_by_data(self._lang_combo, self._store.get_ui_language())
        form.addRow("界面语言" if self._ui_lang != "en" else "UI Language", self._lang_combo)

        self._llm_enable = QCheckBox(
            "启用 F4 大模型交互（使用 API）" if self._ui_lang != "en" else "Enable F4 LLM (via API)", self
        )
        self._llm_enable.setChecked(self._store.get_llm_enabled())
        form.addRow("", self._llm_enable)



        hotkey_box = QGroupBox("快捷键" if self._ui_lang != "en" else "Hotkeys", self)
        hotkey_layout = QFormLayout(hotkey_box)
        hotkey_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._hk_f1 = _HotkeyEdit(hotkey_box)
        self._hk_f2 = _HotkeyEdit(hotkey_box)
        self._hk_f3 = _HotkeyEdit(hotkey_box)
        self._hk_f4 = _HotkeyEdit(hotkey_box)
        self._hk_f5 = _HotkeyEdit(hotkey_box)

        hotkey_layout.addRow("F1 划词" if self._ui_lang != "en" else "F1 Hover", self._hk_f1)
        hotkey_layout.addRow("F2 打字" if self._ui_lang != "en" else "F2 Type", self._hk_f2)
        hotkey_layout.addRow("F3 截图" if self._ui_lang != "en" else "F3 Screenshot", self._hk_f3)
        hotkey_layout.addRow("F4 对话" if self._ui_lang != "en" else "F4 Chat", self._hk_f4)
        hotkey_layout.addRow("F5 仪表盘" if self._ui_lang != "en" else "F5 Dashboard", self._hk_f5)

        hk_btn_row = QWidget(hotkey_box)
        hk_btn_layout = QHBoxLayout(hk_btn_row)
        hk_btn_layout.setContentsMargins(0, 0, 0, 0)
        hk_btn_layout.setSpacing(8)
        self._btn_hotkeys_reset = QPushButton("恢复默认" if self._ui_lang != "en" else "Reset", hk_btn_row)
        self._btn_hotkeys_save = QPushButton("保存快捷键" if self._ui_lang != "en" else "Save Hotkeys", hk_btn_row)
        hk_btn_layout.addStretch(1)
        hk_btn_layout.addWidget(self._btn_hotkeys_reset)
        hk_btn_layout.addWidget(self._btn_hotkeys_save)
        hotkey_layout.addRow("", hk_btn_row)

        self._load_hotkeys()
        root.addWidget(hotkey_box)

        api_box = QGroupBox("API" if self._ui_lang == "en" else "API 配置", self)
        api_layout = QFormLayout(api_box)
        api_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._profile_combo = QComboBox(api_box)
        for n in self._store.list_profiles():
            self._profile_combo.addItem(n, n)
        self._set_combo_by_data(self._profile_combo, self._store.get_selected_profile())
        api_layout.addRow("配置名称" if self._ui_lang != "en" else "Profile", self._profile_combo)

        p = self._store.get_profile(str(self._profile_combo.currentData() or "default"))
        self._base_url = QLineEdit(api_box)
        self._base_url.setText(p.base_url)
        self._base_url.setPlaceholderText("https://api.example.com/v1")
        api_layout.addRow("API URL", self._base_url)

        self._model = QLineEdit(api_box)
        self._model.setText(p.model)
        self._model.setPlaceholderText("gpt-4o-mini / deepseek-chat / ...")
        api_layout.addRow("Model", self._model)

        key_row = QWidget(api_box)
        key_row_layout = QHBoxLayout(key_row)
        key_row_layout.setContentsMargins(0, 0, 0, 0)
        key_row_layout.setSpacing(8)

        self._api_key = QLineEdit(key_row)
        self._api_key.setEchoMode(QLineEdit.Password)
        self._api_key.setText(p.api_key)
        self._api_key.setPlaceholderText("sk-...")

        self._show_key = QCheckBox("显示" if self._ui_lang != "en" else "Show", key_row)
        self._show_key.setChecked(False)
        self._show_key.toggled.connect(
            lambda on: self._api_key.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
        )
        key_row_layout.addWidget(self._api_key, 1)
        key_row_layout.addWidget(self._show_key)
        api_layout.addRow("API Key", key_row)

        root.addWidget(api_box)

        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        self._btn_save = QPushButton("保存" if self._ui_lang != "en" else "Save", row)
        self._btn_delete = QPushButton("删除" if self._ui_lang != "en" else "Delete", row)
        self._btn_ok = QPushButton("确定" if self._ui_lang != "en" else "OK", row)
        row_layout.addStretch(1)
        row_layout.addWidget(self._btn_save)
        row_layout.addWidget(self._btn_delete)
        row_layout.addWidget(self._btn_ok)
        root.addWidget(row)

        self._profile_combo.currentIndexChanged.connect(self._load_profile)
        self._btn_save.clicked.connect(self._save)
        self._btn_delete.clicked.connect(self._delete)
        self._btn_hotkeys_reset.clicked.connect(self._reset_hotkeys)
        self._btn_hotkeys_save.clicked.connect(lambda: self._save_hotkeys(show_success=True))
        self._btn_ok.clicked.connect(self._ok)

    def _set_combo_by_data(self, combo: QComboBox, value: str) -> None:
        value = str(value or "")
        for i in range(combo.count()):
            if str(combo.itemData(i)) == value:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(0)

    def _load_profile(self) -> None:
        name = str(self._profile_combo.currentData() or "default")
        p = self._store.get_profile(name)
        self._base_url.setText(p.base_url)
        self._model.setText(p.model)
        self._api_key.setText(p.api_key)
        self._store.set_selected_profile(name)

    def _save(self) -> None:
        name = str(self._profile_combo.currentData() or "default").strip() or "default"
        p = ApiProfile(
            name=name,
            base_url=str(self._base_url.text() or "").strip(),
            api_key=str(self._api_key.text() or "").strip(),
            model=str(self._model.text() or "").strip(),
        )
        self._store.upsert_profile(p)
        self._store.set_selected_profile(name)
        QMessageBox.information(
            self, "提示" if self._ui_lang != "en" else "Info", "已保存" if self._ui_lang != "en" else "Saved"
        )

    def _delete(self) -> None:
        name = str(self._profile_combo.currentData() or "default").strip()
        if not name or name == "default":
            return
        self._store.delete_profile(name)
        self._profile_combo.clear()
        for n in self._store.list_profiles():
            self._profile_combo.addItem(n, n)
        self._set_combo_by_data(self._profile_combo, self._store.get_selected_profile())
        self._load_profile()

    def _ok(self) -> None:
        self._store.set_ui_language(str(self._lang_combo.currentData() or "zh-CN"))
        self._store.set_llm_enabled(bool(self._llm_enable.isChecked()))
        self._store.set_selected_profile(str(self._profile_combo.currentData() or "default"))
        if not self._save_hotkeys(show_success=False):
            return
        self.accept()

    def _load_hotkeys(self) -> None:
        hk = self._store.get_hotkeys()
        self._hk_f1.set_hotkey(int(hk.get("f1", {}).get("mods", 0)), int(hk.get("f1", {}).get("vk", 0x70)))
        self._hk_f2.set_hotkey(int(hk.get("f2", {}).get("mods", 0)), int(hk.get("f2", {}).get("vk", 0x71)))
        self._hk_f3.set_hotkey(int(hk.get("f3", {}).get("mods", 0)), int(hk.get("f3", {}).get("vk", 0x72)))
        self._hk_f4.set_hotkey(int(hk.get("f4", {}).get("mods", 0)), int(hk.get("f4", {}).get("vk", 0x73)))
        self._hk_f5.set_hotkey(int(hk.get("f5", {}).get("mods", 0)), int(hk.get("f5", {}).get("vk", 0x74)))

    def _reset_hotkeys(self) -> None:
        self._hk_f1.set_hotkey(0, 0x70)
        self._hk_f2.set_hotkey(0, 0x71)
        self._hk_f3.set_hotkey(0, 0x72)
        self._hk_f4.set_hotkey(0, 0x73)
        self._hk_f5.set_hotkey(0, 0x74)

    def _collect_hotkeys(self) -> dict[str, dict[str, int]]:
        return {
            "f1": self._hk_f1.hotkey(),
            "f2": self._hk_f2.hotkey(),
            "f3": self._hk_f3.hotkey(),
            "f4": self._hk_f4.hotkey(),
            "f5": self._hk_f5.hotkey(),
        }

    def _save_hotkeys(self, show_success: bool) -> bool:
        hk = self._collect_hotkeys()
        labels = {
            "f1": "F1 划词" if self._ui_lang != "en" else "F1 Hover",
            "f2": "F2 打字" if self._ui_lang != "en" else "F2 Type",
            "f3": "F3 截图" if self._ui_lang != "en" else "F3 Screenshot",
            "f4": "F4 对话" if self._ui_lang != "en" else "F4 Chat",
            "f5": "F5 仪表盘" if self._ui_lang != "en" else "F5 Dashboard",
        }
        seen: dict[tuple[int, int], str] = {}
        conflicts: list[tuple[str, str, str]] = []
        for k, v in hk.items():
            key = (int(v.get("mods", 0)), int(v.get("vk", 0)))
            if key in seen:
                conflicts.append((labels.get(seen[key], seen[key]), labels.get(k, k), _format_hotkey(*key)))
            else:
                seen[key] = k
        if conflicts:
            msg = "\n".join([f"{a} / {b}: {combo}" for a, b, combo in conflicts[:3]])
            QMessageBox.warning(
                self,
                "冲突" if self._ui_lang != "en" else "Conflict",
                ("快捷键冲突，请修改后再保存：\n" if self._ui_lang != "en" else "Hotkey conflict, please change and save again:\n")
                + msg,
            )
            return False

        self._store.set_hotkeys(hk)
        ok = callable(self._on_hotkeys_changed)
        if ok:
            try:
                self._on_hotkeys_changed()
            except Exception:
                ok = False
        if show_success:
            QMessageBox.information(
                self,
                "提示" if self._ui_lang != "en" else "Info",
                "已保存并生效" if (self._ui_lang != "en" and ok) else ("Saved and applied" if ok else ("已保存，重启后生效" if self._ui_lang != "en" else "Saved, restart required")),
            )
        return True


MainWindow = DashboardWindow
