"""从 Windows 正式绘制函数导出首页动图；仅使用模拟音量，不启动窗口或麦克风。

在项目环境运行：python docs/media/render_floating_ball.py
可选 --font 指定支持中文的字体。输出仅为文档资源，不进入应用。
"""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from overlay import (  # noqa: E402
    SHAPE_TRANSITION_DURATION_SECONDS,
    _smoothstep,
    render_deep_button_base,
    render_waveform_layer,
)

SIZE = (800, 320)
BALL_SIZE = 176
FPS = 25
SECONDS = 6.8
STAGES = (
    ("点一下，开始说话", "悬浮在手边，随时开始录音", "待机圆环"),
    ("边说话，边显示文字", "录音时，光带随声音起伏", "录音声波"),
    ("再点一下，完成输入", "Windows 可将最终文字自动输入原软件", "停止收回"),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path,
                        default=Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc")
    args = parser.parse_args()
    fonts = {size: ImageFont.truetype(str(args.font), size) for size in (15, 17, 19, 30)}
    base = render_deep_button_base(BALL_SIZE, "#103E83")

    def frame(t: float, stage_override: int | None = None) -> Image.Image:
        stage = 0 if t < 1.4 else 1 if t < 4.8 else 2
        if stage_override is not None:
            stage = stage_override
        mix = (_smoothstep(min(1, max(0, (t - 1.4) / SHAPE_TRANSITION_DURATION_SECONDS)))
               if t < 4.8 else 1 - _smoothstep(min(1, (t - 4.8) / SHAPE_TRANSITION_DURATION_SECONDS)))
        levels = [(.18 + .65 * math.sin(t * 3.1 + i * .45) ** 2) for i in range(7)]
        # 模拟信号仅用于文档展示；正式应用读取真实麦克风音量。
        sphere = Image.alpha_composite(base, render_waveform_layer(BALL_SIZE, levels, t * 5, mix))
        img = Image.new("RGB", SIZE, "#F3F6FB")
        draw = ImageDraw.Draw(img)
        draw.text((32, 25), "语点 · 悬浮球语音输入", font=fonts[19], fill="#1455B8")
        draw.text((32, 100), STAGES[stage][0], font=fonts[30], fill="#14233D")
        draw.text((32, 153), STAGES[stage][1], font=fonts[17], fill="#53627A")
        draw.text((32, 200), "Windows 动画演示 · 模拟音量 · 球体放大展示", font=fonts[15], fill="#66758C")
        img.paste(sphere, (580, 55), sphere)
        draw.line((32, 257, 768, 257), fill="#D8E1EE", width=1)
        for i, (_, _, label) in enumerate(STAGES):
            x = 36 + i * 250
            color = "#1455B8" if i == stage else "#68768B"
            draw.text((x, 278), f"{i + 1}  {label}", font=fonts[17], fill=color)
        return img

    frames = [frame(i / FPS) for i in range(round(SECONDS * FPS))]
    # 全局调色板避免逐帧重新量化造成球体色阶闪烁。
    samples = [frames[i] for i in (0, 40, 65, 90, 120, 145)]
    atlas = Image.new("RGB", (SIZE[0], SIZE[1] * len(samples)))
    for i, sample in enumerate(samples):
        atlas.paste(sample, (0, i * SIZE[1]))
    palette = atlas.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    indexed = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    output = ROOT / "docs/screenshots"
    output.mkdir(parents=True, exist_ok=True)
    indexed[0].save(output / "floating-ball-demo.gif", save_all=True,
                    append_images=indexed[1:], duration=1000 // FPS, loop=1,
                    optimize=True, disposal=1)
    # 静态版覆盖三种状态，便于不想观看动态效果的读者查看。
    poster = Image.new("RGB", (SIZE[0], SIZE[1] * 3))
    for i, t in enumerate((0, 3, 6)):
        poster.paste(frame(t, i), (0, SIZE[1] * i))
    poster.save(output / "floating-ball-states.png", optimize=True)
    print("已导出悬浮球动图与三状态静态图。")


if __name__ == "__main__":
    main()
