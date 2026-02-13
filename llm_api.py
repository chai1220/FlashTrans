from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LlmConfig:
    base_url: str
    api_key: str
    model: str


class LlmError(RuntimeError):
    pass


def _build_chat_url(base_url: str) -> str:
    base_url = str(base_url or "").strip()
    if not base_url:
        raise LlmError("Missing API base URL")
    base_url = base_url.rstrip("/")
    if base_url.endswith("/v1"):
        return base_url + "/chat/completions"
    if base_url.endswith("/chat/completions"):
        return base_url
    return base_url + "/v1/chat/completions"


def chat_completions(cfg: LlmConfig, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
    url = _build_chat_url(cfg.base_url)
    model = str(cfg.model or "").strip()
    if not model:
        model = "default"

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
        "stream": False,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    api_key = str(cfg.api_key or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        raise LlmError(f"HTTP {e.code}: {body or e.reason}") from None
    except Exception as e:
        raise LlmError(str(e)) from None

    try:
        obj = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception as e:
        raise LlmError(f"Invalid response JSON: {e}") from None

    try:
        choices = obj.get("choices") or []
        if not choices:
            raise KeyError("choices")
        msg = choices[0].get("message") or {}
        content = str(msg.get("content") or "")
        return content.strip()
    except Exception:
        raise LlmError("Missing choices/message/content in response") from None

