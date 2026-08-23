# 悬浮语音按钮

## 实时识别

- 默认启用“实时识别”：讲话时，悬浮按钮上方会显示不断更新的临时文字。
- 停止录音后，仍由所选本地模型或在线服务读取完整原始音频并生成最终文字；历史记录、剪贴板和原软件都只写入一次。
- Windows 的“本地模式”页面可选择 `Streaming Paraformer` 或 `Zipformer` 负责边说边显示文字；默认使用中英混说准确率更高的 Streaming Paraformer，性能较弱的电脑可选响应更快的 Zipformer。
- 两个实时模型都在本机处理中文、英文和中英混说，只使用处理器，不上传录音。实时文字和停止后的整段识别结果都不会再经过通用文字改写、补标点或大小写整理。
- 停止录音后会比较实时结果与整段识别结果；若整段结果明显丢句、无关或破坏英文，保留更完整的实时结果。这个过程只在两份模型输出中择优，不改写文字。
- 若实时模型暂时不可用或处理速度跟不上，程序会保留完整录音，并继续执行原有的停止后整段识别，不会丢失本次录音。

实时模型来自 sherpa-onnx 官方模型：

- Streaming Paraformer：https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-paraformer-bilingual-zh-en.tar.bz2
- Zipformer 固定版本：https://huggingface.co/csukuangfj/k2fsa-zipformer-bilingual-zh-en-t/tree/8a7306b4d4d40c3cb1bdb80e8f2f605167570af3
- 所有文件的大小和 SHA-256 均由程序内资源清单校验，校验失败不会加载。

一个可选择本地模型或国内在线服务的 Windows 悬浮语音输入按钮。设置与历史记录使用本地 HTML、CSS、JavaScript 和系统 WebView2；悬浮层使用 Windows 逐像素 Alpha 分层窗口。默认使用本地识别，不会上传录音。项目内另有 `android-app` 安卓悬浮版源码与安装包。

当前 Windows 源码版本为 `0.16.2`。

## 共用悬浮按钮调试页

- `recording-button-lab.html`（页面标题“录音按钮调试台”）是 Windows 与安卓手机端共用悬浮按钮的统一设计、调试和验收页面，不是手机 App 主界面预览。
- 用户提到“共用按钮”“电脑和手机共用的按钮”“按钮调试页”或“专门调试按钮的页面”时，默认指这个独立调试页；不要改开或新建简化实验页，也不要打开安卓手机框预览代替它。
- 调试页覆盖待机／录音状态、1:1 实际尺寸、2×2 对齐、颜色、尺寸、透明度、波形强度、波形速度、垂直位置和不同背景。页面中确认的按钮视觉与状态行为应作为 Windows 和安卓悬浮按钮的共同基准；应用到任一正式端前仍需取得用户明确确认。
- 该页面可能由本机预览服务从 Codex 预览存档启动；定位时优先按文件名 `recording-button-lab.html` 或目录名 `recording-button-lab-feedback` 查找，不要仅凭旧的 `127.0.0.1` 端口判断文件位置。

## 安卓悬浮版

`android-app` 面向红米 K70，默认使用本地模型，也保留系统默认语音识别：

- “录音、记录、设置”已重写为同一个本地 HTML、CSS、JavaScript 单页界面；Kotlin 只承担 WebView 宿主、麦克风、模型、权限、数据库与系统悬浮窗等平台能力。
- 系统级悬浮小球可拖动，点击开始或停止识别；长按会取消本次识别并关闭小球。悬浮球采用透明玻璃质感与边缘微光，可调整透明度，也可独立关闭悬浮识别文字框。
- 可选择 Zipformer＋Paraformer、仅 Zipformer、仅 Paraformer 三种本地方案；录音首页会显示当前启用的一套或两套模型，默认实时识别并在停止后按语音片段校正。
- Zipformer 与 Paraformer 不再放进 APK：首次使用时可在设置页分别下载、暂停、继续、校验、删除或重新下载，更新 App 不会重复下载已校验模型；开发测试可用脚本按哈希增量同步到同一目录。
- 已安装模型会在后台预加载并在进程内复用，不会每句话重新加载。实时模型使用 4 路改进波束搜索和长句分段；最终校正明显丢句或破坏英文时会保留更完整的实时结果。
- 只有麦克风真正开始收音后，录音页与悬浮小球才显示由真实音量驱动的连续曲线声波；新一轮开始会清空上一轮文字。
- 底部导航固定包含“录音、记录、设置”三个入口，不再通过三个原生页面切换，因此图标、文字和选中状态保持稳定。
- Zipformer 实时模型和 Paraformer 最终校正都支持中文、英文和中英混说；实时输出会过滤 `<nuk>` 等模型内部标记。
- 系统服务可能自行联网；本地识别不会上传录音，日志不记录识别正文。
- App 固定为竖屏；录音页卡片顺序为当前模型、识别结果、声波与开始按钮，历史记录支持整卡复制及右上角灰色删除按钮。
- 当前源码版本为 `0.8.2`，识别运行库为 `sherpa-onnx 1.13.5`，详细构建、模型同步和日志说明见 `android-app/README.md`。

## 使用方法

1. 把光标放到需要输入文字的软件中。
2. 双击 `启动悬浮语音按钮.vbs`。
3. 空闲时悬浮按钮严格复刻共用调试页的通透蓝色主圆与灰色双弧圆环，圆形边界外不绘制特效；单击按钮或按全局快捷键 `Ctrl+Alt+Space`，播放开始提示音后开始录音。
4. 说话时按钮的灰色圆环会连续展开为由真实音量驱动的三层蓝青曲线声波，不显示三点或空白中间帧；再次单击或按快捷键停止收音后播放结束提示音，声波连续收回为圆环。
5. 程序使用设置页选定的方式转写并保存到识别历史。默认自动粘贴回原软件；关闭“识别后自动输入”后，只复制到系统剪贴板，不再切换窗口或自动粘贴。

可拖动按钮改变位置。拖动过程不会抢走当前输入焦点，也不使用 Windows 标题栏拖动或全局鼠标钩子；即使鼠标在按钮外松开、拖动被系统取消或窗口关闭，也会自动结束本次拖动。右键按钮可打开“设置与历史记录”、打开日志目录或退出。

## 设置与历史记录

右键悬浮按钮，选择“设置与历史记录…”：

- 窗口是完整的本地网页界面，不使用 Tk/ttk 控件；页面资源不连接外网。
- “按钮设置”可选择任意按钮颜色、把整体透明度设置为 30%～100%、把按钮大小设置为 64～80 px，并修改全局录音快捷键。保存后悬浮按钮会自动更新，无需重启。
- “识别后自动输入”默认开启；关闭后仍会识别、保存历史并复制到剪贴板，但不会自动把文字输入当前软件。
- 可开启“待命模式”：麦克风使用 Windows 本机控制词识别持续监听“开始”和“结束”。空闲和待命状态都保留蓝青玻璃质感，并在中间显示紧凑的灰色双弧圆环；说“开始”后播放提示音并开始本机录音，说“结束”后完成转写，去除正文首尾的控制词，只保存到识别历史。也支持“开始录音、开始说话、停止录音、结束录音、结束说话”。
- 待机、录音和处理中使用同一个自定义主色；Windows 端按共用调试页相同的 82% 主圆与 48% 原始背景图叠层绘制，背景层严格裁在圆形边界内，不再二次着色，也不显示圆外特效。灰色圆环与三层实时曲线使用 280 毫秒连续可逆形变，处理中保持当前过渡，不显示三点、空白中间帧或额外呼吸光环，也不会变红；Windows 关闭界面动画时直接显示目标状态。
- “识别历史”会在本机保存最近 500 条成功识别文字，支持搜索、查看全文、复制单条、复制全部、删除和清空；复制全部按从新到旧顺序用空行分隔每条正文。
- 从历史记录复制的文字会写入 Windows 系统剪贴板，关闭窗口后仍可再次粘贴。
- “本地模式”可分别选择实时显示模型、停止后的整段识别模型和运行设备；模型区只展开当前选择模型的大小、语言与配置要求。“在线模型”可选择火山引擎、科大讯飞、腾讯云或阿里云。在线服务凭据保存在当前 Windows 用户的凭据管理器中，不写入普通配置文件。
- Windows 正式设置页现有 3 个本地识别选项：`Faster-Whisper Small`、`Qwen3-ASR 0.6B INT8` 和 `Qwen3-ASR 1.7B`。设置页会显示下载大小、已占空间、进度、速度、剩余时间和校验状态，并提供暂停、继续、失败重试、删除和重新下载。
- 选择在线服务会上传本次完整录音，可能产生厂商费用；在线录音统一限制为 55 秒。网络临时故障可回退到用户选择的本地模型，鉴权、额度或参数错误不会被隐藏。

历史数据库位于 `%LOCALAPPDATA%\FloatingVoiceButton\history.db`，不会上传；日志也不会记录识别正文。

## 运行要求

- Windows 10 或 Windows 11
- 标准 CPython 3.11（当前正式依赖的已验证版本），安装时勾选“添加到 PATH”；启动脚本会优先使用默认位置的 Python 3.11。本机 Anaconda Python 3.12 加载 `transcribe.cpp 0.2.1` 原生组件时会异常退出，不要用它启动本程序
- Microsoft Edge WebView2 Runtime（Windows 11 通常已自带；缺少时需先安装）
- Windows 所有现用模型统一以 `O:\程序\共享模型仓库` 为规范源；源码通过相对于共同上级目录的路径定位，也可用 `VOICE_INPUT_MODEL_REPOSITORY` 覆盖。运行时如需复制到 `%LOCALAPPDATA%\FloatingVoiceButton\models`，该副本仅是可重建缓存。删除应用缓存不会删除共享仓库，重新使用时直接从共享仓库恢复，不重复联网下载
- 不带模型轻量升级版不会把模型编译进 EXE 或 ZIP。解压后，程序从 `语点.exe` 旁边独立的 `models` 文件夹读取外置模型；也可继续通过 `VOICE_INPUT_MODEL_REPOSITORY` 指定其他模型仓库。
- 编译版必须先完整解压再运行，既可放在本机磁盘，也可从 NAS 或 `\\服务器\共享` 这类 UNC 网络路径启动。网络共享兼容依赖 `语点.exe` 同目录的 `语点.exe.config`，升级、复制或整理文件时不要删除；仍不能直接从 ZIP 内运行。
- Windows 编译版分为两种：第一次安装优先下载“首次安装版”，它在 `models` 文件夹附带 Faster-Whisper Small 与 Streaming Paraformer；以后升级可只下载“不带模型轻量升级版”，直接复用电脑上已经安装的模型，不重复下载模型文件。
- 轻量升级不会删除 `%LOCALAPPDATA%\FloatingVoiceButton\models` 中的模型缓存。若模型放在旧版 `语点.exe` 旁边的 `models` 文件夹，升级时应保留该文件夹，或把它与新版程序放在同一目录。
- `语点.exe`、任务管理器中的语点进程及 Windows 通知区域统一使用 `assets\app.ico` 应用图标。通知区域图标左键打开设置，右键打开与悬浮按钮相同的菜单。
- 首次使用前运行 `python -m pip install -r requirements.txt`
- 需要粘贴文字的目标软件与本程序应以相同权限运行；权限不同时 Windows 可能阻止自动粘贴

## 配置

首次拖动按钮后，会在 `%LOCALAPPDATA%\FloatingVoiceButton\config.json` 生成配置。可退出程序后修改：

- `paste_wait_ms`：切回原软件后、粘贴前的缓冲时间
- `auto_paste_enabled`：识别后是否自动切回原软件并粘贴，默认开启；关闭时只保存历史并复制到剪贴板
- `button_color`：按钮主色，格式如 `#2563EB`
- `button_opacity`：按钮透明度，范围 30～100
- `button_size`：按钮大小，范围 64～80 px，默认 72 px
- `global_hotkey`：全局开始/停止录音快捷键，默认 `Ctrl+Alt+Space`；也可直接使用 `F1`～`F24`
- `standby_enabled`：是否启用持续监听“开始／结束”的待命模式，默认关闭
- `realtime_model`：边说边显示文字所用模型；默认 `streaming-paraformer-bilingual-zh-en`，也可设为 `zipformer-bilingual-zh-en-exp32-int8`
- `recognition_engine`：识别方式，默认 `local:faster-whisper-small`
- `fallback_model`：在线临时故障时使用的本地备用模型
- `local_asr_device`：本地模型设备，`auto` 自动选择、`cpu` 固定 CPU、`gpu` 固定兼容 GPU；普通 Windows 版默认自动回退 CPU
- Qwen3-ASR 1.7B 的模型编号为 `qwen3-asr-1.7b-q5km`

## 本地模型性能要求

以下最低与推荐配置是保守的工程估算，实际速度会随处理器代际、录音长度和后台负载变化。普通电脑优先选择“自动选择”或“使用处理器”；只有安装了兼容运行组件时才选择显卡。

| 模型 | 主要用途 | 模型大小 | 最低配置 | 推荐配置 | 显卡 |
| --- | --- | ---: | --- | --- | --- |
| SenseVoiceSmall INT8 | 中文短句、粤语及中英日韩 | 约 230 MB | 双核 64 位 CPU、4 GB 内存 | 4 核 CPU、8 GB 内存 | 非必需 |
| Paraformer 中文轻量版 INT8 | 普通话、中英混说及部分方言，速度优先 | 约 82 MB | 双核 64 位 CPU、4 GB 内存 | 4 核 CPU、8 GB 内存 | 非必需 |
| Qwen3-ASR 0.6B INT8 | 多种中文方言、30 多种语言及复杂语音 | 约 1 GB | 4 核 64 位 CPU、8 GB 内存 | 6 核以上 CPU、16 GB 内存 | 非必需，CUDA 可选 |
| Faster-Whisper Small | 多语言通用备用 | 约 486 MB | 4 核 64 位 CPU、4 GB 内存 | 6 至 8 核 CPU、8 GB 内存 | 非必需；GPU 需 NVIDIA CUDA 12 与 cuDNN 9 |
| Qwen3-ASR 1.7B | 中英混说、方言及多语言整段识别 | 约 1.52 GB | 4 核 64 位 CPU、12 GB 内存 | 8 核 CPU、16 GB 内存 | 支持 Intel、AMD、NVIDIA Vulkan；不可用时回退 CPU |

设置页会显示每个模型的真实安装状态、运行组件状态和性能要求。当前电脑没有兼容推理显卡时，“自动选择”会使用 CPU。

### Qwen3-ASR 1.7B

- 使用单个 `Qwen3-ASR-1.7B-Q5_K_M.gguf` 模型文件，按需下载后约占 1.52 GB 磁盘空间。
- 模型可离线识别中英文混说、中文方言和多种语言，不依赖额外文字修正模块。
- 1.7B 使用 `transcribe.cpp 0.2.1` 的 CPU/Vulkan 后端和固定 Q5_K_M 权重。它负责停止录音后的离线整段识别；讲话过程中的临时文字由设置页选中的 Streaming Paraformer 或 Zipformer 生成。
- 模型固定来源：https://huggingface.co/handy-computer/Qwen3-ASR-1.7B-gguf/tree/92282af1610a2db19d66f2bef1e260f5deca782d ，目标文件大小为 `1,517,290,464` 字节，SHA-256 为 `034c557fe92ff8fcd9a9c041cbdaad347be0a86a58d3a348f63cf3f0180879d0`。
- 推理实现与模型说明：https://github.com/handy-computer/transcribe.cpp/blob/v0.2.1/docs/models/qwen3-asr-1.7b.md 。第三方来源与许可见 `THIRD_PARTY_NOTICES.md`。

## 国内在线识别

- 火山引擎：豆包语音大模型录音文件极速版，需要应用密钥；旧控制台可另填访问密钥。
- 科大讯飞：语音听写流式接口，需要应用编号、接口密钥和接口密钥口令；录音按实时速度上传。
- 腾讯云：一句话识别，需要访问密钥编号和访问密钥。
- 阿里云：智能语音交互一句话识别，需要项目密钥、访问密钥编号和访问密钥。

程序不会把一段录音自动依次上传给多个在线厂商，也不会在默认本地模式下访问在线识别服务。

## 日志

日志位于 `%LOCALAPPDATA%\FloatingVoiceButton\logs`：

- `运行.log`：启动、退出和关键操作成功记录
- `错误.log`：警告、失败及异常堆栈
- `面板-运行.log`、`面板-错误.log`：设置与历史窗口的独立日志
- 1.7B 下载进度、暂停、继续、校验和删除只记录资源编号、版本、字节数与错误类型；下载网址中的查询参数和识别正文不会写入日志

两类日志各自最多约 512 KB，并保留一份轮转备份。右键悬浮按钮可直接打开日志目录。

## 开发验证

在项目目录运行：

```powershell
python -m unittest discover -s tests -v
python -m py_compile app.py automation.py audio_level.py cloud_asr.py config_store.py context_menu.py credential_store.py global_hotkey.py history_store.py live_transcript.py local_asr.py logger.py model_download.py overlay.py realtime_asr.py recognition_router.py settings_panel.py standby_listener.py test_mode_signal.py
```

本地编译不带模型的轻量升级版：

```powershell
python tools\build_windows.py --variant lite
```

成品、SHA-256 校验文件和编译说明生成在 `发布版本`，模型与编译缓存不会提交到 Git。
