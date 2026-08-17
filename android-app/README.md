# 安卓语音输入

面向红米 K70 的本地中英双语语音识别 App，当前版本为 `0.8.0`。主界面统一使用本地 HTML、CSS 和 JavaScript，Kotlin 只负责 WebView 宿主、麦克风、识别模型、权限、历史数据库、下载器、通知和系统级悬浮窗等平台能力。

## 主要功能

- “录音、记录、设置”位于同一个网页式单页界面中，切换页面时底栏不会重建，图标和文字保持统一排列。
- 实际麦克风开始收音前明确显示“准备中”，开始收音后才进入“正在聆听”，避免漏掉开头。
- Zipformer 使用 `modified_beam_search` 和 4 条活动路径实时识别中文、英文及中英混说；检测到句段端点后提交当前段并继续识别长句。
- 停止后可用 Paraformer 校正完整句子；若校正结果明显丢句或把英文拆成异常单字母，会保留更完整的实时结果。
- 每次新识别都会清空上一轮临时文字，不再残留旧内容。
- 识别声波由原生音量值驱动本地 SVG 三层连续曲线，只在真正收音时运动；系统开启“减少动态效果”后会降低动态更新。
- 最终文字保存在本机 SQLite 历史中，最多 500 条，支持搜索、复制、删除和清空。
- 系统级悬浮按钮支持拖动、点击开始或停止、长按关闭，并使用连续曲线表示真实收音。
- 仍可切换到手机系统语音服务；该方式是否联网由手机服务决定。

## 界面与安全边界

网页资源位于 `app/src/main/assets/web`，通过 AndroidX `WebViewAssetLoader` 从受控的本地域名加载。页面不直接申请麦克风，不访问外部网络，不允许外部跳转；识别文字通过 JSON 编码传入网页，并只使用 `textContent` 渲染。

界面支持：

- 简体中文和 UTF-8
- 浅色、深色与系统字体缩放
- 竖屏、横屏、窄屏和较宽屏幕
- 安全区、至少 48 dp 的主要触控区域
- 系统“减少动态效果”偏好

## 模型与安装包

模型不再编入 APK，也不提交到 Git。安装包只包含应用、网页界面、识别运行库和小型资源，模型在首次使用相关方案时单独下载。当前资源为：

| 资源 | 用途 | 大小 |
| --- | --- | ---: |
| 中英双语 Zipformer | 实时出字、中文、英文和中英混说 | 60,142,871 字节，约 57.4 MiB |
| 中英双语 Paraformer | 停止后校正完整句子 | 81,904,027 字节，约 78.1 MiB |
| 合计 | 推荐的双模型方案 | 142,046,898 字节，约 135.5 MiB |

应用内“设置 → 离线模型”会显示资源用途、下载大小、已占空间、手机可用空间、进度、速度、预计剩余时间和版本。下载支持暂停、继续、HTTP Range 断点续传、失败重试和 SHA-256 校验；校验成功后才原子写入版本标记。开始下载时还会预留 64 MiB 可用空间。用户可删除或重新下载单个模型。

模型清单位于 `app/src/main/assets/model-resources.json`，下载地址固定到上游提交，包含每个文件的精确字节数和 SHA-256。最终目录统一为应用私有的：

```text
no_backup/resource-packs/<资源编号>/<版本>/
```

Zipformer 与 Paraformer 均来自 k2-fsa/sherpa-onnx 官方公开模型，许可证为 Apache-2.0；来源链接记录在资源清单中。

## 开发机同步模型

开发机的模型放在被 Git 忽略的 `local-resources/models`：

```text
local-resources/models/
├─ zipformer-bilingual/
└─ paraformer/
```

安装新的 debug APK 后运行：

```powershell
python scripts/同步安卓模型.py
```

只有一台已授权手机时无需参数；多台设备可增加 `--serial <设备序列号>`。脚本先校验本机文件，再比较手机中的大小和 SHA-256，只传输新增或变化的文件。临时文件校验成功后才替换最终文件，并在全部文件就绪后写入版本标记；失败不会删除手机上仍可用的旧资源。

同步脚本日志分开保存在：

```text
scripts/logs/模型同步-运行.log
scripts/logs/模型同步-错误.log
```

日志目录已忽略，不会提交到 Git；日志会隐藏本机模型目录。

## 构建与检查

要求 JDK 17、Android SDK 35、Gradle 8.9。项目根目录执行：

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

debug APK 位于 `app/build/outputs/apk/debug/app-debug.apk`。GitHub Actions 会依次运行资源清单测试、Android 单元测试、Lint、构建，并检查 APK 中不存在 `.onnx` 或 `.model` 文件。

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

本地识别不会上传录音，应用不保存录音，也不会把识别正文写入日志。手机系统识别可能把音频交给系统服务商处理。

## 运行日志

应用日志位于私有目录：

```text
files/logs/运行.log
files/logs/错误.log
```

两类日志分别轮转，只记录版本、操作编号、阶段、耗时、心跳、模型状态和错误堆栈，不记录识别正文。debug 包可用 `adb shell run-as com.smyongbu.voiceinput` 只读提取。
