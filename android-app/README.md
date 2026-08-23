# 安卓语音输入

面向红米 K70 的本地中英双语语音识别 App，当前版本为 `0.12.2`。主界面统一使用本地 HTML、CSS 和 JavaScript，Kotlin 只负责 WebView 宿主、麦克风、识别模型、权限、历史数据库、下载器、通知和系统级悬浮窗等平台能力。Streaming Paraformer、Zipformer 与 Qwen3-ASR 0.6B INT8 使用 `sherpa-onnx 1.13.5`；Faster-Whisper Small 与 Qwen3-ASR 1.7B Q5_K_M 使用固定提交的 `transcribe.cpp` Android JNI 运行层。

## 主要功能

- “录音、记录、设置”位于同一个网页式单页界面中，切换页面时底栏不会重建；App 固定为竖屏。
- 录音页依次显示当前模型、识别结果、声波与开始按钮；记录卡片整卡可复制，右下角显示复制图标，右上角使用灰色关闭图标删除。
- 实际麦克风开始收音前明确显示“准备中”，开始收音后才进入“正在聆听”，避免漏掉开头。
- “实时显示”和“最后识别”是两个始终可见、彼此独立的模型选择组。实时显示可选 Streaming Paraformer 或 Zipformer；最后识别可选 Faster-Whisper Small、Qwen3-ASR 0.6B INT8 或 Qwen3-ASR 1.7B Q5_K_M。录音首页用两个独立卡片上下显示当前模型；下载或校验时卡片按真实字节进度填充并在模型名右侧显示百分比，模型可用后保持浅蓝色。
- Streaming Paraformer 与 Zipformer 都在讲话时实时显示中文、英文及中英混说文字；Zipformer 使用 `modified_beam_search` 和 4 条活动路径，并在检测到句段端点后提交当前段、继续识别长句。
- 停止收音后，所选最终模型直接读取本轮完整原始音频并生成最终文字。界面中的 Faster-Whisper Small 在 Android 上使用同一 Whisper Small 的 `transcribe.cpp` GGUF Q8_0 模型；Qwen3-ASR 1.7B Q5_K_M 同样由 `transcribe.cpp` 运行，Qwen3-ASR 0.6B INT8 继续由 `sherpa-onnx` 运行。
- 每次新识别都会清空上一轮临时文字，不再残留旧内容。
- 识别声波由原生音量值驱动本地 SVG 三层连续曲线，只在真正收音时运动；系统开启“减少动态效果”后会降低动态更新。
- 最终文字保存在本机 SQLite 历史中，最多 500 条；记录按聊天方式由旧到新排列，最新内容在底部，支持搜索、复制单条、复制全部、删除和清空。
- 系统级悬浮按钮支持拖动、点击开始或停止、长按关闭；拖动松手后用 200 毫秒缓出动画吸附最近的左侧或右侧安全边缘，并保存贴边方向和相对高度。文字框随球移动并优先位于屏幕内侧。网页预览和系统桌面悬浮球统一为白色玻璃质感，圆球边界外不绘制光效。设置中可调整 35%—100% 透明度和 48—88 dp 大小；默认待机不显示文字框，识别时显示，停止后保留最终文字 2 秒，点击文字框可复制并显示“已复制”1 秒。
- 仍可切换到手机系统语音服务；该方式是否联网由手机服务决定。

## 界面与安全边界

网页资源位于 `app/src/main/assets/web`，通过 AndroidX `WebViewAssetLoader` 从受控的本地域名加载。页面不直接申请麦克风，不访问外部网络，不允许外部跳转；识别文字通过 JSON 编码传入网页，并只使用 `textContent` 渲染。

### UI 浏览页

面向用户查看、标注和验收的独立预览入口位于项目上级目录的 `UI预览\打开预览.html`。该页面包含外部说明区、19.5:9 手机框、常用网页宽度切换和模拟状态，可直接双击打开；手机框内部加载 `UI预览\app\index.html?preview=1`。日常查看不要直接打开正式资源目录中的裸 `app/src/main/assets/web/index.html`，也不依赖项目外的公共预览目录。

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
| Streaming Paraformer INT8 | 实时显示中文、英文和中英混说文字 | 237,202,501 字节，约 226.2 MiB |
| 中英双语 Zipformer | 实时显示中文、英文和中英混说文字 | 60,142,871 字节，约 57.4 MiB |
| Faster-Whisper Small（GGUF Q8_0） | 停止后对完整原始音频生成最终文字 | 269,751,136 字节，约 257.3 MiB |
| Qwen3-ASR 0.6B INT8 | 停止后高质量识别中英文和中英混说 | 987,015,347 字节，约 941.3 MiB |
| Qwen3-ASR 1.7B Q5_K_M | 停止后高质量识别多语言、中文方言和中英混说 | 1,517,290,464 字节，约 1.41 GiB |
| 合计 | 五套资源全部安装 | 3,071,402,319 字节，约 2.86 GiB |

实时显示和最后识别必须各选择一套模型，两组可以任意组合，用户只需下载实际选择的资源。“离线模型”显示每套资源的用途、版本、下载大小、已占空间、进度、速度和预计剩余时间。下载支持暂停、继续、HTTP Range 断点续传、失败重试和 SHA-256 校验；校验成功后才原子写入版本标记。开始下载时还会预留 64 MiB 可用空间。用户可删除或重新下载单个模型。

模型清单位于 `app/src/main/assets/model-resources.json`，下载地址固定到上游提交，包含每个文件的精确字节数和 SHA-256。最终目录统一为应用私有的：

```text
no_backup/resource-packs/<资源编号>/<版本>/
```

Streaming Paraformer、Zipformer 与 Qwen3-ASR 0.6B INT8 使用 k2-fsa/sherpa-onnx 公开模型；Faster-Whisper Small 和 Qwen3-ASR 1.7B 使用 handy-computer 发布的 `transcribe.cpp` GGUF 模型。五套模型均标记为 Apache-2.0；`sherpa-onnx` 为 Apache-2.0，固定提交的 `transcribe.cpp` 为 MIT。来源、固定版本、许可证与逐文件校验信息记录在资源清单和 `THIRD_PARTY_NOTICES.md` 中；同一份第三方说明也随 APK 放入 `assets/licenses`。

## 开发机同步模型

开发机的模型统一放在项目外的共享规范源 `O:\程序\共享模型仓库`。同步脚本通过相对于共同上级目录的路径定位，也可用环境变量 `VOICE_INPUT_MODEL_REPOSITORY` 或参数 `--source-root` 覆盖：

```text
O:\程序\共享模型仓库\
├─ streaming-paraformer-bilingual-zh-en/
├─ zipformer-bilingual/
├─ qwen3-asr-0.6b-int8/
├─ faster-whisper-small-gguf-q8-0/
│  └─ whisper-small-Q8_0.gguf
└─ qwen3-asr-1.7b-gguf-q5-k-m/
   └─ Qwen3-ASR-1.7B-Q5_K_M.gguf
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

debug APK 位于 `app/build/outputs/apk/debug/app-debug.apk`。GitHub Actions 会依次运行资源清单测试、Android 单元测试、Lint、构建，并检查 APK 中不存在 `.onnx`、`.model`、`.bin` 或 `.gguf` 模型文件。

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

本地识别不会上传录音。原始音频只用于当次实时与最终识别，识别完成或取消后不作为用户资料保存；历史数据库只保存最终文字。日志始终不记录识别正文。手机系统识别可能把音频交给系统服务商处理。

## 运行日志

应用日志位于私有目录：

```text
files/logs/运行.log
files/logs/错误.log
```

两类日志分别轮转，只记录版本、操作编号、阶段、耗时、心跳、模型状态和错误堆栈，不记录识别正文。debug 包可用 `adb shell run-as com.smyongbu.voiceinput` 只读提取。
