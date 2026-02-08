from __future__ import annotations

import ctypes
import re
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QThread, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QCursor, QGuiApplication, QImage
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon, QStyle

from core_engine import CoreEngine
from main_window import DashboardWindow
from snipping_tool import SnippingOverlay
from ui_popups import FloatingPopup, ScreenshotResultOverlay

WM_HOTKEY = 0x0312
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
                            QTimer.singleShot(0, lambda: self._popup.f2_canceled_with_paste.emit(self._popup.input_edit.text()))
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

    def register_fkeys(self) -> dict[int, bool]:
        QGuiApplication.instance().installNativeEventFilter(self._filter)
        results: dict[int, bool] = {}
        results[1] = self._register_one(1, VK_F1)
        results[2] = self._register_one(2, VK_F2)
        results[3] = self._register_one(3, VK_F3)
        return results

    def unregister_all(self) -> None:
        for hid in list(self._registered):
            UnregisterHotKey(None, hid)
            self._registered.discard(hid)
        try:
            QGuiApplication.instance().removeNativeEventFilter(self._filter)
        except Exception:
            pass

    def _register_one(self, hotkey_id: int, vk: int) -> bool:
        ok = bool(RegisterHotKey(None, int(hotkey_id), MOD_NOREPEAT, int(vk)))
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
    failed = Signal(int, str)

    def __init__(self, engine: CoreEngine) -> None:
        super().__init__()
        self._engine = engine

    @Slot(int, str)
    def translate_en2zh(self, req_id: int, text: str) -> None:
        try:
            translated = self._engine.translate_en2zh(text)
            self.text_done.emit(int(req_id), translated)
        except Exception as e:
            self.failed.emit(int(req_id), str(e))

    @Slot(int, str)
    def translate_zh2en(self, req_id: int, text: str) -> None:
        try:
            translated = self._engine.translate_zh2en(text)
            self.text_done.emit(int(req_id), translated)
        except Exception as e:
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
    request_image = Signal(int, QImage)

    def __init__(
        self,
        tray: QSystemTrayIcon,
        overlay: SnippingOverlay,
        engine: CoreEngine,
        dashboard: DashboardWindow,
    ) -> None:
        super().__init__()
        self._tray = tray
        self._overlay = overlay
        self._engine = engine
        self._dashboard = dashboard

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
        self._worker = EngineWorker(engine)
        self._worker.moveToThread(self._thread)
        self.request_text_en2zh.connect(self._worker.translate_en2zh, Qt.QueuedConnection)
        self.request_text_zh2en.connect(self._worker.translate_zh2en, Qt.QueuedConnection)
        self.request_image.connect(self._worker.process_image, Qt.QueuedConnection)
        self._worker.text_done.connect(self._on_text_done, Qt.QueuedConnection)
        self._worker.image_done.connect(self._on_image_done, Qt.QueuedConnection)
        self._worker.failed.connect(self._on_failed, Qt.QueuedConnection)
        self._thread.start()

        self._overlay.captured.connect(self._on_screenshot_captured)
        self._overlay.canceled.connect(self._on_screenshot_canceled)

        self._dashboard.translate_requested.connect(self._dashboard_translate)
        self._dashboard.copy_source_requested.connect(self._dashboard_copy_source)
        self._dashboard.copy_target_requested.connect(self._dashboard_copy_target)
        self._dashboard.clear_requested.connect(self._dashboard_clear)
        self._dashboard.settings_requested.connect(self._dashboard.toggle_theme)

    def shutdown(self) -> None:
        self._dismiss_hooks.shutdown()
        self._f1_timer.stop()
        self._thread.quit()
        self._thread.wait(1500)

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
            return

        if mode == "DASH":
            self._dashboard.set_target_text((translated or "").strip())
            self._dashboard.show()
            self._dashboard.raise_()
            self._dashboard.activateWindow()
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
        self._pending.pop(int(req_id), None)
        self._busy_image = False
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
        is_zh = bool(re.search(r'[\u4e00-\u9fa5]', src))
        self._dashboard.set_target_text("Translating...")
        req_id = self._alloc_req_id()
        self._pending[req_id] = ("DASH", None)
        if is_zh:
            self.request_text_zh2en.emit(req_id, src)
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


def _validate_models_or_exit(model_dir_en2zh: Path, model_dir_zh2en: Path) -> None:
    missing: list[Path] = []
    for d in (model_dir_en2zh, model_dir_zh2en):
        sp = d / "source.spm"
        if not sp.exists():
            missing.append(sp.resolve())
    if missing:
        QMessageBox.critical(None, "FlashTrans", "Missing model file(s):\n" + "\n".join(str(p) for p in missing))
        sys.exit(1)


def main() -> int:
    app = QApplication([])
    app.setApplicationName("FlashTrans")
    app.setQuitOnLastWindowClosed(False)

    model_dir_en2zh = Path("./models/opus-mt-en-zh-int8").resolve()
    model_dir_zh2en = Path("./models/opus-mt-zh-en-int8").resolve()
    _validate_models_or_exit(model_dir_en2zh, model_dir_zh2en)

    icon = app.style().standardIcon(QStyle.SP_FileDialogInfoView)
    tray = QSystemTrayIcon(icon, app)
    menu = QMenu()
    act_dashboard = menu.addAction("打开仪表盘")
    act_exit = menu.addAction("退出")
    tray.setContextMenu(menu)
    tray.setToolTip("FlashTrans（离线翻译）\nF1 划词中英互译 / F2 输入中英互译 / F3 截图中英互译")
    tray.show()

    overlay = SnippingOverlay()
    engine = CoreEngine(model_dir_en2zh=model_dir_en2zh, model_dir_zh2en=model_dir_zh2en)
    dashboard = DashboardWindow()
    dashboard.hide()
    controller = AppController(tray, overlay, engine, dashboard)

    hotkeys = GlobalHotkeyManager()
    results = hotkeys.register_fkeys()
    if not all(results.values()):
        tray.showMessage("FlashTrans", "全局热键注册失败：可能被其他程序占用。", QSystemTrayIcon.Warning, 2500)

    hotkeys.hotkey_pressed.connect(
        lambda hid: controller.on_hotkey_f1()
        if hid == 1
        else controller.on_hotkey_f2()
        if hid == 2
        else controller.on_hotkey_f3()
        if hid == 3
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
