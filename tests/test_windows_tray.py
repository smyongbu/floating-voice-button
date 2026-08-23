import ctypes
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import windows_tray


class WindowsTrayTests(unittest.TestCase):
    def test_load_icon_uses_ico_file_and_windows_icon_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            icon = Path(directory) / "语点.ico"
            icon.write_bytes(b"ico")
            with patch.object(windows_tray.user32, "LoadImageW", return_value=123) as load:
                self.assertEqual(windows_tray.load_icon(icon), 123)
        load.assert_called_once_with(
            None,
            str(icon),
            windows_tray.IMAGE_ICON,
            0,
            0,
            windows_tray.LR_LOADFROMFILE | windows_tray.LR_DEFAULTSIZE,
        )

    def test_notification_icon_adds_and_removes_same_icon(self):
        calls = []

        def notify(action, pointer):
            data = ctypes.cast(
                pointer,
                ctypes.POINTER(windows_tray.NOTIFYICONDATAW),
            ).contents
            calls.append((action, int(data.hWnd), int(data.hIcon), data.szTip))
            return True

        with (
            patch.object(windows_tray.user32, "RegisterWindowMessageW", return_value=99),
            patch.object(windows_tray.shell32, "Shell_NotifyIconW", side_effect=notify),
        ):
            icon = windows_tray.NotificationAreaIcon(88, 77, "语点")
            self.assertTrue(icon.is_taskbar_created(99))
            icon.remove()
            icon.remove()
        self.assertEqual(
            calls,
            [
                (windows_tray.NIM_ADD, 88, 77, "语点"),
                (windows_tray.NIM_DELETE, 88, 77, "语点"),
            ],
        )

    def test_restore_recreates_icon_after_explorer_restart(self):
        with (
            patch.object(windows_tray.user32, "RegisterWindowMessageW", return_value=99),
            patch.object(windows_tray.shell32, "Shell_NotifyIconW", return_value=True) as notify,
        ):
            icon = windows_tray.NotificationAreaIcon(88, 77, "语点")
            icon.restore()
            icon.remove()
        self.assertEqual(notify.call_count, 3)


if __name__ == "__main__":
    unittest.main()
