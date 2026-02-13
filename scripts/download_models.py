from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path
from urllib.request import urlretrieve


def _require_hf() -> tuple[object, object]:
    try:
        from huggingface_hub import snapshot_download  # type: ignore
    except Exception as e:
        raise SystemExit(f"Missing dependency huggingface_hub: {e}")
    try:
        import hf_transfer  # noqa: F401

        os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
    except Exception:
        pass
    return snapshot_download, None


def _download_nllb(models_dir: Path) -> None:
    snapshot_download, _ = _require_hf()
    out_dir = (models_dir / "nllb-200-1.3b-int8").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id="OpenNMT/nllb-200-distilled-1.3B-ct2-int8",
        local_dir=str(out_dir),
        local_dir_use_symlinks=False,
    )
    src = out_dir / "source.spm"
    tgt = out_dir / "target.spm"
    if not src.exists():
        tmp = out_dir / "_tokenizer_download.tmp"
        url = (
            "https://hf-mirror.com/mbazaNLP/Quantized_Nllb_Finetuned_Edu_En_Kin_8bit"
            "/resolve/main/flores200_sacrebleu_tokenizer_spm.model"
        )
        try:
            urlretrieve(url, tmp)
            tmp.replace(src)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
    if src.exists() and not tgt.exists():
        shutil.copyfile(src, tgt)


def _download_qwen(models_dir: Path, variant: str) -> None:
    snapshot_download, _ = _require_hf()
    repo_id = "unsloth/Qwen3-1.7B-GGUF"
    allow_patterns = [f"*{variant}*.gguf"]
    with tempfile.TemporaryDirectory(prefix="flashtans_qwen_tmp_") as td:
        tmp_dir = Path(td).resolve()
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(tmp_dir),
            local_dir_use_symlinks=False,
            allow_patterns=allow_patterns,
        )

        ggufs = list(tmp_dir.rglob("*.gguf"))
        if not ggufs:
            raise SystemExit(f"Download completed but no gguf found for patterns: {allow_patterns}")
        ggufs.sort(key=lambda p: p.stat().st_size, reverse=True)
        chosen = ggufs[0]
        dest = (models_dir / "qwen3-1.7b-q4.gguf").resolve()
        shutil.copyfile(chosen, dest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models-dir", default="models", help="Models directory (default: ./models)")
    parser.add_argument("--nllb", action="store_true", help="Download NLLB CTranslate2 model")
    parser.add_argument("--qwen", action="store_true", help="Download Qwen3 GGUF model")
    parser.add_argument("--qwen-variant", default="Q4_K_XL", help="GGUF quant variant pattern (default: Q4_K_XL)")
    parser.add_argument("--hf-endpoint", default="", help="Override Hugging Face endpoint (e.g. https://hf-mirror.com)")
    parser.add_argument("--proxy", default="", help="HTTP(S) proxy (e.g. http://127.0.0.1:7890)")
    args = parser.parse_args()

    if args.hf_endpoint:
        os.environ["HF_ENDPOINT"] = str(args.hf_endpoint).rstrip("/")
    if args.proxy:
        p = str(args.proxy).strip()
        os.environ["HTTPS_PROXY"] = p
        os.environ["HTTP_PROXY"] = p

    models_dir = Path(args.models_dir).resolve()
    models_dir.mkdir(parents=True, exist_ok=True)

    if not args.nllb and not args.qwen:
        parser.error("Specify at least one of --nllb or --qwen")

    if args.nllb:
        _download_nllb(models_dir)
    if args.qwen:
        _download_qwen(models_dir, args.qwen_variant)

    print(str(models_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
