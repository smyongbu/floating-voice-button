# 语点

把说话变成文字的悬浮语音输入工具，提供 Windows 和 Android 客户端。本地模型识别时，录音不上传。

**[下载安卓三模型版 · 0.15.0](https://github.com/smyongbu/floating-voice-button/releases/download/voice-bundled-models-v1/voicepoint-0.15.0-android-arm64-three-models.apk)**　｜　[全部下载](https://github.com/smyongbu/floating-voice-button/releases)

## 界面

<table>
  <tr><th>录音 · 深色主题</th><th>设置 · 浅色主题</th></tr>
  <tr>
    <td valign="top"><img src="https://raw.githubusercontent.com/smyongbu/floating-voice-button/main/android-app/docs/screenshots/recording-dark.png" width="280" alt="语点安卓录音页预览，展示当前模型、识别结果和开始识别按钮"></td>
    <td valign="top"><img src="https://raw.githubusercontent.com/smyongbu/floating-voice-button/main/android-app/docs/screenshots/settings-light.png" width="280" alt="语点安卓设置页预览，展示白色黑色主题切换与三个识别模型"></td>
  </tr>
</table>

以上为安卓界面预览的局部截图，展示界面外观；并非真机识别测试截图。

## 能做什么

- **边说边看文字**：实时转写，停止录音后生成最终结果。
- **悬浮按钮**：在其他应用上层开始、停止录音，位置可拖动。
- **本地识别**：支持中文、英文及中英混说，速度随设备和模型变化。
- **历史记录**：搜索、复制和删除识别文字；Windows 支持自动粘贴。
- **黑白主题**：安卓设置页可切换；单段录音上限 3 分钟。

## 安卓安装

1. 下载上方 **APK**，在 Android 8.0 及以上的 arm64 手机上安装。
2. 首次启动等待内置模型解包；无需再联网下载模型。
3. 允许麦克风权限；需要悬浮按钮时，再开启“显示在其他应用上层”权限。
4. 点击“开始识别”，讲话后再次点击停止；最终文字可在记录页查看、复制。

安装包约 **2.10 GB**，内置 **Streaming Paraformer、Whisper Small Q8_0、Qwen3-ASR 1.7B Q5_K_M**。解包后的模型约 **2.02 GB**，安装包与模型副本合计约 **4.12 GB**，请另留安装临时空间。

当前为开发测试版，构建、签名和模型完整性已核验，真机安装与识别效果待验证。使用手机系统语音服务时，是否联网由系统服务决定。

---

[安卓源码与构建说明](https://github.com/smyongbu/floating-voice-button/tree/agent/update-voice-recognition/android-app) · [问题反馈](https://github.com/smyongbu/floating-voice-button/issues)
