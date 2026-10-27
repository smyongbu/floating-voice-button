# 安卓语音输入

面向红米 K70 的本地中英双语语音识别 App，安装后名称为“语点”，当前版本为 `0.15.0`。主界面统一使用本地 HTML、CSS 和 JavaScript，Kotlin 只负责 WebView 宿主、麦克风、识别模型、权限、历史数据库、下载器、通知和系统级悬浮窗等平台能力。Streaming Paraformer 使用 `sherpa-onnx 1.13.5`；Faster-Whisper Small 与 Qwen3-ASR 1.7B Q5_K_M 使用固定提交的 `transcribe.cpp` Android JNI 运行层。

## 主要功能

- “录音、记录、设置”位于同一个网页式单页界面中，切换页面时底栏不会重建；App 固定为竖屏。
- 录音页依次显示当前模型、识别结果、声波与开始按钮；记录卡片整卡可复制，右下角显示复制图标，右上角使用灰色关闭图标删除。
- 实际麦克风开始收音前明确显示“准备中”，开始收音后才进入“正在聆听”，避免漏掉开头。
- 停止收音后会立即把音频加入后台最终识别队列，可以继续录制下一段；最终模型按录制顺序逐条处理，首页显示排队数量，记录页显示“最后识别中”或“排队等待”。队列最多等待 8 段，达到上限时会保留并保存实时文字，不丢失已有转写。
- “实时显示”和“最后识别”是两个始终可见、彼此独立的模型选择组。实时显示可选 Streaming Paraformer；最后识别可选 Faster-Whisper Small 或 Qwen3-ASR 1.7B Q5_K_M。录音首页用两个独立卡片上下显示当前模型；下载或校验时卡片按真实字节进度填充并在模型名右侧显示百分比，模型可用后保持浅蓝色。
- Streaming Paraformer 都在讲话时实时显示中文、英文及中英混说文字，并在检测到句段端点后提交当前段、继续识别长句。
- 停止收音后，所选最终模型直接读取本轮完整原始音频并生成最终文字。界面中的 Faster-Whisper Small 在 Android 上使用同一 Whisper Small 的 `transcribe.cpp` GGUF Q8_0 模型；Qwen3-ASR 1.7B Q5_K_M 同样由 `transcribe.cpp` 运行。
- 每次新识别都会清空上一轮临时文字，不再残留旧内容。
- 识别声波由原生音量值驱动本地 SVG 三层连续曲线，只在真正收音时运动；系统开启“减少动态效果”后会降低动态更新。
- 最终文字保存在本机 SQLite 历史中，最多 500 条；记录按聊天方式由旧到新排列，最新内容在底部，支持搜索、复制单条、复制全部、删除和清空。
- 系统级悬浮按钮支持拖动、点击开始或停止、长按关闭；拖动松手后用 200 毫秒缓出动画吸附最近的左侧或右侧安全边缘，并保存贴边方向和相对高度。文字框随球移动并优先位于屏幕内侧。网页预览和系统桌面悬浮球统一为白色玻璃质感，圆球边界外不绘制光效。设置中可调整 35%—100% 透明度和 48—88 dp 大小；默认待机不显示文字框，识别时显示，停止后保留最终文字 2 秒，点击文字框可复制并显示“已复制”1 秒。
- 仍可切换到手机系统语音服务；该方式是否联网由手机服务决定。

## 界面与安全边界

网页资源位于 `app/src/main/assets/web`，通过 AndroidX `WebViewAssetLoader` 从受控的本地域名加载。页面不直接申请麦克风，不访问外部网络，不允许外部跳转；识别文字通过 JSON 编码传入网页，并只使用 `textContent` 渲染。

### UI 浏览页

面向用户查看、标注和验收的独立预览入口位于项目上级目录的 `UI预览\打开预览.html`。该页面包含外部说明区、19.5:9 手机框、屏幕比例切换和模拟状态，可直接双击打开；手机框内部加载 `UI预览\app\index.html?preview=1`。日常查看不要直接打开正式资源目录中的裸 `app/src/main/assets/web/index.html`，也不依赖项目外的公共预览目录。

界面支持：

- 简体中文和 UTF-8
- 浅色、深色与系统字体缩放
- 竖屏、窄屏和较宽屏幕；不提供横屏模式
- 安全区、至少 48 dp 的主要触控区域
- 系统“减少动态效果”偏好

## 模型与安装包

本次按用户要求提供自带三个模型的 APK：Streaming Paraformer、Whisper Small Q8_0（界面沿用 Faster-Whisper Small 名称）及 Qwen3-ASR 1.7B Q5_K_M。模型不进入源码 Git 历史，作为 GitHub 模型资源附件保存；云构建下载后逐文件核对大小与 SHA-256，再嵌入 APK。轻量构建仍可通过不传 `-PbundledModels=true` 保留。当前资源为：

| 资源 | 用途 | 大小 |
| --- | --- | ---: |
| Streaming Paraformer INT8 | 实时显示中文、英文和中英混说文字 | 237,202,501 字节，约 226.2 MiB |
| Faster-Whisper Small（GGUF Q8_0） | 停止后对完整原始音频生成最终文字 | 269,751,136 字节，约 257.3 MiB |
| Qwen3-ASR 1.7B Q5_K_M | 停止后高质量识别多语言、中文方言和中英混说 | 1,517,290,464 字节，约 1.41 GiB |
| 合计 | 三套资源全部安装 | 2,024,244,101 字节，约 1.89 GiB |

实时显示和最后识别必须各选择一套模型，两组可以任意组合，用户只需下载实际选择的资源。“离线模型”显示每套资源的用途、版本、下载大小、已占空间、进度、速度和预计剩余时间。下载支持暂停、继续、HTTP Range 断点续传、失败重试和 SHA-256 校验；校验成功后才原子写入版本标记。开始下载时还会预留 64 MiB 可用空间。用户可删除或重新下载单个模型。

模型清单位于 `app/src/main/assets/model-resources.json`，下载地址固定到上游提交，包含每个文件的精确字节数和 SHA-256。最终目录统一为应用私有的：

```text
no_backup/resource-packs/<资源编号>/<版本>/
```

Streaming Paraformer 使用 k2-fsa/sherpa-onnx 公开模型；Faster-Whisper Small 和 Qwen3-ASR 1.7B 使用 handy-computer 发布的 `transcribe.cpp` GGUF 模型。三套模型均标记为 Apache-2.0；`sherpa-onnx` 为 Apache-2.0，固定提交的 `transcribe.cpp` 为 MIT。来源、固定版本、许可证与逐文件校验信息记录在资源清单和 `THIRD_PARTY_NOTICES.md` 中；同一份第三方说明也随 APK 放入 `assets/licenses`。

## 开发机同步模型

开发机的模型统一放在项目外的共享规范源 `D:\程序\共享模型仓库`。同步脚本通过相对于共同上级目录的路径定位，也可用环境变量 `VOICE_INPUT_MODEL_REPOSITORY` 或参数 `--source-root` 覆盖：

```text
D:\程序\共享模型仓库\
├─ streaming-paraformer-bilingual-zh-en/
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


## 0.14.0 本轮构建

- 应用已确认的设置页白色／黑色主题切换，选择保存在本机 WebView 存储中；首次跟随系统。配色覆盖录音按钮和设置页悬浮球演示背景、网格及文字框。
- 删除设置页“诊断与日志”卡片和复制入口，保留版本信息。
- 收音上限从 10 分钟改为 3 分钟。准备模型不计时，由原生收音层的单调时钟截止时间和最多 2,880,000 个 16 kHz 样本双重限制；网页和系统悬浮入口共用，到时沿用最终识别队列并保存结果。网页倒计时读取原生剩余时间。
- 模型下载、权限与最终识别仍使用正式接口；发布前端移除预览模拟识别与示例历史回退。浏览器未连接宿主时显示服务不可用，不模拟成功。
- 版本号 0.14.0，versionCode 21；继续沿用已配置的长期开发签名，不读取或更换签名密钥。

当前阶段：正式源码同步完成，6 项资源单元检查、网页脚本语法及正式页面控件引用检查已通过；Kotlin 单元测试、Lint、APK 构建、签名及真机检查须以实际构建结果为准。用户已于 2026-10-27 明确允许上传至现有公开仓库并继续云编译；构建完成后再记录 APK 核验结果。AI规划服务连接失败，待同步本轮确认、正式实施与构建证据。

## 0.14.1 模型精简

按用户要求移除 Qwen3-ASR 0.6B INT8 的选项、下载清单和运行分支；旧选择迁移为 Faster-Whisper Small，其余模型和历史记录保持。电脑共享模型已列入本轮定向清理。验证与构建结果见本轮交付记录；AI规划暂不可连接，尚未同步。

2026-10-27：移除 Zipformer 模型选项、下载清单和加载分支，旧选择迁移到 Streaming Paraformer；用户已自行删除安卓模型。本轮仅本地修改，不上传、不编译、不安装；6项资源测试及脚本语法核验通过，Kotlin编译未执行。AI规划尚未同步。


## 0.15.0 自带三模型版本

本轮用户明确要求将三个模型上传 GitHub 并编译进安装包，覆盖原来的按需下载默认要求。原始模型合计 2,024,244,101 字节，约 1.89 GiB；最终 APK 大小以实际产物为准。首次启动在后台从 APK 提取到原有私有 resource-packs 目录，显示安装进度；逐文件先写 .part，大小和 SHA-256 均正确后原子替换，全部文件就绪再写安装标记。已安装同版本模型直接复用，升级不重复复制。失败保留已有完整文件，点击重试时继续从 APK 本地安装，不要求重新联网下载。APK 自身占用与解包副本会同时存在；删除消费副本不能移除安装包中的资源，下次启动会恢复缺失的内置模型。

- 构建资源：GitHub Release `voice-bundled-models-v1`，五个逻辑权重／词表文件及 `bundled-models.json`（Qwen 大文件使用 64 MiB 附件分块，云端逐块校验后还原完整文件，再校验原始总大小和 SHA-256），按固定版本与哈希复用。
- 本地资源准备：`python scripts/bundle_models.py --export --source-root <共享模型仓库>`，仅在忽略的 local-resources 中建立消费链接／副本。
- 上传：完成本机 GitHub 登录后运行 `python scripts/upload_model_assets.py`；令牌仅由 Git Credential Manager 加密存储提供，不显示、不写入源码或日志。
- 云端准备：`python scripts/bundle_models.py --stage --release-dir local-resources/github-model-assets`。
- 含模型构建：`gradle --no-daemon -PbundledModels=true assembleDebug`；模型资产来自 build/generated/bundled-assets，缺少清单时拒绝构建。
- 最终核验：`python scripts/bundle_models.py --verify-apk <本次APK>`，检查三个模型的身份、文件大小、SHA-256，拒绝缺失或额外模型；签名、包名和版本另由 apksigner 与 aapt 核对。
- 回归：`python -B -m unittest discover -s scripts/tests -v`；Kotlin 单元测试覆盖内置模型安装、可信文件复用、坏哈希保留旧文件和截断文件不落成正式资源。

2026-10-27 交付：源码与三个模型均已上传到现有公开仓库；[云构建 40455142929](https://github.com/smyongbu/floating-voice-button/actions/runs/40455142929) 全部成功，构建源码提交 `2453dbf6661e6beba573d82a84ff38bacea2b1a7`。十一项 Python 资源测试、安卓单元测试、Lint、内置模型核验与签名版本核验通过。APK 已下载到 `安装包\语点-0.15.0-Android-arm64-三模型开发版.apk`，本机再读包内三个模型的五个文件，版本、大小和 SHA-256 全部通过。APK 大小 2,097,560,174 字节，SHA-256 `e26a3fc6ee6ca255421d9341b9673588772e8f02dde9361dc3126dd5eb88c1e9`；包名 `com.smyongbu.voiceinput`，版本 0.15.0／23，最低 Android 8.0，arm64，固定开发证书 SHA-256 `a0f437136ccf8b61580c01d2b6af132f681fadafbfc40d11586f8610fd66a7ba`。资源页安装包附件名为 `voicepoint-0.15.0-android-arm64-three-models.apk`（GitHub 会清理中文附件名，后续工作流使用稳定英文附件名），中文显示标签与本地文件名保留。后续构建只下载模型附件和清单，避免把已交付 APK 再当构建资源下载。

安装包下载：[GitHub 资源页](https://github.com/smyongbu/floating-voice-button/releases/tag/voice-bundled-models-v1)。首次启动解包模型，已装同版本可复用；安装包与私有模型副本合计约 4.12 GB，另预留安装临时空间。电脑当前未连接可用 Android 设备，真机安装、离线首次解包与实际识别效果尚未验证。AI规划服务仍不可连接，以上本轮授权、上传、构建和核验证据尚未同步。


本轮发现历史 Actions Artifact 存储配额已满；APK 和校验文件改存到同一 GitHub 模型资源页，不开通付费配额。

## GitHub 首页维护

2026-10-27：首页精简为软件介绍、安卓下载、功能和首次使用，配两张项目权威预览的局部截图并明确来源；完整开发说明保留在本文。首页正文维护于 `docs/仓库首页.md`，发布时只映射到远程默认分支 `README.md` 并同步 `docs/screenshots` 下图片，不覆盖本机共用仓库中正在修改的 Windows README，不夹带 Windows 源码。此次仅文档更新，不重新编译 APK。AI规划服务仍无法连接，本轮文档需求与更新证据尚未同步。

## 主线同步（2026-10-27）

Windows 0.16.12 与 Android 0.15.0 的正式更新统一整合至 `main`，保留各自版本和已验证产物。安卓工作流仅由 `main` 下安卓源码／构建配置的变化触发，纯文档更新不编译；资源上传脚本以 `main` 为新资源标签的默认来源。旧分支保留为历史，不再承载正式更新。项目长期约定见根目录 `AGENTS.md`。AI规划服务不可用，本轮需求与合并证据尚未同步。

合并快照通过 341 项 Windows 测试、11 项安卓资源测试、两端 JavaScript 语法及工作流 YAML 检查。两端运行源码与各自成功云构建版本逐文件一致；既有构建证据：[Windows 40465037539](https://github.com/smyongbu/floating-voice-button/actions/runs/40465037539)、[Android 40455142929](https://github.com/smyongbu/floating-voice-button/actions/runs/40455142929)。本轮使用 `[skip ci]` 跳过同版本重复打包，后续正式代码更新按 main 下的平台路径触发。

2026-10-27：首页按 Windows／Android 分区，顶部提供各平台版本、下载和系统要求；补充 Windows 按钮设置与本地模型页的正式前端预览截图，保留安卓深浅主题预览。Windows 原生截图工具未获准访问对应 Python 窗口，故配图明确注明浏览器预览与示例状态，不作为真机或识别效果证据。Windows 三个下载分卷逐项核对远程附件存在；此次仅文档和配图更新，不重新编译。AI规划服务不可用时，本轮首页更正与验证证据尚未同步。
