import ctypes
import threading
import unittest
from ctypes import wintypes
from unittest.mock import Mock, call, patch

from PIL import Image

import live_transcript
from live_transcript import HGDI_ERROR, LiveTranscriptWindow, MONITORINFO


class LiveTranscriptWindowTests(unittest.TestCase):
    def _window(self) -> LiveTranscriptWindow:
        window = LiveTranscriptWindow.__new__(LiveTranscriptWindow)
        window.hwnd = 91
        window.width = 1
        window.height = 1
        window._text = "测试"
        window._visible = True
        window._state_lock = threading.RLock()
        window._position = Mock(return_value=(12, 34))
        window._image = Mock(return_value=Image.new("RGBA", (1, 1)))
        return window

    def _render_with_failure(self, failure: str):
        window = self._window()
        with (
            patch.object(live_transcript, "user32") as user32,
            patch.object(live_transcript, "gdi32") as gdi32,
            patch.object(live_transcript, "premultiplied_bgra", return_value=b"\0" * 4),
            patch.object(live_transcript.ctypes, "memmove"),
        ):
            user32.GetDC.return_value = 101
            gdi32.CreateCompatibleDC.return_value = 202

            def create_dib_section(_dc, _info, _usage, bits, _section, _offset):
                if failure != "dib_without_bits":
                    bits._obj.value = 0x1000
                return 303

            gdi32.CreateDIBSection.side_effect = create_dib_section
            gdi32.SelectObject.return_value = 404
            user32.UpdateLayeredWindow.return_value = True

            if failure == "get_dc":
                user32.GetDC.return_value = 0
            elif failure == "compatible_dc":
                gdi32.CreateCompatibleDC.return_value = 0
            elif failure == "dib":
                gdi32.CreateDIBSection.return_value = 0
                gdi32.CreateDIBSection.side_effect = None
            elif failure == "select":
                gdi32.SelectObject.return_value = 0
            elif failure == "select_hgdi_error":
                gdi32.SelectObject.return_value = HGDI_ERROR
            elif failure == "update":
                user32.UpdateLayeredWindow.return_value = False

            with self.assertRaises(OSError):
                window._render()

            return user32, gdi32

    def test_pointer_and_handle_win32_prototypes_are_explicit(self):
        self.assertEqual(
            live_transcript.user32.MonitorFromWindow.argtypes,
            [wintypes.HWND, wintypes.DWORD],
        )
        self.assertIs(live_transcript.user32.MonitorFromWindow.restype, wintypes.HMONITOR)
        self.assertEqual(live_transcript.user32.GetMonitorInfoW.argtypes[0], wintypes.HMONITOR)
        monitor_info_pointer = live_transcript.user32.GetMonitorInfoW.argtypes[1]
        self.assertIs(monitor_info_pointer._type_, MONITORINFO)
        self.assertEqual(
            live_transcript.user32.ShowWindow.argtypes,
            [wintypes.HWND, ctypes.c_int],
        )
        self.assertIs(live_transcript.user32.ShowWindow.restype, wintypes.BOOL)

    def test_get_dc_failure_has_nothing_to_release(self):
        user32, gdi32 = self._render_with_failure("get_dc")
        gdi32.CreateCompatibleDC.assert_not_called()
        gdi32.DeleteObject.assert_not_called()
        gdi32.DeleteDC.assert_not_called()
        user32.ReleaseDC.assert_not_called()

    def test_compatible_dc_failure_releases_screen_dc(self):
        user32, gdi32 = self._render_with_failure("compatible_dc")
        gdi32.DeleteObject.assert_not_called()
        gdi32.DeleteDC.assert_not_called()
        user32.ReleaseDC.assert_called_once_with(None, 101)

    def test_dib_failure_releases_both_dcs(self):
        user32, gdi32 = self._render_with_failure("dib")
        gdi32.DeleteObject.assert_not_called()
        gdi32.DeleteDC.assert_called_once_with(202)
        user32.ReleaseDC.assert_called_once_with(None, 101)

    def test_dib_without_bits_deletes_returned_bitmap_and_releases_dcs(self):
        user32, gdi32 = self._render_with_failure("dib_without_bits")
        gdi32.DeleteObject.assert_called_once_with(303)
        gdi32.DeleteDC.assert_called_once_with(202)
        user32.ReleaseDC.assert_called_once_with(None, 101)

    def test_select_failure_deletes_bitmap_and_releases_dcs_without_restore(self):
        for failure in ("select", "select_hgdi_error"):
            with self.subTest(failure=failure):
                user32, gdi32 = self._render_with_failure(failure)
                gdi32.SelectObject.assert_called_once_with(202, 303)
                gdi32.DeleteObject.assert_called_once_with(303)
                gdi32.DeleteDC.assert_called_once_with(202)
                user32.ReleaseDC.assert_called_once_with(None, 101)

    def test_update_failure_restores_selection_before_releasing_resources(self):
        user32, gdi32 = self._render_with_failure("update")
        self.assertEqual(gdi32.SelectObject.call_args_list, [call(202, 303), call(202, 404)])
        gdi32.DeleteObject.assert_called_once_with(303)
        gdi32.DeleteDC.assert_called_once_with(202)
        user32.ReleaseDC.assert_called_once_with(None, 101)
        user32.ShowWindow.assert_not_called()


if __name__ == "__main__":
    unittest.main()
