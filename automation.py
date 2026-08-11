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

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9
KEYEVENTF_KEYUP = 0x0002

VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_D = 0x44
VK_A = 0x41
VK_C = 0x43
VK_V = 0x56


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


def find_codex_window(keywords: list[str], process_names: list[str]) -> WindowInfo | None:
    lowered_keywords = [item.casefold() for item in keywords if item]
    lowered_processes = {item.casefold() for item in process_names if item}
    candidates = list_windows()
    for window in candidates:
        if window.process_name.casefold() in lowered_processes:
            return window
    for window in candidates:
        if any(keyword in window.title.casefold() for keyword in lowered_keywords):
            return window
    return None


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


def foreground_window() -> int:
    return int(user32.GetForegroundWindow())


def _tap(vk: int) -> None:
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def hotkey(*keys: int) -> None:
    for key in keys:
        user32.keybd_event(key, 0, 0, 0)
    for key in reversed(keys):
        user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)


def start_or_stop_dictation() -> None:
    hotkey(VK_CONTROL, VK_SHIFT, VK_D)


def select_all_and_copy() -> None:
    hotkey(VK_CONTROL, VK_A)
    time.sleep(0.08)
    hotkey(VK_CONTROL, VK_C)


def paste() -> None:
    hotkey(VK_CONTROL, VK_V)
