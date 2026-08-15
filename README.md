# 悬浮语音按钮

## 实时识别

- 默认启用“实时识别”：讲话时，悬浮按钮上方会显示不断更新的临时文字。
- 停止录音后，仍由所选本地模型或在线服务完成一次最终校正；历史记录、剪贴板和原软件都只写入最终文字一次。
- 设置与历史记录窗口的“语言识别模型”页面可以切换“实时识别”和“整段识别”。
- 实时预览与待命控制词识别共用本地 `Zipformer 中文实时轻量版 INT8`，约 26.6 MB，只用处理器运行；送入该模型的实时预览和待命音频都不会上传。最低建议为双核 64 位处理器和 4 GB 内存，推荐 4 核处理器和 8 GB 内存。
- 若实时模型暂时不可用或处理速度跟不上，普通录音会保留完整音频并继续执行停止后的整段识别，不会丢失本次录音；待命模式则会给出提示并保持关闭，不会改用系统或在线语音识别。

实时预览与待命控制词识别使用的模型来自 sherpa-onnx 官方模型：

- 模型说明：https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-ctc/zipformer-ctc-models.html
- 下载地址：https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-small-ctc-zh-int8-2025-04-01.tar.bz2
- 压缩包 SHA-256：`b3b309f7ce4a737195fcc6963ea19b0653a7d3401580af5ae0d3e284cbb71f0b`

一个可选择本地模型或国内在线服务的 Windows 悬浮语音输入按钮。设置与历史记录使用本地 HTML、CSS、JavaScript 和系统 WebView2；悬浮层使用 Windows 逐像素 Alpha 分层窗口。默认使用本地识别，不会上传录音。项目内另有 `android-app` 安卓悬浮版源码与安装包。

## 安卓悬浮版

`android-app` 面向红米 K70，默认使用本地模型，也保留系统默认语音识别：

- 系统级悬浮小球可拖动，点击开始或停止识别，悬浮字幕边说边更新。
- 可选择 Zipformer＋Paraformer、仅 Zipformer、仅 Paraformer 三种本地方案；默认实时识别并在停止后整体校正。
- 录音期间主界面与悬浮小球显示真实收音波形，最终文字自动保存到本机历史。
- 主界面可切换到手机系统默认识别，并支持查看历史和复制最终文字。
- 系统服务可能自行联网；本地识别不会上传录音，日志不记录识别正文。
- 安装包位于 `android-app/安装包/安卓语音输入-本地识别悬浮版.apk`。

## 使用方法

1. 把光标放到需要输入文字的软件中。
2. 双击 `启动悬浮语音按钮.vbs`。
3. 单击悬浮按钮，或按全局快捷键 `Ctrl+Alt+Space` 开始录音。
4. 说话时按钮显示随收音跳动的 7 条细波形；再次单击或按快捷键停止。
5. 程序使用设置页选定的方式转写，保存到识别历史，并自动粘贴回原软件。文字也会保留在系统剪贴板中。

可拖动按钮改变位置。右键按钮可打开“设置与历史记录”、打开日志目录或退出。

## 设置与历史记录

右键悬浮按钮，选择“设置与历史记录…”：

- 窗口是完整的本地网页界面，不使用 Tk/ttk 控件；页面资源不连接外网。
- “按钮设置”可选择任意按钮颜色、把整体透明度设置为 30%～100%，并修改全局录音快捷键。保存后悬浮按钮会自动更新，无需重启。
- 可开启“待命模式”：麦克风使用本地 Zipformer 轻量模型持续监听“开始”和“结束”，仅使用处理器运行，待命音频不会上传。开启后悬浮按钮变为灰色，并显示随收音变化的七条待命线；请把“开始”和“结束”作为单独一句说出，并在前后短暂停顿。说“开始”后先播放提示音，再恢复为自定义颜色并开始本机录音；正文说完稍停，再单独说“结束”，程序会先停止收音，再播放提示音并完成转写，控制词音频不会保存。也支持“开始录音、开始说话、停止录音、结束录音、结束说话”。
- 录音和处理中使用用户设置的自定义主色，不会变红；只有尚未开始录音的待命状态使用灰色。
- 最终文字会执行一次轻量修正：只整理安全的中文空格和单个标点。它不使用语言大模型、不占用显卡，也不会猜测词义、删除重复句或改写原意。
- “识别历史”会在本机保存最近 500 条成功识别文字，支持搜索、查看全文、复制、删除和清空。
- 从历史记录复制的文字会写入 Windows 系统剪贴板，关闭窗口后仍可再次粘贴。
- “本地模式”可选择本地模型和运行设备；“在线模型”可选择火山引擎、科大讯飞、腾讯云或阿里云。在线服务凭据保存在当前 Windows 用户的凭据管理器中，不写入普通配置文件。
- 选择在线服务会上传本次完整录音，可能产生厂商费用；在线录音统一限制为 55 秒。网络临时故障可回退到用户选择的本地模型，鉴权、额度或参数错误不会被隐藏。

历史数据库位于 `%LOCALAPPDATA%\FloatingVoiceButton\history.db`，不会上传；日志也不会记录识别正文。

## 运行要求

- Windows 10 或 Windows 11
- Python 3.11 或更高版本，安装时勾选“添加到 PATH”
- Microsoft Edge WebView2 Runtime（Windows 11 通常已自带；缺少时需先安装）
- 已提供四个可选的本地整段识别模型，以及一个用于实时预览和待命控制词识别的 Zipformer 轻量模型；首次使用会复制到本机 `%LOCALAPPDATA%\FloatingVoiceButton\models`
- 首次使用前运行 `python -m pip install -r requirements.txt`
- 需要粘贴文字的目标软件与本程序应以相同权限运行；权限不同时 Windows 可能阻止自动粘贴

## 配置

首次拖动按钮后，会在 `%LOCALAPPDATA%\FloatingVoiceButton\config.json` 生成配置。可退出程序后修改：

- `paste_wait_ms`：切回原软件后、粘贴前的缓冲时间
- `button_color`：按钮主色，格式如 `#2563EB`
- `button_opacity`：按钮透明度，范围 30～100
- `global_hotkey`：全局开始/停止录音快捷键，默认 `Ctrl+Alt+Space`；也可直接使用 `F1`～`F24`
- `standby_enabled`：是否启用本地 Zipformer 持续监听“开始／结束”的待命模式，默认关闭
- `recognition_engine`：识别方式，默认 `local:sensevoice-small-int8`
- `fallback_model`：在线临时故障时使用的本地备用模型
- `local_asr_device`：本地模型设备，`auto` 自动选择、`cpu` 固定 CPU、`gpu` 固定兼容 GPU；普通 Windows 版默认自动回退 CPU

## 本地模型性能要求

以下最低与推荐配置是保守的工程估算，实际速度会随处理器代际、录音长度和后台负载变化。普通电脑优先选择“自动选择”或“使用处理器”；只有安装了兼容运行组件时才选择显卡。

| 模型 | 主要用途 | 模型大小 | 最低配置 | 推荐配置 | 显卡 |
| --- | --- | ---: | --- | --- | --- |
| SenseVoiceSmall INT8 | 中文短句、粤语及中英日韩 | 约 230 MB | 双核 64 位 CPU、4 GB 内存 | 4 核 CPU、8 GB 内存 | 非必需 |
| Paraformer 中文轻量版 INT8 | 普通话、中英混说及部分方言，速度优先 | 约 82 MB | 双核 64 位 CPU、4 GB 内存 | 4 核 CPU、8 GB 内存 | 非必需 |
| Qwen3-ASR 0.6B INT8 | 多种中文方言、30 多种语言及复杂语音 | 约 1 GB | 4 核 64 位 CPU、8 GB 内存 | 6 核以上 CPU、16 GB 内存 | 非必需，CUDA 可选 |
| Faster-Whisper Small | 多语言通用备用 | 约 486 MB | 4 核 64 位 CPU、4 GB 内存 | 6 至 8 核 CPU、8 GB 内存 | 非必需；GPU 需 NVIDIA CUDA 12 与 cuDNN 9 |

设置页会显示每个模型的真实安装状态、运行组件状态和性能要求，并提供“测试模型”按钮。当前电脑没有兼容推理显卡时，“自动选择”会使用 CPU。

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

两类日志各自最多约 512 KB，并保留一份轮转备份。右键悬浮按钮可直接打开日志目录。

## 开发验证

在项目目录运行：

```powershell
python -m unittest discover -s tests -v
python -m py_compile app.py automation.py audio_level.py cloud_asr.py config_store.py credential_store.py global_hotkey.py history_store.py live_transcript.py local_asr.py logger.py overlay.py realtime_asr.py recognition_router.py settings_panel.py standby_listener.py transcript_refinement.py
```
