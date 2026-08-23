from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from ctypes import wintypes
from typing import Callable, Protocol


WM_DRAWITEM = 0x002B
WM_MEASUREITEM = 0x002C
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_KILLFOCUS = 0x0008
WM_MOUSEACTIVATE = 0x0021
WM_KEYDOWN = 0x0100
WM_HOTKEY = 0x0312
WM_MOUSEMOVE = 0x0200
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_MOUSELEAVE = 0x02A3
WM_DPICHANGED = 0x02E0

ODT_MENU = 1
ODS_SELECTED = 0x0001
ODS_DISABLED = 0x0004
ODS_GRAYED = 0x0002

MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
MFT_OWNERDRAW = 0x0100
MIIM_STATE = 0x00000001
MIIM_ID = 0x00000002
MIIM_STRING = 0x00000040
MIIM_FTYPE = 0x00000100
MIIM_DATA = 0x00000020
MFS_ENABLED = 0x00000000

MIM_BACKGROUND = 0x00000002
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

SPI_GETHIGHCONTRAST = 0x0042
HCF_HIGHCONTRASTON = 0x00000001

DT_LEFT = 0x00000000
DT_VCENTER = 0x00000004
DT_SINGLELINE = 0x00000020
DT_NOPREFIX = 0x00000800
TRANSPARENT = 1
PS_SOLID = 0
NULL_PEN = 8
HOLLOW_BRUSH = 5

MSAA_MENU_SIG = 0xAA0DF00D
USER_DEFAULT_SCREEN_DPI = 96

WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
SW_SHOWNOACTIVATE = 4
MA_NOACTIVATE = 3
CS_DROPSHADOW = 0x00020000
TME_LEAVE = 0x00000002
VK_ESCAPE = 0x1B
ESCAPE_HOTKEY_ID = 0xD771
MONITOR_DEFAULTTONEAREST = 0x00000002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SRCCOPY = 0x00CC0020


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


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wintypes.HDC),
        ("fErase", wintypes.BOOL),
        ("rcPaint", wintypes.RECT),
        ("fRestore", wintypes.BOOL),
        ("fIncUpdate", wintypes.BOOL),
        ("rgbReserved", wintypes.BYTE * 32),
    ]


class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("hwndTrack", wintypes.HWND),
        ("dwHoverTime", wintypes.DWORD),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class MSAAMENUINFO(ctypes.Structure):
    _fields_ = [
        ("dwMSAASignature", wintypes.DWORD),
        ("cchWText", wintypes.DWORD),
        ("pszWText", wintypes.LPWSTR),
    ]


class MenuItemData(ctypes.Structure):
    # MSAAMENUINFO 必须是首成员，系统才能向 MSAA 暴露 owner-draw 项名称。
    _fields_ = [
        ("msaa", MSAAMENUINFO),
        ("command_id", wintypes.UINT),
    ]


class MENUITEMINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("fMask", wintypes.UINT),
        ("fType", wintypes.UINT),
        ("fState", wintypes.UINT),
        ("wID", wintypes.UINT),
        ("hSubMenu", wintypes.HMENU),
        ("hbmpChecked", wintypes.HBITMAP),
        ("hbmpUnchecked", wintypes.HBITMAP),
        ("dwItemData", ctypes.c_size_t),
        ("dwTypeData", wintypes.LPWSTR),
        ("cch", wintypes.UINT),
        ("hbmpItem", wintypes.HBITMAP),
    ]


class MENUINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.DWORD),
        ("dwStyle", wintypes.DWORD),
        ("cyMax", wintypes.UINT),
        ("hbrBack", wintypes.HBRUSH),
        ("dwContextHelpID", wintypes.DWORD),
        ("dwMenuData", ctypes.c_size_t),
    ]


class MEASUREITEMSTRUCT(ctypes.Structure):
    _fields_ = [
        ("CtlType", wintypes.UINT),
        ("CtlID", wintypes.UINT),
        ("itemID", wintypes.UINT),
        ("itemWidth", wintypes.UINT),
        ("itemHeight", wintypes.UINT),
        ("itemData", ctypes.c_size_t),
    ]


class DRAWITEMSTRUCT(ctypes.Structure):
    _fields_ = [
        ("CtlType", wintypes.UINT),
        ("CtlID", wintypes.UINT),
        ("itemID", wintypes.UINT),
        ("itemAction", wintypes.UINT),
        ("itemState", wintypes.UINT),
        ("hwndItem", wintypes.HWND),
        ("hDC", wintypes.HDC),
        ("rcItem", wintypes.RECT),
        ("itemData", ctypes.c_size_t),
    ]


class HIGHCONTRASTW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwFlags", wintypes.DWORD),
        ("lpszDefaultScheme", wintypes.LPWSTR),
    ]


@dataclass(frozen=True)
class MenuItemSpec:
    command_id: int
    label: str
    icon: str


@dataclass
class _StoredMenuItem:
    spec: MenuItemSpec
    text_buffer: ctypes.Array
    data: MenuItemData

    @property
    def address(self) -> int:
        return ctypes.addressof(self.data)


MENU_ITEMS = (
    MenuItemSpec(1, "设置与历史记录", "palette"),
    MenuItemSpec(2, "打开日志目录", "folder"),
    MenuItemSpec(3, "退出语点", "power"),
)


def scale_for_dpi(value: int, dpi: int) -> int:
    """把 DIP 转为当前监视器像素，并至少保留 1 像素。"""
    safe_dpi = max(1, int(dpi))
    return max(1, (int(value) * safe_dpi + USER_DEFAULT_SCREEN_DPI // 2) // USER_DEFAULT_SCREEN_DPI)


@dataclass(frozen=True)
class IndependentMenuLayout:
    """独立弹窗的物理像素布局；不再交给系统 #32768 决定宽度。"""

    dpi: int
    width: int
    height: int
    padding: int
    row_height: int
    separator_gap: int
    corner_radius: int

    @classmethod
    def from_dpi(cls, dpi: int) -> "IndependentMenuLayout":
        safe_dpi = max(USER_DEFAULT_SCREEN_DPI, int(dpi))
        padding = scale_for_dpi(6, safe_dpi)
        row_height = scale_for_dpi(44, safe_dpi)
        separator_gap = scale_for_dpi(12, safe_dpi)
        return cls(
            dpi=safe_dpi,
            width=scale_for_dpi(232, safe_dpi),
            height=padding * 2 + row_height * 3 + separator_gap,
            padding=padding,
            row_height=row_height,
            separator_gap=separator_gap,
            corner_radius=scale_for_dpi(8, safe_dpi),
        )

    def row_rect(self, index: int) -> wintypes.RECT:
        if not 0 <= int(index) < len(MENU_ITEMS):
            raise IndexError(index)
        top = self.padding + index * self.row_height
        if index == 2:
            top += self.separator_gap
        return wintypes.RECT(
            self.padding,
            top,
            self.width - self.padding,
            top + self.row_height,
        )

    @property
    def separator_y(self) -> int:
        return self.padding + self.row_height * 2 + self.separator_gap // 2

    def hit_test(self, x: int, y: int) -> int:
        for index, item in enumerate(MENU_ITEMS):
            rect = self.row_rect(index)
            if rect.left <= x < rect.right and rect.top <= y < rect.bottom:
                return item.command_id
        return 0

    def clamp_to_work_area(self, x: int, y: int, work: wintypes.RECT) -> tuple[int, int]:
        max_x = max(int(work.left), int(work.right) - self.width)
        max_y = max(int(work.top), int(work.bottom) - self.height)
        return (
            min(max(int(x), int(work.left)), max_x),
            min(max(int(y), int(work.top)), max_y),
        )


def independent_menu_should_close(message: int, wparam: int = 0) -> bool:
    """集中描述独立菜单的退出消息，方便无 GUI 单测。"""
    if message in (WM_CLOSE, WM_DESTROY, WM_KILLFOCUS, WM_MOUSELEAVE):
        return True
    if message == WM_HOTKEY and int(wparam) == ESCAPE_HOTKEY_ID:
        return True
    if message == WM_KEYDOWN and int(wparam) == VK_ESCAPE:
        return True
    return False


def _colorref(red: int, green: int, blue: int) -> int:
    return (blue << 16) | (green << 8) | red


class MenuApi(Protocol):
    def dpi_for_window(self, hwnd: int) -> int: ...
    def is_high_contrast(self) -> bool: ...
    def get_cursor_position(self) -> tuple[int, int]: ...
    def create_popup_menu(self) -> int: ...
    def insert_owner_item(self, menu: int, position: int, info: MENUITEMINFOW) -> None: ...
    def append_string_item(self, menu: int, command_id: int, label: str) -> None: ...
    def append_separator(self, menu: int) -> None: ...
    def set_menu_background(self, menu: int, brush: int) -> None: ...
    def track_popup_menu(self, menu: int, flags: int, x: int, y: int, hwnd: int) -> int: ...
    def destroy_menu(self, menu: int) -> bool: ...
    def create_brush(self, color: int) -> int: ...
    def create_pen(self, width: int, color: int) -> int: ...
    def create_font(self, pixel_height: int) -> int: ...
    def delete_object(self, handle: int) -> bool: ...
    def fill_rect(self, hdc: int, rect: wintypes.RECT, brush: int) -> None: ...
    def round_rect(self, hdc: int, rect: wintypes.RECT, radius: int, brush: int) -> None: ...
    def draw_text(self, hdc: int, text: str, rect: wintypes.RECT, font: int, color: int) -> None: ...
    def draw_icon(self, hdc: int, icon: str, rect: wintypes.RECT, pen: int, dpi: int) -> None: ...


class NativeMenuApi:
    """对 Win32 菜单/GDI 调用做窄封装，便于隔离测试。"""

    def __init__(self) -> None:
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        self._configure_prototypes()

    def _configure_prototypes(self) -> None:
        self.user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        self.user32.GetDpiForWindow.restype = wintypes.UINT
        self.user32.SystemParametersInfoW.argtypes = [
            wintypes.UINT, wintypes.UINT, wintypes.LPVOID, wintypes.UINT
        ]
        self.user32.SystemParametersInfoW.restype = wintypes.BOOL
        self.user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        self.user32.GetCursorPos.restype = wintypes.BOOL
        self.user32.CreatePopupMenu.argtypes = []
        self.user32.CreatePopupMenu.restype = wintypes.HMENU
        self.user32.InsertMenuItemW.argtypes = [
            wintypes.HMENU,
            wintypes.UINT,
            wintypes.BOOL,
            ctypes.POINTER(MENUITEMINFOW),
        ]
        self.user32.InsertMenuItemW.restype = wintypes.BOOL
        self.user32.AppendMenuW.argtypes = [
            wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR
        ]
        self.user32.AppendMenuW.restype = wintypes.BOOL
        self.user32.SetMenuInfo.argtypes = [wintypes.HMENU, ctypes.POINTER(MENUINFO)]
        self.user32.SetMenuInfo.restype = wintypes.BOOL
        self.user32.TrackPopupMenu.argtypes = [
            wintypes.HMENU,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        self.user32.TrackPopupMenu.restype = wintypes.BOOL
        self.user32.DestroyMenu.argtypes = [wintypes.HMENU]
        self.user32.DestroyMenu.restype = wintypes.BOOL
        self.user32.FillRect.argtypes = [
            wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH
        ]
        self.user32.FillRect.restype = ctypes.c_int
        self.user32.DrawTextW.argtypes = [
            wintypes.HDC,
            wintypes.LPCWSTR,
            ctypes.c_int,
            ctypes.POINTER(wintypes.RECT),
            wintypes.UINT,
        ]
        self.user32.DrawTextW.restype = ctypes.c_int

        self.gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
        self.gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
        self.gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.COLORREF]
        self.gdi32.CreatePen.restype = wintypes.HANDLE
        self.gdi32.CreateFontW.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPCWSTR,
        ]
        self.gdi32.CreateFontW.restype = wintypes.HANDLE
        self.gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
        self.gdi32.DeleteObject.restype = wintypes.BOOL
        self.gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
        self.gdi32.SelectObject.restype = wintypes.HANDLE
        self.gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
        self.gdi32.SetTextColor.restype = wintypes.COLORREF
        self.gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
        self.gdi32.SetBkMode.restype = ctypes.c_int
        self.gdi32.GetStockObject.argtypes = [ctypes.c_int]
        self.gdi32.GetStockObject.restype = wintypes.HANDLE
        self.gdi32.RoundRect.argtypes = [
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self.gdi32.RoundRect.restype = wintypes.BOOL
        self.gdi32.MoveToEx.argtypes = [
            wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.POINTER(wintypes.POINT)
        ]
        self.gdi32.MoveToEx.restype = wintypes.BOOL
        self.gdi32.LineTo.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        self.gdi32.LineTo.restype = wintypes.BOOL
        self.gdi32.Ellipse.argtypes = [
            wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int
        ]
        self.gdi32.Ellipse.restype = wintypes.BOOL

    @staticmethod
    def _raise_last_error(operation: str) -> None:
        error = ctypes.get_last_error()
        raise ctypes.WinError(error) if error else OSError(f"{operation}失败")

    def dpi_for_window(self, hwnd: int) -> int:
        return int(self.user32.GetDpiForWindow(hwnd) or USER_DEFAULT_SCREEN_DPI)

    def is_high_contrast(self) -> bool:
        state = HIGHCONTRASTW()
        state.cbSize = ctypes.sizeof(HIGHCONTRASTW)
        if not self.user32.SystemParametersInfoW(
            SPI_GETHIGHCONTRAST, state.cbSize, ctypes.byref(state), 0
        ):
            # 查询失败时优先保留系统可访问性视觉。
            return True
        return bool(state.dwFlags & HCF_HIGHCONTRASTON)

    def get_cursor_position(self) -> tuple[int, int]:
        point = wintypes.POINT()
        if not self.user32.GetCursorPos(ctypes.byref(point)):
            self._raise_last_error("读取鼠标位置")
        return int(point.x), int(point.y)

    def create_popup_menu(self) -> int:
        menu = int(self.user32.CreatePopupMenu() or 0)
        if not menu:
            self._raise_last_error("创建菜单")
        return menu

    def insert_owner_item(self, menu: int, position: int, info: MENUITEMINFOW) -> None:
        if not self.user32.InsertMenuItemW(menu, position, True, ctypes.byref(info)):
            self._raise_last_error("插入菜单项")

    def append_string_item(self, menu: int, command_id: int, label: str) -> None:
        if not self.user32.AppendMenuW(menu, MF_STRING, command_id, label):
            self._raise_last_error("添加菜单项")

    def append_separator(self, menu: int) -> None:
        if not self.user32.AppendMenuW(menu, MF_SEPARATOR, 0, None):
            self._raise_last_error("添加菜单分隔线")

    def set_menu_background(self, menu: int, brush: int) -> None:
        info = MENUINFO()
        info.cbSize = ctypes.sizeof(MENUINFO)
        info.fMask = MIM_BACKGROUND
        info.hbrBack = brush
        if not self.user32.SetMenuInfo(menu, ctypes.byref(info)):
            self._raise_last_error("设置菜单背景")

    def track_popup_menu(self, menu: int, flags: int, x: int, y: int, hwnd: int) -> int:
        return int(self.user32.TrackPopupMenu(menu, flags, x, y, 0, hwnd, None))

    def destroy_menu(self, menu: int) -> bool:
        return bool(self.user32.DestroyMenu(menu))

    def create_brush(self, color: int) -> int:
        handle = int(self.gdi32.CreateSolidBrush(color) or 0)
        if not handle:
            self._raise_last_error("创建画刷")
        return handle

    def create_pen(self, width: int, color: int) -> int:
        handle = int(self.gdi32.CreatePen(PS_SOLID, width, color) or 0)
        if not handle:
            self._raise_last_error("创建画笔")
        return handle

    def create_font(self, pixel_height: int) -> int:
        handle = int(
            self.gdi32.CreateFontW(
                -abs(pixel_height),
                0,
                0,
                0,
                400,
                0,
                0,
                0,
                1,
                0,
                0,
                5,
                0,
                "Microsoft YaHei UI",
            )
            or 0
        )
        if not handle:
            self._raise_last_error("创建菜单字体")
        return handle

    def delete_object(self, handle: int) -> bool:
        return bool(self.gdi32.DeleteObject(handle))

    def fill_rect(self, hdc: int, rect: wintypes.RECT, brush: int) -> None:
        if not self.user32.FillRect(hdc, ctypes.byref(rect), brush):
            self._raise_last_error("填充菜单背景")

    def round_rect(self, hdc: int, rect: wintypes.RECT, radius: int, brush: int) -> None:
        old_brush = self.gdi32.SelectObject(hdc, brush)
        old_pen = self.gdi32.SelectObject(hdc, self.gdi32.GetStockObject(NULL_PEN))
        try:
            if not self.gdi32.RoundRect(
                hdc, rect.left, rect.top, rect.right, rect.bottom, radius, radius
            ):
                self._raise_last_error("绘制菜单选中背景")
        finally:
            if old_pen:
                self.gdi32.SelectObject(hdc, old_pen)
            if old_brush:
                self.gdi32.SelectObject(hdc, old_brush)

    def draw_text(self, hdc: int, text: str, rect: wintypes.RECT, font: int, color: int) -> None:
        old_font = self.gdi32.SelectObject(hdc, font)
        old_mode = self.gdi32.SetBkMode(hdc, TRANSPARENT)
        old_color = self.gdi32.SetTextColor(hdc, color)
        try:
            flags = DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX
            if not self.user32.DrawTextW(hdc, text, -1, ctypes.byref(rect), flags):
                self._raise_last_error("绘制菜单文字")
        finally:
            self.gdi32.SetTextColor(hdc, old_color)
            self.gdi32.SetBkMode(hdc, old_mode)
            if old_font:
                self.gdi32.SelectObject(hdc, old_font)

    def draw_icon(self, hdc: int, icon: str, rect: wintypes.RECT, pen: int, dpi: int) -> None:
        old_pen = self.gdi32.SelectObject(hdc, pen)
        old_brush = self.gdi32.SelectObject(hdc, self.gdi32.GetStockObject(HOLLOW_BRUSH))
        try:
            left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
            mid_x = (left + right) // 2
            mid_y = (top + bottom) // 2
            dot = scale_for_dpi(2, dpi)
            if icon == "palette":
                inset = scale_for_dpi(1, dpi)
                self.gdi32.Ellipse(
                    hdc, left + inset, top + inset, right - inset, bottom - inset
                )
                for offset_x, offset_y in ((-3, -3), (2, -4), (4, 1)):
                    dot_x = mid_x + scale_for_dpi(offset_x, dpi)
                    dot_y = mid_y + scale_for_dpi(offset_y, dpi)
                    self.gdi32.Ellipse(
                        hdc,
                        dot_x - dot,
                        dot_y - dot,
                        dot_x + dot,
                        dot_y + dot,
                    )
            elif icon == "folder":
                notch = scale_for_dpi(6, dpi)
                y1 = top + scale_for_dpi(4, dpi)
                y2 = bottom - scale_for_dpi(3, dpi)
                points = (
                    (left, y1 + scale_for_dpi(3, dpi)),
                    (left + notch, y1 + scale_for_dpi(3, dpi)),
                    (left + notch + scale_for_dpi(3, dpi), y1),
                    (right, y1),
                    (right, y2),
                    (left, y2),
                    (left, y1 + scale_for_dpi(3, dpi)),
                )
                self.gdi32.MoveToEx(hdc, *points[0], None)
                for point in points[1:]:
                    self.gdi32.LineTo(hdc, *point)
            else:
                inset = scale_for_dpi(2, dpi)
                self.gdi32.Ellipse(
                    hdc, left + inset, top + inset, right - inset, bottom - inset
                )
                self.gdi32.MoveToEx(hdc, mid_x, top, None)
                self.gdi32.LineTo(hdc, mid_x, mid_y + scale_for_dpi(2, dpi))
        finally:
            if old_brush:
                self.gdi32.SelectObject(hdc, old_brush)
            if old_pen:
                self.gdi32.SelectObject(hdc, old_pen)


class ModernContextMenu:
    """保留系统菜单交互，仅接管普通模式下的三项视觉。"""

    MENU_WIDTH_DIP = 224
    ITEM_HEIGHT_DIP = 40
    FONT_HEIGHT_DIP = 14

    def __init__(
        self,
        owner_hwnd: int,
        *,
        api: MenuApi | None = None,
        on_cleanup_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.owner_hwnd = int(owner_hwnd)
        self.api: MenuApi = api or NativeMenuApi()
        self.on_cleanup_error = on_cleanup_error
        self._showing = False
        self._dpi = USER_DEFAULT_SCREEN_DPI
        self._active_items: dict[int, _StoredMenuItem] = {}
        self._gdi_handles: list[int] = []
        self._theme: dict[str, int] = {}

    def show_at_cursor(self) -> int:
        x, y = self.api.get_cursor_position()
        return self.show_at(x, y)

    def show_at(self, x: int, y: int) -> int:
        if self._showing:
            return 0
        self._showing = True
        menu = 0
        try:
            self._dpi = max(USER_DEFAULT_SCREEN_DPI, self.api.dpi_for_window(self.owner_hwnd))
            menu = self.api.create_popup_menu()
            if self.api.is_high_contrast():
                self._build_system_menu(menu)
            else:
                self._create_theme_resources()
                self.api.set_menu_background(menu, self._theme["background"])
                self._build_owner_draw_menu(menu)
            return self.api.track_popup_menu(
                menu,
                TPM_RIGHTBUTTON | TPM_RETURNCMD,
                int(x),
                int(y),
                self.owner_hwnd,
            )
        finally:
            # 菜单必须先销毁，之后才能释放其仍在引用的画刷与 itemData。
            if menu:
                try:
                    if not self.api.destroy_menu(menu):
                        self._report_cleanup_error(OSError("销毁右键菜单失败"))
                except Exception as exc:
                    self._report_cleanup_error(exc)
            self._active_items.clear()
            self._release_gdi_resources()
            self._theme.clear()
            self._showing = False

    def _build_system_menu(self, menu: int) -> None:
        self.api.append_string_item(menu, MENU_ITEMS[0].command_id, MENU_ITEMS[0].label)
        self.api.append_string_item(menu, MENU_ITEMS[1].command_id, MENU_ITEMS[1].label)
        self.api.append_separator(menu)
        self.api.append_string_item(menu, MENU_ITEMS[2].command_id, MENU_ITEMS[2].label)

    def _create_theme_resources(self) -> None:
        self._theme["background"] = self._remember(
            self.api.create_brush(_colorref(255, 255, 255))
        )
        self._theme["selected"] = self._remember(
            self.api.create_brush(_colorref(234, 242, 255))
        )
        self._theme["icon_pen"] = self._remember(
            self.api.create_pen(scale_for_dpi(1, self._dpi), _colorref(37, 99, 235))
        )
        self._theme["font"] = self._remember(
            self.api.create_font(scale_for_dpi(self.FONT_HEIGHT_DIP, self._dpi))
        )

    def _remember(self, handle: int) -> int:
        self._gdi_handles.append(int(handle))
        return int(handle)

    def _build_owner_draw_menu(self, menu: int) -> None:
        position = 0
        for index, spec in enumerate(MENU_ITEMS):
            if index == 2:
                self.api.append_separator(menu)
                position += 1
            buffer = ctypes.create_unicode_buffer(spec.label)
            data = MenuItemData()
            data.msaa.dwMSAASignature = MSAA_MENU_SIG
            data.msaa.cchWText = len(spec.label)
            data.msaa.pszWText = ctypes.cast(buffer, wintypes.LPWSTR)
            data.command_id = spec.command_id
            stored = _StoredMenuItem(spec, buffer, data)
            self._active_items[stored.address] = stored

            info = MENUITEMINFOW()
            info.cbSize = ctypes.sizeof(MENUITEMINFOW)
            info.fMask = MIIM_FTYPE | MIIM_STATE | MIIM_ID | MIIM_DATA | MIIM_STRING
            info.fType = MFT_OWNERDRAW
            info.fState = MFS_ENABLED
            info.wID = spec.command_id
            info.dwItemData = stored.address
            info.dwTypeData = ctypes.cast(buffer, wintypes.LPWSTR)
            info.cch = len(spec.label)
            self.api.insert_owner_item(menu, position, info)
            position += 1

    def handle_message(self, message: int, _wparam: int, lparam: int) -> bool:
        if not self._showing or not lparam:
            return False
        if message == WM_MEASUREITEM:
            measure = ctypes.cast(
                ctypes.c_void_p(lparam), ctypes.POINTER(MEASUREITEMSTRUCT)
            ).contents
            if measure.CtlType != ODT_MENU or int(measure.itemData) not in self._active_items:
                return False
            measure.itemWidth = scale_for_dpi(self.MENU_WIDTH_DIP, self._dpi)
            measure.itemHeight = scale_for_dpi(self.ITEM_HEIGHT_DIP, self._dpi)
            return True
        if message == WM_DRAWITEM:
            drawing = ctypes.cast(
                ctypes.c_void_p(lparam), ctypes.POINTER(DRAWITEMSTRUCT)
            ).contents
            stored = self._active_items.get(int(drawing.itemData))
            if drawing.CtlType != ODT_MENU or stored is None:
                return False
            self._draw_item(drawing, stored.spec)
            return True
        return False

    def _draw_item(self, drawing: DRAWITEMSTRUCT, spec: MenuItemSpec) -> None:
        rect = wintypes.RECT(
            drawing.rcItem.left,
            drawing.rcItem.top,
            drawing.rcItem.right,
            drawing.rcItem.bottom,
        )
        self.api.fill_rect(drawing.hDC, rect, self._theme["background"])
        selected = bool(drawing.itemState & ODS_SELECTED)
        disabled = bool(drawing.itemState & (ODS_DISABLED | ODS_GRAYED))
        if selected and not disabled:
            inset_x = scale_for_dpi(4, self._dpi)
            inset_y = scale_for_dpi(2, self._dpi)
            selected_rect = wintypes.RECT(
                rect.left + inset_x,
                rect.top + inset_y,
                rect.right - inset_x,
                rect.bottom - inset_y,
            )
            self.api.round_rect(
                drawing.hDC,
                selected_rect,
                scale_for_dpi(8, self._dpi),
                self._theme["selected"],
            )

        icon_left = rect.left + scale_for_dpi(14, self._dpi)
        icon_size = scale_for_dpi(16, self._dpi)
        icon_top = rect.top + max(0, (rect.bottom - rect.top - icon_size) // 2)
        icon_rect = wintypes.RECT(
            icon_left, icon_top, icon_left + icon_size, icon_top + icon_size
        )
        self.api.draw_icon(
            drawing.hDC,
            spec.icon,
            icon_rect,
            self._theme["icon_pen"],
            self._dpi,
        )

        text_left = icon_rect.right + scale_for_dpi(12, self._dpi)
        text_rect = wintypes.RECT(
            text_left,
            rect.top,
            rect.right - scale_for_dpi(12, self._dpi),
            rect.bottom,
        )
        text_color = _colorref(148, 163, 184) if disabled else _colorref(22, 33, 58)
        self.api.draw_text(
            drawing.hDC,
            spec.label,
            text_rect,
            self._theme["font"],
            text_color,
        )

    def _release_gdi_resources(self) -> None:
        handles, self._gdi_handles = self._gdi_handles, []
        for handle in reversed(handles):
            try:
                if not self.api.delete_object(handle):
                    self._report_cleanup_error(OSError(f"释放 GDI 对象失败：{handle}"))
            except Exception as exc:
                self._report_cleanup_error(exc)

    def _report_cleanup_error(self, error: Exception) -> None:
        if self.on_cleanup_error is not None:
            self.on_cleanup_error(error)


class IndependentContextMenu:
    """使用自有窗口类的无激活 Win32 自绘弹窗草案。"""

    def __init__(
        self,
        owner_hwnd: int,
        *,
        on_cleanup_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.owner_hwnd = int(owner_hwnd)
        self.on_cleanup_error = on_cleanup_error
        self.api = NativeMenuApi()
        self.user32 = self.api.user32
        self.gdi32 = self.api.gdi32
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_window_prototypes()
        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._class_name = f"YudianIndependentMenu_{os.getpid()}_{id(self):x}"
        self._instance = self.kernel32.GetModuleHandleW(None)
        self._showing = False
        self._done = False
        self._selected_command = 0
        self._hover_command = 0
        self._mouse_leave_tracking = False
        self._hotkey_registered = False
        self._class_registered = False
        self.hwnd = 0
        self.layout = IndependentMenuLayout.from_dpi(USER_DEFAULT_SCREEN_DPI)
        self._gdi_handles: list[int] = []
        self._theme: dict[str, int] = {}

    def _configure_window_prototypes(self) -> None:
        self.kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self.kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        self.user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
        self.user32.RegisterClassExW.restype = wintypes.ATOM
        self.user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        self.user32.UnregisterClassW.restype = wintypes.BOOL
        self.user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        self.user32.CreateWindowExW.restype = wintypes.HWND
        self.user32.DefWindowProcW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        ]
        self.user32.DefWindowProcW.restype = LRESULT
        self.user32.DestroyWindow.argtypes = [wintypes.HWND]
        self.user32.DestroyWindow.restype = wintypes.BOOL
        self.user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.ShowWindow.restype = wintypes.BOOL
        self.user32.UpdateWindow.argtypes = [wintypes.HWND]
        self.user32.UpdateWindow.restype = wintypes.BOOL
        self.user32.GetMessageW.argtypes = [
            ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
        ]
        self.user32.GetMessageW.restype = wintypes.BOOL
        self.user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
        self.user32.TranslateMessage.restype = wintypes.BOOL
        self.user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
        self.user32.DispatchMessageW.restype = LRESULT
        self.user32.PostQuitMessage.argtypes = [ctypes.c_int]
        self.user32.PostQuitMessage.restype = None
        self.user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
        self.user32.LoadCursorW.restype = wintypes.HANDLE
        self.user32.RegisterHotKey.argtypes = [
            wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT
        ]
        self.user32.RegisterHotKey.restype = wintypes.BOOL
        self.user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.UnregisterHotKey.restype = wintypes.BOOL
        self.user32.TrackMouseEvent.argtypes = [ctypes.POINTER(TRACKMOUSEEVENT)]
        self.user32.TrackMouseEvent.restype = wintypes.BOOL
        self.user32.InvalidateRect.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.RECT), wintypes.BOOL
        ]
        self.user32.InvalidateRect.restype = wintypes.BOOL
        self.user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
        self.user32.BeginPaint.restype = wintypes.HDC
        self.user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
        self.user32.EndPaint.restype = wintypes.BOOL
        self.user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user32.GetClientRect.restype = wintypes.BOOL
        self.user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        self.user32.MonitorFromPoint.restype = wintypes.HANDLE
        self.user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
        self.user32.GetMonitorInfoW.restype = wintypes.BOOL
        self.user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        self.user32.SetWindowPos.restype = wintypes.BOOL
        self.user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.BOOL]
        self.user32.SetWindowRgn.restype = ctypes.c_int
        self.user32.GetSysColor.argtypes = [ctypes.c_int]
        self.user32.GetSysColor.restype = wintypes.DWORD

        self.gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self.gdi32.CreateCompatibleDC.restype = wintypes.HDC
        self.gdi32.DeleteDC.argtypes = [wintypes.HDC]
        self.gdi32.DeleteDC.restype = wintypes.BOOL
        self.gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        self.gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
        self.gdi32.BitBlt.argtypes = [
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.DWORD,
        ]
        self.gdi32.BitBlt.restype = wintypes.BOOL
        self.gdi32.CreateRoundRectRgn.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self.gdi32.CreateRoundRectRgn.restype = wintypes.HANDLE

    def show_at_cursor(self) -> int:
        return self.show_at(*self.api.get_cursor_position())

    def handle_message(self, _message: int, _wparam: int, _lparam: int) -> bool:
        """主悬浮窗无需再处理系统菜单的 owner-draw 消息。"""
        return False

    def show_at(self, x: int, y: int) -> int:
        if self._showing:
            return 0
        self._showing = True
        self._done = False
        self._selected_command = 0
        self._hover_command = 0
        self._mouse_leave_tracking = False
        quit_code: int | None = None
        try:
            dpi = self.api.dpi_for_window(self.owner_hwnd)
            self.layout = IndependentMenuLayout.from_dpi(dpi)
            work = self._monitor_work_area(int(x), int(y))
            popup_x, popup_y = self.layout.clamp_to_work_area(int(x), int(y), work)
            self._register_class()
            self._create_theme_resources()
            self.hwnd = int(
                self.user32.CreateWindowExW(
                    WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                    self._class_name,
                    "语点菜单",
                    WS_POPUP,
                    popup_x,
                    popup_y,
                    self.layout.width,
                    self.layout.height,
                    self.owner_hwnd,
                    None,
                    self._instance,
                    None,
                )
                or 0
            )
            if not self.hwnd:
                NativeMenuApi._raise_last_error("创建独立右键菜单")
            self._apply_rounded_region()
            self._hotkey_registered = bool(
                self.user32.RegisterHotKey(
                    self.hwnd, ESCAPE_HOTKEY_ID, 0, VK_ESCAPE
                )
            )
            self.user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self.user32.UpdateWindow(self.hwnd)

            message = MSG()
            while not self._done:
                result = int(self.user32.GetMessageW(ctypes.byref(message), None, 0, 0))
                if result == -1:
                    NativeMenuApi._raise_last_error("读取独立菜单消息")
                if result == 0:
                    quit_code = int(message.wParam)
                    break
                self.user32.TranslateMessage(ctypes.byref(message))
                self.user32.DispatchMessageW(ctypes.byref(message))
            return self._selected_command
        finally:
            if self.hwnd:
                self.user32.DestroyWindow(self.hwnd)
            self._unregister_hotkey()
            self._release_theme_resources()
            self._unregister_class()
            self.hwnd = 0
            self._showing = False
            if quit_code is not None:
                self.user32.PostQuitMessage(quit_code)

    def _register_class(self) -> None:
        window_class = WNDCLASSEXW()
        window_class.cbSize = ctypes.sizeof(WNDCLASSEXW)
        window_class.style = CS_DROPSHADOW
        window_class.lpfnWndProc = self._wndproc_ref
        window_class.hInstance = self._instance
        window_class.hCursor = self.user32.LoadCursorW(None, ctypes.c_void_p(32512))
        window_class.lpszClassName = self._class_name
        if not self.user32.RegisterClassExW(ctypes.byref(window_class)):
            NativeMenuApi._raise_last_error("注册独立菜单窗口类")
        self._class_registered = True

    def _unregister_class(self) -> None:
        if not self._class_registered:
            return
        self._class_registered = False
        if not self.user32.UnregisterClassW(self._class_name, self._instance):
            self._report_cleanup_error(OSError("注销独立菜单窗口类失败"))

    def _monitor_work_area(self, x: int, y: int) -> wintypes.RECT:
        monitor = self.user32.MonitorFromPoint(
            wintypes.POINT(int(x), int(y)), MONITOR_DEFAULTTONEAREST
        )
        if not monitor:
            NativeMenuApi._raise_last_error("查找菜单所在显示器")
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not self.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            NativeMenuApi._raise_last_error("读取显示器工作区")
        return info.rcWork

    def _create_theme_resources(self) -> None:
        high_contrast = self.api.is_high_contrast()
        if high_contrast:
            background = int(self.user32.GetSysColor(4))
            selected = int(self.user32.GetSysColor(13))
            danger_selected = selected
            text = int(self.user32.GetSysColor(7))
            selected_text = int(self.user32.GetSysColor(14))
            icon = text
            icon_selected = selected_text
            danger = text
            border = int(self.user32.GetSysColor(6))
        else:
            background = _colorref(255, 255, 255)
            selected = _colorref(239, 246, 255)
            danger_selected = _colorref(255, 241, 242)
            text = _colorref(23, 32, 51)
            selected_text = text
            icon = _colorref(100, 112, 135)
            icon_selected = _colorref(37, 99, 235)
            danger = _colorref(220, 38, 38)
            border = _colorref(228, 233, 241)
        self._theme["background"] = self._remember_window_gdi(
            self.api.create_brush(background)
        )
        self._theme["selected"] = self._remember_window_gdi(
            self.api.create_brush(selected)
        )
        self._theme["danger_selected"] = self._remember_window_gdi(
            self.api.create_brush(danger_selected)
        )
        self._theme["icon_pen"] = self._remember_window_gdi(
            self.api.create_pen(scale_for_dpi(1, self.layout.dpi), icon)
        )
        self._theme["icon_selected_pen"] = self._remember_window_gdi(
            self.api.create_pen(
                scale_for_dpi(1, self.layout.dpi),
                icon_selected,
            )
        )
        self._theme["danger_pen"] = self._remember_window_gdi(
            self.api.create_pen(scale_for_dpi(1, self.layout.dpi), danger)
        )
        self._theme["border_pen"] = self._remember_window_gdi(
            self.api.create_pen(scale_for_dpi(1, self.layout.dpi), border)
        )
        self._theme["font"] = self._remember_window_gdi(
            self.api.create_font(scale_for_dpi(14, self.layout.dpi))
        )
        self._theme["text"] = text
        self._theme["selected_text"] = selected_text
        self._theme["danger"] = danger

    def _remember_window_gdi(self, handle: int) -> int:
        self._gdi_handles.append(int(handle))
        return int(handle)

    def _release_theme_resources(self) -> None:
        handles, self._gdi_handles = self._gdi_handles, []
        for handle in reversed(handles):
            try:
                if not self.api.delete_object(handle):
                    self._report_cleanup_error(OSError(f"释放独立菜单 GDI 对象失败：{handle}"))
            except Exception as exc:
                self._report_cleanup_error(exc)
        self._theme.clear()

    def _apply_rounded_region(self) -> None:
        region = self.gdi32.CreateRoundRectRgn(
            0,
            0,
            self.layout.width + 1,
            self.layout.height + 1,
            self.layout.corner_radius,
            self.layout.corner_radius,
        )
        if not region:
            NativeMenuApi._raise_last_error("创建菜单圆角区域")
        if not self.user32.SetWindowRgn(self.hwnd, region, True):
            self.gdi32.DeleteObject(region)
            NativeMenuApi._raise_last_error("应用菜单圆角区域")
        # SetWindowRgn 成功后区域句柄所有权归系统，不能再 DeleteObject。

    def _wnd_proc(self, hwnd, message, wparam, lparam):
        try:
            if message == WM_ERASEBKGND:
                return 1
            if message == WM_MOUSEACTIVATE:
                return MA_NOACTIVATE
            if message == WM_DESTROY:
                if self._hotkey_registered:
                    self.user32.UnregisterHotKey(hwnd, ESCAPE_HOTKEY_ID)
                    self._hotkey_registered = False
                self.hwnd = 0
                self._done = True
                return 0
            if message == WM_PAINT:
                self._paint(hwnd)
                return 0
            if message == WM_MOUSEMOVE:
                if not self._mouse_leave_tracking:
                    tracking = TRACKMOUSEEVENT()
                    tracking.cbSize = ctypes.sizeof(TRACKMOUSEEVENT)
                    tracking.dwFlags = TME_LEAVE
                    tracking.hwndTrack = hwnd
                    if self.user32.TrackMouseEvent(ctypes.byref(tracking)):
                        self._mouse_leave_tracking = True
                x = ctypes.c_short(int(lparam) & 0xFFFF).value
                y = ctypes.c_short((int(lparam) >> 16) & 0xFFFF).value
                command = self.layout.hit_test(x, y)
                if command != self._hover_command:
                    self._hover_command = command
                    self.user32.InvalidateRect(hwnd, None, False)
                return 0
            if message in (WM_LBUTTONUP, WM_RBUTTONUP):
                x = ctypes.c_short(int(lparam) & 0xFFFF).value
                y = ctypes.c_short((int(lparam) >> 16) & 0xFFFF).value
                self._selected_command = self.layout.hit_test(x, y)
                self._close_popup(hwnd)
                return 0
            if independent_menu_should_close(message, int(wparam)):
                self._close_popup(hwnd)
                return 0
            if message == WM_DPICHANGED:
                self._apply_dpi_change(hwnd, int(wparam), int(lparam))
                return 0
        except Exception as exc:
            self._report_cleanup_error(exc)
            self._close_popup(hwnd)
            return 0
        return self.user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _apply_dpi_change(self, hwnd: int, wparam: int, lparam: int) -> None:
        dpi = max(USER_DEFAULT_SCREEN_DPI, wparam & 0xFFFF)
        suggested = ctypes.cast(
            ctypes.c_void_p(lparam), ctypes.POINTER(wintypes.RECT)
        ).contents
        self._release_theme_resources()
        self.layout = IndependentMenuLayout.from_dpi(dpi)
        work = self._monitor_work_area(suggested.left, suggested.top)
        x, y = self.layout.clamp_to_work_area(suggested.left, suggested.top, work)
        self._create_theme_resources()
        if not self.user32.SetWindowPos(
            hwnd,
            None,
            x,
            y,
            self.layout.width,
            self.layout.height,
            SWP_NOZORDER | SWP_NOACTIVATE,
        ):
            NativeMenuApi._raise_last_error("调整独立菜单 DPI")
        self._apply_rounded_region()
        self.user32.InvalidateRect(hwnd, None, False)

    def _paint(self, hwnd: int) -> None:
        paint = PAINTSTRUCT()
        target_dc = self.user32.BeginPaint(hwnd, ctypes.byref(paint))
        if not target_dc:
            NativeMenuApi._raise_last_error("开始绘制独立菜单")
        memory_dc = 0
        bitmap = 0
        old_bitmap = 0
        try:
            client = wintypes.RECT()
            if not self.user32.GetClientRect(hwnd, ctypes.byref(client)):
                NativeMenuApi._raise_last_error("读取独立菜单区域")
            width, height = client.right - client.left, client.bottom - client.top
            memory_dc = int(self.gdi32.CreateCompatibleDC(target_dc) or 0)
            if not memory_dc:
                NativeMenuApi._raise_last_error("创建菜单缓冲画布")
            bitmap = int(self.gdi32.CreateCompatibleBitmap(target_dc, width, height) or 0)
            if not bitmap:
                NativeMenuApi._raise_last_error("创建菜单缓冲位图")
            old_bitmap = int(self.gdi32.SelectObject(memory_dc, bitmap) or 0)
            self.api.fill_rect(memory_dc, client, self._theme["background"])

            for index, item in enumerate(MENU_ITEMS):
                row = self.layout.row_rect(index)
                selected = item.command_id == self._hover_command
                if selected:
                    self.api.round_rect(
                        memory_dc,
                        row,
                        scale_for_dpi(6, self.layout.dpi),
                        self._theme[
                            "danger_selected"
                            if item.command_id == 3
                            else "selected"
                        ],
                    )
                text_rect = wintypes.RECT(
                    row.left + scale_for_dpi(12, self.layout.dpi),
                    row.top,
                    row.right - scale_for_dpi(12, self.layout.dpi),
                    row.bottom,
                )
                self.api.draw_text(
                    memory_dc,
                    item.label,
                    text_rect,
                    self._theme["font"],
                    self._theme["danger"]
                    if item.command_id == 3
                    else self._theme["selected_text"]
                    if selected
                    else self._theme["text"],
                )

            old_pen = self.gdi32.SelectObject(memory_dc, self._theme["border_pen"])
            old_brush = self.gdi32.SelectObject(
                memory_dc, self.gdi32.GetStockObject(HOLLOW_BRUSH)
            )
            try:
                separator_inset = scale_for_dpi(6, self.layout.dpi)
                self.gdi32.MoveToEx(
                    memory_dc,
                    separator_inset,
                    self.layout.separator_y,
                    None,
                )
                self.gdi32.LineTo(
                    memory_dc,
                    width - separator_inset,
                    self.layout.separator_y,
                )
                self.gdi32.RoundRect(
                    memory_dc,
                    0,
                    0,
                    width - 1,
                    height - 1,
                    self.layout.corner_radius,
                    self.layout.corner_radius,
                )
            finally:
                if old_brush:
                    self.gdi32.SelectObject(memory_dc, old_brush)
                if old_pen:
                    self.gdi32.SelectObject(memory_dc, old_pen)
            if not self.gdi32.BitBlt(
                target_dc, 0, 0, width, height, memory_dc, 0, 0, SRCCOPY
            ):
                NativeMenuApi._raise_last_error("提交独立菜单画面")
        finally:
            if memory_dc and old_bitmap:
                self.gdi32.SelectObject(memory_dc, old_bitmap)
            if bitmap:
                self.gdi32.DeleteObject(bitmap)
            if memory_dc:
                self.gdi32.DeleteDC(memory_dc)
            self.user32.EndPaint(hwnd, ctypes.byref(paint))

    def _close_popup(self, hwnd: int) -> None:
        if hwnd and self.hwnd:
            self.user32.DestroyWindow(hwnd)

    def _unregister_hotkey(self) -> None:
        if self._hotkey_registered and self.hwnd:
            self.user32.UnregisterHotKey(self.hwnd, ESCAPE_HOTKEY_ID)
        self._hotkey_registered = False

    def _report_cleanup_error(self, error: Exception) -> None:
        if self.on_cleanup_error is not None:
            self.on_cleanup_error(error)


__all__ = [
    "DRAWITEMSTRUCT",
    "ESCAPE_HOTKEY_ID",
    "IndependentContextMenu",
    "IndependentMenuLayout",
    "MEASUREITEMSTRUCT",
    "MENU_ITEMS",
    "MSAAMENUINFO",
    "MSAA_MENU_SIG",
    "ModernContextMenu",
    "NativeMenuApi",
    "ODT_MENU",
    "ODS_SELECTED",
    "TPM_RETURNCMD",
    "TPM_RIGHTBUTTON",
    "WM_DRAWITEM",
    "WM_CLOSE",
    "WM_HOTKEY",
    "WM_KEYDOWN",
    "WM_KILLFOCUS",
    "WM_MEASUREITEM",
    "WM_MOUSELEAVE",
    "VK_ESCAPE",
    "independent_menu_should_close",
    "scale_for_dpi",
]
