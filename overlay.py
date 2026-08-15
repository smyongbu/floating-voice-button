from __future__ import annotations

import ctypes
import colorsys
import os
import threading
from ctypes import wintypes
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

from global_hotkey import parse_hotkey


LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", wintypes.BYTE),
        ("BlendFlags", wintypes.BYTE),
        ("SourceConstantAlpha", wintypes.BYTE),
        ("AlphaFormat", wintypes.BYTE),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
        ("lPrivate", wintypes.DWORD),
    ]


user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE),
    wintypes.HDC, ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
    ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD,
]
user32.UpdateLayeredWindow.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.SetCapture.argtypes = [wintypes.HWND]
user32.SetCapture.restype = wintypes.HWND
user32.ReleaseCapture.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL


WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WS_POPUP = 0x80000000
SW_SHOWNOACTIVATE = 4
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_ERASEBKGND = 0x0014
WM_MOUSEACTIVATE = 0x0021
WM_NCHITTEST = 0x0084
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200
WM_RBUTTONUP = 0x0205
WM_HOTKEY = 0x0312
WM_APP_RENDER = 0x8001
WM_APP_HOTKEY_UPDATE = 0x8002
MA_NOACTIVATE = 3
HTCLIENT = 1
HTTRANSPARENT = -1
MK_LBUTTON = 0x0001
ULW_ALPHA = 0x00000002
AC_SRC_ALPHA = 0x01
MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100


def premultiplied_bgra(image: Image.Image) -> bytes:
    rgba = image.convert("RGBA").tobytes()
    result = bytearray(len(rgba))
    for index in range(0, len(rgba), 4):
        red, green, blue, alpha = rgba[index:index + 4]
        result[index] = blue * alpha // 255
        result[index + 1] = green * alpha // 255
        result[index + 2] = red * alpha // 255
        result[index + 3] = alpha
    return bytes(result)


def rgb_from_hex(value: str) -> tuple[int, int, int]:
    text = str(value).strip().lstrip("#")
    if len(text) != 6:
        raise ValueError("按钮颜色必须是六位十六进制颜色。")
    try:
        return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))
    except ValueError as exc:
        raise ValueError("按钮颜色必须是六位十六进制颜色。") from exc


def tint_button_image(image: Image.Image, color: str) -> Image.Image:
    """只替换按钮的彩色区域，保留白色图标、描边和逐像素 Alpha。"""
    target_red, target_green, target_blue = rgb_from_hex(color)
    target_hue, target_saturation, target_value = colorsys.rgb_to_hsv(
        target_red / 255, target_green / 255, target_blue / 255
    )
    tinted = image.convert("RGBA")
    pixels = bytearray(tinted.tobytes())
    for index in range(0, len(pixels), 4):
        red, green, blue, alpha = pixels[index:index + 4]
        maximum = max(red, green, blue)
        minimum = min(red, green, blue)
        saturation = 0.0 if maximum == 0 else (maximum - minimum) / maximum
        if alpha and saturation >= 0.16 and maximum >= 35:
            _hue, _saturation, value = colorsys.rgb_to_hsv(
                red / 255, green / 255, blue / 255
            )
            new_value = max(0.0, min(1.0, target_value * (0.78 + value * 0.26)))
            new_red, new_green, new_blue = colorsys.hsv_to_rgb(
                target_hue, target_saturation, new_value
            )
            pixels[index] = round(new_red * 255)
            pixels[index + 1] = round(new_green * 255)
            pixels[index + 2] = round(new_blue * 255)
    return Image.frombytes("RGBA", tinted.size, bytes(pixels))


def render_waveform_layer(size: int, levels: list[float]) -> Image.Image:
    """在 4 倍分辨率绘制彼此分离的细波形柱，再缩小获得平滑边缘。"""
    oversample = 4
    canvas_size = size * oversample
    layer = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    scale = size / 72 * oversample
    centers = (18, 24, 30, 36, 42, 48, 54)
    normalized = [max(0.0, min(1.0, float(value))) for value in levels[-7:]]
    if len(normalized) < 7:
        normalized = [0.08] * (7 - len(normalized)) + normalized
    center_y = canvas_size / 2
    half_width = 0.9 * scale
    for center, level in zip(centers, normalized):
        height = (5 + level * 23) * scale
        center_x = center * scale
        draw.rounded_rectangle(
            (
                center_x - half_width,
                center_y - height / 2,
                center_x + half_width,
                center_y + height / 2,
            ),
            radius=half_width,
            fill=(255, 255, 255, 255),
        )
    return layer.resize((size, size), Image.Resampling.LANCZOS)


def render_standby_layer(
    size: int, levels: list[float] | None = None
) -> Image.Image:
    """绘制待命波形：安静时等高，说话时跟随收音变化。"""
    return render_waveform_layer(size, [0.0] * 7 if levels is None else levels)


def button_base_state(state: str) -> str:
    """待命与录音共用无图案底图，避免麦克风和波形叠在一起。"""
    return "recording" if state == "standby" else state


def button_render_color(state: str, configured_color: str) -> str:
    """待命使用中性灰，开始录音后恢复用户设置的主题色。"""
    return "#8A94A6" if state == "standby" else configured_color


class LayeredButtonWindow:
    def __init__(
        self,
        title: str,
        size: int,
        x: int,
        y: int,
        images: dict[str, Path],
        on_click: Callable[[], None],
        on_move: Callable[[int, int], None],
        on_open_panel: Callable[[], None],
        on_open_logs: Callable[[], None],
        on_close: Callable[[], None],
        on_error: Callable[[Exception], None],
        hotkey: str = "Ctrl+Alt+Space",
        button_color: str = "#2563EB",
        button_opacity: int = 100,
    ) -> None:
        self.title = title
        self.size = size
        self.x = x
        self.y = y
        self.images = {name: Image.open(path).convert("RGBA") for name, path in images.items()}
        self.on_click = on_click
        self.on_move = on_move
        self.on_open_panel = on_open_panel
        self.on_open_logs = on_open_logs
        self.on_close = on_close
        self.on_error = on_error
        self.hotkey_label = ""
        self.hotkey_registered = False
        self._hotkey_id = 0
        self._next_hotkey_id = 0xA110
        self._hotkey_lock = threading.Lock()
        self._hotkey_request_lock = threading.Lock()
        self._pending_hotkey: tuple[str, threading.Event, dict] | None = None
        self._owner_thread_id = int(kernel32.GetCurrentThreadId())
        self.state = "idle"
        self.waveform = [0.08] * 7
        self.button_color = f"#{''.join(f'{part:02X}' for part in rgb_from_hex(button_color))}"
        self.button_opacity = max(30, min(100, int(button_opacity)))
        self._appearance_cache: dict[tuple[str, str, int], Image.Image] = {}
        self.state_lock = threading.Lock()
        self.hwnd = 0
        self.drag_start: tuple[int, int, int, int] | None = None
        self.dragging = False
        self._class_name = f"FloatingVoiceButton_{os.getpid()}"
        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._create_window()
        self.hotkey_registered, _reason = self.set_hotkey(hotkey)

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
            self._class_name, self.title, WS_POPUP,
            self.x, self.y, self.size, self.size,
            None, None, instance, None,
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
                screen_x = ctypes.c_short(lparam & 0xFFFF).value
                screen_y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                local_x, local_y = screen_x - rect.left, screen_y - rect.top
                radius = self.size / 2 - 3
                if (local_x - self.size / 2) ** 2 + (local_y - self.size / 2) ** 2 > radius ** 2:
                    return HTTRANSPARENT
                return HTCLIENT
            if message == WM_LBUTTONDOWN:
                cursor = wintypes.POINT()
                rect = wintypes.RECT()
                user32.GetCursorPos(ctypes.byref(cursor))
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                self.drag_start = (cursor.x, cursor.y, rect.left, rect.top)
                self.dragging = False
                user32.SetCapture(hwnd)
                return 0
            if message == WM_MOUSEMOVE and self.drag_start and (wparam & MK_LBUTTON):
                cursor = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(cursor))
                start_x, start_y, window_x, window_y = self.drag_start
                dx, dy = cursor.x - start_x, cursor.y - start_y
                if self.dragging or abs(dx) + abs(dy) >= 4:
                    self.dragging = True
                    self.x, self.y = window_x + dx, window_y + dy
                    user32.SetWindowPos(
                        hwnd, None, self.x, self.y, 0, 0,
                        SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
                    )
                return 0
            if message == WM_LBUTTONUP:
                user32.ReleaseCapture()
                was_dragging = self.dragging
                self.drag_start = None
                self.dragging = False
                if was_dragging:
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    self.x, self.y = rect.left, rect.top
                    self.on_move(self.x, self.y)
                    self._render()
                else:
                    self.on_click()
                return 0
            if message == WM_RBUTTONUP:
                self._show_menu()
                return 0
            if message == WM_HOTKEY and int(wparam) == self._hotkey_id:
                self.on_click()
                return 0
            if message == WM_APP_HOTKEY_UPDATE:
                request = self._pending_hotkey
                self._pending_hotkey = None
                if request is not None:
                    hotkey, completed, result = request
                    result["value"] = self._apply_hotkey(hotkey)
                    completed.set()
                return 0
            if message == WM_APP_RENDER:
                self._render()
                return 0
            if message == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if message == WM_DESTROY:
                self._unregister_hotkey()
                self.on_close()
                user32.PostQuitMessage(0)
                return 0
        except Exception as exc:
            self.on_error(exc)
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _show_menu(self) -> None:
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, 1, "设置与历史记录…")
        user32.AppendMenuW(menu, MF_STRING, 2, "打开日志目录")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, 3, "退出")
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        command = user32.TrackPopupMenu(
            menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, point.x, point.y, 0, self.hwnd, None
        )
        user32.DestroyMenu(menu)
        if command == 1:
            self.on_open_panel()
        elif command == 2:
            self.on_open_logs()
        elif command == 3:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def _render(self) -> None:
        if self.dragging:
            return
        rect = wintypes.RECT()
        if self.hwnd and user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            self.x, self.y = rect.left, rect.top
        with self.state_lock:
            state = self.state
            color = button_render_color(state, self.button_color)
            opacity = self.button_opacity
            waveform = list(self.waveform)
            cache_key = (state, color, self.size)
            image = self._appearance_cache.get(cache_key)
            if image is None:
                source_state = button_base_state(state)
                image = self.images[source_state]
                if image.size != (self.size, self.size):
                    image = image.resize((self.size, self.size), Image.Resampling.LANCZOS)
                image = tint_button_image(image, color)
                self._appearance_cache[cache_key] = image
        if state == "recording":
            image = Image.alpha_composite(image.copy(), render_waveform_layer(self.size, waveform))
        elif state == "standby":
            image = Image.alpha_composite(
                image.copy(), render_standby_layer(self.size, waveform)
            )
        pixels = premultiplied_bgra(image)
        screen_dc = user32.GetDC(None)
        memory_dc = gdi32.CreateCompatibleDC(screen_dc)
        bitmap_info = BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = self.size
        bitmap_info.bmiHeader.biHeight = -self.size
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
            destination = wintypes.POINT(self.x, self.y)
            source = wintypes.POINT(0, 0)
            size = wintypes.SIZE(self.size, self.size)
            blend = BLENDFUNCTION(0, 0, round(255 * opacity / 100), AC_SRC_ALPHA)
            if not user32.UpdateLayeredWindow(
                self.hwnd, screen_dc, ctypes.byref(destination), ctypes.byref(size),
                memory_dc, ctypes.byref(source), 0, ctypes.byref(blend), ULW_ALPHA,
            ):
                raise ctypes.WinError()
        finally:
            gdi32.SelectObject(memory_dc, previous)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(memory_dc)
            user32.ReleaseDC(None, screen_dc)

    def set_state(self, state: str) -> None:
        with self.state_lock:
            self.state = state
        user32.PostMessageW(self.hwnd, WM_APP_RENDER, 0, 0)

    def set_waveform(self, levels: list[float]) -> None:
        normalized = [max(0.0, min(1.0, float(value))) for value in levels[-7:]]
        if len(normalized) < 7:
            normalized = [0.08] * (7 - len(normalized)) + normalized
        with self.state_lock:
            self.waveform = normalized
        user32.PostMessageW(self.hwnd, WM_APP_RENDER, 0, 0)

    def set_appearance(self, color: str, opacity: int) -> None:
        red, green, blue = rgb_from_hex(color)
        normalized_color = f"#{red:02X}{green:02X}{blue:02X}"
        normalized_opacity = max(30, min(100, int(opacity)))
        with self.state_lock:
            self.button_color = normalized_color
            self.button_opacity = normalized_opacity
            self._appearance_cache.clear()
        user32.PostMessageW(self.hwnd, WM_APP_RENDER, 0, 0)

    def set_hotkey(self, hotkey: str) -> tuple[bool, str]:
        if int(kernel32.GetCurrentThreadId()) == self._owner_thread_id:
            return self._apply_hotkey(hotkey)
        with self._hotkey_request_lock:
            completed = threading.Event()
            result: dict[str, tuple[bool, str]] = {}
            self._pending_hotkey = (hotkey, completed, result)
            if not user32.PostMessageW(self.hwnd, WM_APP_HOTKEY_UPDATE, 0, 0):
                self._pending_hotkey = None
                return False, "无法通知悬浮窗口更新全局快捷键。"
            if not completed.wait(3.0):
                self._pending_hotkey = None
                return False, "全局快捷键更新等待超时。"
            return result.get("value", (False, "全局快捷键更新没有返回结果。"))

    def _apply_hotkey(self, hotkey: str) -> tuple[bool, str]:
        try:
            parsed = parse_hotkey(hotkey)
        except ValueError as exc:
            return False, str(exc)
        with self._hotkey_lock:
            if self.hotkey_registered and parsed.label == self.hotkey_label:
                return True, ""
            self._next_hotkey_id += 1
            candidate_id = self._next_hotkey_id
            if not user32.RegisterHotKey(
                self.hwnd, candidate_id, parsed.modifiers, parsed.virtual_key
            ):
                error_code = int(kernel32.GetLastError())
                return False, f"快捷键 {parsed.label} 已被其他程序占用（系统错误 {error_code}）。"
            previous_id = self._hotkey_id
            if self.hotkey_registered and previous_id:
                user32.UnregisterHotKey(self.hwnd, previous_id)
            self._hotkey_id = candidate_id
            self.hotkey_label = parsed.label
            self.hotkey_registered = True
            return True, ""

    def _unregister_hotkey(self) -> None:
        with self._hotkey_lock:
            if self.hotkey_registered and self._hotkey_id:
                user32.UnregisterHotKey(self.hwnd, self._hotkey_id)
            self.hotkey_registered = False
            self._hotkey_id = 0

    def close(self) -> None:
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def run(self) -> None:
        self._render()
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        message = MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
