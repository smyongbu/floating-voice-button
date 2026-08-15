import unittest
import ctypes
from unittest.mock import patch

import automation


class AutomationTests(unittest.TestCase):
    def test_missing_foreground_window_returns_zero(self):
        with patch.object(automation.user32, "GetForegroundWindow", return_value=None):
            self.assertEqual(automation.foreground_window(), 0)

    def test_clipboard_writer_uses_valid_owner_window(self):
        buffer = ctypes.create_string_buffer(128)
        with (
            patch.object(automation.user32, "IsWindow", return_value=True),
            patch.object(automation.user32, "OpenClipboard", return_value=True) as open_clipboard,
            patch.object(automation.user32, "EmptyClipboard", return_value=True),
            patch.object(automation.user32, "SetClipboardData", return_value=123),
            patch.object(automation.user32, "CloseClipboard", return_value=True),
            patch.object(automation.kernel32, "GlobalAlloc", return_value=123),
            patch.object(automation.kernel32, "GlobalLock", return_value=ctypes.addressof(buffer)),
            patch.object(automation.kernel32, "GlobalUnlock", return_value=True),
        ):
            self.assertTrue(automation.write_clipboard_text("历史文字", 456))
        open_clipboard.assert_called_once_with(456)

    def test_clipboard_writer_rejects_missing_owner_without_clearing(self):
        with (
            patch.object(automation.user32, "IsWindow", return_value=False),
            patch.object(automation.user32, "EmptyClipboard") as empty_clipboard,
        ):
            with self.assertRaises(ValueError):
                automation.write_clipboard_text("不能丢失的文字", 0)
        empty_clipboard.assert_not_called()


if __name__ == "__main__":
    unittest.main()
