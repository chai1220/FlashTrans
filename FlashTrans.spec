from __future__ import annotations

import importlib.util
import os
from pathlib import Path

try:
    from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules  # type: ignore
except Exception:
    collect_dynamic_libs = None
    collect_submodules = None

block_cipher = None

project_root = Path(SPECPATH).resolve()
models_dir = Path(os.environ.get("FLASHTRANS_MODELS_DIR", str(project_root / "models"))).resolve()
icon_file = project_root / "assets" / "icon.ico"
flavor = str(os.environ.get("FLASHTRANS_FLAVOR", "opus") or "opus").strip().lower()
exe_name = "FlashTrans"
if flavor == "nllb":
    exe_name = "FlashTrans-NLLB"
elif flavor == "qwen":
    exe_name = "FlashTrans-Qwen"

hiddenimports = []
binaries = []
if flavor == "qwen" and collect_submodules is not None:
    hiddenimports += collect_submodules("llama_cpp")
if flavor == "qwen" and collect_dynamic_libs is not None:
    binaries += collect_dynamic_libs("llama_cpp")

datas = []
assets_dir = project_root / "assets"
logo_png = assets_dir / "new_logo.png"
if logo_png.exists() and logo_png.is_file():
    datas.append((str(logo_png), "assets"))
if models_dir.exists():
    readme = models_dir / "README.txt"
    if readme.exists() and readme.is_file():
        datas.append((str(readme), "models"))
    if flavor == "nllb":
        roots = [models_dir / "nllb-200-1.3b-int8"]
        for root in roots:
            if root.exists():
                for p in root.rglob("*"):
                    if p.is_file():
                        rel_dir = p.parent.relative_to(models_dir)
                        datas.append((str(p), str(Path("models") / rel_dir)))
    elif flavor == "qwen":
        p = models_dir / "qwen3-1.7b-q4.gguf"
        if p.exists() and p.is_file():
            datas.append((str(p), "models"))
    else:
        for p in models_dir.rglob("*"):
            if p.is_file():
                rel_dir = p.parent.relative_to(models_dir)
                datas.append((str(p), str(Path("models") / rel_dir)))

rapid_spec = importlib.util.find_spec("rapidocr_onnxruntime")
if rapid_spec is not None and rapid_spec.submodule_search_locations:
    rapid_dir = Path(list(rapid_spec.submodule_search_locations)[0])
    rapid_cfg = rapid_dir / "config.yaml"
    if rapid_cfg.exists():
        datas.append((str(rapid_cfg), "rapidocr_onnxruntime"))
    rapid_models = rapid_dir / "models"
    if rapid_models.exists():
        for p in rapid_models.rglob("*"):
            if p.is_file():
                rel_dir = p.parent.relative_to(rapid_dir)
                datas.append((str(p), str(Path("rapidocr_onnxruntime") / rel_dir)))

a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=(flavor == "qwen"),
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=exe_name,
    icon=str(icon_file),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=exe_name,
)
