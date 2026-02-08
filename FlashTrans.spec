from __future__ import annotations

import importlib.util
from pathlib import Path

block_cipher = None

project_root = Path(SPECPATH).resolve()
models_dir = project_root / "models"
icon_file = project_root / "assets" / "icon.ico"

datas = []
if models_dir.exists():
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
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FlashTrans",
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
    name="FlashTrans",
)
