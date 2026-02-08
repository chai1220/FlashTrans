from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt

try:
    import numpy as np  # type: ignore
except Exception:
    np = None  # type: ignore

try:
    from rapidocr_onnxruntime import RapidOCR  # type: ignore
except Exception:
    RapidOCR = None  # type: ignore

try:
    import ctranslate2  # type: ignore
except Exception:
    ctranslate2 = None  # type: ignore

try:
    import sentencepiece as spm  # type: ignore
except Exception:
    spm = None  # type: ignore


@dataclass(frozen=True)
class EngineStatus:
    ocr_ready: bool
    en2zh_ready: bool
    zh2en_ready: bool
    last_error: str = ""
    ocr_error: str = ""
    en2zh_error: str = ""
    zh2en_error: str = ""


class CoreEngine:
    def __init__(
        self,
        model_dir_en2zh: str | os.PathLike = "./models/opus-mt-en-zh-int8",
        model_dir_zh2en: str | os.PathLike = "./models/opus-mt-zh-en-int8",
    ) -> None:
        self._model_dir_en2zh = Path(model_dir_en2zh)
        self._model_dir_zh2en = Path(model_dir_zh2en)

        self._ocr: Any = None
        self._ocr_ready = False

        self.translator_en2zh: Any = None
        self._sp_en2zh_src: Any = None
        self._sp_en2zh_tgt: Any = None
        self._en2zh_ready = False

        self.translator_zh2en: Any = None
        self._sp_zh2en_src: Any = None
        self._sp_zh2en_tgt: Any = None
        self._zh2en_ready = False

        self._last_error = ""
        self._last_ocr_error = ""
        self._last_en2zh_error = ""
        self._last_zh2en_error = ""

        self._init_all()

    def status(self) -> EngineStatus:
        return EngineStatus(
            ocr_ready=self._ocr_ready,
            en2zh_ready=self._en2zh_ready,
            zh2en_ready=self._zh2en_ready,
            last_error=self._last_error,
            ocr_error=self._last_ocr_error,
            en2zh_error=self._last_en2zh_error,
            zh2en_error=self._last_zh2en_error,
        )

    def translate_en2zh(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        if not self._en2zh_ready or self.translator_en2zh is None:
            self._set_error(self._last_en2zh_error or "EN->ZH translator not ready", kind="en2zh")
            return ""
        try:
            return self._run_translate(text, self.translator_en2zh, self._sp_en2zh_src, self._sp_en2zh_tgt)
        except Exception as e:
            self._set_error(f"EN->ZH translation failed: {e}", kind="en2zh")
            return ""

    def translate_zh2en(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        if not self._zh2en_ready or self.translator_zh2en is None:
            self._set_error(self._last_zh2en_error or "ZH->EN translator not ready", kind="zh2en")
            return ""
        try:
            return self._run_translate(text, self.translator_zh2en, self._sp_zh2en_src, self._sp_zh2en_tgt)
        except Exception as e:
            self._set_error(f"ZH->EN translation failed: {e}", kind="zh2en")
            return ""

    def ocr_image(self, image_data: Any) -> str:
        if not self._ocr_ready or self._ocr is None:
            self._set_error(self._last_ocr_error or "OCR not ready", kind="ocr")
            return ""
        try:
            np_img = self._to_numpy_bgr(image_data)
        except Exception as e:
            self._set_error(f"Image conversion failed: {e}", kind="ocr")
            return ""
        try:
            result = self._ocr(np_img)
        except Exception as e:
            self._set_error(f"OCR failed: {e}", kind="ocr")
            return ""
        return (self._extract_rapidocr_text(result) or "").strip()

    def process_image(self, image_data: Any) -> tuple[str, str]:
        source_text = (self.ocr_image(image_data) or "").strip()
        if not source_text:
            msg = self._last_ocr_error or "No text detected"
            return "", msg
        is_zh = bool(re.search(r"[\u4e00-\u9fff]", source_text))
        if is_zh:
            translated = self.translate_zh2en(source_text)
            if not translated:
                return source_text, self._last_zh2en_error or "No translation result"
            return source_text, translated
        translated = self.translate_en2zh(source_text)
        if not translated:
            return source_text, self._last_en2zh_error or "No translation result"
        return source_text, translated

    def _init_all(self) -> None:
        self._init_ocr()
        self._init_translator_en2zh()
        self._init_translator_zh2en()

    def _init_ocr(self) -> None:
        try:
            if RapidOCR is None:
                raise ModuleNotFoundError("rapidocr_onnxruntime not installed")
            self._ocr = RapidOCR()
            if np is not None:
                try:
                    self._ocr(np.zeros((32, 32, 3), dtype=np.uint8))
                except Exception:
                    pass
            self._ocr_ready = True
        except Exception as e:
            self._ocr = None
            self._ocr_ready = False
            self._set_error(f"RapidOCR init failed: {e}", kind="ocr")

    def _init_translator_en2zh(self) -> None:
        try:
            self.translator_en2zh, self._sp_en2zh_src, self._sp_en2zh_tgt = self._load_ct2_translator(
                self._model_dir_en2zh
            )
            self._en2zh_ready = True
        except Exception as e:
            self.translator_en2zh = None
            self._sp_en2zh_src = None
            self._sp_en2zh_tgt = None
            self._en2zh_ready = False
            self._set_error(str(e), kind="en2zh")

    def _init_translator_zh2en(self) -> None:
        try:
            self.translator_zh2en, self._sp_zh2en_src, self._sp_zh2en_tgt = self._load_ct2_translator(
                self._model_dir_zh2en
            )
            self._zh2en_ready = True
        except Exception as e:
            self.translator_zh2en = None
            self._sp_zh2en_src = None
            self._sp_zh2en_tgt = None
            self._zh2en_ready = False
            self._set_error(str(e), kind="zh2en")

    def _load_ct2_translator(self, model_dir: Path) -> tuple[Any, Any, Any]:
        if ctranslate2 is None:
            raise ModuleNotFoundError("ctranslate2 not installed")
        if spm is None:
            raise ModuleNotFoundError("sentencepiece not installed")
        if not model_dir.exists():
            raise FileNotFoundError(f"Model directory not found: {model_dir.resolve()}")

        src_spm = model_dir / "source.spm"
        if not src_spm.exists():
            raise FileNotFoundError(f"Missing source.spm: {src_spm.resolve()}")

        tgt_spm = model_dir / "target.spm"
        sp_src = spm.SentencePieceProcessor(model_proto=src_spm.read_bytes())
        sp_tgt = None
        if tgt_spm.exists():
            sp_tgt = spm.SentencePieceProcessor(model_proto=tgt_spm.read_bytes())

        translator = ctranslate2.Translator(
            str(model_dir),
            device="cpu",
            compute_type="int8",
            inter_threads=1,
            intra_threads=max(1, (os.cpu_count() or 4) // 2),
        )
        return translator, sp_src, sp_tgt

    def _run_translate(self, text: str, translator: Any, sp_src: Any, sp_tgt: Any) -> str:
        tokens = sp_src.encode_as_pieces(text)
        if tokens and tokens[-1] != "</s>":
            tokens.append("</s>")
        if not tokens:
            return ""
        results = translator.translate_batch(
            [tokens],
            beam_size=2,
            repetition_penalty=1.2,
            max_decoding_length=256,
            return_scores=False,
        )
        if not results or not results[0].hypotheses:
            return ""
        hyp = results[0].hypotheses[0]
        if sp_tgt is not None:
            return sp_tgt.decode_pieces([t for t in hyp if t not in ("</s>", "<pad>")]).strip()
        return self._detokenize_ct2(hyp)

    def _to_numpy_bgr(self, image_data: Any) -> Any:
        if np is None:
            raise RuntimeError("numpy not installed")

        if isinstance(image_data, np.ndarray):
            arr = image_data
            if arr.ndim == 2:
                return np.stack([arr, arr, arr], axis=-1)
            if arr.ndim == 3 and arr.shape[2] >= 3:
                return arr[:, :, :3]
            raise ValueError("Unsupported ndarray shape")

        qimage = self._try_extract_qimage(image_data)
        if qimage is None:
            raise TypeError(f"Unsupported image_data type: {type(image_data)!r}")

        from PySide6.QtGui import QImage  # type: ignore

        if qimage.format() != QImage.Format_RGBA8888:
            qimage = qimage.convertToFormat(QImage.Format_RGBA8888)

        w = qimage.width()
        h = qimage.height()
        if max(w, h) < 900:
            qimage = qimage.scaled(w * 2, h * 2, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            w = qimage.width()
            h = qimage.height()

        bytes_per_line = int(qimage.bytesPerLine())
        ptr = qimage.bits()
        buf = ptr.tobytes() if hasattr(ptr, "tobytes") else bytes(ptr)
        rgba = np.frombuffer(buf, dtype=np.uint8).reshape((h, bytes_per_line // 4, 4))
        rgba = rgba[:, :w, :]
        bgr = rgba[:, :, :3][:, :, ::-1].copy()
        return bgr

    def _try_extract_qimage(self, image_data: Any) -> Any | None:
        try:
            from PySide6.QtGui import QImage, QPixmap  # type: ignore
        except Exception:
            return None

        if isinstance(image_data, QImage):
            return image_data
        if isinstance(image_data, QPixmap):
            return image_data.toImage()
        if hasattr(image_data, "toImage"):
            try:
                return image_data.toImage()
            except Exception:
                return None
        return None

    def _extract_rapidocr_text(self, result: Any) -> str:
        if not result:
            return ""
        ocr_result = result[0] if isinstance(result, (list, tuple)) else result
        if not ocr_result:
            return ""
        lines: list[str] = []
        for item in ocr_result:
            if not item:
                continue
            text = ""
            if isinstance(item, (list, tuple)):
                if len(item) >= 2 and isinstance(item[1], str):
                    text = item[1]
            elif isinstance(item, dict):
                text = str(item.get("text", ""))
            else:
                text = str(item)
            text = (text or "").strip()
            if text:
                lines.append(text)
        return "\n".join(lines).strip()

    def _detokenize_ct2(self, tokens: list[str]) -> str:
        parts: list[str] = []
        for t in tokens:
            if not t or t in ("</s>", "<pad>"):
                continue
            parts.append(t.replace("▁", " "))
        return "".join(parts).strip()

    def _set_error(self, msg: str, kind: str = "") -> None:
        msg = str(msg or "")
        self._last_error = msg
        if kind == "ocr":
            self._last_ocr_error = msg
        elif kind == "en2zh":
            self._last_en2zh_error = msg
        elif kind == "zh2en":
            self._last_zh2en_error = msg


TranslatorEngine = CoreEngine
