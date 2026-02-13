from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class QwenLocalConfig:
    model_path: Path
    context_length: int = 4096
    gpu_layers: int = 0
    n_threads: int = 0
    n_batch: int = 512


class LocalQwenError(RuntimeError):
    pass


class LocalQwen:
    def __init__(self, cfg: QwenLocalConfig) -> None:
        self._cfg = cfg
        self._llama = None

    def ensure_loaded(self) -> None:
        if self._llama is not None:
            return
        try:
            from llama_cpp import Llama
        except Exception as e:
            raise LocalQwenError(f"llama-cpp-python not available: {e}") from None
        model_path = Path(self._cfg.model_path)
        if not model_path.exists():
            raise LocalQwenError(f"Model file not found: {model_path}")
        self._llama = Llama(
            model_path=str(model_path),
            n_ctx=int(self._cfg.context_length),
            n_gpu_layers=int(self._cfg.gpu_layers),
            n_threads=int(self._cfg.n_threads) if self._cfg.n_threads > 0 else None,
            n_batch=int(self._cfg.n_batch),
            verbose=False,
        )

    def translate(self, text: str, target_lang: str) -> str:
        self.ensure_loaded()
        text = (text or "").strip()
        if not text:
            return ""
        target_lang = (target_lang or "auto").strip().lower()

        system = "You are a professional translator. Return only the translation."
        if target_lang and target_lang != "auto":
            system += f" Target language: {target_lang}."

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ]
        out = self._chat(messages, temperature=0.1)
        out = out.strip()
        out = _strip_think(out)
        return out.strip()

    def chat(self, question: str, context_title: str, context_source: str, context_translated: str) -> str:
        self.ensure_loaded()
        question = (question or "").strip()
        if not question:
            return ""
        ctx_title = (context_title or "").strip()
        ctx_source = (context_source or "").strip()
        ctx_translated = (context_translated or "").strip()

        system = "You are a helpful assistant. Answer in Chinese unless the user explicitly requests another language."
        if ctx_title or ctx_source or ctx_translated:
            ctx_lines = []
            if ctx_title:
                ctx_lines.append(f"[Context] {ctx_title}")
            if ctx_source:
                ctx_lines.append(f"[Source] {ctx_source}")
            if ctx_translated:
                ctx_lines.append(f"[Translation] {ctx_translated}")
            system += "\n\n" + "\n".join(ctx_lines)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ]
        out = self._chat(messages, temperature=0.3)
        return out.strip()

    def _chat(self, messages, temperature: float) -> str:
        if self._llama is None:
            raise LocalQwenError("Model not loaded")
        try:
            resp = self._llama.create_chat_completion(
                messages=messages,
                temperature=float(temperature),
                stream=False,
            )
            content = resp["choices"][0]["message"]["content"]
            return str(content or "")
        except Exception:
            prompt = _to_chatml(messages)
            resp = self._llama(
                prompt,
                temperature=float(temperature),
                top_p=0.9,
                max_tokens=512,
                stop=["<|im_end|>"],
            )
            text = str(resp["choices"][0]["text"] or "")
            return text


def _to_chatml(messages) -> str:
    parts: list[str] = []
    for m in messages:
        role = str(m.get("role") or "user").strip()
        content = str(m.get("content") or "")
        parts.append(f"<|im_start|>{role}\n{content}<|im_end|>\n")
    parts.append("<|im_start|>assistant\n")
    return "".join(parts)


def _strip_think(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    return text


def guess_target_lang(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "auto"
    return "en" if bool(re.search(r"[\u4e00-\u9fff]", t)) else "zh"
