from __future__ import annotations

import base64
import ctypes
import json
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QSettings


@dataclass(frozen=True)
class ApiProfile:
    name: str
    base_url: str
    api_key: str
    model: str


class SettingsStore:
    def __init__(self) -> None:
        self._qs = QSettings("chai1220", "FlashTrans")

    def get_ui_language(self) -> str:
        v = str(self._qs.value("ui_language", "zh-CN"))
        return v if v in ("zh-CN", "en") else "zh-CN"

    def set_ui_language(self, lang: str) -> None:
        lang = str(lang or "")
        if lang not in ("zh-CN", "en"):
            lang = "zh-CN"
        self._qs.setValue("ui_language", lang)

    def get_subject(self) -> str:
        return ""

    def set_subject(self, subject: str) -> None:
        pass

    def get_target_language(self) -> str:
        v = str(self._qs.value("target_language", "auto") or "auto").lower().strip()
        return v or "auto"

    def set_target_language(self, lang: str) -> None:
        self._qs.setValue("target_language", str(lang or "").lower().strip() or "auto")

    def get_selected_profile(self) -> str:
        return str(self._qs.value("api_selected_profile", "default") or "default")

    def set_selected_profile(self, name: str) -> None:
        self._qs.setValue("api_selected_profile", str(name or "default").strip() or "default")

    def list_profiles(self) -> list[str]:
        raw = str(self._qs.value("api_profiles", "") or "")
        if not raw:
            return ["default"]
        try:
            obj = json.loads(raw)
        except Exception:
            return ["default"]
        if not isinstance(obj, dict):
            return ["default"]
        names = [str(k) for k in obj.keys() if str(k).strip()]
        if "default" not in names:
            names.insert(0, "default")
        return sorted(set(names))

    def get_profile(self, name: str | None = None) -> ApiProfile:
        name = str(name or self.get_selected_profile() or "default").strip() or "default"
        raw = str(self._qs.value("api_profiles", "") or "")
        if raw:
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict) and isinstance(obj.get(name), dict):
                    it = obj[name]
                    return ApiProfile(
                        name=name,
                        base_url=str(it.get("base_url", "") or ""),
                        api_key=self._decrypt(str(it.get("api_key", "") or "")),
                        model=str(it.get("model", "") or ""),
                    )
            except Exception:
                pass
        return ApiProfile(name=name, base_url="", api_key="", model="")

    def upsert_profile(self, profile: ApiProfile) -> None:
        raw = str(self._qs.value("api_profiles", "") or "")
        obj: dict[str, Any] = {}
        if raw:
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    obj = loaded
            except Exception:
                obj = {}

        name = str(profile.name or "default").strip() or "default"
        obj[name] = {
            "base_url": str(profile.base_url or "").strip(),
            "api_key": self._encrypt(str(profile.api_key or "")),
            "model": str(profile.model or "").strip(),
        }
        self._qs.setValue("api_profiles", json.dumps(obj, ensure_ascii=False))

    def delete_profile(self, name: str) -> None:
        name = str(name or "").strip()
        if not name or name == "default":
            return
        raw = str(self._qs.value("api_profiles", "") or "")
        if not raw:
            return
        try:
            obj = json.loads(raw)
        except Exception:
            return
        if not isinstance(obj, dict):
            return
        if name in obj:
            obj.pop(name, None)
            self._qs.setValue("api_profiles", json.dumps(obj, ensure_ascii=False))
        if self.get_selected_profile() == name:
            self.set_selected_profile("default")

    def get_llm_enabled(self) -> bool:
        return bool(self._qs.value("llm_enabled", False))

    def set_llm_enabled(self, enabled: bool) -> None:
        self._qs.setValue("llm_enabled", bool(enabled))

    def get_translation_backend(self) -> str:
        v = str(self._qs.value("translation_backend", "offline") or "offline").strip().lower()
        return v if v in ("offline", "api") else "offline"

    def set_translation_backend(self, backend: str) -> None:
        backend = str(backend or "").strip().lower()
        if backend not in ("offline", "api"):
            backend = "offline"
        self._qs.setValue("translation_backend", backend)

    def get_hotkeys(self) -> dict[str, dict[str, int]]:
        defaults: dict[str, dict[str, int]] = {
            "f1": {"vk": 0x70, "mods": 0},
            "f2": {"vk": 0x71, "mods": 0},
            "f3": {"vk": 0x72, "mods": 0},
            "f4": {"vk": 0x73, "mods": 0},
            "f5": {"vk": 0x74, "mods": 0},
        }
        raw = str(self._qs.value("hotkeys", "") or "")
        if not raw:
            return defaults
        try:
            obj = json.loads(raw)
        except Exception:
            return defaults
        if not isinstance(obj, dict):
            return defaults

        out: dict[str, dict[str, int]] = {}
        for k, dv in defaults.items():
            v = obj.get(k)
            if isinstance(v, dict):
                vk = int(v.get("vk", dv["vk"]) or dv["vk"])
                mods = int(v.get("mods", dv["mods"]) or dv["mods"])
                out[k] = {"vk": vk, "mods": mods}
            else:
                out[k] = {"vk": int(dv["vk"]), "mods": int(dv["mods"])}
        return out

    def set_hotkeys(self, hotkeys: dict[str, dict[str, int]]) -> None:
        out: dict[str, dict[str, int]] = {}
        for k in ("f1", "f2", "f3", "f4", "f5"):
            v = hotkeys.get(k)
            if not isinstance(v, dict):
                continue
            try:
                vk = int(v.get("vk", 0))
                mods = int(v.get("mods", 0))
            except Exception:
                continue
            if vk <= 0:
                continue
            out[k] = {"vk": vk, "mods": mods}
        self._qs.setValue("hotkeys", json.dumps(out, ensure_ascii=False))

    def _encrypt(self, plain: str) -> str:
        plain = str(plain or "")
        if not plain:
            return ""
        try:
            blob = _dpapi_encrypt(plain.encode("utf-8"))
            return base64.b64encode(blob).decode("ascii")
        except Exception:
            return ""

    def _decrypt(self, cipher_b64: str) -> str:
        cipher_b64 = str(cipher_b64 or "")
        if not cipher_b64:
            return ""
        try:
            blob = base64.b64decode(cipher_b64.encode("ascii"), validate=False)
            plain = _dpapi_decrypt(blob)
            return plain.decode("utf-8", errors="ignore")
        except Exception:
            return ""


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_CryptProtectData = _crypt32.CryptProtectData
_CryptProtectData.argtypes = [
    ctypes.POINTER(_DATA_BLOB),
    ctypes.c_wchar_p,
    ctypes.POINTER(_DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.POINTER(_DATA_BLOB),
]
_CryptProtectData.restype = ctypes.c_int

_CryptUnprotectData = _crypt32.CryptUnprotectData
_CryptUnprotectData.argtypes = [
    ctypes.POINTER(_DATA_BLOB),
    ctypes.POINTER(ctypes.c_wchar_p),
    ctypes.POINTER(_DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.POINTER(_DATA_BLOB),
]
_CryptUnprotectData.restype = ctypes.c_int

_LocalFree = _kernel32.LocalFree
_LocalFree.argtypes = [ctypes.c_void_p]
_LocalFree.restype = ctypes.c_void_p


def _dpapi_encrypt(data: bytes) -> bytes:
    in_buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    in_blob = _DATA_BLOB(cbData=len(data), pbData=ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_ubyte)))
    out_blob = _DATA_BLOB()
    ok = _CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
    if not ok:
        raise OSError(ctypes.get_last_error())
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        _LocalFree(out_blob.pbData)


def _dpapi_decrypt(data: bytes) -> bytes:
    in_buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    in_blob = _DATA_BLOB(cbData=len(data), pbData=ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_ubyte)))
    out_blob = _DATA_BLOB()
    ok = _CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
    if not ok:
        raise OSError(ctypes.get_last_error())
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        _LocalFree(out_blob.pbData)
