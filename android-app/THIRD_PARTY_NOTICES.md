# Android 第三方软件与模型说明

## whisper.cpp

- 项目：`ggml-org/whisper.cpp`
- 固定版本：`v1.9.2`
- 固定提交：`306c88f4d1286aec1bf96e544632897886af5501`
- 来源：<https://github.com/ggml-org/whisper.cpp>
- 许可证：MIT
- 使用范围：构建时下载并编译为 Android arm64 JNI 识别运行库。

```text
MIT License

Copyright (c) 2023-2026 The ggml authors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## FUTO Whisper ACFT Multilingual-74

- 模型：`base_acft_q8_0.bin`（Multilingual-74）
- 模型来源与许可：<https://huggingface.co/futo-org/acft-whisper-base>
- 模型许可证：Apache-2.0（<https://huggingface.co/futo-org/acft-whisper-base/blob/main/LICENSE>）
- ACFT 方法与训练代码：<https://github.com/futo-org/whisper-acft>（MIT）
- 校验：81,768,602 字节，SHA-256 `e44f352c9aa2c3609dece20c733c4ad4a75c28cd9ab07d005383df55fa96efc4`
- 使用范围：用户按需下载到 App 私有资源目录；模型文件不进入 Git 或 APK。

本项目只调用上述独立运行库和模型，未复制 FUTO Voice Input 或 FUTO Keyboard 的 App 源码。
