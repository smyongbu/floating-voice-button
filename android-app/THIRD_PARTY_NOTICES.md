# Android 第三方软件与模型说明

本文件记录 Android App 实际使用的识别运行库和五套按需下载模型。模型不进入 Git 或 APK；精确字节数和 SHA-256 与 `app/src/main/assets/model-resources.json` 保持一致。

## sherpa-onnx

- 项目：`k2-fsa/sherpa-onnx`
- 固定版本：`v1.13.5`
- 来源：<https://github.com/k2-fsa/sherpa-onnx/tree/v1.13.5>
- 许可证：Apache-2.0（<https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.5/LICENSE>）
- 使用范围：Android arm64 运行 Streaming Paraformer、Zipformer 和 Qwen3-ASR 0.6B INT8。

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

## 中英双语 Zipformer

- 资源编号：`zipformer-bilingual`
- 来源：<https://huggingface.co/csukuangfj/k2fsa-zipformer-bilingual-zh-en-t/tree/8a7306b4d4d40c3cb1bdb80e8f2f605167570af3>
- 固定版本：`8a7306b4d4d40c3cb1bdb80e8f2f605167570af3`
- 许可证：Apache-2.0
- 合计：60,142,871 字节
- 文件校验：
  - `encoder-epoch-99-avg-1.int8.onnx`：42,980,793 字节；SHA-256 `db6f51551762e40e549166fe041ea3e45464370b595e9ad23f06478ec3794fbb`
  - `decoder-epoch-99-avg-1.onnx`：13,877,276 字节；SHA-256 `89be509a83175261695bdef5fd1c7b9ab1129a663d1284e7ba9f8507b21e0906`
  - `joiner-epoch-99-avg-1.int8.onnx`：3,228,485 字节；SHA-256 `bdda356d6f9b8c2d7cee9ee0e26075fa537490f7fd06520be408d287073667b9`
  - `tokens.txt`：56,317 字节；SHA-256 `a8e0e4ec53810e433789b54a5c0134a7eaa2ffca595a6334d54c00da858841d3`

## Faster-Whisper Small（GGUF Q8_0）

- 资源编号：`faster-whisper-small-gguf-q8-0`
- 模型文件：`whisper-small-Q8_0.gguf`
- 来源：<https://huggingface.co/handy-computer/whisper-small-gguf/tree/c0214bd34be9296695486f838e0142f900803159>
- 固定版本：`c0214bd34be9296695486f838e0142f900803159`
- 许可证：Apache-2.0
- 校验：269,751,136 字节；SHA-256 `9b9c8811bbcc82a7766f0fb0925614bdacb0923b2cc630daeac17108b655b860`
- 说明：界面沿用 Faster-Whisper Small 名称；Android 实际使用同一 Whisper Small 的 `transcribe.cpp` GGUF Q8_0 格式。

## Qwen3-ASR 0.6B INT8

- 资源编号：`qwen3-asr-0.6b-int8`
- 来源：<https://huggingface.co/csukuangfj2/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25/tree/68818b2313fe77bd06f6a7c5068ff3ef59d02b8a>
- 固定版本：`68818b2313fe77bd06f6a7c5068ff3ef59d02b8a`
- 许可证：Apache-2.0
- 合计：987,015,347 字节
- 文件校验：
  - `conv_frontend.onnx`：44,148,281 字节；SHA-256 `d22dc4423e0940e49884e903d2ea2f7e5567c14fc1aed97e4e26d6b8f208ef9e`
  - `encoder.int8.onnx`：182,491,662 字节；SHA-256 `60748d3e6744a57c9c91e1b17424a6c2990567e8adceb0783940c03ed98fa9d9`
  - `decoder.int8.onnx`：755,914,231 字节；SHA-256 `4f6885be5959ae26af3089d38ee7972c5fafbeeb1cf8d5e76eab6d8b61ca5771`
  - `tokenizer/merges.txt`：1,671,853 字节；SHA-256 `8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5`
  - `tokenizer/tokenizer_config.json`：12,487 字节；SHA-256 `4942d005604266809309cabc9f4e9cb89ce855d59b14681fdc0e1cc62ea26c4c`
  - `tokenizer/vocab.json`：2,776,833 字节；SHA-256 `ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910`

## Qwen3-ASR 1.7B Q5_K_M

- 资源编号：`qwen3-asr-1.7b-gguf-q5-k-m`
- 模型文件：`Qwen3-ASR-1.7B-Q5_K_M.gguf`
- 来源：<https://huggingface.co/handy-computer/Qwen3-ASR-1.7B-gguf/tree/92282af1610a2db19d66f2bef1e260f5deca782d>
- 固定版本：`92282af1610a2db19d66f2bef1e260f5deca782d`
- 许可证：Apache-2.0
- 校验：1,517,290,464 字节；SHA-256 `034c557fe92ff8fcd9a9c041cbdaad347be0a86a58d3a348f63cf3f0180879d0`
- 使用范围：由 `transcribe.cpp` 读取，在停止收音后生成最终文字。

五套模型合计 3,071,402,319 字节（约 2.86 GiB），均由用户按需下载或经 ADB 按哈希增量同步到 App 私有资源目录。
