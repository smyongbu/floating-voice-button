import unittest
from pathlib import Path

from PIL import Image


class AssetTests(unittest.TestCase):
    def test_button_assets_are_square_rgba_images(self):
        asset_dir = Path(__file__).resolve().parents[1] / "assets"
        for name in ("idle", "hover", "recording", "busy"):
            with Image.open(asset_dir / f"button_{name}.png") as image:
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.size[0], image.size[1])
                self.assertEqual(image.size, (288, 288))
                self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_button_has_no_white_outer_ring(self):
        asset_dir = Path(__file__).resolve().parents[1] / "assets"
        for name in ("idle", "hover", "recording", "busy"):
            with Image.open(asset_dir / f"button_{name}.png").convert("RGBA") as image:
                for y in range(288):
                    for x in range(288):
                        if ((x - 144) ** 2 + (y - 144) ** 2) ** 0.5 < 116:
                            continue
                        red, green, blue, alpha = image.getpixel((x, y))
                        self.assertFalse(
                            alpha >= 96 and min(red, green, blue) >= 175,
                            f"{name} 在外圈仍有白色像素 ({x},{y})",
                        )


if __name__ == "__main__":
    unittest.main()
