from __future__ import annotations

import ctypes
import os
import re
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QThread, Qt, QTimer, Signal, Slot, QRect
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon, QStyle

from chat_window import ChatWindow
from core_engine import CoreEngine
from llm_api import LlmConfig, chat_completions
from local_qwen import LocalQwen, LocalQwenError, QwenLocalConfig, guess_target_lang
from main_window import DashboardWindow
from settings_store import SettingsStore
from snipping_tool import SnippingOverlay
from ui_popups import FloatingPopup, ScreenshotResultOverlay

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
WM_XBUTTONDOWN = 0x020B

VK_F1 = 0x70
VK_F2 = 0x71
VK_F3 = 0x72
VK_F4 = 0x73
VK_F5 = 0x74

VK_CONTROL = 0x11
VK_C = 0x43
VK_V = 0x56
VK_INSERT = 0x2D
VK_A = 0x41
VK_ESCAPE = 0x1B
VK_RETURN = 0x0D

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_UNICODE = 0x0004
MAPVK_VK_TO_VSC = 0

ULONG_PTR = getattr(wintypes, "ULONG_PTR", ctypes.c_size_t)
LRESULT = getattr(wintypes, "LRESULT", ctypes.c_ssize_t)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def _autocrop_alpha(img: QImage, alpha_threshold: int = 8) -> QImage:
    img = img.convertToFormat(QImage.Format_RGBA8888)
    w, h = img.width(), img.height()
    if w <= 0 or h <= 0:
        return img

    left, top = w, h
    right, bottom = -1, -1

    for y in range(h):
        for x in range(w):
            a = img.pixelColor(x, y).alpha()
            if a > alpha_threshold:
                if x < left: left = x
                if y < top: top = y
                if x > right: right = x
                if y > bottom: bottom = y

    if right < left or bottom < top:
        return img

    rect = QRect(left, top, right - left + 1, bottom - top + 1)
    rect = rect.adjusted(-1, -1, 1, 1).intersected(QRect(0, 0, w, h))
    return img.copy(rect)

def _make_logo_icon() -> QIcon:
    logo_path = None
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
        for cand in (
            base_dir / "new_logo.png",
            base_dir / "_internal" / "assets" / "new_logo.png",
        ):
            if cand.exists():
                logo_path = cand
                break

    if logo_path is None:
        base_dir = Path(__file__).resolve().parent
        cand = base_dir / "assets" / "new_logo.png"
        if cand.exists():
            logo_path = cand

    if logo_path is not None:
        img = QImage(str(logo_path))
        if not img.isNull():
            cropped = _autocrop_alpha(img, alpha_threshold=8)

            icon = QIcon()
            for size in (16, 20, 24, 32, 48, 64, 128, 256):
                pm = QPixmap.fromImage(
                    cropped.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                if pm.width() != size or pm.height() != size:
                    canvas = QPixmap(size, size)
                    canvas.fill(Qt.transparent)
                    p = QPainter(canvas)
                    x = (size - pm.width()) // 2
                    y = (size - pm.height()) // 2
                    p.drawPixmap(x, y, pm)
                    p.end()
                    pm = canvas

                icon.addPixmap(pm)
            return icon

    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0))

        margin = max(1, size // 10)
        bar_h = max(2, size // 5)
        stem_w = max(2, size // 5)
        stem_h = max(2, size - margin * 2 - bar_h)

        radius_bar = max(1, bar_h // 2)
        radius_stem = max(1, stem_w // 2)

        painter.drawRoundedRect(margin, margin, size - margin * 2, bar_h, radius_bar, radius_bar)
        stem_x = (size - stem_w) // 2
        stem_y = margin + bar_h
        painter.drawRoundedRect(stem_x, stem_y, stem_w, stem_h, radius_stem, radius_stem)

        painter.end()
        icon.addPixmap(pm)
    return icon

RegisterHotKey = user32.RegisterHotKey
RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
RegisterHotKey.restype = wintypes.BOOL

UnregisterHotKey = user32.UnregisterHotKey
UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
UnregisterHotKey.restype = wintypes.BOOL

SendInput = user32.SendInput
SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
SendInput.restype = wintypes.UINT

keybd_event = user32.keybd_event
keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ULONG_PTR]
keybd_event.restype = None

MapVirtualKeyW = user32.MapVirtualKeyW
MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
MapVirtualKeyW.restype = wintypes.UINT

GetForegroundWindow = user32.GetForegroundWindow
GetForegroundWindow.argtypes = []
GetForegroundWindow.restype = wintypes.HWND

SetForegroundWindow = user32.SetForegroundWindow
SetForegroundWindow.argtypes = [wintypes.HWND]
SetForegroundWindow.restype = wintypes.BOOL

GetWindowThreadProcessId = user32.GetWindowThreadProcessId
GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
GetWindowThreadProcessId.restype = wintypes.DWORD

AttachThreadInput = user32.AttachThreadInput
AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
AttachThreadInput.restype = wintypes.BOOL

GetClipboardSequenceNumber = user32.GetClipboardSequenceNumber
GetClipboardSequenceNumber.argtypes = []
GetClipboardSequenceNumber.restype = wintypes.DWORD

OpenClipboard = user32.OpenClipboard
OpenClipboard.argtypes = [wintypes.HWND]
OpenClipboard.restype = wintypes.BOOL

CloseClipboard = user32.CloseClipboard
CloseClipboard.argtypes = []
CloseClipboard.restype = wintypes.BOOL

GetClipboardData = user32.GetClipboardData
GetClipboardData.argtypes = [wintypes.UINT]
GetClipboardData.restype = wintypes.HANDLE

IsClipboardFormatAvailable = user32.IsClipboardFormatAvailable
IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
IsClipboardFormatAvailable.restype = wintypes.BOOL

CF_UNICODETEXT = 13

GetWindowRect = user32.GetWindowRect
GetWindowRect.argtypes = [wintypes.HWND, ctypes.c_void_p]
GetWindowRect.restype = wintypes.BOOL

GlobalLock = kernel32.GlobalLock
GlobalLock.argtypes = [wintypes.HGLOBAL]
GlobalLock.restype = wintypes.LPVOID

GlobalUnlock = kernel32.GlobalUnlock
GlobalUnlock.argtypes = [wintypes.HGLOBAL]
GlobalUnlock.restype = wintypes.BOOL

GlobalSize = kernel32.GlobalSize
GlobalSize.argtypes = [wintypes.HGLOBAL]
GlobalSize.restype = ctypes.c_size_t

SetWindowsHookExW = user32.SetWindowsHookExW
SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
SetWindowsHookExW.restype = wintypes.HHOOK

CallNextHookEx = user32.CallNextHookEx
CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
CallNextHookEx.restype = LRESULT

UnhookWindowsHookEx = user32.UnhookWindowsHookEx
UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
UnhookWindowsHookEx.restype = wintypes.BOOL

GetModuleHandleW = kernel32.GetModuleHandleW
GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
GetModuleHandleW.restype = wintypes.HMODULE

GetCurrentThreadId = kernel32.GetCurrentThreadId
GetCurrentThreadId.argtypes = []
GetCurrentThreadId.restype = wintypes.DWORD

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


LowLevelKeyboardProc = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
LowLevelMouseProc = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _send_ctrl_c() -> None:
    _send_ctrl_combo_scan(VK_C)
    _send_ctrl_combo_vk(VK_C)
    sc_ctrl = int(MapVirtualKeyW(VK_CONTROL, MAPVK_VK_TO_VSC))
    sc_c = int(MapVirtualKeyW(VK_C, MAPVK_VK_TO_VSC))
    keybd_event(VK_CONTROL, sc_ctrl, 0, ULONG_PTR(0))
    keybd_event(VK_C, sc_c, 0, ULONG_PTR(0))
    keybd_event(VK_C, sc_c, KEYEVENTF_KEYUP, ULONG_PTR(0))
    keybd_event(VK_CONTROL, sc_ctrl, KEYEVENTF_KEYUP, ULONG_PTR(0))


def _send_ctrl_v() -> None:
    sc_ctrl = int(MapVirtualKeyW(VK_CONTROL, MAPVK_VK_TO_VSC))
    sc_v = int(MapVirtualKeyW(VK_V, MAPVK_VK_TO_VSC))
    keybd_event(VK_CONTROL, sc_ctrl, 0, ULONG_PTR(0))
    keybd_event(VK_V, sc_v, 0, ULONG_PTR(0))
    keybd_event(VK_V, sc_v, KEYEVENTF_KEYUP, ULONG_PTR(0))
    keybd_event(VK_CONTROL, sc_ctrl, KEYEVENTF_KEYUP, ULONG_PTR(0))


def _send_ctrl_a() -> None:
    _send_ctrl_combo_scan(VK_A)
    _send_ctrl_combo_vk(VK_A)


def _send_ctrl_insert_copy() -> None:
    _send_ctrl_combo_scan(VK_INSERT)
    _send_ctrl_combo_vk(VK_INSERT)
    sc_ctrl = int(MapVirtualKeyW(VK_CONTROL, MAPVK_VK_TO_VSC))
    sc_ins = int(MapVirtualKeyW(VK_INSERT, MAPVK_VK_TO_VSC))
    keybd_event(VK_CONTROL, sc_ctrl, 0, ULONG_PTR(0))
    keybd_event(VK_INSERT, sc_ins, 0, ULONG_PTR(0))
    keybd_event(VK_INSERT, sc_ins, KEYEVENTF_KEYUP, ULONG_PTR(0))
    keybd_event(VK_CONTROL, sc_ctrl, KEYEVENTF_KEYUP, ULONG_PTR(0))


def _refocus(hwnd: int) -> None:
    if not hwnd:
        return
    cur_tid = int(GetCurrentThreadId())
    pid = wintypes.DWORD(0)
    fg_tid = int(GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid)))
    if fg_tid:
        AttachThreadInput(wintypes.DWORD(cur_tid), wintypes.DWORD(fg_tid), True)
    SetForegroundWindow(wintypes.HWND(hwnd))
    if fg_tid:
        AttachThreadInput(wintypes.DWORD(cur_tid), wintypes.DWORD(fg_tid), False)


def _send_ctrl_combo_scan(vk: int) -> None:
    extra = ULONG_PTR(0)
    sc_ctrl = int(MapVirtualKeyW(VK_CONTROL, MAPVK_VK_TO_VSC))
    sc_key = int(MapVirtualKeyW(int(vk), MAPVK_VK_TO_VSC))
    inputs = (INPUT * 4)(
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, sc_ctrl, KEYEVENTF_SCANCODE, 0, extra)),
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, sc_key, KEYEVENTF_SCANCODE, 0, extra)),
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, sc_key, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, extra)),
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, sc_ctrl, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, extra)),
    )
    SendInput(len(inputs), ctypes.byref(inputs), ctypes.sizeof(INPUT))


def _send_ctrl_combo_vk(vk: int) -> None:
    extra = ULONG_PTR(0)
    inputs = (INPUT * 4)(
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_CONTROL, 0, 0, 0, extra)),
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(int(vk), 0, 0, 0, extra)),
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(int(vk), 0, KEYEVENTF_KEYUP, 0, extra)),
        INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0, extra)),
    )
    SendInput(len(inputs), ctypes.byref(inputs), ctypes.sizeof(INPUT))


def _send_text_input(text: str) -> None:
    if not text:
        return
    extra = ULONG_PTR(0)
    for ch in text:
        w_scan = ord(ch)
        inputs = (INPUT * 2)(
            INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, w_scan, KEYEVENTF_UNICODE, 0, extra)),
            INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, w_scan, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, extra)),
        )
        SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))
        time.sleep(0.01)


def _get_clipboard_text_win32() -> str:
    for _ in range(12):
        if OpenClipboard(None):
            break
        time.sleep(0.005)
    else:
        return ""
    try:
        if not IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        h = GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        p = GlobalLock(h)
        if not p:
            return ""
        try:
            size = int(GlobalSize(h))
            if size <= 0:
                return ""
            raw = ctypes.string_at(p, size)
            try:
                return raw.decode("utf-16-le", errors="ignore").split("\x00", 1)[0]
            except Exception:
                return ""
        finally:
            GlobalUnlock(h)
    finally:
        CloseClipboard()


class _GlobalDismissHooks(QObject):
    def __init__(self, popup: FloatingPopup, shot: ScreenshotResultOverlay) -> None:
        super().__init__()
        self._popup = popup
        self._shot = shot
        self._kbd_hook: wintypes.HHOOK | None = None
        self._mouse_hook: wintypes.HHOOK | None = None
        self._kbd_proc: object | None = None
        self._mouse_proc: object | None = None

    def enable(self) -> None:
        if self._kbd_hook is None:
            self._install_keyboard()
        if self._mouse_hook is None:
            self._install_mouse()

    def disable_if_idle(self) -> None:
        if self._popup.isVisible() or self._shot.isVisible():
            return
        self._uninstall_all()

    def shutdown(self) -> None:
        self._uninstall_all()

    def _install_keyboard(self) -> None:
        @LowLevelKeyboardProc
        def _proc(nCode, wParam, lParam):
            if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if int(info.vkCode) == VK_ESCAPE:
                    if self._popup.isVisible() or self._shot.isVisible():
                        if self._popup.isVisible() and self._popup.isActiveWindow():
                            return CallNextHookEx(self._kbd_hook or 0, nCode, wParam, lParam)
                        if self._popup.isVisible() and self._popup.input_edit.isVisible():
                            QTimer.singleShot(
                                0, lambda: self._popup.f2_canceled_with_paste.emit(self._popup.input_edit.toPlainText())
                            )
                            QTimer.singleShot(0, self._popup.hide)
                        else:
                            QTimer.singleShot(0, self._popup.close)
                        QTimer.singleShot(0, self._shot.close)
            return CallNextHookEx(self._kbd_hook or 0, nCode, wParam, lParam)

        self._kbd_proc = _proc
        hmod = GetModuleHandleW(None)
        self._kbd_hook = SetWindowsHookExW(WH_KEYBOARD_LL, ctypes.cast(_proc, ctypes.c_void_p), hmod, 0)

    def _install_mouse(self) -> None:
        @LowLevelMouseProc
        def _proc(nCode, wParam, lParam):
            if nCode >= 0 and wParam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_XBUTTONDOWN):
                info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                x = int(info.pt.x)
                y = int(info.pt.y)
                if self._popup.isVisible():
                    try:
                        r = RECT()
                        hwnd = wintypes.HWND(int(self._popup.winId()))
                        if GetWindowRect(hwnd, ctypes.byref(r)):
                            if not (r.left <= x <= r.right and r.top <= y <= r.bottom):
                                QTimer.singleShot(0, self._popup.close)
                    except Exception:
                        if not self._popup.geometry().contains(x, y):
                            QTimer.singleShot(0, self._popup.close)
                if self._shot.isVisible():
                    try:
                        r = RECT()
                        hwnd = wintypes.HWND(int(self._shot.winId()))
                        if GetWindowRect(hwnd, ctypes.byref(r)):
                            if not (r.left <= x <= r.right and r.top <= y <= r.bottom):
                                QTimer.singleShot(0, self._shot.close)
                    except Exception:
                        if not self._shot.geometry().contains(x, y):
                            QTimer.singleShot(0, self._shot.close)
            return CallNextHookEx(self._mouse_hook or 0, nCode, wParam, lParam)

        self._mouse_proc = _proc
        hmod = GetModuleHandleW(None)
        self._mouse_hook = SetWindowsHookExW(WH_MOUSE_LL, ctypes.cast(_proc, ctypes.c_void_p), hmod, 0)

    def _uninstall_all(self) -> None:
        if self._kbd_hook is not None:
            UnhookWindowsHookEx(self._kbd_hook)
            self._kbd_hook = None
            self._kbd_proc = None
        if self._mouse_hook is not None:
            UnhookWindowsHookEx(self._mouse_hook)
            self._mouse_hook = None
            self._mouse_proc = None


class GlobalHotkeyManager(QObject):
    hotkey_pressed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._registered: set[int] = set()
        self._filter = _HotkeyNativeEventFilter(self.hotkey_pressed)

    def register_hotkeys(self, hotkeys: dict[int, tuple[int, int]]) -> dict[int, bool]:
        QGuiApplication.instance().installNativeEventFilter(self._filter)
        results: dict[int, bool] = {}
        for hid, spec in hotkeys.items():
            try:
                mods, vk = spec
                results[int(hid)] = self._register_one(int(hid), int(vk), int(mods))
            except Exception:
                results[int(hid)] = False
        return results

    def unregister_all(self) -> None:
        for hid in list(self._registered):
            UnregisterHotKey(None, hid)
            self._registered.discard(hid)
        try:
            QGuiApplication.instance().removeNativeEventFilter(self._filter)
        except Exception:
            pass

    def _register_one(self, hotkey_id: int, vk: int, mods: int) -> bool:
        ok = bool(RegisterHotKey(None, int(hotkey_id), int(MOD_NOREPEAT | mods), int(vk)))
        if ok:
            self._registered.add(int(hotkey_id))
        return ok


class _HotkeyNativeEventFilter(QAbstractNativeEventFilter):
    def __init__(self, signal: Signal) -> None:
        super().__init__()
        self._signal = signal

    def nativeEventFilter(self, eventType, message):
        if eventType not in ("windows_generic_MSG", "windows_dispatcher_MSG"):
            return False, 0
        try:
            addr = int(message)
        except Exception:
            return False, 0
        msg = wintypes.MSG.from_address(addr)
        if msg.message == WM_HOTKEY:
            self._signal.emit(int(msg.wParam))
            return True, 0
        return False, 0


class EngineWorker(QObject):
    text_done = Signal(int, str)
    image_done = Signal(int, str, str)
    chat_done = Signal(int, str)
    failed = Signal(int, str)

    def __init__(self, engine: CoreEngine, qwen_model_path: Path | None = None) -> None:
        super().__init__()
        self._engine = engine
        self._llm_cfg: LlmConfig | None = None
        self._local_qwen: LocalQwen | None = None
        self._qwen_model_path: Path | None = None
        if qwen_model_path is not None and str(qwen_model_path):
            try:
                p = Path(qwen_model_path)
                self._qwen_model_path = p
                if p.exists():
                    import os
                    n_threads = max(1, (os.cpu_count() or 4) // 2)
                    self._local_qwen = LocalQwen(
                        QwenLocalConfig(model_path=p, context_length=4096, gpu_layers=0, n_threads=n_threads, n_batch=512)
                    )
            except Exception:
                self._local_qwen = None

    @Slot(int, str)
    def translate_en2zh(self, req_id: int, text: str) -> None:
        try:
            if self._local_qwen is not None:
                translated = self._local_qwen.translate(text, target_lang="zh")
            else:
                translated = self._engine.translate_en2zh(text)
            self.text_done.emit(int(req_id), translated)
        except Exception as e:
            self.failed.emit(int(req_id), str(e))

    @Slot(int, str)
    def translate_zh2en(self, req_id: int, text: str) -> None:
        try:
            if self._local_qwen is not None:
                translated = self._local_qwen.translate(text, target_lang="en")
            else:
                translated = self._engine.translate_zh2en(text)
            self.text_done.emit(int(req_id), translated)
        except Exception as e:
            self.failed.emit(int(req_id), str(e))

    @Slot(int, str, str, str)
    def translate_nllb(self, req_id: int, text: str, src_lang: str, tgt_lang: str) -> None:
        try:
            out = self._engine.translate_nllb(text, src_lang=src_lang, tgt_lang=tgt_lang)
            self.text_done.emit(int(req_id), out)
        except Exception as e:
            self.failed.emit(int(req_id), str(e))

    @Slot(object)
    def update_llm_settings(self, cfg: object) -> None:
        if not isinstance(cfg, dict):
            self._llm_cfg = None
            return
        base_url = str(cfg.get("base_url", "") or "").strip()
        api_key = str(cfg.get("api_key", "") or "").strip()
        model = str(cfg.get("model", "") or "").strip()
        if not base_url:
            self._llm_cfg = None
            return
        self._llm_cfg = LlmConfig(base_url=base_url, api_key=api_key, model=model)

    @Slot(int, str, str, bool)
    def llm_translate(self, req_id: int, text: str, target_lang: str, use_api: bool) -> None:
        use_api = bool(use_api)

        def _run_local():
            if self._local_qwen is None:
                name = self._qwen_model_path.name if self._qwen_model_path is not None else "qwen3-1.7b-q4.gguf"
                self.failed.emit(int(req_id), f"Missing local model file: {name}")
                return
            try:
                out = self._local_qwen.translate(text, target_lang=target_lang)
                self.text_done.emit(int(req_id), out)
            except Exception as e:
                self.failed.emit(int(req_id), str(e))

        if not use_api:
            _run_local()
            return

        if self._llm_cfg is None:
            # Fallback if API not configured but local is ready (and flavor is qwen)
            if self._flavor == "qwen" and self._local_qwen is not None:
                _run_local()
                return
            self.failed.emit(int(req_id), "LLM API not configured")
            return

        text = str(text or "").strip()
        if not text:
            self.text_done.emit(int(req_id), "")
            return
        target_lang = str(target_lang or "auto").strip().lower()

        system = "You are a professional translator. Return only the translation."
        if target_lang and target_lang != "auto":
            system = system + f" Target language: {target_lang}."
        messages = [{"role": "system", "content": system}, {"role": "user", "content": text}]
        try:
            out = chat_completions(self._llm_cfg, messages, temperature=0.1)
            # Strip think tags from API result too if present
            out = re.sub(r"<think>[\s\S]*?</think>", "", out, flags=re.IGNORECASE).strip()
            self.text_done.emit(int(req_id), out)
        except Exception as e:
            # Fallback on API failure
            if self._flavor == "qwen" and self._local_qwen is not None:
                _run_local()
                return
            self.failed.emit(int(req_id), str(e))

    @Slot(int, object)
    def llm_chat(self, req_id: int, payload: object) -> None:
        if not isinstance(payload, dict):
            self.failed.emit(int(req_id), "Invalid chat payload")
            return
        use_api = bool(payload.get("use_api", False))
        question = str(payload.get("question", "") or "").strip()
        if not question:
            self.chat_done.emit(int(req_id), "")
            return

        ctx_text = str(payload.get("context", "") or "").strip()

        def _run_local_chat():
            if self._local_qwen is None:
                name = self._qwen_model_path.name if self._qwen_model_path is not None else "qwen3-1.7b-q4.gguf"
                self.failed.emit(int(req_id), f"Missing local model file: {name}")
                return
            try:
                out = self._local_qwen.chat(
                    question=question,
                    context_title="",
                    context_source=ctx_text,
                    context_translated="",
                )
                self.chat_done.emit(int(req_id), out)
            except Exception as e:
                self.failed.emit(int(req_id), str(e))

        if not use_api:
            _run_local_chat()
            return

        if self._llm_cfg is None:
            if self._flavor == "qwen" and self._local_qwen is not None:
                _run_local_chat()
                return
            self.failed.emit(int(req_id), "LLM API not configured")
            return

        system = "You are a helpful assistant. Answer in Chinese unless the user explicitly requests another language."
        if ctx_text:
            system = system + "\n\n[Context]\n" + ctx_text
        messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]
        try:
            out = chat_completions(self._llm_cfg, messages, temperature=0.3)
            self.chat_done.emit(int(req_id), out)
        except Exception as e:
            if self._flavor == "qwen" and self._local_qwen is not None:
                _run_local_chat()
                return
            self.failed.emit(int(req_id), str(e))

    @Slot(int, QImage)
    def process_image(self, req_id: int, image: QImage) -> None:
        try:
            source, target = self._engine.process_image(image)
            self.image_done.emit(int(req_id), source, target)
        except Exception as e:
            self.failed.emit(int(req_id), str(e))


class AppController(QObject):
    request_text_en2zh = Signal(int, str)
    request_text_zh2en = Signal(int, str)
    request_text_nllb = Signal(int, str, str, str)
    request_image = Signal(int, QImage)
    request_llm_translate = Signal(int, str, str, bool)
    request_llm_chat = Signal(int, object)
    request_llm_settings = Signal(object)

    def __init__(
        self,
        tray: QSystemTrayIcon,
        overlay: SnippingOverlay,
        engine: CoreEngine,
        dashboard: DashboardWindow,
        flavor: str = "opus",
        qwen_model_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._tray = tray
        self._overlay = overlay
        self._engine = engine
        self._dashboard = dashboard
        self._flavor = str(flavor or "opus").strip().lower()
        self._qwen_model_path = qwen_model_path

        self._popup = FloatingPopup()
        self._popup.dismissed.connect(self._on_popup_dismissed)
        self._popup.f2_confirmed.connect(self._on_f2_confirmed)
        self._popup.f2_canceled_with_paste.connect(self._on_f2_canceled_with_paste)
        self._shot_overlay = ScreenshotResultOverlay()
        self._shot_overlay.extract_requested.connect(self._open_dashboard_from_shot)
        self._shot_overlay.dismissed.connect(self._on_shot_dismissed)
        self._dismiss_hooks = _GlobalDismissHooks(self._popup, self._shot_overlay)

        self._popup_close_timer = QTimer(self)
        self._popup_close_timer.setSingleShot(True)
        self._popup_close_timer.timeout.connect(self._popup.close)

        self._shot_close_timer = QTimer(self)
        self._shot_close_timer.setSingleShot(True)
        self._shot_close_timer.timeout.connect(self._shot_overlay.close)

        self._busy_image = False
        self._next_req_id = 1
        self._pending: dict[int, tuple[str, object]] = {}
        self._last_shot_source = ""
        self._last_shot_target = ""
        self._last_shot_rect: object | None = None
        self._f2_req_id: int | None = None
        self._f2_target_hwnd: int | None = None
        self._f1_ctx: dict[str, object] | None = None
        self._f1_timer = QTimer(self)
        self._f1_timer.setInterval(15)
        self._f1_timer.timeout.connect(self._poll_f1_clipboard)

        self._thread = QThread()
        self._worker = EngineWorker(engine, qwen_model_path=qwen_model_path)
        self._worker.moveToThread(self._thread)
        self.request_text_en2zh.connect(self._worker.translate_en2zh, Qt.QueuedConnection)
        self.request_text_zh2en.connect(self._worker.translate_zh2en, Qt.QueuedConnection)
        self.request_text_nllb.connect(self._worker.translate_nllb, Qt.QueuedConnection)
        self.request_image.connect(self._worker.process_image, Qt.QueuedConnection)
        self.request_llm_translate.connect(self._worker.llm_translate, Qt.QueuedConnection)
        self.request_llm_chat.connect(self._worker.llm_chat, Qt.QueuedConnection)
        self.request_llm_settings.connect(self._worker.update_llm_settings, Qt.QueuedConnection)
        self._worker.text_done.connect(self._on_text_done, Qt.QueuedConnection)
        self._worker.image_done.connect(self._on_image_done, Qt.QueuedConnection)
        self._worker.chat_done.connect(self._on_chat_done, Qt.QueuedConnection)
        self._worker.failed.connect(self._on_failed, Qt.QueuedConnection)
        self._thread.start()

        self._overlay.captured.connect(self._on_screenshot_captured)
        self._overlay.canceled.connect(self._on_screenshot_canceled)

        self._dashboard.translate_requested.connect(self._dashboard_translate)
        self._dashboard.copy_source_requested.connect(self._dashboard_copy_source)
        self._dashboard.copy_target_requested.connect(self._dashboard_copy_target)
        self._dashboard.clear_requested.connect(self._dashboard_clear)
        self._store = SettingsStore()
        self._chat = ChatWindow()
        self._chat.message_submitted.connect(self._on_chat_message)
        self._chat.dismissed.connect(self._on_chat_dismissed)
        self._last_context: dict[str, str] = {"title": "", "source": "", "translated": ""}
        self._sync_llm_settings()

        if self._flavor == "nllb":
            self._dashboard.set_backend_info("NLLB 1.3B (OpenNMT CT2 int8)")
        elif self._flavor == "qwen":
            self._dashboard.set_backend_info("Qwen3 (local GGUF)")
        else:
            self._dashboard.set_backend_info("Opus-MT (CT2 int8)")

    def shutdown(self) -> None:
        self._dismiss_hooks.shutdown()
        self._f1_timer.stop()
        self._thread.quit()
        self._thread.wait(1500)

    def on_hotkey_f4(self) -> None:
        self._sync_llm_settings()
        local_qwen_ready = bool(self._qwen_model_path and Path(self._qwen_model_path).exists())
        if self._flavor == "qwen":
            if (not local_qwen_ready) and (not self._store.get_llm_enabled()):
                self._tray.showMessage(
                    "FlashTrans",
                    "未找到本地 Qwen 模型，请下载到 models/ 目录后重启，或在设置里启用 API。",
                    QSystemTrayIcon.Warning,
                    5000,
                )
                return
        else:
            if not self._store.get_llm_enabled():
                self._tray.showMessage("FlashTrans", "F4 大模型交互未启用，请在仪表盘设置中开启。", QSystemTrayIcon.Information, 3000)
                return
        cb = QApplication.clipboard()
        initial_text = (_get_clipboard_text_win32() or (cb.text() or "")).strip()
        if self._chat.isVisible():
            self._chat.activateWindow()
            self._chat.raise_()
        else:
            self._chat.show()
        if initial_text:
            self._chat.set_input_text(initial_text)

    def on_hotkey_f5(self) -> None:
        if not self._dashboard:
            return
        if self._dashboard.isMinimized():
            self._dashboard.showNormal()
        elif not self._dashboard.isVisible():
            self._dashboard.show()
        self._dashboard.adjustSize()
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        geom = screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)
        size = self._dashboard.size()
        x = geom.center().x() - size.width() // 2
        y = geom.center().y() - size.height() // 2
        self._dashboard.move(max(geom.left(), x), max(geom.top(), y))
        self._dashboard.raise_()
        self._dashboard.activateWindow()
        self._dashboard.setFocus()

    def on_hotkey_f1(self) -> None:
        if self._popup.isVisible():
            self._popup.close()
            return

        hwnd = int(GetForegroundWindow())
        anchor = QCursor.pos()
        seq0 = int(GetClipboardSequenceNumber())
        cb = QApplication.clipboard()
        initial_text = (_get_clipboard_text_win32() or (cb.text() or "")).strip()
        self._f1_ctx = {
            "hwnd": hwnd,
            "anchor": anchor,
            "seq0": seq0,
            "initial_text": initial_text,
            "t0": time.monotonic(),
            "sent_insert": False,
        }

        self._popup.open_f1(anchor, "", "读取选中文本...")
        self._popup_close_timer.start(8000)
        self._dismiss_hooks.enable()

        _refocus(hwnd)
        _send_ctrl_c()
        self._f1_timer.start()

    def _poll_f1_clipboard(self) -> None:
        ctx = self._f1_ctx
        if not ctx:
            self._f1_timer.stop()
            return

        anchor = ctx.get("anchor")
        if anchor is None:
            self._f1_ctx = None
            self._f1_timer.stop()
            return

        cb = QApplication.clipboard()
        seq0 = int(ctx.get("seq0", 0))
        initial_text = str(ctx.get("initial_text", "") or "")
        t0 = float(ctx.get("t0", 0.0))
        sent_insert = bool(ctx.get("sent_insert", False))

        text = (_get_clipboard_text_win32() or (cb.text() or "")).strip()
        seq_now = int(GetClipboardSequenceNumber())

        if text and (seq_now != seq0 or text != initial_text):
            self._f1_timer.stop()
            self._f1_ctx = None
            self._popup.open_f1(anchor, text, "Translating...")
            req_id = self._alloc_req_id()
            is_zh = bool(re.search(r"[\u4e00-\u9fff]", text))
            if self._flavor == "qwen":
                target_lang = "en" if is_zh else "zh"
                use_api = False
                self._pending[req_id] = ("F1_LLM", (anchor, text))
                self.request_llm_translate.emit(req_id, text, target_lang, bool(use_api))
            else:
                self._pending[req_id] = ("F1", (anchor, text, is_zh))
                if is_zh:
                    self.request_text_zh2en.emit(req_id, text)
                else:
                    self.request_text_en2zh.emit(req_id, text)
            return

        elapsed = time.monotonic() - t0
        if (not sent_insert) and elapsed >= 0.25:
            ctx["sent_insert"] = True
            _refocus(int(ctx.get("hwnd", 0)))
            _send_ctrl_insert_copy()
            return

        if elapsed >= 0.9:
            self._f1_timer.stop()
            self._f1_ctx = None
            if text:
                self._popup.open_f1(anchor, text, "Translating...")
                req_id = self._alloc_req_id()
                is_zh = bool(re.search(r"[\u4e00-\u9fff]", text))
                if self._flavor == "qwen":
                    target_lang = "en" if is_zh else "zh"
                    use_api = False
                    self._pending[req_id] = ("F1_LLM", (anchor, text))
                    self.request_llm_translate.emit(req_id, text, target_lang, bool(use_api))
                else:
                    self._pending[req_id] = ("F1", (anchor, text, is_zh))
                    if is_zh:
                        self.request_text_zh2en.emit(req_id, text)
                    else:
                        self.request_text_en2zh.emit(req_id, text)
                return
            if initial_text:
                self._popup.open_f1(anchor, initial_text, "Translating...")
                req_id = self._alloc_req_id()
                is_zh = bool(re.search(r"[\u4e00-\u9fff]", initial_text))
                if self._flavor == "qwen":
                    target_lang = "en" if is_zh else "zh"
                    use_api = False
                    self._pending[req_id] = ("F1_LLM", (anchor, initial_text))
                    self.request_llm_translate.emit(req_id, initial_text, target_lang, bool(use_api))
                else:
                    self._pending[req_id] = ("F1", (anchor, initial_text, is_zh))
                    if is_zh:
                        self.request_text_zh2en.emit(req_id, initial_text)
                    else:
                        self.request_text_en2zh.emit(req_id, initial_text)
                return
            self._popup.show_error(anchor, "F1 (EN→ZH)", "未获取到选中文本（请确保已选中文字）")
            self._popup_close_timer.start(4000)
            return

    def on_hotkey_f2(self) -> None:
        self._f2_target_hwnd = int(GetForegroundWindow())
        anchor = QCursor.pos()

        def _enter(text: str) -> None:
            self._popup.set_f2_translating()
            req_id = self._alloc_req_id()
            self._f2_req_id = req_id
            is_zh = bool(re.search(r"[\u4e00-\u9fff]", text or ""))
            if self._flavor == "qwen":
                target_lang = "en" if is_zh else "zh"
                use_api = False
                self._pending[req_id] = ("F2_LLM", None)
                self.request_llm_translate.emit(req_id, text, target_lang, bool(use_api))
            else:
                self._pending[req_id] = ("F2", is_zh)
                if is_zh:
                    self.request_text_zh2en.emit(req_id, text)
                else:
                    self.request_text_en2zh.emit(req_id, text)

        self._popup.open_f2(anchor, _enter)
        self._dismiss_hooks.enable()

    def on_hotkey_f3(self) -> None:
        if self._shot_overlay.isVisible():
            self._shot_overlay.close()
            return
        if self._busy_image:
            return
        self._overlay.begin()

    def _alloc_req_id(self) -> int:
        rid = self._next_req_id
        self._next_req_id += 1
        return rid

    def _on_popup_dismissed(self) -> None:
        self._popup_close_timer.stop()
        self._dismiss_hooks.disable_if_idle()

    def _on_shot_dismissed(self) -> None:
        self._shot_close_timer.stop()
        self._dismiss_hooks.disable_if_idle()

    @Slot()
    def _on_screenshot_canceled(self) -> None:
        self._busy_image = False

    @Slot(object, object)
    def _on_screenshot_captured(self, pixmap, rect) -> None:
        if self._busy_image:
            return
        self._busy_image = True
        self._shot_overlay.open_for_rect(rect, "Recognizing...")
        self._dismiss_hooks.enable()
        req_id = self._alloc_req_id()
        self._pending[req_id] = ("F3", rect)
        self.request_image.emit(req_id, pixmap.toImage())

    @Slot(int, str)
    def _on_text_done(self, req_id: int, translated: str) -> None:
        mode, payload = self._pending.pop(int(req_id), ("", None))
        if mode == "F1":
            anchor, source, is_zh = payload
            translated = (translated or "").strip()
            if not translated:
                st = self._engine.status()
                translated = (st.zh2en_error if is_zh else st.en2zh_error) or "No translation result"
            self._popup.open_f1(anchor, source, translated)
            self._popup_close_timer.start(8000)
            self._last_context = {"title": "F1 划词", "source": str(source or ""), "translated": str(translated or "")}
            return

        if mode == "F1_LLM":
            anchor, source = payload
            translated = (translated or "").strip() or "No translation result"
            self._popup.open_f1(anchor, source, translated)
            self._popup_close_timer.start(8000)
            self._last_context = {"title": "F1 划词", "source": str(source or ""), "translated": str(translated or "")}
            return

        if mode == "F2_COMMIT":
            hwnd, source, is_zh = payload
            translated = (translated or "").strip()
            if not translated:
                st = self._engine.status()
                translated = (st.zh2en_error if is_zh else st.en2zh_error) or "No translation result"
            QApplication.clipboard().setText(translated)
            self._popup.hide()
            QApplication.processEvents()
            time.sleep(0.1)
            _refocus(int(hwnd))
            _send_ctrl_v()
            self._last_context = {"title": "F2 打字", "source": str(source or ""), "translated": str(translated or "")}
            return

        if mode == "F2_COMMIT_LLM":
            hwnd, source = payload
            translated = (translated or "").strip() or "No translation result"
            QApplication.clipboard().setText(translated)
            self._popup.hide()
            QApplication.processEvents()
            time.sleep(0.1)
            _refocus(int(hwnd))
            _send_ctrl_v()
            self._last_context = {"title": "F2 打字", "source": str(source or ""), "translated": str(translated or "")}
            return

        if mode == "F2":
            if self._f2_req_id != int(req_id):
                return
            is_zh = bool(payload)
            translated = (translated or "").strip()
            if not translated:
                st = self._engine.status()
                translated = (st.zh2en_error if is_zh else st.en2zh_error) or "No translation result"
            self._popup.set_f2_result(translated)
            self._last_context = {"title": "F2 打字", "source": str(self._popup.input_edit.toPlainText() or ""), "translated": str(translated or "")}
            return

        if mode == "F2_LLM":
            if self._f2_req_id != int(req_id):
                return
            translated = (translated or "").strip() or "No translation result"
            self._popup.set_f2_result(translated)
            self._last_context = {"title": "F2 打字", "source": str(self._popup.input_edit.toPlainText() or ""), "translated": str(translated or "")}
            return

        if mode in ("DASH", "DASH_LLM"):
            self._dashboard.set_target_text((translated or "").strip())
            self._dashboard.show()
            self._dashboard.raise_()
            self._dashboard.activateWindow()
            self._last_context = {"title": "仪表盘翻译", "source": str(self._dashboard.get_source_text() or ""), "translated": str(translated or "")}
            return

        if mode == "F3_LLM":
            rect, source = payload
            translated = (translated or "").strip() or "No translation result"
            self._last_shot_source = (source or "").strip()
            self._last_shot_target = translated
            self._last_shot_rect = rect
            self._shot_overlay.open_for_rect(rect, translated)
            self._shot_close_timer.start(12000)
            self._last_context = {"title": "F3 截图", "source": str(self._last_shot_source or ""), "translated": str(self._last_shot_target or "")}
            return

        self._tray.showMessage("FlashTrans", translated or "No translation result", QSystemTrayIcon.Information, 1500)

    @Slot(int, str, str)
    def _on_image_done(self, req_id: int, source: str, target: str) -> None:
        mode, rect = self._pending.pop(int(req_id), ("", None))
        self._busy_image = False
        if mode != "F3":
            return

        self._last_shot_source = (source or "").strip()
        self._last_shot_target = (target or "").strip()
        self._last_shot_rect = rect
        self._last_context = {"title": "F3 截图", "source": str(self._last_shot_source or ""), "translated": str(self._last_shot_target or "")}

        if self._flavor == "qwen" and self._last_shot_source and not self._last_shot_target:
            self._shot_overlay.open_for_rect(rect, "翻译中...")
            self._shot_close_timer.start(16000)
            req2 = self._alloc_req_id()
            use_api = False
            target_lang = self._dashboard.get_target_language()
            if not target_lang or target_lang == "auto":
                target_lang = guess_target_lang(self._last_shot_source)
            self._pending[req2] = ("F3_LLM", (rect, self._last_shot_source))
            self.request_llm_translate.emit(req2, self._last_shot_source, target_lang, bool(use_api))
            return

        text = (target or "").strip()
        if not text:
            text = (source or "").strip()
        if not text:
            st = self._engine.status()
            text = st.ocr_error or "No text detected"

        self._shot_overlay.open_for_rect(rect, text)
        self._shot_close_timer.start(12000)

    @Slot(int, str)
    def _on_failed(self, req_id: int, error: str) -> None:
        mode, _payload = self._pending.pop(int(req_id), ("", None))
        self._busy_image = False
        if mode in ("DASH", "DASH_LLM"):
            self._dashboard.set_target_text(error or "Error")
            self._dashboard.show()
            self._dashboard.raise_()
            self._dashboard.activateWindow()
            return
        if mode == "F3_LLM":
            rect, _source = _payload
            self._shot_overlay.open_for_rect(rect, error or "Error")
            self._shot_close_timer.start(12000)
            return
        if mode == "CHAT":
            self._chat.append_status(f"错误：{error or ''}".strip())
            return
        self._tray.showMessage("FlashTrans", error, QSystemTrayIcon.Warning, 2500)

    def _open_dashboard_from_shot(self) -> None:
        self._shot_overlay.close()
        self._dashboard.set_source_text(self._last_shot_source)
        self._dashboard.set_target_text(self._last_shot_target)

        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is not None:
            screen_geom = screen.availableGeometry()
            dashboard_geom = self._dashboard.frameGeometry()
            center_x = screen_geom.center().x() - dashboard_geom.width() // 2
            center_y = screen_geom.center().y() - dashboard_geom.height() // 2
            self._dashboard.move(center_x, center_y)

        self._dashboard.showNormal()
        self._dashboard.setWindowState(self._dashboard.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self._dashboard.raise_()
        self._dashboard.activateWindow()

    def _dashboard_translate(self) -> None:
        src = (self._dashboard.get_source_text() or "").strip()
        if not src:
            return
        target_lang = self._dashboard.get_target_language()

        self._dashboard.set_target_text("Translating...")
        req_id = self._alloc_req_id()
        if self._flavor == "qwen":
            if target_lang == "auto":
                target_lang = guess_target_lang(src)
            self._pending[req_id] = ("DASH_LLM", None)
            self.request_llm_translate.emit(req_id, src, target_lang, False)
            return

        if self._flavor == "nllb":
            tgt_map = {
                "zh": "zho_Hans",
                "en": "eng_Latn",
                "ja": "jpn_Jpan",
                "ko": "kor_Hang",
                "fr": "fra_Latn",
                "de": "deu_Latn",
                "es": "spa_Latn",
                "ru": "rus_Cyrl",
            }

            def guess_src_lang(text: str) -> str:
                if re.search(r"[\u4e00-\u9fff]", text):
                    return "zho_Hans"
                if re.search(r"[\u3040-\u30ff]", text):
                    return "jpn_Jpan"
                if re.search(r"[\uac00-\ud7af]", text):
                    return "kor_Hang"
                if re.search(r"[\u0400-\u04ff]", text):
                    return "rus_Cyrl"
                return "eng_Latn"

            src_lang = guess_src_lang(src)
            if target_lang == "auto":
                tgt_lang = "eng_Latn" if src_lang == "zho_Hans" else "zho_Hans"
            else:
                tgt_lang = tgt_map.get(target_lang, "")
                if not tgt_lang:
                    self._dashboard.set_target_text("该目标语言当前未配置")
                    return
            if tgt_lang == src_lang:
                self._dashboard.set_target_text(src)
                return
            self._pending[req_id] = ("DASH", None)
            self.request_text_nllb.emit(req_id, src, src_lang, tgt_lang)
            return

        if target_lang not in ("auto", "zh", "en"):
            self._dashboard.set_target_text("该目标语言需要使用其他版本")
            return

        is_zh = bool(re.search(r"[\u4e00-\u9fff]", src))
        if target_lang == "auto":
            target_lang = "en" if is_zh else "zh"
        self._pending[req_id] = ("DASH", None)
        if target_lang == "en":
            if is_zh:
                self.request_text_zh2en.emit(req_id, src)
            else:
                self._dashboard.set_target_text(src)
        else:
            if is_zh:
                self._dashboard.set_target_text(src)
            else:
                self.request_text_en2zh.emit(req_id, src)

    def _on_f2_confirmed(self, text: str) -> None:
        src = (text or "").strip()
        if not src:
            return
        hwnd = int(self._f2_target_hwnd or GetForegroundWindow())
        self._popup.set_f2_translating()
        req_id = self._alloc_req_id()
        is_zh = bool(re.search(r"[\u4e00-\u9fff]", src))
        if self._flavor == "qwen":
            target_lang = "en" if is_zh else "zh"
            use_api = False
            self._pending[req_id] = ("F2_COMMIT_LLM", (hwnd, src))
            self.request_llm_translate.emit(req_id, src, target_lang, bool(use_api))
        else:
            self._pending[req_id] = ("F2_COMMIT", (hwnd, src, is_zh))
            if is_zh:
                self.request_text_zh2en.emit(req_id, src)
            else:
                self.request_text_en2zh.emit(req_id, src)

    def _on_f2_canceled_with_paste(self, text: str) -> None:
        src = (text or "").strip()
        if not src:
            self._popup.hide()
            return
        hwnd = int(self._f2_target_hwnd or GetForegroundWindow())
        QApplication.clipboard().setText(src)
        self._popup.hide()
        QApplication.processEvents()
        time.sleep(0.1)
        _refocus(hwnd)
        _send_ctrl_v()

    def _dashboard_copy_source(self) -> None:
        QApplication.clipboard().setText(self._dashboard.get_source_text() or "")

    def _dashboard_copy_target(self) -> None:
        QApplication.clipboard().setText(self._dashboard.target_edit.toPlainText() or "")

    def _dashboard_clear(self) -> None:
        self._dashboard.set_source_text("")
        self._dashboard.set_target_text("")

    def _sync_llm_settings(self) -> None:
        p = self._store.get_profile()
        cfg = {"base_url": p.base_url, "api_key": p.api_key, "model": p.model}
        self.request_llm_settings.emit(cfg)

    def _on_chat_message(self, payload: object) -> None:
        self._sync_llm_settings()
        local_qwen_ready = bool(self._qwen_model_path and Path(self._qwen_model_path).exists())
        if not isinstance(payload, dict):
            return
        q = str(payload.get("question", "") or "").strip()
        if not q:
            return
        ctx = str(payload.get("context", "") or "").strip()

        if self._flavor == "qwen":
            if (not local_qwen_ready) and (not self._store.get_llm_enabled()):
                self._chat.append_status("未找到本地 Qwen 模型，请下载到 models/ 目录后重启，或在设置里启用 API。")
                return
            use_api = bool(self._store.get_llm_enabled())
        else:
            if not self._store.get_llm_enabled():
                self._chat.append_status("未启用 F4 大模型交互，请在仪表盘设置中开启。")
                return
            use_api = True

        self._chat.append_user(q)
        self._chat.append_status("助手思考中...")
        req_id = self._alloc_req_id()
        self._pending[req_id] = ("CHAT", None)
        worker_payload = {
            "question": q,
            "context": ctx,
            "use_api": bool(use_api),
        }
        self.request_llm_chat.emit(req_id, worker_payload)

    @Slot(int, str)
    def _on_chat_done(self, req_id: int, answer: str) -> None:
        self._pending.pop(int(req_id), None)
        self._chat.append_assistant(answer or "")

    def _on_chat_dismissed(self) -> None:
        return


def main() -> int:
    app = QApplication([])
    app.setApplicationName("FlashTrans")
    app.setQuitOnLastWindowClosed(False)

    store = SettingsStore()
    base_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    env_flavor = str(os.environ.get("FLASHTRANS_FLAVOR", "") or "").strip().lower()
    exe_stem = Path(sys.executable).stem.lower() if getattr(sys, "frozen", False) else ""
    if env_flavor in ("qwen", "nllb", "opus"):
        flavor = env_flavor
    elif "qwen" in exe_stem:
        flavor = "qwen"
    elif "nllb" in exe_stem:
        flavor = "nllb"
    else:
        flavor = "opus"
    models_candidates = [base_dir / "models", base_dir / "_internal" / "models"]

    def _pick_models_root() -> Path:
        if flavor == "qwen":
            rel = Path("qwen3-1.7b-q4.gguf")
        elif flavor == "nllb":
            rel = Path("nllb-200-1.3b-int8") / "model.bin"
        else:
            rel = Path("opus-mt-en-zh-int8") / "model.bin"

        for cand in models_candidates:
            if (cand / rel).exists():
                return cand.resolve()
        for cand in models_candidates:
            if cand.exists():
                return cand.resolve()
        return models_candidates[0].resolve()

    models_root = _pick_models_root()
    model_dir_en2zh = (models_root / "opus-mt-en-zh-int8").resolve()
    model_dir_zh2en = (models_root / "opus-mt-zh-en-int8").resolve()
    nllb_dir = (models_root / "nllb-200-1.3b-int8").resolve()
    qwen_model_path = (models_root / "qwen3-1.7b-q4.gguf").resolve()

    icon = _make_logo_icon()
    app.setWindowIcon(icon)
    tray = QSystemTrayIcon(icon, app)
    menu = QMenu()
    act_dashboard = menu.addAction("打开仪表盘")
    act_exit = menu.addAction("退出")
    tray.setContextMenu(menu)
    tray.setToolTip("FlashTrans")
    tray.show()

    overlay = SnippingOverlay()
    if flavor == "nllb":
        engine = CoreEngine(mt_backend="nllb", nllb_model_dir=nllb_dir)
    elif flavor == "qwen":
        engine = CoreEngine(mt_backend="none")
    else:
        engine = CoreEngine(model_dir_en2zh=model_dir_en2zh, model_dir_zh2en=model_dir_zh2en)
    st = engine.status()
    if flavor in ("opus", "nllb") and ((not st.en2zh_ready) or (not st.zh2en_ready)):
        details = []
        if st.en2zh_error:
            details.append(f"EN->ZH: {st.en2zh_error}")
        if st.zh2en_error:
            details.append(f"ZH->EN: {st.zh2en_error}")
        if flavor == "nllb":
            tip = "NLLB 离线模型未就绪（程序仍可启动）。\n把 models/nllb-200-1.3b-int8/ 放到程序同目录后重启。"
        else:
            tip = "离线翻译模型未就绪（程序仍可启动）。\n把 models/ 放到 FlashTrans.exe 同目录后重启。"
        if details:
            tip = tip + "\n\n" + "\n".join(details[:2])
        tray.showMessage("FlashTrans", tip, QSystemTrayIcon.Warning, 7000)
    if os.environ.get("FLASHTRANS_DEBUG_MODELS", "") == "1":
        lines = [f"models_root: {models_root}"]
        if flavor == "qwen":
            lines.append(f"qwen: {qwen_model_path} ({'OK' if qwen_model_path.exists() else 'MISSING'})")
        if flavor == "nllb":
            lines.append(f"nllb: {nllb_dir} ({'OK' if (nllb_dir / 'model.bin').exists() else 'MISSING'})")
        tray.showMessage("FlashTrans", "\n".join(lines), QSystemTrayIcon.Information, 7000)
    hotkeys = GlobalHotkeyManager()

    def _vk_to_key_name(vk: int) -> str:
        vk = int(vk)
        if 0x70 <= vk <= 0x87:
            return f"F{vk - 0x6F}"
        if 0x30 <= vk <= 0x39:
            return chr(vk)
        if 0x41 <= vk <= 0x5A:
            return chr(vk)
        names = {0x20: "Space", 0x09: "Tab", 0x1B: "Esc", 0x0D: "Enter"}
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

    def _load_hotkeys() -> dict[int, tuple[int, int]]:
        hk = store.get_hotkeys()
        return {
            1: (int(hk.get("f1", {}).get("mods", 0)), int(hk.get("f1", {}).get("vk", VK_F1))),
            2: (int(hk.get("f2", {}).get("mods", 0)), int(hk.get("f2", {}).get("vk", VK_F2))),
            3: (int(hk.get("f3", {}).get("mods", 0)), int(hk.get("f3", {}).get("vk", VK_F3))),
            4: (int(hk.get("f4", {}).get("mods", 0)), int(hk.get("f4", {}).get("vk", VK_F4))),
            5: (int(hk.get("f5", {}).get("mods", 0)), int(hk.get("f5", {}).get("vk", VK_F5))),
        }

    def _update_tray_tooltip() -> None:
        m = _load_hotkeys()
        tray.setToolTip(
            "FlashTrans\n"
            f"{_format_hotkey(*m[1])} 划词 / "
            f"{_format_hotkey(*m[2])} 打字 / "
            f"{_format_hotkey(*m[3])} 截图 / "
            f"{_format_hotkey(*m[4])} 对话 / "
            f"{_format_hotkey(*m[5])} 仪表盘"
        )

    def _apply_hotkeys() -> None:
        hotkeys.unregister_all()
        results = hotkeys.register_hotkeys(_load_hotkeys())
        _update_tray_tooltip()
        if not all(results.values()):
            tray.showMessage("FlashTrans", "全局热键注册失败：可能被其他程序占用。", QSystemTrayIcon.Warning, 2500)

    dashboard = DashboardWindow(on_hotkeys_changed=_apply_hotkeys)
    dashboard.hide()
    controller = AppController(
        tray,
        overlay,
        engine,
        dashboard,
        flavor=flavor,
        qwen_model_path=qwen_model_path if flavor == "qwen" else None,
    )

    _apply_hotkeys()

    hotkeys.hotkey_pressed.connect(
        lambda hid: controller.on_hotkey_f1()
        if hid == 1
        else controller.on_hotkey_f2()
        if hid == 2
        else controller.on_hotkey_f3()
        if hid == 3
        else controller.on_hotkey_f4()
        if hid == 4
        else controller.on_hotkey_f5()
        if hid == 5
        else None
    )

    act_dashboard.triggered.connect(lambda: (dashboard.show(), dashboard.raise_(), dashboard.activateWindow()))
    act_exit.triggered.connect(app.quit)

    def _cleanup() -> None:
        hotkeys.unregister_all()
        controller.shutdown()

    app.aboutToQuit.connect(_cleanup)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
