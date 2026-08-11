# 悬浮语音按钮

一个仅通过 Windows 界面自动化工作的悬浮麦克风按钮。程序不调用 Codex API、不读取音频，也不接入语音识别服务。

## 使用方法

1. 打开 Codex，并把光标放到希望开始语音输入的任务输入框中。
2. 双击 `启动悬浮语音按钮.vbs`。
3. 在原软件中单击蓝色悬浮按钮。程序会记住该软件，切换到 Codex，并按下 `Ctrl+Shift+D`。
4. 说话时按钮为红色。再次单击红色按钮，程序会结束语音输入，等待转写完成，复制文字，切回原软件并粘贴。

可拖动按钮改变位置；右键按钮可打开日志目录、重新查找 Codex 或退出。

## 运行要求

- Windows 10 或 Windows 11
- Python 3.11 或更高版本，安装时勾选“添加到 PATH”
- Codex 的语音输入快捷键为 `Ctrl+Shift+D`
- 原软件与 Codex 需以相同权限运行；若一个使用管理员权限、另一个没有，Windows 会阻止自动输入

## 配置

首次拖动按钮后，会在 `%LOCALAPPDATA%\FloatingVoiceButton\config.json` 生成配置。可退出程序后修改：

- `codex_window_keywords`：用于匹配 Codex 窗口标题
- `codex_process_names`：优先匹配的进程名；当前桌面版通常显示为 `ChatGPT.exe`
- `transcription_wait_ms`：结束录音后等待文字出现的时间，默认 900 毫秒
- `copy_wait_ms`、`paste_wait_ms`：复制和粘贴前的缓冲时间

如果网络或转写较慢，可把 `transcription_wait_ms` 调大到 `1500` 或 `2500`。

## 日志

日志位于 `%LOCALAPPDATA%\FloatingVoiceButton\logs`：

- `运行.log`：启动、退出和关键操作成功记录
- `错误.log`：警告、失败及异常堆栈

两类日志各自最多约 512 KB，并保留一份轮转备份。右键悬浮按钮可直接打开日志目录。

## 开发验证

在项目目录运行：

```powershell
python -m unittest discover -s tests -v
python -m py_compile app.py automation.py logger.py
```
