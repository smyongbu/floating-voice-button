from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path


WM_APP = 0x8000
WM_TRAY_CALLBACK = WM_APP + 0x41
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
NIM_ADD = 0x00000000
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

user32.LoadImageW.argtypes = [
    wintypes.HINSTANCE,
    wintypes.LPCWSTR,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.LoadImageW.restype = wintypes.HANDLE
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.DestroyIcon.restype = wintypes.BOOL
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.RegisterWindowMessageW.restype = wintypes.UINT
shell32.Shell_NotifyIconW.argtypes = [
    wintypes.DWORD,
    ctypes.POINTER(NOTIFYICONDATAW),
]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL


def load_icon(path: Path | str) -> int:
    icon_path = Path(path)
    if not icon_path.is_file():
        raise FileNotFoundError(f"应用图标不存在：{icon_path}")
    handle = user32.LoadImageW(
        None,
        str(icon_path),
        IMAGE_ICON,
        0,
        0,
        LR_LOADFROMFILE | LR_DEFAULTSIZE,
    )
    if not handle:
        raise ctypes.WinError()
    return int(handle)


def destroy_icon(handle: int) -> None:
    if handle:
        user32.DestroyIcon(handle)


class NotificationAreaIcon:
    """把现有应用图标注册到 Windows 通知区域。"""

    def __init__(self, hwnd: int, icon_handle: int, tooltip: str) -> None:
        if not hwnd or not icon_handle:
            raise ValueError("通知区域图标需要有效窗口和图标句柄。")
        self.hwnd = int(hwnd)
        self.icon_handle = int(icon_handle)
        self.tooltip = str(tooltip or "语点")[:127]
        self.callback_message = WM_TRAY_CALLBACK
        self.taskbar_created_message = int(
            user32.RegisterWindowMessageW("TaskbarCreated")
        )
        self.added = False
        self.add()

    def _data(self) -> NOTIFYICONDATAW:
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = 1
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = self.callback_message
        data.hIcon = self.icon_handle
        data.szTip = self.tooltip
        return data

    def add(self) -> None:
        data = self._data()
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data)):
            raise RuntimeError("无法创建 Windows 通知区域图标。")
        self.added = True

    def remove(self) -> None:
        if not self.added:
            return
        data = self._data()
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))
        self.added = False

    def restore(self) -> None:
        self.added = False
        self.add()

    def is_taskbar_created(self, message: int) -> bool:
        return bool(
            self.taskbar_created_message
            and int(message) == self.taskbar_created_message
        )
