import unittest

import app


class ConfigTests(unittest.TestCase):
    def test_default_timing_is_non_negative(self):
        for key in ("transcription_wait_ms", "copy_wait_ms", "paste_wait_ms"):
            self.assertGreaterEqual(app.DEFAULT_CONFIG[key], 0)

    def test_button_size_is_in_supported_range(self):
        self.assertGreaterEqual(app.DEFAULT_CONFIG["button_size"], 48)
        self.assertLessEqual(app.DEFAULT_CONFIG["button_size"], 96)


if __name__ == "__main__":
    unittest.main()

