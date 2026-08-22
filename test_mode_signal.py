from __future__ import annotations

import ctypes
from ctypes import wintypes


TEST_MODE_EVENT_NAME = "Local\\FloatingVoiceButton_TestMode_Request_v1"
TEST_MODE_READY_NAME = "Local\\FloatingVoiceButton_TestMode_Ready_v1"
TEST_MODE_BLOCKED_NAME = "Local\\FloatingVoiceButton_TestMode_Blocked_v1"
SYNCHRONIZE = 0x00100000
EVENT_MODIFY_STATE = 0x0002
WAIT_OBJECT_0 = 0x00000000

kernel32 = ctypes.windll.kernel32
kernel32.CreateEventW.argtypes = [
    wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR
]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenEventW.restype = wintypes.HANDLE
kernel32.SetEvent.argtypes = [wintypes.HANDLE]
kernel32.SetEvent.restype = wintypes.BOOL
kernel32.ResetEvent.argtypes = [wintypes.HANDLE]
kernel32.ResetEvent.restype = wintypes.BOOL
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


class TestModeLease:
    """设置面板持有的跨进程测试信号；进程退出后内核会自动销毁。"""

    def __init__(self) -> None:
        self._handle: int | None = None
        self._ready_handle: int | None = None
        self._blocked_handle: int | None = None

    @property
    def active(self) -> bool:
        return self._handle is not None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        handles = [
            kernel32.CreateEventW(None, True, False, name)
            for name in (TEST_MODE_EVENT_NAME, TEST_MODE_READY_NAME, TEST_MODE_BLOCKED_NAME)
        ]
        if not all(handles):
            for handle in handles:
                if handle:
                    kernel32.CloseHandle(handle)
            raise ctypes.WinError()
        self._handle, self._ready_handle, self._blocked_handle = map(int, handles)
        kernel32.ResetEvent(self._ready_handle)
        kernel32.ResetEvent(self._blocked_handle)
        if not kernel32.SetEvent(self._handle):
            self.release()
            raise ctypes.WinError()

    def wait_for_host(self, timeout: float = 6.0) -> str:
        """等待主悬浮球暂停完成；返回 ready、blocked 或 timeout。"""
        if self._ready_handle is None or self._blocked_handle is None:
            return "timeout"
        import time

        deadline = time.monotonic() + max(0.1, float(timeout))
        while time.monotonic() < deadline:
            if kernel32.WaitForSingleObject(self._blocked_handle, 0) == WAIT_OBJECT_0:
                return "blocked"
            if kernel32.WaitForSingleObject(self._ready_handle, 0) == WAIT_OBJECT_0:
                return "ready"
            time.sleep(0.04)
        return "timeout"

    def release(self) -> None:
        handles = (self._handle, self._ready_handle, self._blocked_handle)
        self._handle = self._ready_handle = self._blocked_handle = None
        handle = handles[0]
        if handle is None:
            return
        for item in handles:
            if item is not None:
                try:
                    kernel32.ResetEvent(item)
                finally:
                    kernel32.CloseHandle(item)


def test_mode_is_active() -> bool:
    """非阻塞检查设置面板是否正在占用麦克风进行测试。"""
    handle = kernel32.OpenEventW(SYNCHRONIZE, False, TEST_MODE_EVENT_NAME)
    if not handle:
        return False
    try:
        return int(kernel32.WaitForSingleObject(handle, 0)) == WAIT_OBJECT_0
    finally:
        kernel32.CloseHandle(handle)


def _signal_named_event(name: str) -> None:
    handle = kernel32.OpenEventW(
        SYNCHRONIZE | EVENT_MODIFY_STATE, False, name
    )
    if not handle:
        return
    try:
        kernel32.SetEvent(handle)
    finally:
        kernel32.CloseHandle(handle)


def signal_test_mode_ready() -> None:
    _signal_named_event(TEST_MODE_READY_NAME)


def signal_test_mode_blocked() -> None:
    _signal_named_event(TEST_MODE_BLOCKED_NAME)
