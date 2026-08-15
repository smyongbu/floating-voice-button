import unittest

from PIL import Image

from overlay import (
    button_base_state,
    button_render_color,
    premultiplied_bgra,
    render_standby_layer,
    render_waveform_layer,
    rgb_from_hex,
    tint_button_image,
)


class OverlayTests(unittest.TestCase):
    def test_standby_is_gray_and_active_states_keep_configured_color(self):
        configured = "#2563EB"
        self.assertEqual(button_render_color("standby", configured), "#8A94A6")
        for state in ("idle", "busy", "recording"):
            with self.subTest(state=state):
                self.assertEqual(button_render_color(state, configured), configured)

    def test_standby_uses_plain_recording_base(self):
        self.assertEqual(button_base_state("standby"), "recording")
        self.assertEqual(button_base_state("idle"), "idle")

    def test_premultiplied_bgra_has_zero_rgb_for_transparent_pixel(self):
        image = Image.new("RGBA", (1, 1), (200, 100, 50, 0))
        self.assertEqual(premultiplied_bgra(image), bytes((0, 0, 0, 0)))

    def test_premultiplied_channels_do_not_exceed_alpha(self):
        image = Image.new("RGBA", (1, 1), (255, 128, 64, 128))
        blue, green, red, alpha = premultiplied_bgra(image)
        self.assertLessEqual(max(blue, green, red), alpha)
        self.assertEqual(alpha, 128)

    def test_recording_red_is_tinted_to_configured_blue(self):
        image = Image.new("RGBA", (2, 1))
        image.putdata([(230, 35, 45, 210), (255, 255, 255, 180)])
        tinted = tint_button_image(image, "#2563EB")
        colored, white = tinted.getpixel((0, 0)), tinted.getpixel((1, 0))
        self.assertGreater(colored[2], colored[0])
        self.assertEqual(colored[3], 210)
        self.assertEqual(white, (255, 255, 255, 180))

    def test_hex_color_accepts_hash(self):
        self.assertEqual(rgb_from_hex("#12ABEF"), (0x12, 0xAB, 0xEF))

    def test_recording_bars_are_thin_and_visibly_separated_at_all_sizes(self):
        for size in (64, 72, 96):
            with self.subTest(size=size):
                layer = render_waveform_layer(size, [1.0] * 7)
                occupied = [layer.getpixel((x, size // 2))[3] >= 128 for x in range(size)]
                segments: list[tuple[int, int]] = []
                start: int | None = None
                for index, value in enumerate(occupied + [False]):
                    if value and start is None:
                        start = index
                    elif not value and start is not None:
                        segments.append((start, index - 1))
                        start = None
                widths = [end - start + 1 for start, end in segments]
                gaps = [segments[index + 1][0] - segments[index][1] - 1 for index in range(6)]
                self.assertEqual(len(segments), 7)
                self.assertLessEqual(max(widths), 4)
                self.assertGreaterEqual(min(gaps), 2)

    def test_standby_layer_is_flat_in_silence_and_moves_with_audio(self):
        silent = render_standby_layer(72, [0.0] * 7)
        active = render_standby_layer(72, [0.0, 0.1, 0.3, 1.0, 0.3, 0.1, 0.0])

        def bar_heights(image):
            return [
                sum(image.getpixel((x, y))[3] >= 128 for y in range(72))
                for x in (18, 24, 30, 36, 42, 48, 54)
            ]

        silent_heights = bar_heights(silent)
        active_heights = bar_heights(active)
        self.assertEqual(len(set(silent_heights)), 1)
        self.assertGreater(active_heights[3], active_heights[0])
        self.assertNotEqual(silent.tobytes(), active.tobytes())


if __name__ == "__main__":
    unittest.main()
