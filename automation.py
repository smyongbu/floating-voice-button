from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from dataclasses import dataclass


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 显式声明会传递指针/句柄的 Win32 函数，避免 64 位 Python 将句柄截断。
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_D = 0x44
VK_A = 0x41
VK_C = 0x43
VK_V = 0x56
VK_X = 0x58
VK_BACK = 0x08
VK_DELETE = 0x2E
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    process_name: str


def _window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def _process_name(hwnd: int) -> str:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value.rsplit("\\", 1)[-1]
        return ""
    finally:
        kernel32.CloseHandle(handle)


def list_windows() -> list[WindowInfo]:
    windows: list[WindowInfo] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def callback(hwnd: int, _lparam: int) -> bool:
        if user32.IsWindowVisible(hwnd) and _window_title(hwnd).strip():
            windows.append(WindowInfo(hwnd, _window_title(hwnd), _process_name(hwnd)))
        return True

    user32.EnumWindows(callback, 0)
    return windows


def activate_window(hwnd: int) -> bool:
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    user32.ShowWindow(hwnd, SW_RESTORE)
    foreground = user32.GetForegroundWindow()
    current_thread = kernel32.GetCurrentThreadId()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    attached = False
    if foreground_thread and foreground_thread != current_thread:
        attached = bool(user32.AttachThreadInput(current_thread, foreground_thread, True))
    try:
        user32.BringWindowToTop(hwnd)
        return bool(user32.SetForegroundWindow(hwnd))
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, foreground_thread, False)


def activate_window_and_wait(hwnd: int, timeout_seconds: float = 1.5) -> bool:
    """激活窗口并等待 Windows 确认它确实成为前台窗口。"""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        activate_window(hwnd)
        if foreground_window() == hwnd:
            return True
        time.sleep(0.05)
    return False


def foreground_window() -> int:
    hwnd = user32.GetForegroundWindow()
    return int(hwnd) if hwnd else 0


def window_title(hwnd: int) -> str:
    return _window_title(hwnd) if hwnd and user32.IsWindow(hwnd) else ""


def hotkey(*keys: int) -> None:
    for key in keys:
        user32.keybd_event(key, 0, 0, 0)
    for key in reversed(keys):
        user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)


def read_clipboard_text(retries: int = 6) -> str | None:
    """读取 Unicode 剪贴板；短暂被其他进程占用时自动重试。"""
    for _ in range(max(1, retries)):
        if user32.OpenClipboard(None):
            try:
                if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                    return None
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return None
                pointer = kernel32.GlobalLock(handle)
                if not pointer:
                    return None
                try:
                    return ctypes.wstring_at(pointer)
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
        time.sleep(0.03)
    return None


def write_clipboard_text(text: str, owner_hwnd: int, retries: int = 8) -> bool:
    """把 Unicode 文本写入 Windows 系统剪贴板，调用结束后内容仍会保留。"""
    if not owner_hwnd or not user32.IsWindow(owner_hwnd):
        raise ValueError("写入剪贴板需要一个有效窗口。")
    encoded = str(text).encode("utf-16-le") + b"\x00\x00"
    memory = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
    if not memory:
        return False
    pointer = kernel32.GlobalLock(memory)
    if not pointer:
        kernel32.GlobalFree(memory)
        return False
    try:
        ctypes.memmove(pointer, encoded, len(encoded))
    finally:
        kernel32.GlobalUnlock(memory)
    try:
        for _ in range(max(1, retries)):
            if not user32.OpenClipboard(owner_hwnd):
                time.sleep(0.03)
                continue
            try:
                if not user32.EmptyClipboard():
                    return False
                if not user32.SetClipboardData(CF_UNICODETEXT, memory):
                    return False
                # SetClipboardData 成功后，内存所有权交给 Windows。
                memory = None
                return True
            finally:
                user32.CloseClipboard()
        return False
    finally:
        if memory:
            kernel32.GlobalFree(memory)


def paste() -> None:
    hotkey(VK_CONTROL, VK_V)
