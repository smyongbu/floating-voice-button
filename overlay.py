from __future__ import annotations

import ctypes
import colorsys
import math
import os
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Callable

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from context_menu import IndependentContextMenu, WM_DRAWITEM, WM_MEASUREITEM
from global_hotkey import parse_hotkey
from windows_tray import NotificationAreaIcon, destroy_icon, load_icon


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
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.SystemParametersInfoW.argtypes = [
    wintypes.UINT, wintypes.UINT, wintypes.LPVOID, wintypes.UINT,
]
user32.SystemParametersInfoW.restype = wintypes.BOOL
user32.SetTimer.argtypes = [
    wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p,
]
user32.SetTimer.restype = ctypes.c_size_t
user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
user32.KillTimer.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [
    ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostQuitMessage.restype = None
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
kernel32.GetCurrentThreadId.argtypes = []
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
WM_CANCELMODE = 0x001F
WM_ERASEBKGND = 0x0014
WM_MOUSEACTIVATE = 0x0021
WM_NCHITTEST = 0x0084
WM_TIMER = 0x0113
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CAPTURECHANGED = 0x0215
WM_HOTKEY = 0x0312
WM_APP_RENDER = 0x8001
WM_APP_HOTKEY_UPDATE = 0x8002
WM_APP_SIZE_UPDATE = 0x8003
MA_NOACTIVATE = 3
HTCLIENT = 1
HTTRANSPARENT = -1
VK_LBUTTON = 0x01
ULW_ALPHA = 0x00000002
AC_SRC_ALPHA = 0x01
DRAG_TIMER_ID = 0xD6A9
DRAG_TIMER_INTERVAL_MS = 16
DRAG_THRESHOLD = 4
SHAPE_TIMER_ID = 0xA61A
SHAPE_TIMER_INTERVAL_MS = 16
SHAPE_TRANSITION_DURATION_SECONDS = 0.28
SHAPE_TRANSITION_MIN_DURATION_SECONDS = 0.12
SPI_GETCLIENTAREAANIMATION = 0x1042
VOICE_SHAPE_STATES = frozenset({"idle", "standby", "busy", "recording"})
CONFIRMED_BACKGROUND_INSET_RATIO = 0.15625
CONFIRMED_BACKGROUND_OPACITY = 0.48
CONFIRMED_BUTTON_OPACITY = 0.82
HGDI_ERROR = ctypes.c_void_p(-1).value


def client_area_animations_enabled() -> bool:
    """遵循 Windows 的“在窗口内显示动画控件和元素”系统设置。"""
    enabled = wintypes.BOOL()
    if not user32.SystemParametersInfoW(
        SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0
    ):
        return True
    return bool(enabled.value)


def _smoothstep(progress: float) -> float:
    progress = max(0.0, min(1.0, float(progress)))
    return progress * progress * (3.0 - 2.0 * progress)


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


def _mix_rgb(
    first: tuple[int, int, int], second: tuple[int, int, int], amount: float
) -> tuple[int, int, int]:
    amount = max(0.0, min(1.0, float(amount)))
    return tuple(
        round(start + (end - start) * amount)
        for start, end in zip(first, second)
    )


def _gradient_rgb(
    stops: tuple[tuple[float, tuple[int, int, int]], ...], amount: float
) -> tuple[int, int, int]:
    amount = max(0.0, min(1.0, float(amount)))
    for index in range(len(stops) - 1):
        start_at, start_color = stops[index]
        end_at, end_color = stops[index + 1]
        if amount <= end_at:
            width = max(0.0001, end_at - start_at)
            return _mix_rgb(start_color, end_color, (amount - start_at) / width)
    return stops[-1][1]


def _gradient_rgba(
    stops: tuple[tuple[float, tuple[int, int, int, int]], ...], amount: float
) -> tuple[int, int, int, int]:
    amount = max(0.0, min(1.0, float(amount)))
    for index in range(len(stops) - 1):
        start_at, start_color = stops[index]
        end_at, end_color = stops[index + 1]
        if amount <= end_at:
            width = max(0.0001, end_at - start_at)
            local = (amount - start_at) / width
            rgb = _mix_rgb(start_color[:3], end_color[:3], local)
            alpha = round(start_color[3] + (end_color[3] - start_color[3]) * local)
            return (*rgb, alpha)
    return stops[-1][1]


def _scaled_alpha(image: Image.Image, amount: float) -> Image.Image:
    result = image.copy()
    alpha = result.getchannel("A").point(
        lambda value: round(value * max(0.0, min(1.0, amount)))
    )
    result.putalpha(alpha)
    return result


def confirmed_button_padding(size: int) -> int:
    """返回共用网页预览中背景图超出主圆的单侧尺寸。"""
    if size <= 0:
        raise ValueError("按钮尺寸必须大于零。")
    return max(1, round(size * CONFIRMED_BACKGROUND_INSET_RATIO))


def confirmed_button_surface_size(size: int) -> int:
    """返回裁切前包含网页背景素材外沿的内部画布尺寸。"""
    return size + confirmed_button_padding(size) * 2


def _render_confirmed_button_base(
    size: int, color: str, source: Image.Image
) -> Image.Image:
    """按网页叠层规则绘制底图，并把效果严格裁在主圆内。"""
    padding = confirmed_button_padding(size)
    surface_size = confirmed_button_surface_size(size)
    oversample = 4
    mask = Image.new("L", (surface_size * oversample, surface_size * oversample), 0)
    mask_draw = ImageDraw.Draw(mask)
    start = padding * oversample
    end = (padding + size) * oversample - 1
    mask_draw.ellipse((start, start, end, end), fill=255)
    clip_mask = mask.resize((surface_size, surface_size), Image.Resampling.LANCZOS)
    button_alpha = clip_mask.point(
        lambda value: round(value * CONFIRMED_BUTTON_OPACITY)
    )

    red, green, blue = rgb_from_hex(color)
    button = Image.new("RGBA", (surface_size, surface_size), (red, green, blue, 0))
    button.putalpha(button_alpha)
    background = source.convert("RGBA").resize(
        (surface_size, surface_size), Image.Resampling.LANCZOS
    )
    combined = Image.alpha_composite(
        button, _scaled_alpha(background, CONFIRMED_BACKGROUND_OPACITY)
    )
    crop_box = (padding, padding, padding + size, padding + size)
    combined = combined.crop(crop_box)
    combined.putalpha(ImageChops.multiply(
        combined.getchannel("A"), clip_mask.crop(crop_box)
    ))
    return combined


def render_glass_button_base(
    size: int, color: str, source: Image.Image | None = None
) -> Image.Image:
    """绘制通透圆形底图；有确认素材时严格复刻共用网页叠层。"""
    if size <= 0:
        raise ValueError("按钮尺寸必须大于零。")
    if source is not None:
        return _render_confirmed_button_base(size, color, source)
    theme = rgb_from_hex(color)
    center = size / 2
    radius = size * 0.455

    halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    halo_draw = ImageDraw.Draw(halo)
    halo_inset = size * 0.055
    halo_draw.ellipse(
        (halo_inset, halo_inset, size - halo_inset, size - halo_inset),
        fill=(56, 189, 248, 112),
    )
    halo = halo.filter(ImageFilter.GaussianBlur(size * 0.045))

    sphere = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = sphere.load()
    start_color = _mix_rgb((244, 251, 255), theme, 0.18)
    end_color = _mix_rgb((8, 145, 178), theme, 0.12)
    highlight_x = center - radius * 0.34
    highlight_y = center - radius * 0.42
    for y in range(size):
        dy = (y + 0.5 - center) / radius
        for x in range(size):
            dx = (x + 0.5 - center) / radius
            distance = math.hypot(dx, dy)
            if distance > 1.03:
                continue
            diagonal = max(0.0, min(1.0, (dx + dy + 1.75) / 3.5))
            if diagonal <= 0.52:
                base = _mix_rgb(start_color, theme, diagonal / 0.52)
            else:
                base = _mix_rgb(theme, end_color, (diagonal - 0.52) / 0.48)

            highlight_distance = math.hypot(
                (x + 0.5 - highlight_x) / radius,
                (y + 0.5 - highlight_y) / radius,
            )
            highlight = max(0.0, min(1.0, (0.62 - highlight_distance) / 0.54))
            highlight = highlight * highlight * 0.78
            shaded = _mix_rgb(base, (255, 255, 255), highlight)
            bottom_shade = max(0.0, dy * 0.12 + dx * 0.05)
            shaded = _mix_rgb(shaded, (16, 65, 135), bottom_shade)

            edge = max(0.0, min(1.0, (distance - 0.955) / 0.06))
            shaded = _mix_rgb(shaded, (191, 229, 255), edge * 0.7)
            pixels[x, y] = (*shaded, 255)

    mask_scale = 4
    mask = Image.new("L", (size * mask_scale, size * mask_scale), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_center = center * mask_scale
    mask_radius = radius * mask_scale
    mask_draw.ellipse(
        (
            mask_center - mask_radius,
            mask_center - mask_radius,
            mask_center + mask_radius,
            mask_center + mask_radius,
        ),
        fill=255,
    )
    sphere.putalpha(mask.resize((size, size), Image.Resampling.LANCZOS))

    inner = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inner_draw = ImageDraw.Draw(inner)
    inner_inset = center - radius * 0.88
    inner_draw.ellipse(
        (inner_inset, inner_inset, size - inner_inset, size - inner_inset),
        outline=(255, 255, 255, 62),
        width=max(1, round(size * 0.008)),
    )
    return Image.alpha_composite(halo, Image.alpha_composite(sphere, inner))


def render_recording_halo(size: int) -> Image.Image:
    """绘制限制在固定窗口画布内的录音呼吸光环。"""
    oversample = 3
    canvas_size = size * oversample
    blue = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    blue_draw = ImageDraw.Draw(blue)
    blue_inset = canvas_size * 0.022
    blue_draw.ellipse(
        (blue_inset, blue_inset, canvas_size - blue_inset, canvas_size - blue_inset),
        outline=(96, 165, 250, 108),
        width=max(2, round(canvas_size * 0.038)),
    )
    blue = blue.filter(ImageFilter.GaussianBlur(canvas_size * 0.034))

    cyan = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    cyan_draw = ImageDraw.Draw(cyan)
    cyan_inset = canvas_size * 0.047
    cyan_draw.ellipse(
        (cyan_inset, cyan_inset, canvas_size - cyan_inset, canvas_size - cyan_inset),
        outline=(103, 232, 249, 192),
        width=max(2, round(canvas_size * 0.026)),
    )
    cyan = cyan.filter(ImageFilter.GaussianBlur(canvas_size * 0.016))
    return Image.alpha_composite(blue, cyan).resize(
        (size, size), Image.Resampling.LANCZOS
    )


def extract_light_symbol(size: int, source: Image.Image) -> Image.Image:
    """从现有按钮素材中只提取白色麦克风或状态圆点。"""
    resized = source.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    source_pixels = resized.load()
    target_pixels = result.load()
    for y in range(size):
        for x in range(size):
            red, green, blue, alpha = source_pixels[x, y]
            maximum = max(red, green, blue)
            minimum = min(red, green, blue)
            saturation = 0.0 if maximum == 0 else (maximum - minimum) / maximum
            if alpha and maximum >= 175 and saturation <= 0.16:
                strength = max(0.0, min(1.0, (maximum - 160) / 70))
                target_pixels[x, y] = (255, 255, 255, round(alpha * strength))
    return result


def _normalized_levels(levels: list[float]) -> list[float]:
    normalized = [max(0.0, min(1.0, float(value))) for value in levels[-7:]]
    if len(normalized) < 7:
        normalized = [0.08] * (7 - len(normalized)) + normalized
    return normalized


def _interpolate_level(levels: list[float], ratio: float) -> float:
    position = max(0.0, min(1.0, ratio)) * (len(levels) - 1)
    start = int(position)
    end = min(len(levels) - 1, start + 1)
    return levels[start] + (levels[end] - levels[start]) * (position - start)


def _wave_points(
    size: int,
    levels: list[float],
    amplitude_scale: float,
    cycles: float,
    phase: float,
    count: int = 48,
) -> list[tuple[float, float]]:
    left = size * 0.11
    width = size * 0.78
    center_y = size * 0.5
    average = sum(levels) / len(levels)
    peak = max(levels)
    energy = average * 0.58 + peak * 0.42
    base_amplitude = size * (0.032 + energy * 0.13) * amplitude_scale
    points: list[tuple[float, float]] = []
    for index in range(count + 1):
        ratio = index / count
        envelope = math.sin(math.pi * ratio) ** 1.65
        local_level = _interpolate_level(levels, ratio)
        local_scale = 0.82 + (local_level - average) * 0.36
        harmonic = math.sin(ratio * math.tau * cycles + phase)
        detail = math.sin(ratio * math.tau * (cycles * 1.9) - phase * 0.6) * 0.17
        points.append(
            (
                left + ratio * width,
                center_y + (harmonic + detail) * base_amplitude * envelope * local_scale,
            )
        )
    return points


def _standby_arc_points(
    size: int, lower_half: bool, count: int = 48
) -> list[tuple[float, float]]:
    center = size * 0.5
    radius = size * 0.16
    points: list[tuple[float, float]] = []
    for index in range(count + 1):
        ratio = index / count
        angle = math.pi + ratio * math.pi if lower_half else math.pi - ratio * math.pi
        points.append(
            (center + math.cos(angle) * radius, center + math.sin(angle) * radius)
        )
    return points


def _standby_line_points(size: int, count: int = 48) -> list[tuple[float, float]]:
    left = size * 0.34
    width = size * 0.32
    center = size * 0.5
    return [(left + width * index / count, center) for index in range(count + 1)]


def _interpolate_points(
    start: list[tuple[float, float]],
    end: list[tuple[float, float]],
    amount: float,
) -> list[tuple[float, float]]:
    return [
        (
            start_x + (end_x - start_x) * amount,
            start_y + (end_y - start_y) * amount,
        )
        for (start_x, start_y), (end_x, end_y) in zip(start, end)
    ]


def _draw_gradient_path(
    layer: Image.Image,
    points: list[tuple[float, float]],
    colors: tuple[tuple[float, tuple[int, int, int, int]], ...],
    width: float,
    opacity: int,
    glow: bool = False,
) -> None:
    if opacity <= 0:
        return
    oversample = 4
    scaled = [(round(x * oversample), round(y * oversample)) for x, y in points]
    line_width = max(1, round(width * oversample))
    segment_count = max(1, len(scaled) - 1)
    if glow:
        glow_layer = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        for index, (start, end) in enumerate(zip(scaled, scaled[1:])):
            red, green, blue, stop_alpha = _gradient_rgba(
                colors, (index + 0.5) / segment_count
            )
            segment_alpha = round(opacity * stop_alpha / 255)
            if segment_alpha <= 1:
                continue
            glow_color = _mix_rgb((red, green, blue), (255, 255, 255), 0.34)
            glow_draw.line(
                (start, end),
                fill=(*glow_color, min(92, round(segment_alpha * 0.42))),
                width=max(line_width + 2, round(width * oversample * 1.65)),
            )
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(oversample * 0.85))
        layer.alpha_composite(glow_layer)
    draw = ImageDraw.Draw(layer)
    for index, (start, end) in enumerate(zip(scaled, scaled[1:])):
        red, green, blue, stop_alpha = _gradient_rgba(
            colors, (index + 0.5) / segment_count
        )
        segment_alpha = round(opacity * stop_alpha / 255)
        if segment_alpha <= 1:
            continue
        draw.line(
            (start, end),
            fill=(red, green, blue, segment_alpha),
            width=line_width,
        )
    radius = line_width // 2
    if radius:
        for point, ratio in ((scaled[0], 0.0), (scaled[-1], 1.0)):
            red, green, blue, stop_alpha = _gradient_rgba(colors, ratio)
            endpoint_alpha = round(opacity * stop_alpha / 255)
            if endpoint_alpha <= 1:
                continue
            draw.ellipse(
                (point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius),
                fill=(red, green, blue, endpoint_alpha),
            )


def render_waveform_layer(
    size: int,
    levels: list[float],
    phase: float = 0.0,
    shape_mix: float = 1.0,
) -> Image.Image:
    """绘制从待机圆环平滑展开的三层蓝青录音波形。"""
    if size <= 0:
        raise ValueError("按钮尺寸必须大于零。")
    shape_mix = max(0.0, min(1.0, float(shape_mix)))
    levels = _normalized_levels(levels)
    oversample = 4
    layer = Image.new("RGBA", (size * oversample, size * oversample), (0, 0, 0, 0))
    back = _interpolate_points(
        _standby_line_points(size),
        _wave_points(size, levels, 0.43, 2.9, -phase * 0.82),
        shape_mix,
    )
    middle = _interpolate_points(
        _standby_arc_points(size, True),
        _wave_points(size, levels, 0.68, 1.82, phase * 0.64 + 0.7),
        shape_mix,
    )
    front = _interpolate_points(
        _standby_arc_points(size, False),
        _wave_points(size, levels, 1.0, 2.25, phase),
        shape_mix,
    )
    back_colors = (
        (0.0, (219, 234, 254, 0)),
        (0.22, (186, 230, 253, 209)),
        (0.78, (125, 211, 252, 209)),
        (1.0, (219, 234, 254, 0)),
    )
    middle_colors = (
        (0.0, (125, 211, 252, 0)),
        (0.2, (125, 211, 252, 255)),
        (0.52, (34, 211, 238, 255)),
        (0.82, (56, 189, 248, 255)),
        (1.0, (125, 211, 252, 0)),
    )
    front_colors = (
        (0.0, (59, 130, 246, 0)),
        (0.16, (37, 99, 235, 255)),
        (0.5, (6, 182, 212, 255)),
        (0.84, (37, 99, 235, 255)),
        (1.0, (59, 130, 246, 0)),
    )
    _draw_gradient_path(layer, back, back_colors, 1.15, round(209 * shape_mix))
    _draw_gradient_path(
        layer,
        middle,
        middle_colors if shape_mix > 0.02 else (
            (0.0, (107, 114, 128, 255)),
            (1.0, (107, 114, 128, 255)),
        ),
        1.65 + (1.45 - 1.65) * shape_mix,
        round(255 + (224 - 255) * shape_mix),
    )
    _draw_gradient_path(
        layer,
        front,
        front_colors if shape_mix > 0.02 else (
            (0.0, (107, 114, 128, 255)),
            (1.0, (107, 114, 128, 255)),
        ),
        1.65 + (2.05 - 1.65) * shape_mix,
        255,
        glow=shape_mix > 0.02,
    )
    return layer.resize((size, size), Image.Resampling.LANCZOS)


def render_standby_layer(
    size: int, levels: list[float] | None = None
) -> Image.Image:
    """绘制待命状态的紧凑灰色双弧圆环。"""
    return render_waveform_layer(
        size,
        [0.0] * 7 if levels is None else levels,
        shape_mix=0.0,
    )


def button_base_state(state: str) -> str:
    """待命与录音共用无图案底图，避免麦克风和波形叠在一起。"""
    if state == "standby":
        return "recording"
    if state == "disabled":
        return "idle"
    return state


def button_render_color(state: str, configured_color: str) -> str:
    """只有禁用状态使用中性灰；待命仍保留玻璃主题色。"""
    return "#8A94A6" if state == "disabled" else configured_color


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
        app_icon: Path | None = None,
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
        self._size_request_lock = threading.Lock()
        self._pending_size: tuple[int, threading.Event, dict] | None = None
        self._owner_thread_id = int(kernel32.GetCurrentThreadId())
        self.state = "idle"
        self.waveform = [0.08] * 7
        self._wave_phase = 0.0
        self._last_waveform_at = time.monotonic()
        self._shape_mix = 0.0
        self._shape_from = 0.0
        self._shape_target = 0.0
        self._shape_started_at = 0.0
        self._shape_duration = 0.0
        self._shape_timer_id = 0
        self._motion_enabled = client_area_animations_enabled()
        self.button_color = f"#{''.join(f'{part:02X}' for part in rgb_from_hex(button_color))}"
        self.button_opacity = max(30, min(100, int(button_opacity)))
        self._appearance_cache: dict[tuple[object, ...], Image.Image] = {}
        self.state_lock = threading.Lock()
        self._render_request_lock = threading.Lock()
        self._render_pending = False
        self.hwnd = 0
        self.drag_start: tuple[int, int, int, int] | None = None
        self.dragging = False
        self._drag_timer_id = 0
        self._class_name = f"FloatingVoiceButton_{os.getpid()}"
        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._app_icon_handle = load_icon(app_icon) if app_icon else 0
        self._tray_icon: NotificationAreaIcon | None = None
        self._create_window()
        self._context_menu = IndependentContextMenu(
            self.hwnd,
            on_cleanup_error=self.on_error,
        )
        if self._app_icon_handle:
            self._tray_icon = NotificationAreaIcon(
                self.hwnd,
                self._app_icon_handle,
                "语点",
            )
        self.hotkey_registered, _reason = self.set_hotkey(hotkey)

    def _create_window(self) -> None:
        instance = kernel32.GetModuleHandleW(None)
        window_class = WNDCLASSEXW()
        window_class.cbSize = ctypes.sizeof(WNDCLASSEXW)
        window_class.lpfnWndProc = self._wndproc_ref
        window_class.hInstance = instance
        window_class.hIcon = self._app_icon_handle
        window_class.hIconSm = self._app_icon_handle
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
            tray_icon = getattr(self, "_tray_icon", None)
            if tray_icon is not None and tray_icon.is_taskbar_created(message):
                tray_icon.restore()
                return 0
            if tray_icon is not None and message == tray_icon.callback_message:
                event = int(lparam) & 0xFFFF
                if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self.on_open_panel()
                    return 0
                if event == WM_RBUTTONUP:
                    self._show_menu()
                    return 0
            if message in (WM_DRAWITEM, WM_MEASUREITEM):
                if self._context_menu.handle_message(message, wparam, lparam):
                    return 1
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
                if (
                    (local_x - self.size / 2) ** 2
                    + (local_y - self.size / 2) ** 2
                    > radius ** 2
                ):
                    return HTTRANSPARENT
                return HTCLIENT
            if message == WM_LBUTTONDOWN:
                self._begin_pointer_action(hwnd)
                return 0
            if message == WM_TIMER:
                if int(wparam) == self._drag_timer_id:
                    self._handle_drag_timer(hwnd)
                    return 0
                if int(wparam) == self._shape_timer_id:
                    self._request_render()
                    return 0
            if message == WM_LBUTTONUP:
                self._finish_pointer_action(hwnd)
                return 0
            if message in (WM_CANCELMODE, WM_CAPTURECHANGED):
                self._cancel_pointer_action(hwnd)
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
            if message == WM_APP_SIZE_UPDATE:
                request = self._pending_size
                self._pending_size = None
                if request is not None:
                    size, completed, result = request
                    try:
                        result["value"] = self._apply_size(size)
                    except Exception as exc:
                        result["error"] = exc
                    finally:
                        completed.set()
                return 0
            if message == WM_APP_RENDER:
                with self._render_request_lock:
                    self._render_pending = False
                self._render()
                return 0
            if message == WM_CLOSE:
                self._cancel_pointer_action(hwnd)
                self._stop_shape_timer(hwnd)
                user32.DestroyWindow(hwnd)
                return 0
            if message == WM_DESTROY:
                self._cancel_pointer_action(hwnd)
                self._stop_shape_timer(hwnd)
                self._unregister_hotkey()
                if tray_icon is not None:
                    tray_icon.remove()
                self.on_close()
                user32.PostQuitMessage(0)
                return 0
        except Exception as exc:
            self.on_error(exc)
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    @staticmethod
    def _cursor_position() -> tuple[int, int]:
        cursor = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(cursor)):
            raise ctypes.WinError()
        return int(cursor.x), int(cursor.y)

    @staticmethod
    def _window_position(hwnd: int) -> tuple[int, int]:
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise ctypes.WinError()
        return int(rect.left), int(rect.top)

    def _begin_pointer_action(self, hwnd: int) -> None:
        self._cancel_pointer_action(hwnd)
        cursor_x, cursor_y = self._cursor_position()
        window_x, window_y = self._window_position(hwnd)
        self.drag_start = (cursor_x, cursor_y, window_x, window_y)
        self.dragging = False
        timer_id = int(user32.SetTimer(
            hwnd, DRAG_TIMER_ID, DRAG_TIMER_INTERVAL_MS, None
        ))
        if not timer_id:
            self.drag_start = None
            raise ctypes.WinError()
        self._drag_timer_id = timer_id

    def _apply_drag_position(self, hwnd: int, x: int, y: int) -> None:
        if not user32.SetWindowPos(
            hwnd, None, int(x), int(y), 0, 0,
            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
        ):
            raise ctypes.WinError()
        self.x, self.y = int(x), int(y)

    def _advance_pointer_action(self, hwnd: int) -> None:
        if self.drag_start is None:
            return
        cursor_x, cursor_y = self._cursor_position()
        start_x, start_y, window_x, window_y = self.drag_start
        dx, dy = cursor_x - start_x, cursor_y - start_y
        if not self.dragging and abs(dx) + abs(dy) < DRAG_THRESHOLD:
            return
        self.dragging = True
        target_x, target_y = window_x + dx, window_y + dy
        if (target_x, target_y) == (self.x, self.y):
            return
        try:
            self._apply_drag_position(hwnd, target_x, target_y)
        except Exception:
            self._cancel_pointer_action(hwnd)
            raise

    def _handle_drag_timer(self, hwnd: int) -> None:
        if self.drag_start is None:
            self._cancel_pointer_action(hwnd)
            return
        if not (int(user32.GetAsyncKeyState(VK_LBUTTON)) & 0x8000):
            self._finish_pointer_action(hwnd)
            return
        self._advance_pointer_action(hwnd)

    def _stop_drag_timer(self, hwnd: int) -> None:
        timer_id, self._drag_timer_id = self._drag_timer_id, 0
        if timer_id:
            user32.KillTimer(hwnd, timer_id)

    def _cancel_pointer_action(self, hwnd: int | None = None) -> None:
        target_hwnd = int(hwnd or self.hwnd or 0)
        self._stop_drag_timer(target_hwnd)
        self.drag_start = None
        self.dragging = False

    def _finish_pointer_action(self, hwnd: int) -> None:
        if self.drag_start is None:
            self._stop_drag_timer(hwnd)
            return
        self._advance_pointer_action(hwnd)
        was_dragging = self.dragging
        self._stop_drag_timer(hwnd)
        self.drag_start = None
        self.dragging = False
        if was_dragging:
            self.on_move(self.x, self.y)
            self._render()
        else:
            self.on_click()

    def _show_menu(self) -> None:
        command = self._context_menu.show_at_cursor()
        if command == 1:
            self.on_open_panel()
        elif command == 2:
            self.on_open_logs()
        elif command == 3:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def _shape_mix_at_locked(self, now: float) -> tuple[float, bool]:
        """推进圆环与声波的形变，并返回当前进度和是否仍在过渡。"""
        if self._shape_duration <= 0.0 or not self._motion_enabled:
            self._shape_mix = self._shape_target
            self._shape_from = self._shape_target
            self._shape_started_at = 0.0
            self._shape_duration = 0.0
            return self._shape_mix, False

        progress = max(
            0.0,
            min(1.0, (now - self._shape_started_at) / self._shape_duration),
        )
        eased = _smoothstep(progress)
        self._shape_mix = (
            self._shape_from
            + (self._shape_target - self._shape_from) * eased
        )
        if progress >= 1.0:
            self._shape_mix = self._shape_target
            self._shape_from = self._shape_target
            self._shape_started_at = 0.0
            self._shape_duration = 0.0
            return self._shape_mix, False
        return self._shape_mix, True

    def _retarget_shape_locked(self, state: str, now: float) -> None:
        current, _transitioning = self._shape_mix_at_locked(now)
        target = 1.0 if state == "recording" else 0.0
        if target == self._shape_target:
            return

        self._shape_from = current
        self._shape_target = target
        distance = abs(target - current)
        if (
            not self._motion_enabled
            or state not in VOICE_SHAPE_STATES
            or distance <= 0.001
        ):
            self._shape_mix = target
            self._shape_from = target
            self._shape_started_at = 0.0
            self._shape_duration = 0.0
            return

        self._shape_started_at = now
        self._shape_duration = max(
            SHAPE_TRANSITION_MIN_DURATION_SECONDS,
            SHAPE_TRANSITION_DURATION_SECONDS * distance,
        )

    def _stop_shape_timer(self, hwnd: int | None = None) -> None:
        timer_id, self._shape_timer_id = self._shape_timer_id, 0
        if timer_id:
            user32.KillTimer(int(hwnd or self.hwnd or 0), timer_id)

    def _sync_shape_timer(self, transitioning: bool) -> None:
        if not transitioning:
            self._stop_shape_timer()
            return
        if self._shape_timer_id:
            return
        timer_id = int(user32.SetTimer(
            self.hwnd, SHAPE_TIMER_ID, SHAPE_TIMER_INTERVAL_MS, None
        ))
        if not timer_id:
            raise ctypes.WinError()
        self._shape_timer_id = timer_id

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
            wave_phase = self._wave_phase
            shape_mix, shape_transitioning = self._shape_mix_at_locked(
                time.monotonic()
            )
            voice_shape_state = state in VOICE_SHAPE_STATES
            cache_key = ("visual", state, color, self.size)
            background_source = self.images.get("background")
            glass_key = (
                "glass", color, self.size,
                "confirmed" if background_source is not None else "generated",
            )
            image = (
                None if voice_shape_state
                else self._appearance_cache.get(cache_key)
            )
            glass = self._appearance_cache.get(glass_key)

        if image is None:
            if glass is None:
                glass = render_glass_button_base(
                    self.size, color, background_source
                )
            image = glass
            if not voice_shape_state:
                source_state = "idle" if state == "disabled" else state
                source = self.images.get(source_state, self.images["idle"])
                image = Image.alpha_composite(
                    image, extract_light_symbol(self.size, source)
                )
            with self.state_lock:
                self._appearance_cache.setdefault(glass_key, glass)
                if not voice_shape_state:
                    image = self._appearance_cache.setdefault(cache_key, image)

        if voice_shape_state:
            image = Image.alpha_composite(
                image,
                render_waveform_layer(
                    self.size,
                    waveform,
                    phase=wave_phase,
                    shape_mix=shape_mix,
                ),
            )
        self._update_layered_pixels(premultiplied_bgra(image), opacity)
        self._sync_shape_timer(shape_transitioning)

    def _update_layered_pixels(self, pixels: bytes, opacity: int) -> None:
        screen_dc = 0
        memory_dc = 0
        bitmap = 0
        previous = 0
        bitmap_selected = False
        bitmap_info = BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = self.size
        bitmap_info.bmiHeader.biHeight = -self.size
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bitmap_info.bmiHeader.biCompression = 0
        bitmap_info.bmiHeader.biSizeImage = len(pixels)
        bits = ctypes.c_void_p()
        try:
            screen_dc = user32.GetDC(None)
            if not screen_dc:
                raise ctypes.WinError()
            memory_dc = gdi32.CreateCompatibleDC(screen_dc)
            if not memory_dc:
                raise ctypes.WinError()
            bitmap = gdi32.CreateDIBSection(
                screen_dc, ctypes.byref(bitmap_info), 0, ctypes.byref(bits), None, 0
            )
            if not bitmap or not bits.value:
                raise ctypes.WinError()
            previous = gdi32.SelectObject(memory_dc, bitmap)
            if int(previous or 0) in (0, -1, HGDI_ERROR):
                raise ctypes.WinError()
            bitmap_selected = True
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
            if bitmap_selected and memory_dc:
                gdi32.SelectObject(memory_dc, previous)
            if bitmap:
                gdi32.DeleteObject(bitmap)
            if memory_dc:
                gdi32.DeleteDC(memory_dc)
            if screen_dc:
                user32.ReleaseDC(None, screen_dc)

    def _request_render(self) -> None:
        with self._render_request_lock:
            if self._render_pending or not self.hwnd:
                return
            self._render_pending = True
        if user32.PostMessageW(self.hwnd, WM_APP_RENDER, 0, 0):
            return
        with self._render_request_lock:
            self._render_pending = False
        raise ctypes.WinError()

    def set_state(self, state: str) -> None:
        now = time.monotonic()
        with self.state_lock:
            if state == "recording" and self.state != "recording":
                self._last_waveform_at = now
                self._wave_phase = 0.0
            self._retarget_shape_locked(state, now)
            self.state = state
        self._request_render()

    def set_waveform(self, levels: list[float]) -> None:
        normalized = _normalized_levels(levels)
        now = time.monotonic()
        with self.state_lock:
            should_render = self.state == "recording"
            if should_render:
                elapsed = max(0.0, min(0.2, now - self._last_waveform_at))
                energy = sum(normalized) / len(normalized)
                self._wave_phase = (
                    self._wave_phase + elapsed * (2.4 + energy * 5.6)
                ) % math.tau
            self._last_waveform_at = now
            self.waveform = normalized
        if should_render:
            self._request_render()

    def set_appearance(self, color: str, opacity: int) -> None:
        red, green, blue = rgb_from_hex(color)
        normalized_color = f"#{red:02X}{green:02X}{blue:02X}"
        normalized_opacity = max(30, min(100, int(opacity)))
        with self.state_lock:
            self.button_color = normalized_color
            self.button_opacity = normalized_opacity
            self._appearance_cache.clear()
        self._request_render()

    def _apply_size(self, size: int) -> int:
        normalized_size = max(64, min(80, int(size)))
        if normalized_size == self.size:
            return normalized_size
        delta = normalized_size - self.size
        target_x = self.x - delta // 2
        target_y = self.y - delta // 2
        if not user32.SetWindowPos(
            self.hwnd, None, target_x, target_y, normalized_size, normalized_size,
            SWP_NOZORDER | SWP_NOACTIVATE,
        ):
            raise ctypes.WinError()
        with self.state_lock:
            self.size = normalized_size
            self.x, self.y = target_x, target_y
            self._appearance_cache.clear()
        self.on_move(target_x, target_y)
        self._request_render()
        return normalized_size

    def set_size(self, size: int) -> int:
        if int(kernel32.GetCurrentThreadId()) == self._owner_thread_id:
            return self._apply_size(size)
        with self._size_request_lock:
            completed = threading.Event()
            result: dict[str, object] = {}
            self._pending_size = (int(size), completed, result)
            if not user32.PostMessageW(self.hwnd, WM_APP_SIZE_UPDATE, 0, 0):
                self._pending_size = None
                raise ctypes.WinError()
            if not completed.wait(3.0):
                self._pending_size = None
                raise TimeoutError("悬浮按钮大小更新等待超时。")
            if "error" in result:
                raise result["error"]
            return int(result.get("value", self.size))

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
        try:
            self._render()
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            message = MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            if self._tray_icon is not None:
                self._tray_icon.remove()
            if self._app_icon_handle:
                destroy_icon(self._app_icon_handle)
                self._app_icon_handle = 0
