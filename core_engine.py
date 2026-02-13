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
        mt_backend: str = "opus",
        nllb_model_dir: str | os.PathLike | None = None,
        nllb_src_lang_en: str = "eng_Latn",
        nllb_tgt_lang_zh: str = "zho_Hans",
    ) -> None:
        self._mt_backend = str(mt_backend or "opus").strip().lower()
        self._nllb_model_dir = Path(nllb_model_dir) if nllb_model_dir else None
        self._nllb_src_lang_en = str(nllb_src_lang_en or "eng_Latn").strip()
        self._nllb_tgt_lang_zh = str(nllb_tgt_lang_zh or "zho_Hans").strip()
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
        text = self._normalize_english_input(text)
        if not text:
            return ""
        if self._mt_backend == "none":
            self._set_error("Translation backend disabled", kind="en2zh")
            return ""
        if not self._en2zh_ready or self.translator_en2zh is None:
            self._set_error(self._last_en2zh_error or "EN->ZH translator not ready", kind="en2zh")
            return ""
        try:
            if self._mt_backend == "nllb":
                return self._translate_nllb(text, src_lang=self._nllb_src_lang_en, tgt_lang=self._nllb_tgt_lang_zh)
            return self._translate_with_chunking(text, self.translator_en2zh, self._sp_en2zh_src, self._sp_en2zh_tgt)
        except Exception as e:
            self._set_error(f"EN->ZH translation failed: {e}", kind="en2zh")
            return ""

    def translate_zh2en(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        if self._mt_backend == "none":
            self._set_error("Translation backend disabled", kind="zh2en")
            return ""
        if not self._zh2en_ready or self.translator_zh2en is None:
            self._set_error(self._last_zh2en_error or "ZH->EN translator not ready", kind="zh2en")
            return ""
        try:
            if self._mt_backend == "nllb":
                return self._translate_nllb(text, src_lang=self._nllb_tgt_lang_zh, tgt_lang=self._nllb_src_lang_en)
            return self._translate_with_chunking(text, self.translator_zh2en, self._sp_zh2en_src, self._sp_zh2en_tgt)
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
        source_text = self._normalize_ocr_text(self.ocr_image(image_data) or "")
        if not source_text:
            msg = self._last_ocr_error or "No text detected"
            return "", msg
        if self._mt_backend == "none":
            return source_text, ""
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

    def translate_nllb(self, text: str, src_lang: str, tgt_lang: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        if self._mt_backend != "nllb":
            raise RuntimeError("NLLB backend not enabled")
        if not self._en2zh_ready or self.translator_en2zh is None:
            raise RuntimeError(self._last_en2zh_error or "NLLB translator not ready")
        return self._translate_nllb(text, src_lang=src_lang, tgt_lang=tgt_lang)

    def _normalize_ocr_text(self, text: str) -> str:
        text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\\\s*[nN]\b", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
        text = re.sub(r"\n{2}", "\n", text)
        text = re.sub(r"[ ]{2,}", " ", text).strip()

        if re.search(r"[\u4e00-\u9fff]", text):
            text = text.replace("义件", "文件")
            text = text.replace("工试", "重试")

        if re.search(r"[A-Za-z]", text):
            tokens = text.split(" ")
            merged: list[str] = []
            for i, tok in enumerate(tokens):
                tok = tok.strip()
                if not tok:
                    continue
                if (
                    len(tok) == 1
                    and tok.isalpha()
                    and tok.islower()
                    and merged
                    and re.search(r"[A-Za-z]$", merged[-1])
                    and (i + 1 >= len(tokens) or not tokens[i + 1][:1].islower())
                ):
                    merged[-1] = merged[-1] + tok
                else:
                    merged.append(tok)
            text = " ".join(merged)
            text = re.sub(r"[ ]{2,}", " ", text).strip()

        return text

    def _init_all(self) -> None:
        self._init_ocr()
        if self._mt_backend == "none":
            return
        if self._mt_backend == "nllb":
            self._init_translator_nllb()
        else:
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

    def _init_translator_nllb(self) -> None:
        try:
            model_dir = self._nllb_model_dir
            if model_dir is None:
                raise ValueError("nllb_model_dir not set")
            translator, sp_src, sp_tgt = self._load_ct2_translator(model_dir)

            self.translator_en2zh = translator
            self._sp_en2zh_src = sp_src
            self._sp_en2zh_tgt = sp_tgt
            self._en2zh_ready = True

            self.translator_zh2en = translator
            self._sp_zh2en_src = sp_src
            self._sp_zh2en_tgt = sp_tgt
            self._zh2en_ready = True
        except Exception as e:
            self.translator_en2zh = None
            self._sp_en2zh_src = None
            self._sp_en2zh_tgt = None
            self._en2zh_ready = False
            self.translator_zh2en = None
            self._sp_zh2en_src = None
            self._sp_zh2en_tgt = None
            self._zh2en_ready = False
            self._set_error(str(e), kind="en2zh")

    def _load_ct2_translator(self, model_dir: Path) -> tuple[Any, Any, Any]:
        if ctranslate2 is None:
            raise ModuleNotFoundError("ctranslate2 not installed")
        if spm is None:
            raise ModuleNotFoundError("sentencepiece not installed")
        if not model_dir.exists():
            raise FileNotFoundError(f"Model directory not found: {model_dir.resolve()}")

        def _pick_first_existing(names: list[str]) -> Path | None:
            for name in names:
                p = model_dir / name
                if p.exists():
                    return p
            return None

        src_model = _pick_first_existing(["sentencepiece.model", "source.spm", "sentencepiece.bpe.model"])
        if src_model is None:
            raise FileNotFoundError(
                "Missing SentencePiece model. Expected one of: "
                + ", ".join(["sentencepiece.model", "source.spm", "sentencepiece.bpe.model"])
                + f" in {model_dir.resolve()}"
            )

        tgt_model = _pick_first_existing(["target.spm", "sentencepiece.model", "sentencepiece.bpe.model"])
        if tgt_model is None:
            tgt_model = src_model

        sp_src = spm.SentencePieceProcessor(model_proto=src_model.read_bytes())
        sp_tgt = None
        if tgt_model.exists():
            sp_tgt = spm.SentencePieceProcessor(model_proto=tgt_model.read_bytes())

        translator = ctranslate2.Translator(
            str(model_dir),
            device="cpu",
            compute_type="int8",
            inter_threads=1,
            intra_threads=max(1, (os.cpu_count() or 4) // 2),
        )
        return translator, sp_src, sp_tgt

    def _translate_with_chunking(
        self,
        text: str,
        translator: Any,
        sp_src: Any,
        sp_tgt: Any,
        target_prefix_token: str | None = None,
        source_prefix_tokens: list[str] | None = None,
    ) -> str:
        text = (text or "").strip()
        if not text:
            return ""

        chunks = self._chunk_text(text)
        token_lists: list[list[str]] = []
        token_to_chunk: list[int] = []
        out_by_chunk: list[str] = ["" for _ in chunks]

        for i, ch in enumerate(chunks):
            if ch == "\n":
                out_by_chunk[i] = "\n"
                continue
            ch = (ch or "").strip()
            if not ch:
                continue
            tokens = sp_src.encode_as_pieces(ch)
            if source_prefix_tokens:
                tokens = [*source_prefix_tokens, *tokens]
            if tokens and tokens[-1] != "</s>":
                tokens.append("</s>")
            if not tokens:
                continue
            token_to_chunk.append(i)
            token_lists.append(tokens)

        if token_lists:
            kwargs: dict[str, Any] = {
                "beam_size": 7,
                "repetition_penalty": 1.5,
                "max_decoding_length": 1024,
                "return_scores": False,
            }
            try:
                kwargs["no_repeat_ngram_size"] = 5
            except Exception:
                pass
            if target_prefix_token:
                kwargs["target_prefix"] = [[str(target_prefix_token)]] * len(token_lists)
            results = translator.translate_batch(token_lists, **kwargs)
            for res_idx, chunk_idx in enumerate(token_to_chunk):
                hyp = []
                if results and res_idx < len(results) and results[res_idx].hypotheses:
                    hyp = results[res_idx].hypotheses[0]
                drop_leading: set[str] = set()
                if target_prefix_token:
                    drop_leading.add(str(target_prefix_token))
                if source_prefix_tokens:
                    drop_leading.update([str(t) for t in source_prefix_tokens if t])
                while hyp and hyp[0] in drop_leading:
                    hyp = hyp[1:]
                if hyp:
                    hyp = [t for t in hyp if not (t.startswith("__") and t.endswith("__"))]
                if not hyp:
                    continue
                if sp_tgt is not None:
                    out = sp_tgt.decode_pieces([t for t in hyp if t not in ("</s>", "<pad>")]).strip()
                else:
                    out = self._detokenize_ct2(hyp)
                out_by_chunk[chunk_idx] = self._postprocess_translation(out)

        merged_parts: list[str] = []
        for part in out_by_chunk:
            if not part:
                continue
            if part == "\n":
                merged_parts.append("\n")
                continue
            if merged_parts and merged_parts[-1] not in ("\n", " "):
                prev = merged_parts[-1]
                prev_tail = prev[-1] if prev else ""
                cur_head = part[0] if part else ""
                if prev_tail not in "，。！？；：、,.!?;:":
                    if not (
                        re.match(r"[\u4e00-\u9fff]", prev_tail or "") and re.match(r"[\u4e00-\u9fff]", cur_head or "")
                    ):
                        merged_parts.append(" ")
            merged_parts.append(part)

        merged = "".join(merged_parts)
        merged = re.sub(r"[ \t]{2,}", " ", merged)
        merged = re.sub(r"[ ]+\n", "\n", merged)
        merged = re.sub(r"\n[ ]+", "\n", merged)
        return merged.strip()

    def _translate_nllb(self, text: str, src_lang: str, tgt_lang: str) -> str:
        src_lang = str(src_lang or "").strip()
        tgt_lang = str(tgt_lang or "").strip()
        if not src_lang or not tgt_lang:
            raise ValueError("Missing NLLB language codes")
        return self._translate_with_chunking(
            text,
            self.translator_en2zh,
            self._sp_en2zh_src,
            self._sp_en2zh_tgt,
            target_prefix_token=tgt_lang,
            source_prefix_tokens=[src_lang],
        )

    def _chunk_text(self, text: str) -> list[str]:
        text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        parts: list[str] = []
        for block in re.split(r"(\n+)", text):
            if not block:
                continue
            if block.startswith("\n"):
                parts.extend(["\n"] * len(block))
                continue
            block_parts = re.split(r"(?<=[。！？!?；;。\.…])", block)
            for seg in block_parts:
                seg = seg.strip()
                if not seg:
                    continue
                has_zh = bool(re.search(r"[\u4e00-\u9fff]", seg))
                comma_count = seg.count("，") + seg.count(",")
                if has_zh and (len(seg) > 80 or (comma_count >= 2 and len(seg) > 40)):
                    parts.extend([s for s in re.split(r"(?<=[，,])", seg) if s.strip()])
                elif (not has_zh) and (len(seg) > 180):
                    parts.extend([s for s in re.split(r"(?<=[,])", seg) if s.strip()])
                else:
                    parts.append(seg)
        return parts or [text]

    def _normalize_english_input(self, text: str) -> str:
        text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text).strip()
        if not text:
            return ""

        text = re.sub(r"\b(can\s+)roll(\s+it)\b", r"\1scroll\2", text, flags=re.IGNORECASE)
        text = re.sub(r"\broll(\s+it)\b", r"scroll\1", text, flags=re.IGNORECASE)
        text = re.sub(r"\byou can roll\b", "you can scroll", text, flags=re.IGNORECASE)

        text = re.sub(
            r"what'?s\s+the\s+big\s+deal\s+with\s+your\s+f1\s+and\s+f2\s+translation",
            "why are your F1 and F2 translation boxes so big",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\bthe\s+return\s+identified\s+after\s+pressing\s+f3\b",
            "the recognition result after pressing F3",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\bthe document that was packed\b", "the packaged document", text, flags=re.IGNORECASE)

        sentences = re.split(r"(?<=[.!?])\s+", text)
        deduped: list[str] = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            key = s.lower()
            if deduped and deduped[-1].lower() == key:
                continue
            deduped.append(s)
        text = " ".join(deduped)
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        text = re.sub(r"([,.;:!?])(?=[A-Za-z])", r"\1 ", text)
        text = re.sub(r"[ ]{2,}", " ", text).strip()
        return text

    def _postprocess_translation(self, text: str) -> str:
        text = str(text or "")
        text = text.replace("\u00a0", " ")
        text = text.replace("▁", " ")
        text = text.replace("⁇", "")
        text = text.replace("??", "")
        text = re.sub(r"[ \t]{2,}", " ", text)
        has_zh = bool(re.search(r"[\u4e00-\u9fff]", text))
        if has_zh:
            text = text.replace(",", "，").replace("?", "？").replace("!", "！").replace(";", "；").replace(":", "：")
            text = re.sub(r"(?<!\.)\.(?!\.)", "。", text)
            term_map = {
                "变量位移活塞": "变量柱塞泵",
                "可变位移活塞": "变量柱塞泵",
                "可变位移活塞泵": "变量柱塞泵",
                "变量位移活塞泵": "变量柱塞泵",
                "反响": "齿隙",
                "侧隙": "齿隙",
                "表面修饰": "表面粗糙度",
                "表面光洁度": "表面粗糙度",
                "公差": "公差",
                "tolerances": "公差",
                "柱塞": "柱塞",
                "活塞": "柱塞",
                "泵": "泵",
            }
            for wrong, correct in term_map.items():
                text = text.replace(wrong, correct)
        text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
        text = re.sub(r"\s+([，。！？；：、])", r"\1", text)
        text = re.sub(r"([，。！？；：、])\s+", r"\1", text)
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
        text = (
            text.replace("， ", "，")
            .replace("。 ", "。")
            .replace("？ ", "？")
            .replace("！ ", "！")
            .replace("； ", "；")
            .replace("： ", "：")
        )
        return text.strip()

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
