from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

from overlay import (
    AC_SRC_ALPHA,
    BITMAPINFO,
    BITMAPINFOHEADER,
    BLENDFUNCTION,
    HTTRANSPARENT,
    LRESULT,
    MA_NOACTIVATE,
    SW_SHOWNOACTIVATE,
    ULW_ALPHA,
    WM_CLOSE,
    WM_DESTROY,
    WM_ERASEBKGND,
    WM_MOUSEACTIVATE,
    WM_NCHITTEST,
    WNDCLASSEXW,
    WNDPROC,
    WS_EX_LAYERED,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    WS_EX_TOPMOST,
    WS_POPUP,
    gdi32,
    kernel32,
    premultiplied_bgra,
    user32,
)


WM_APP_UPDATE = 0x8031
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
MONITOR_DEFAULTTONEAREST = 2


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, draw: ImageDraw.ImageDraw, font, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for character in str(text or ""):
        candidate = f"{current}{character}"
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = character
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[-3:] or ["正在聆听…"]


class LiveTranscriptWindow:
    """不抢焦点、点击穿透并锚定悬浮按钮的实时字幕条。"""

    def __init__(
        self,
        anchor_hwnd: int,
        button_size: int,
        on_error: Callable[[Exception], None],
        width: int = 340,
        height: int = 96,
    ) -> None:
        self.anchor_hwnd = int(anchor_hwnd)
        self.button_size = int(button_size)
        self.width = int(width)
        self.height = int(height)
        self.on_error = on_error
        self.hwnd = 0
        self._text = "正在聆听…"
        self._visible = False
        self._state_lock = threading.RLock()
        self._class_name = f"FloatingVoiceTranscript_{os.getpid()}"
        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._owner_thread_id = int(kernel32.GetCurrentThreadId())
        self._create_window()

    def _create_window(self) -> None:
        instance = kernel32.GetModuleHandleW(None)
        window_class = WNDCLASSEXW()
        window_class.cbSize = ctypes.sizeof(WNDCLASSEXW)
        window_class.lpfnWndProc = self._wndproc_ref
        window_class.hInstance = instance
        window_class.lpszClassName = self._class_name
        if not user32.RegisterClassExW(ctypes.byref(window_class)):
            raise ctypes.WinError()
        self.hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            self._class_name,
            "实时识别文字",
            WS_POPUP,
            0,
            0,
            self.width,
            self.height,
            None,
            None,
            instance,
            None,
        )
        if not self.hwnd:
            raise ctypes.WinError()

    def _wnd_proc(self, hwnd, message, wparam, lparam):
        try:
            if message == WM_ERASEBKGND:
                return 1
            if message == WM_MOUSEACTIVATE:
                return MA_NOACTIVATE
            if message == WM_NCHITTEST:
                return HTTRANSPARENT
            if message == WM_APP_UPDATE:
                self._render()
                return 0
            if message == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if message == WM_DESTROY:
                return 0
        except Exception as exc:
            self.on_error(exc)
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _position(self) -> tuple[int, int]:
        anchor = wintypes.RECT()
        if not user32.GetWindowRect(self.anchor_hwnd, ctypes.byref(anchor)):
            return 0, 0
        monitor = user32.MonitorFromWindow(self.anchor_hwnd, MONITOR_DEFAULTTONEAREST)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            work = wintypes.RECT(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
        else:
            work = info.rcWork
        x = round((anchor.left + anchor.right - self.width) / 2)
        y = anchor.top - self.height - 12
        if y < work.top:
            y = anchor.bottom + 12
        x = max(work.left + 8, min(x, work.right - self.width - 8))
        y = max(work.top + 8, min(y, work.bottom - self.height - 8))
        return x, y

    def _image(self, text: str) -> Image.Image:
        scale = 3
        image = Image.new("RGBA", (self.width * scale, self.height * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (2 * scale, 2 * scale, (self.width - 2) * scale, (self.height - 2) * scale),
            radius=16 * scale,
            fill=(17, 24, 39, 238),
            outline=(255, 255, 255, 42),
            width=1 * scale,
        )
        font = _font(14 * scale)
        lines = _wrap_text(text[-180:], draw, font, (self.width - 36) * scale)
        line_height = 22 * scale
        total_height = len(lines) * line_height
        y = (self.height * scale - total_height) // 2
        for line in lines:
            draw.text((18 * scale, y), line, font=font, fill=(255, 255, 255, 255))
            y += line_height
        return image.resize((self.width, self.height), Image.Resampling.LANCZOS)

    def _render(self) -> None:
        with self._state_lock:
            text = self._text
            visible = self._visible
        if not visible:
            user32.ShowWindow(self.hwnd, 0)
            return
        x, y = self._position()
        image = self._image(text)
        pixels = premultiplied_bgra(image)
        screen_dc = user32.GetDC(None)
        memory_dc = gdi32.CreateCompatibleDC(screen_dc)
        bitmap_info = BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = self.width
        bitmap_info.bmiHeader.biHeight = -self.height
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bitmap_info.bmiHeader.biCompression = 0
        bitmap_info.bmiHeader.biSizeImage = len(pixels)
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(
            screen_dc, ctypes.byref(bitmap_info), 0, ctypes.byref(bits), None, 0
        )
        if not bitmap or not bits.value:
            raise ctypes.WinError()
        previous = gdi32.SelectObject(memory_dc, bitmap)
        try:
            ctypes.memmove(bits.value, pixels, len(pixels))
            destination = wintypes.POINT(x, y)
            source = wintypes.POINT(0, 0)
            size = wintypes.SIZE(self.width, self.height)
            blend = BLENDFUNCTION(0, 0, 255, AC_SRC_ALPHA)
            if not user32.UpdateLayeredWindow(
                self.hwnd,
                screen_dc,
                ctypes.byref(destination),
                ctypes.byref(size),
                memory_dc,
                ctypes.byref(source),
                0,
                ctypes.byref(blend),
                ULW_ALPHA,
            ):
                raise ctypes.WinError()
        finally:
            gdi32.SelectObject(memory_dc, previous)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(memory_dc)
            user32.ReleaseDC(None, screen_dc)
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)

    def show(self, text: str = "正在聆听…") -> None:
        with self._state_lock:
            self._text = str(text or "正在聆听…")
            self._visible = True
        user32.PostMessageW(self.hwnd, WM_APP_UPDATE, 0, 0)

    def update(self, text: str) -> None:
        with self._state_lock:
            if not self._visible:
                return
            self._text = str(text or "正在聆听…")
        user32.PostMessageW(self.hwnd, WM_APP_UPDATE, 0, 0)

    def hide(self) -> None:
        with self._state_lock:
            self._visible = False
        user32.PostMessageW(self.hwnd, WM_APP_UPDATE, 0, 0)

    def follow_anchor(self) -> None:
        with self._state_lock:
            visible = self._visible
        if visible:
            user32.PostMessageW(self.hwnd, WM_APP_UPDATE, 0, 0)

    def close(self) -> None:
        if self.hwnd:
            if int(kernel32.GetCurrentThreadId()) == self._owner_thread_id:
                user32.DestroyWindow(self.hwnd)
                self.hwnd = 0
            else:
                user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
