# 安卓语音输入

面向红米 K70 的本地中英双语语音识别 App，当前版本为 `0.11.0`。主界面统一使用本地 HTML、CSS 和 JavaScript，Kotlin 只负责 WebView 宿主、麦克风、识别模型、权限、历史数据库、下载器、通知和系统级悬浮窗等平台能力。实时与 Paraformer／Qwen3-ASR 方案使用 `sherpa-onnx 1.13.5`；Whisper ACFT 方案使用固定版本的 `whisper.cpp` Android JNI 运行层。

## 主要功能

- “录音、记录、设置”位于同一个网页式单页界面中，切换页面时底栏不会重建；App 固定为竖屏。
- 录音页依次显示当前模型、识别结果、声波与开始按钮；记录卡片整卡可复制，右下角显示复制图标，右上角使用灰色关闭图标删除。
- 实际麦克风开始收音前明确显示“准备中”，开始收音后才进入“正在聆听”，避免漏掉开头。
- Zipformer 使用 `modified_beam_search` 和 4 条活动路径实时识别中文、英文及中英混说；检测到句段端点后提交当前段并继续识别长句。
- Zipformer＋Paraformer／Qwen3-ASR 方案停止后会按照 Zipformer 检测到的语音端点进行分段二次识别；Paraformer 下载小、速度快，Qwen3-ASR 中英文混说质量更高但约 941.3 MiB、处理更慢。
- `Whisper ACFT 多语言`可以单独对完整录音进行整段识别，也可以与 Zipformer 组合：讲话时由 Zipformer 实时出字，停止后 Whisper ACFT 直接读取原始录音，独立进行第二次完整识别。它不是读取并编辑 Zipformer 初稿的文字校准器。
- Zipformer＋Whisper 组合默认采用 Whisper 的第二次完整识别结果；只有结果为空、没有有效文字、包含异常控制字符、输出速度明显不可能或出现长段机械循环时，才回退到实时初稿。两份结果在测试模式中都会保留，便于实测对照。
- 每次新识别都会清空上一轮临时文字，不再残留旧内容。
- 识别声波由原生音量值驱动本地 SVG 三层连续曲线，只在真正收音时运动；系统开启“减少动态效果”后会降低动态更新。
- 最终文字保存在本机 SQLite 历史中，最多 500 条；记录按聊天方式由旧到新排列，最新内容在底部，支持搜索、复制单条、复制全部、删除和清空。
- 系统级悬浮按钮支持拖动、点击开始或停止、长按关闭；拖动松手后用 200 毫秒缓出动画吸附最近的左侧或右侧安全边缘，并保存贴边方向和相对高度。文字框随球移动并优先位于屏幕内侧。网页预览和系统桌面悬浮球统一为白色玻璃质感，圆球边界外不绘制光效。设置中可调整 35%—100% 透明度和 48—88 dp 大小；默认待机不显示文字框，识别时显示，停止后保留最终文字 2 秒，点击文字框可复制并显示“已复制”1 秒。
- “识别测试模式”默认关闭。开启后，每轮本地识别会额外保留原始 WAV、实时初稿和第二次识别结果；仅识别方案只保留单份识别文字和录音。测试资料只在应用私有目录中保存，可按条删除或全部清空。
- 仍可切换到手机系统语音服务；该方式是否联网由手机服务决定。

## 界面与安全边界

网页资源位于 `app/src/main/assets/web`，通过 AndroidX `WebViewAssetLoader` 从受控的本地域名加载。页面不直接申请麦克风，不访问外部网络，不允许外部跳转；识别文字通过 JSON 编码传入网页，并只使用 `textContent` 渲染。

界面支持：

- 简体中文和 UTF-8
- 浅色、深色与系统字体缩放
- 竖屏、窄屏和较宽屏幕；不提供横屏模式
- 安全区、至少 48 dp 的主要触控区域
- 系统“减少动态效果”偏好

## 模型与安装包

模型不再编入 APK，也不提交到 Git。安装包只包含应用、网页界面、识别运行库和小型资源，模型在首次使用相关方案时单独下载。当前资源为：

| 资源 | 用途 | 大小 |
| --- | --- | ---: |
| 中英双语 Zipformer | 实时出字、中文、英文和中英混说 | 60,142,871 字节，约 57.4 MiB |
| 中英双语 Paraformer | 停止后按语音片段二次识别；单独使用时整段识别 | 81,904,027 字节，约 78.1 MiB |
| Qwen3-ASR 0.6B INT8 | 停止后高质量二次识别中英文及中英混说 | 987,015,347 字节，约 941.3 MiB |
| Whisper ACFT Multilingual-74 | 停止后对原始录音进行整段识别；可与 Zipformer 组成实时＋二次识别方案 | 81,768,602 字节，约 78.0 MiB |
| 合计 | 四套资源全部安装 | 1,210,830,847 字节，约 1.13 GiB |

录音首页会直接显示当前使用的是一套还是两套模型；应用内“设置 → 识别方案”可选择 Zipformer＋Paraformer、Zipformer＋Qwen3-ASR 或 Zipformer＋Whisper ACFT，也可单独使用任一模型。Zipformer＋Whisper 的精确资源合计为 141,911,473 字节，约 135.3 MiB。“离线模型”显示每套资源的用途、版本、下载大小、已占空间、进度、速度和预计剩余时间。下载支持暂停、继续、HTTP Range 断点续传、失败重试和 SHA-256 校验；校验成功后才原子写入版本标记。开始下载时还会预留 64 MiB 可用空间。用户可删除或重新下载单个模型。

模型清单位于 `app/src/main/assets/model-resources.json`，下载地址固定到上游提交，包含每个文件的精确字节数和 SHA-256。最终目录统一为应用私有的：

```text
no_backup/resource-packs/<资源编号>/<版本>/
```

Zipformer、Paraformer 与 Qwen3-ASR 均使用 k2-fsa/sherpa-onnx 官方公开模型，许可证为 Apache-2.0。Whisper 运行层使用固定提交与归档哈希的 `ggml-org/whisper.cpp`（MIT）；ACFT 方法来自 `futo-org/whisper-acft`（MIT），Multilingual-74 模型卡标记为 Apache-2.0。本项目未复制 FUTO Voice Input 或 FUTO Keyboard 的 App 源码。来源、许可证与模型校验信息记录在资源清单和 `THIRD_PARTY_NOTICES.md` 中；同一份第三方说明也随 APK 放入 `assets/licenses`。

## 开发机同步模型

开发机的模型统一放在项目外的共享规范源 `O:\程序\共享模型仓库`。同步脚本通过相对于共同上级目录的路径定位，也可用环境变量 `VOICE_INPUT_MODEL_REPOSITORY` 或参数 `--source-root` 覆盖：

```text
O:\程序\共享模型仓库\
├─ zipformer-bilingual/
├─ paraformer/
├─ qwen3-asr-0.6b-int8/
└─ whisper-acft-multilingual-74/
   └─ base_acft_q8_0.bin
```

安装新的 debug APK 后运行：

```powershell
python scripts/同步安卓模型.py
```

只有一台已授权手机时无需参数；多台设备可增加 `--serial <设备序列号>`。临时使用其他仓库时可增加 `--source-root <模型仓库路径>`。脚本先校验本机文件，再比较手机中的大小和 SHA-256，只传输新增或变化的文件。临时文件校验成功后才替换最终文件，并在全部文件就绪后写入版本标记；失败不会删除手机上仍可用的旧资源。

同步脚本日志分开保存在：

```text
scripts/logs/模型同步-运行.log
scripts/logs/模型同步-错误.log
```

日志目录已忽略，不会提交到 Git；日志会隐藏本机模型目录。

## 构建与检查

要求 JDK 17、Android SDK 35、Android NDK 27.0.12077973、CMake 3.22.1 和 Gradle 8.9。项目根目录执行：

```powershell
gradle --no-daemon testDebugUnitTest
gradle --no-daemon lintDebug
gradle --no-daemon assembleDebug
```

还可执行资源清单与同步脚本测试：

```powershell
python -m unittest discover -s scripts/tests -v
node --check app/src/main/assets/web/app.js
```

debug APK 位于 `app/build/outputs/apk/debug/app-debug.apk`。GitHub Actions 会依次运行资源清单测试、Android 单元测试、Lint、构建，并检查 APK 中不存在 `.onnx`、`.model` 或 `.bin` 模型文件。

## 安装、升级与卸载

首次安装可在手机上打开 debug APK，或在已授权的开发机执行：

```powershell
adb install app/build/outputs/apk/debug/app-debug.apk
```

项目使用固定的私有开发签名。以后安装同一签名的新版本时，使用 `adb install -r` 即可原地升级，并保留历史记录、设置和已下载模型。若手机中已有由其他签名生成的旧测试包，首次切换到固定签名时必须先卸载旧包；卸载会同时清除该 App 的历史记录、设置和已下载模型。

卸载可在手机“设置 → 应用管理 → 安卓语音输入”中完成，或执行：

```powershell
adb uninstall com.smyongbu.voiceinput
```

## 权限与隐私

- 麦克风：本地或系统识别必需。
- 显示在其他应用上层：仅在开启悬浮按钮时申请。
- 通知：Android 13 以上用于显示悬浮前台服务通知。
- 网络：只供用户主动下载离线模型；本地网页界面不会联网。

本地识别不会上传录音。正常模式不保存录音；只有用户显式开启“识别测试模式”后，App 才会把本轮 WAV 和识别结果（组合方案包含实时初稿与第二次结果）写入应用私有目录 `files/test-recordings` 及本地历史数据库。关闭测试模式后不再新增测试资料，已有资料可在设置或测试记录中主动删除。日志始终不记录识别正文。手机系统识别可能把音频交给系统服务商处理。

## 运行日志

应用日志位于私有目录：

```text
files/logs/运行.log
files/logs/错误.log
```

两类日志分别轮转，只记录版本、操作编号、阶段、耗时、心跳、模型状态和错误堆栈，不记录识别正文。debug 包可用 `adb shell run-as com.smyongbu.voiceinput` 只读提取。

测试录音不属于日志；可在 App 的“测试记录”中按条删除，或在“设置 → 识别测试模式”中清空全部测试资料。
