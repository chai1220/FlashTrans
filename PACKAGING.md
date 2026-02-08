# 打包与发布（Windows）

## 要上传到 GitHub 的内容（推荐）

- 代码：`*.py`、`README.md`、`技术日志.md`、`requirements.txt`
- 模型：`models/`（可选，见“模型怎么发”）
- 不要上传：`.venv/`、`__pycache__/`、`pip cache`、`dist/`、`build/`

`.gitignore` 已经帮你写好，会自动忽略这些目录。

## PyTorch 能删吗？

- **运行阶段**：本项目运行只需要 `PySide6 / numpy / rapidocr_onnxruntime / ctranslate2 / sentencepiece`，不依赖 torch。
- **转换阶段**（把 HuggingFace 模型转换成 CTranslate2）：才需要 torch（见 `requirements-convert.txt`）。

如果你后续不打算在这个环境里再做模型转换，可以卸载：

```powershell
.\.venv\Scripts\pip uninstall torch torchvision torchaudio -y
```

## pip cache 需要删吗？

- 不影响运行；只是占磁盘。
- 你需要释放空间可以清：

```powershell
.\.venv\Scripts\pip cache purge
```

## 发给朋友：单个 EXE vs 安装包

### 方案 A：便携版（推荐你先做）

- 输出：一个 zip，里面包含 `FlashTrans.exe + models/ + 依赖 dll`
- 优点：最省事、无需安装、朋友解压就能用
- 缺点：目录会比较大（PySide6 + OCR + 翻译模型）

### 方案 B：安装包（推荐你最终发布）

- 输出：`Setup.exe`，可以创建开始菜单/桌面快捷方式、带卸载
- 优点：更像“正规软件”
- 缺点：需要额外的安装器工具（Inno Setup / NSIS）

建议：**Release 同时放 2 个附件**：Portable.zip + Setup.exe。

## 模型怎么发（两种方式）

1) **直接把 `models/` 放到仓库**  
   - 现在每个 `model.bin` 约 80MB，GitHub 可以接受，但仓库会变大。

2) **不进仓库，只放到 Release 附件**（推荐）  
   - 仓库干净；Release 里放 Portable.zip/Setup.exe，里面自带 models。

## 用 PyInstaller 生成可执行文件（便携版）

在项目根目录：

```powershell
.\.venv\Scripts\python -m pip install -U pyinstaller
.\.venv\Scripts\pyinstaller -y --noconsole --name FlashTrans --add-data "models;models" main.py
```

生成结果：

- `dist/FlashTrans/FlashTrans.exe`（onedir 目录版）

把 `dist/FlashTrans/` 整个目录压缩成 zip，发给朋友即可。

## 生成 Setup 安装包（Inno Setup 思路）

1) 先用 PyInstaller 生成 `dist/FlashTrans/`（onedir）
2) 用 Inno Setup 把这个目录打成 Setup.exe
   - 安装目录：`{pf}\FlashTrans`
   - 创建快捷方式、开机启动（可选）

