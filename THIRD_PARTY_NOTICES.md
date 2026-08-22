# 第三方软件声明

## Qwen3-ASR 1.7B Q5_K_M 模型

- 上游模型：https://huggingface.co/Qwen/Qwen3-ASR-1.7B
- 上游固定提交：`7278e1e70fe206f11671096ffdd38061171dd6e5`
- GGUF 来源：https://huggingface.co/handy-computer/Qwen3-ASR-1.7B-gguf
- GGUF 固定提交：`92282af1610a2db19d66f2bef1e260f5deca782d`
- 文件：`Qwen3-ASR-1.7B-Q5_K_M.gguf`
- 用途：用户在 Windows 设置页选择相关功能时直接从原始模型仓库按需下载；不进入 Git、源码包或安装包。
- 许可：Apache License 2.0。模型文件保留上游 GGUF 元数据；完整许可文本见 https://www.apache.org/licenses/LICENSE-2.0 。

## transcribe.cpp 0.2.1

- 来源：https://github.com/handy-computer/transcribe.cpp
- 固定提交：`ea077b87590bcfb090d7c38c03ab36cd1c7005d3`
- 用途：通过官方 `transcribe-cpp` / `transcribe-cpp-native` Windows 轮子加载 Qwen3-ASR 1.7B GGUF，并使用 CPU 或 Vulkan 后端执行离线转写。
- 许可：MIT License。官方原生轮子同时携带其内置 ggml 与 miniz 的原始 MIT 许可文本。

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

## ggml

- 来源：随 transcribe-cpp-native 0.2.1 提供的 ggml 运行库
- 用途：CPU 与 Vulkan 张量计算后端
- 许可：MIT License

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

## miniz

- 来源：随 transcribe-cpp-native 0.2.1 提供的 miniz
- 用途：运行库内部压缩数据处理
- 许可：MIT License

Copyright 2013-2014 RAD Game Tools and Valve Software
Copyright 2010-2014 Rich Geldreich and Tenacious Software LLC

All Rights Reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
