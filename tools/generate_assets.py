from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets"
SIZE = 72
SCALE = 4


def s(value: float) -> int:
    return round(value * SCALE)


def render_button(color: str, icon: str) -> Image.Image:
    """用高分辨率几何路径绘制，再缩小获得稳定的抗锯齿边缘。"""
    image = Image.new("RGBA", (SIZE * SCALE, SIZE * SCALE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse(
        (s(4), s(4), s(68), s(68)),
        fill=color,
    )
    white = (255, 255, 255, 255)
    if icon == "mic":
        draw.rounded_rectangle((s(30), s(20), s(42), s(42)), radius=s(6), outline=white, width=s(2))
        draw.arc((s(25), s(29), s(47), s(50)), 0, 180, fill=white, width=s(2))
        draw.line((s(36), s(49), s(36), s(56)), fill=white, width=s(2))
        draw.line((s(30), s(56), s(42), s(56)), fill=white, width=s(2))
    elif icon == "stop":
        draw.rounded_rectangle((s(27), s(27), s(45), s(45)), radius=s(3), fill=white)
    elif icon == "busy":
        for x in (27, 36, 45):
            draw.ellipse((s(x - 2.5), s(33.5), s(x + 2.5), s(38.5)), fill=white)
    # 保存 4 倍母版，运行时只做一次高质量缩小，64/72/96 像素都不会被放大变糊。
    return image


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    variants = {
        "idle": ("#2563EB", "mic"),
        "hover": ("#3B82F6", "mic"),
        "recording": ("#2563EB", "none"),
        "busy": ("#2563EB", "busy"),
    }
    for name, (color, icon) in variants.items():
        result = render_button(color, icon)
        result.putpixel((0, 0), (0, 0, 0, 0))
        result.save(OUTPUT / f"button_{name}.png", optimize=True)


if __name__ == "__main__":
    main()
