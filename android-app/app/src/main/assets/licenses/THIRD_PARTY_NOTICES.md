# Android 第三方软件与模型说明

本文件记录 Android App 实际使用的识别运行库和三套模型。本次自带模型版本将三套资源内置于 APK；权重通过 GitHub 资源附件分发，不进入源码 Git 历史。精确字节数和 SHA-256 与 `app/src/main/assets/model-resources.json` 保持一致。

## sherpa-onnx

- 项目：`k2-fsa/sherpa-onnx`
- 固定版本：`v1.13.5`
- 来源：<https://github.com/k2-fsa/sherpa-onnx/tree/v1.13.5>
- 许可证：Apache-2.0（<https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.5/LICENSE>）
- 使用范围：Android arm64 运行 Streaming Paraformer。

## transcribe.cpp

- 项目：`handy-computer/transcribe.cpp`
- 固定提交：`ea077b87590bcfb090d7c38c03ab36cd1c7005d3`
- 固定源码归档 SHA-256：`577826a626c85bd07e40efada8f9578bc2689132f14ad41b71ee496d9a9711d8`
- 来源：<https://github.com/handy-computer/transcribe.cpp/tree/ea077b87590bcfb090d7c38c03ab36cd1c7005d3>
- 许可证：MIT
- 使用范围：构建 Android arm64 JNI 运行库，读取 Faster-Whisper Small 与 Qwen3-ASR 1.7B 的 GGUF 模型。

```text
MIT License

Copyright (c) 2026 The transcribe.cpp authors

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

## Streaming Paraformer INT8

- 资源编号：`streaming-paraformer-bilingual-zh-en`
- 来源：<https://huggingface.co/csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en/tree/8e40c43232a1c5c66c82111efc5820d3accca11b>
- 固定版本：`8e40c43232a1c5c66c82111efc5820d3accca11b`
- 许可证：Apache-2.0
- 合计：237,202,501 字节
- 文件校验：
  - `encoder.int8.onnx`：165,462,184 字节；SHA-256 `81a70226a8934e6ed92aa1d4fc486b428b5398e2f2619ed4897b7294cab90e9a`
  - `decoder.int8.onnx`：71,664,561 字节；SHA-256 `f3cca9f77bb9d93c8fcbfb63ae617b6b1ee96818df3aa3b151c40658fe38594f`
  - `tokens.txt`：75,756 字节；SHA-256 `59aba8873a2ed1e122c25fee421e25f283b63290efbde85c1f01a853d83cb6e6`

## Faster-Whisper Small（GGUF Q8_0）

- 资源编号：`faster-whisper-small-gguf-q8-0`
- 模型文件：`whisper-small-Q8_0.gguf`
- 来源：<https://huggingface.co/handy-computer/whisper-small-gguf/tree/c0214bd34be9296695486f838e0142f900803159>
- 固定版本：`c0214bd34be9296695486f838e0142f900803159`
- 许可证：Apache-2.0
- 校验：269,751,136 字节；SHA-256 `9b9c8811bbcc82a7766f0fb0925614bdacb0923b2cc630daeac17108b655b860`
- 说明：界面沿用 Faster-Whisper Small 名称；Android 实际使用同一 Whisper Small 的 `transcribe.cpp` GGUF Q8_0 格式。

## Qwen3-ASR 1.7B Q5_K_M

- 资源编号：`qwen3-asr-1.7b-gguf-q5-k-m`
- 模型文件：`Qwen3-ASR-1.7B-Q5_K_M.gguf`
- 来源：<https://huggingface.co/handy-computer/Qwen3-ASR-1.7B-gguf/tree/92282af1610a2db19d66f2bef1e260f5deca782d>
- 固定版本：`92282af1610a2db19d66f2bef1e260f5deca782d`
- 许可证：Apache-2.0
- 校验：1,517,290,464 字节；SHA-256 `034c557fe92ff8fcd9a9c041cbdaad347be0a86a58d3a348f63cf3f0180879d0`
- 使用范围：由 `transcribe.cpp` 读取，在停止收音后生成最终文字。

三套模型合计 2,024,244,101 字节（约 1.89 GiB）。自带模型版首次启动从 APK 本地安装至 App 私有资源目录，轻量版保留按需下载或 ADB 增量同步方式。Apache-2.0 完整文本随包保存在 `Apache-2.0.txt`。


## Whisper 上游许可

Whisper Small 来自 OpenAI Whisper。GGUF 发布页标注 Apache-2.0，原始 Whisper 上游许可证为 MIT；保留上游 Copyright (c) 2022 OpenAI 及完整许可文本，随包保存在 `OpenAI-Whisper-MIT.txt`。官方来源：https://github.com/openai/whisper/blob/main/LICENSE 。
