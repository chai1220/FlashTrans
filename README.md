# FlashTrans（离线 OCR + 离线翻译）

默认界面语言：简体中文。

**最新更新 (v1.1.2)**：
- 修复 F4 聊天界面，添加“清除记录”和“保存记录”功能
- 修复 F5 快捷键在设置中修改后失效的问题
- 优化 EXE 文件图标显示，解决模糊和边界框问题
- 移除学科填写功能，简化翻译流程
- 优化 Qwen 本地推理性能（自动线程分配）
- 改进 NLLB 翻译质量（参数优化 + 机械术语映射）

本仓库支持三个构建口味（flavor）：

- **nllb**：离线翻译使用 NLLB（多语言）
- **qwen**：离线翻译 & F4 默认使用本地 Qwen（GGUF）
- **opus**：离线翻译使用 Opus-MT（历史默认）

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

## 3.1 构建便携版（解压即用）

```powershell
.\scripts\build_portable.ps1 -Flavor nllb -Version "1.1.2"
.\scripts\build_portable.ps1 -Flavor qwen -Version "1.1.2"
```

构建产物在 `Output/`。

## 3.2 构建安装包（Inno Setup）

需要先安装 Inno Setup 6（确保 `ISCC.exe` 可用）。**注意**：ISS 安装脚本文件（`.iss`）默认被 `.gitignore` 排除，如需使用脚本自动构建，请确保 `installer/` 目录下存在对应的 ISS 文件。

**方法一：使用构建脚本**（需要 ISS 文件存在）：
```powershell
.\scripts\build_installer.ps1 -Flavor nllb -Version "1.1.2"
.\scripts\build_installer.ps1 -Flavor qwen -Version "1.1.2"
```

**方法二：手动编译**（推荐）：
1. 打开 Inno Setup Compiler 6
2. 分别打开 `installer/FlashTrans-NLLB.iss` 和 `installer/FlashTrans-Qwen.iss`
3. 点击 **Build → Compile** 编译安装包
4. 输出文件位于 `Output/` 目录

> **安全提示**：ISS 文件包含随机生成的 GUID，不包含敏感信息。如需保留 ISS 文件在仓库中，请移除 `.gitignore` 中的 `*.iss` 规则。

## 3.3 完整构建流程（CLI命令）

以下是一步到位的CLI命令，可在项目根目录的PowerShell终端中执行：

```powershell
# 1. 清理缓存和构建文件
Remove-Item -Recurse -Force build, dist, .cache, .tmp -ErrorAction SilentlyContinue

# 2. 生成图标（确保assets/new_logo.png存在）
python scripts/generate_icon.py --out assets/icon.ico

# 3. 构建便携版（两个版本）
.\scripts\build_portable.ps1 -Flavor nllb -Version "1.1.2"
.\scripts\build_portable.ps1 -Flavor qwen -Version "1.1.2"

# 4. 构建安装包（需要Inno Setup 6）
# 注意：ISS 文件默认被 .gitignore 排除，如需使用脚本构建请确保 ISS 文件存在
# 推荐手动编译：打开 Inno Setup，分别编译 installer/FlashTrans-NLLB.iss 和 installer/FlashTrans-Qwen.iss

# 5. 查看输出
Get-ChildItem Output\
```

构建完成后：
- 便携版ZIP文件：`Output/FlashTrans-{NLLB,Qwen}-Portable-1.1.2.zip`
- 安装包EXE文件：`Output/FlashTrans-{NLLB,Qwen}-Setup-1.1.2.exe`

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
- F4：本地聊天助手
  - 按 F4 打开聊天窗口，可与本地 Qwen 模型进行对话
  - 窗口内输入问题，点击“发送”或按 Ctrl+Enter 发送
  - 支持“清除记录”和“保存记录”功能
  - “显示思考过程”按钮可查看模型的推理过程
- F5：显示/激活仪表盘
  - 按 F5 打开或激活翻译仪表盘窗口
  - 如果仪表盘已最小化或隐藏，按 F5 会恢复显示
  - 仪表盘显示历史翻译记录（左原文 / 右译文），支持手动编辑和重新翻译

## 5. 模型说明（可选）

离线模型默认从 `./models/` 读取；打包版会把模型复制到 `_internal/models/`，解压后可直接使用。

常见模型文件：

- NLLB：`./models/nllb-200-1.3b-int8/`
- Qwen：`./models/qwen3-1.7b-q4.gguf`
- Opus：`./models/opus-mt-en-zh-int8/` 与 `./models/opus-mt-zh-en-int8/`

如果没有放置翻译模型或 OCR 初始化失败，会在结果里显示具体原因（例如模型目录不存在），方便你定位问题。

## 5.4 隐私与 API Key

- API 配置使用 Windows 的 QSettings 存储在当前用户侧，并用 DPAPI 加密保存 API Key。
- 不会写入项目目录，也不会被打包到发布 zip/安装包里。
- 仓库内的 `.gitignore` 已忽略构建产物与常见敏感文件，避免误提交泄露信息。

## 5.5 安装包构建安全

- **ISS 文件 GUID 安全性**：Inno Setup 安装脚本（`.iss` 文件）包含随机生成的 GUID 用于标识应用程序。这些 GUID 不包含任何个人信息，仅为安装程序提供唯一标识。
- **GUID 更新**：本项目已为两个版本（NLLB/Qwen）生成了新的随机 GUID，确保无历史关联信息。
- **Git 忽略策略**：`.gitignore` 文件已配置忽略 `*.iss` 文件，防止意外提交安装脚本。如需保留 ISS 文件在仓库中，可移除该规则。
- **构建建议**：
  - 使用 Inno Setup 6 打开对应的 ISS 文件直接编译，无需配置环境变量。
  - 每次发布新版本时，建议生成新的随机 GUID 以增强安全性。
  - 编译后的安装包（`.exe`）不包含源代码或敏感信息。

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

- [main.py](main.py)：系统托盘常驻、Windows 全局热键（F1/F2/F3）、后台线程调度
- [core_engine.py](core_engine.py)：离线 OCR + 离线翻译核心（支持 dummy_mode）
- [main_window.py](main_window.py)：仪表盘窗口（左右原文/译文 + 手动翻译）
- [snipping_tool.py](snipping_tool.py)：全屏透明截图选区（输出截图与选区全局坐标）
- [ui_popups.py](ui_popups.py)：鼠标附近悬浮窗（F1/F2）与选区覆盖显示（F3）

## 7. 常见问题

- 启动时报 `AttributeError: module 'ctypes.wintypes' has no attribute 'ULONG_PTR'`
  - 已修复：对 `ULONG_PTR` 做了兼容回退（使用 `ctypes.c_size_t`），确保在不同 Python/环境下可正常注入 Ctrl+C。

- 按 F1/F2 报 `AttributeError: type object 'PySide6.QtGui.QCursor' has no attribute 'screen'`
  - 已修复：不再使用 `QCursor.screen()`，改用 `QGuiApplication.screenAt(pos)`/`primaryScreen()` 计算弹窗所在屏幕。

## 🧩 致谢与引用 (Credits)
本项目使用了以下开源模型和库，感谢原作者的贡献：
* **翻译模型**:
  - [Helsinki-NLP/Opus-MT](https://huggingface.co/Helsinki-NLP) (Apache-2.0 License)
  - [Meta NLLB-200](https://huggingface.co/facebook/nllb-200-1.3B) (MIT License) - 多语言翻译模型
* **大语言模型**: [Qwen/Qwen2.5-1.7B](https://huggingface.co/Qwen/Qwen2.5-1.7B) (Apache-2.0 License) - 本地对话与翻译增强
* **OCR 引擎**: [RapidOCR](https://github.com/RapidAI/RapidOCR) (Apache-2.0 License)
* **推理框架**:
  - CTranslate2 (用于 NLLB/Opus-MT 翻译模型加速)
  - ONNXRuntime (用于 RapidOCR 推理加速)
  - llama.cpp (用于 Qwen 模型本地推理)
