# 语点

Windows 与 Android 双端悬浮语音输入工具。边说边显示文字，停止后生成最终结果；本地模型识别时，录音不上传。

## 选择你的版本

| 平台 | 当前版本 | 下载 | 系统要求 |
| --- | --- | --- | --- |
| **Windows 电脑版** | 0.16.12 · 自带三模型 | [分卷 001](https://github.com/smyongbu/floating-voice-button/releases/download/voice-bundled-models-v1/Yudian-Windows-v0.16.12-three-models.zip.001) · [002](https://github.com/smyongbu/floating-voice-button/releases/download/voice-bundled-models-v1/Yudian-Windows-v0.16.12-three-models.zip.002) · [003](https://github.com/smyongbu/floating-voice-button/releases/download/voice-bundled-models-v1/Yudian-Windows-v0.16.12-three-models.zip.003) | Windows 10 / 11，64 位 |
| **Android 安卓版** | 0.15.0 · 自带三模型 | [下载 APK](https://github.com/smyongbu/floating-voice-button/releases/download/voice-bundled-models-v1/voicepoint-0.15.0-android-arm64-three-models.apk) | Android 8.0 及以上，arm64 |

Windows 版的 **三个分卷必须全部下载到同一文件夹**，用 7-Zip 打开 `.001` 解压，再运行文件夹里的 `语点.exe`；不要直接在压缩包内运行。[全部下载与校验文件](https://github.com/smyongbu/floating-voice-button/releases/tag/voice-bundled-models-v1)

## Windows 电脑版

悬浮按钮或快捷键开始、停止录音；支持自动粘贴到原软件、识别历史搜索与复制，以及按钮颜色、大小、透明度和快捷键设置。

<img src="https://raw.githubusercontent.com/smyongbu/floating-voice-button/main/docs/screenshots/windows-appearance.png" width="900" alt="Windows 语点按钮设置界面预览，展示悬浮按钮外观、快捷键、实时文字与自动输入设置">

<details>
<summary>查看 Windows 本地模型设置</summary>

<img src="https://raw.githubusercontent.com/smyongbu/floating-voice-button/main/docs/screenshots/windows-models.png" width="900" alt="Windows 语点本地模型界面预览，展示实时模型与停止后识别模型选择">

</details>

Windows 配图来自当前软件正式前端的浏览器预览，模型安装状态为示例；不是识别性能测试结果。首次使用：完整解压 → 运行 `语点.exe` → 将光标放在输入处 → 点击悬浮按钮说话，再次点击停止。

## Android 安卓版

手机内提供录音、记录、设置三个页面；支持系统悬浮按钮、黑白主题切换，单段录音上限 3 分钟。

<table>
  <tr><th>安卓录音 · 深色主题</th><th>安卓设置 · 浅色主题</th></tr>
  <tr>
    <td valign="top"><img src="https://raw.githubusercontent.com/smyongbu/floating-voice-button/main/android-app/docs/screenshots/recording-dark.png" width="280" alt="安卓语点录音页界面预览"></td>
    <td valign="top"><img src="https://raw.githubusercontent.com/smyongbu/floating-voice-button/main/android-app/docs/screenshots/settings-light.png" width="280" alt="安卓语点设置页界面预览，展示主题切换与三个模型"></td>
  </tr>
</table>

安卓配图为项目内界面预览的局部截图，并非真机识别测试截图。

1. 下载并安装 APK，首次启动等待内置模型解包，无需再联网下载模型。
2. 允许麦克风权限；使用悬浮按钮时，再开启“显示在其他应用上层”权限。
3. 点击“开始识别”，讲话后再次点击停止；最终文字可在记录页查看、复制。

APK 约 **2.10 GB**，解包后的模型约 **2.02 GB**，两者合计约 **4.12 GB**，另需预留安装临时空间。当前为开发测试版，真机安装与实际识别效果待验证；手机系统语音服务是否联网由系统服务决定。

---

两个平台的三模型版均包含 **Streaming Paraformer、Whisper Small、Qwen3-ASR 1.7B Q5_K_M**，具体格式和运行方式见各平台文档。

[Windows 使用与开发说明](https://github.com/smyongbu/floating-voice-button/blob/main/docs/windows.md) · [安卓使用与构建说明](https://github.com/smyongbu/floating-voice-button/tree/main/android-app) · [问题反馈](https://github.com/smyongbu/floating-voice-button/issues)
