# FlashTrans（离线 OCR + 离线翻译）

默认界面语言：简体中文。

## 1. 运行环境

- Windows 10/11
- Python 3.12（推荐）

## 2. 安装依赖（推荐使用虚拟环境）

在项目目录打开 PowerShell，执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install PySide6 numpy rapidocr_onnxruntime ctranslate2 sentencepiece
```

## 3. 启动

```powershell
.\.venv\Scripts\python main.py
```

## 4. 使用方式

- 程序启动后：常驻系统托盘（右键托盘图标可退出）
- F1：划词翻译
  - 先在任意软件里选中一段文字，再按 F1
  - 程序会模拟 Ctrl+C 读取剪贴板，并在鼠标附近弹出翻译框显示结果
- 弹窗关闭方式
  - Esc：关闭当前弹窗/覆盖窗
  - 点击窗口外：关闭当前弹窗/覆盖窗
  - 再按一次对应热键（F1/F3）：关闭当前窗口
- F2：打字翻译（输入条）
  - 按 F2 后在鼠标附近弹出输入条（支持中文输入法）
  - 输入后停顿片刻会自动触发翻译；也可以按 Enter 立即翻译
  - 按 Esc：关闭输入条
- F3：截图翻译
  - 按 F3 后全屏框选区域，识别并翻译后在选区位置覆盖显示结果
  - 覆盖窗右下角“提取文字到仪表盘”：打开仪表盘（左原文 / 右译文）

## 5. 模型说明（可选）

默认假设翻译模型路径：

```
./models/opus-mt-en-zh-int8/
```

如果没有放置翻译模型或 OCR 初始化失败，会在结果里显示具体原因（例如模型目录不存在），方便你定位问题。

### 5.1 获取模型（推荐自己转换，最稳）

本项目使用 CTranslate2 的离线 MarianMT 模型。你可以从 HuggingFace 的 `Helsinki-NLP/opus-mt-en-zh` 自行转换为本项目需要的目录：

```powershell
.\.venv\Scripts\python -m pip install -U transformers sentencepiece ctranslate2

# 这一条很关键：转换器需要 torch 来加载 HuggingFace 模型（只用于“转换阶段”，应用运行阶段不依赖 torch）
.\.venv\Scripts\python -m pip install -U torch --index-url https://download.pytorch.org/whl/cpu

# 在项目根目录执行（会自动下载 HuggingFace 模型）
.\.venv\Scripts\ct2-transformers-converter.exe --model Helsinki-NLP/opus-mt-en-zh --output_dir .\models\opus-mt-en-zh-int8 --quantization int8 --force

# 或：先激活虚拟环境，再直接运行命令（等价）
# .\.venv\Scripts\Activate.ps1
# ct2-transformers-converter --model Helsinki-NLP/opus-mt-en-zh --output_dir .\models\opus-mt-en-zh-int8 --quantization int8 --force
```

转换成功后，目录下应包含 CTranslate2 模型文件以及 sentencepiece 相关文件（如 source.spm/target.spm 或 sentencepiece.model）。

### 5.2 这一步在干什么？

- `Helsinki-NLP/opus-mt-en-zh`：原始的 HuggingFace MarianMT 翻译模型（偏“训练/研究”格式）
- `ct2-transformers-converter`：把它转换成 CTranslate2 能直接加载的“推理模型目录”
- `--quantization int8`：把权重量化为 int8，CPU 跑起来更快、占用更小

### 5.3 常见转换报错

- `NameError: name 'torch' is not defined`
  - 原因：虚拟环境里没装 torch（转换器内部直接用 torch 加载模型）
  - 解决：执行上面的 torch 安装命令后再转换一次

## 6. 技术说明（关键模块）

- [main.py](file:///a:/sys/Desk/idea/翻译APP/main.py)：系统托盘常驻、Windows 全局热键（F1/F2/F3）、后台线程调度
- [core_engine.py](file:///a:/sys/Desk/idea/翻译APP/core_engine.py)：离线 OCR + 离线翻译核心（支持 dummy_mode）
- [main_window.py](file:///a:/sys/Desk/idea/翻译APP/main_window.py)：仪表盘窗口（左右原文/译文 + 手动翻译）
- [snipping_tool.py](file:///a:/sys/Desk/idea/翻译APP/snipping_tool.py)：全屏透明截图选区（输出截图与选区全局坐标）
- [ui_popups.py](file:///a:/sys/Desk/idea/翻译APP/ui_popups.py)：鼠标附近悬浮窗（F1/F2）与选区覆盖显示（F3）

## 7. 常见问题

- 启动时报 `AttributeError: module 'ctypes.wintypes' has no attribute 'ULONG_PTR'`
  - 已修复：对 `ULONG_PTR` 做了兼容回退（使用 `ctypes.c_size_t`），确保在不同 Python/环境下可正常注入 Ctrl+C。

- 按 F1/F2 报 `AttributeError: type object 'PySide6.QtGui.QCursor' has no attribute 'screen'`
  - 已修复：不再使用 `QCursor.screen()`，改用 `QGuiApplication.screenAt(pos)`/`primaryScreen()` 计算弹窗所在屏幕。

## 🧩 致谢与引用 (Credits)
本项目使用了以下开源模型和库，感谢原作者的贡献：
* **翻译模型**: [Helsinki-NLP/Opus-MT](https://huggingface.co/Helsinki-NLP) (Apache-2.0 License)
* **OCR 引擎**: [RapidOCR](https://github.com/RapidAI/RapidOCR) (Apache-2.0 License)
* **推理加速**: CTranslate2 & ONNXRuntime