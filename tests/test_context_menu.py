from __future__ import annotations

import ctypes
import inspect
import unittest
from ctypes import wintypes

import context_menu
from context_menu import (
    DRAWITEMSTRUCT,
    ESCAPE_HOTKEY_ID,
    IndependentContextMenu,
    IndependentMenuLayout,
    MEASUREITEMSTRUCT,
    MENU_ITEMS,
    MSAA_MENU_SIG,
    ModernContextMenu,
    ODS_SELECTED,
    ODT_MENU,
    TPM_RETURNCMD,
    TPM_RIGHTBUTTON,
    WM_DRAWITEM,
    WM_CLOSE,
    WM_HOTKEY,
    WM_KEYDOWN,
    WM_KILLFOCUS,
    WM_MEASUREITEM,
    WM_MOUSELEAVE,
    VK_ESCAPE,
    independent_menu_should_close,
    scale_for_dpi,
)


class FakeApi:
    def __init__(self) -> None:
        self.dpi = 96
        self.high_contrast = False
        self.command = 0
        self.cursor = (500, 300)
        self.next_handle = 200
        self.menu_handle = 101
        self.calls: list[tuple] = []
        self.insert_count = 0
        self.fail_insert_at: int | None = None
        self.track_hook = None

    def _resource(self, kind: str) -> int:
        handle = self.next_handle
        self.next_handle += 1
        self.calls.append((f"create_{kind}", handle))
        return handle

    def dpi_for_window(self, hwnd: int) -> int:
        self.calls.append(("dpi_for_window", hwnd))
        return self.dpi

    def is_high_contrast(self) -> bool:
        self.calls.append(("is_high_contrast",))
        return self.high_contrast

    def get_cursor_position(self) -> tuple[int, int]:
        self.calls.append(("get_cursor_position",))
        return self.cursor

    def create_popup_menu(self) -> int:
        self.calls.append(("create_popup_menu", self.menu_handle))
        return self.menu_handle

    def insert_owner_item(self, menu: int, position: int, info) -> None:
        self.insert_count += 1
        self.calls.append(
            ("insert_owner_item", menu, position, info.wID, int(info.dwItemData))
        )
        if self.fail_insert_at == self.insert_count:
            raise OSError("模拟插入失败")

    def append_string_item(self, menu: int, command_id: int, label: str) -> None:
        self.calls.append(("append_string_item", menu, command_id, label))

    def append_separator(self, menu: int) -> None:
        self.calls.append(("append_separator", menu))

    def set_menu_background(self, menu: int, brush: int) -> None:
        self.calls.append(("set_menu_background", menu, brush))

    def track_popup_menu(
        self, menu: int, flags: int, x: int, y: int, hwnd: int
    ) -> int:
        self.calls.append(("track_popup_menu", menu, flags, x, y, hwnd))
        if self.track_hook is not None:
            self.track_hook()
        return self.command

    def destroy_menu(self, menu: int) -> bool:
        self.calls.append(("destroy_menu", menu))
        return True

    def create_brush(self, color: int) -> int:
        handle = self._resource("brush")
        self.calls.append(("brush_color", handle, color))
        return handle

    def create_pen(self, width: int, color: int) -> int:
        handle = self._resource("pen")
        self.calls.append(("pen_style", handle, width, color))
        return handle

    def create_font(self, pixel_height: int) -> int:
        handle = self._resource("font")
        self.calls.append(("font_height", handle, pixel_height))
        return handle

    def delete_object(self, handle: int) -> bool:
        self.calls.append(("delete_object", handle))
        return True

    def fill_rect(self, hdc: int, rect: wintypes.RECT, brush: int) -> None:
        self.calls.append(
            ("fill_rect", hdc, (rect.left, rect.top, rect.right, rect.bottom), brush)
        )

    def round_rect(self, hdc: int, rect: wintypes.RECT, radius: int, brush: int) -> None:
        self.calls.append(
            (
                "round_rect",
                hdc,
                (rect.left, rect.top, rect.right, rect.bottom),
                radius,
                brush,
            )
        )

    def draw_text(
        self, hdc: int, text: str, rect: wintypes.RECT, font: int, color: int
    ) -> None:
        self.calls.append(
            (
                "draw_text",
                hdc,
                text,
                (rect.left, rect.top, rect.right, rect.bottom),
                font,
                color,
            )
        )

    def draw_icon(
        self, hdc: int, icon: str, rect: wintypes.RECT, pen: int, dpi: int
    ) -> None:
        self.calls.append(
            (
                "draw_icon",
                hdc,
                icon,
                (rect.left, rect.top, rect.right, rect.bottom),
                pen,
                dpi,
            )
        )


class ContextMenuTests(unittest.TestCase):
    def test_independent_layout_has_fixed_232_dip_width(self) -> None:
        layout = IndependentMenuLayout.from_dpi(96)
        self.assertEqual(layout.width, 232)
        self.assertEqual(layout.height, 156)

    def test_independent_layout_contains_all_three_rows_and_hits_third_item(self) -> None:
        layout = IndependentMenuLayout.from_dpi(96)
        rows = [layout.row_rect(index) for index in range(3)]
        self.assertEqual(len(rows), 3)
        self.assertLessEqual(rows[0].bottom, rows[1].top)
        self.assertLess(rows[1].bottom, rows[2].top)
        self.assertLess(rows[1].bottom, layout.separator_y)
        self.assertLess(layout.separator_y, rows[2].top)
        self.assertLessEqual(rows[2].bottom, layout.height - layout.padding)
        third_x = (rows[2].left + rows[2].right) // 2
        third_y = (rows[2].top + rows[2].bottom) // 2
        self.assertEqual(layout.hit_test(third_x, third_y), 3)

    def test_independent_layout_scales_width_rows_and_height_with_dpi(self) -> None:
        layout = IndependentMenuLayout.from_dpi(144)
        self.assertEqual(layout.width, 348)
        self.assertEqual(layout.row_height, 66)
        self.assertEqual(layout.height, 234)
        third = layout.row_rect(2)
        self.assertEqual(layout.hit_test(third.left + 1, third.top + 1), 3)

    def test_independent_layout_clamps_to_every_work_area_edge(self) -> None:
        layout = IndependentMenuLayout.from_dpi(96)
        work = wintypes.RECT(100, 50, 1100, 750)
        self.assertEqual(layout.clamp_to_work_area(-999, -999, work), (100, 50))
        self.assertEqual(
            layout.clamp_to_work_area(1090, 740, work),
            (1100 - layout.width, 750 - layout.height),
        )
        self.assertEqual(layout.clamp_to_work_area(400, 300, work), (400, 300))

    def test_independent_close_policy_covers_close_focus_leave_and_escape(self) -> None:
        close_messages = (
            (WM_CLOSE, 0),
            (WM_KILLFOCUS, 0),
            (WM_MOUSELEAVE, 0),
            (WM_HOTKEY, ESCAPE_HOTKEY_ID),
            (WM_KEYDOWN, VK_ESCAPE),
        )
        for message, wparam in close_messages:
            with self.subTest(message=message, wparam=wparam):
                self.assertTrue(independent_menu_should_close(message, wparam))
        self.assertFalse(independent_menu_should_close(WM_HOTKEY, 123))

    def test_independent_window_class_does_not_call_system_popup_menu(self) -> None:
        source = inspect.getsource(IndependentContextMenu)
        self.assertNotIn("CreatePopupMenu", source)
        self.assertNotIn("TrackPopupMenu", source)
        self.assertIn("CreateWindowExW", source)

    def test_independent_menu_paints_text_without_icons(self) -> None:
        source = inspect.getsource(IndependentContextMenu._paint)
        self.assertIn("draw_text", source)
        self.assertNotIn("draw_icon", source)

    def test_dpi_scaling_uses_dips(self) -> None:
        self.assertEqual(scale_for_dpi(40, 96), 40)
        self.assertEqual(scale_for_dpi(40, 120), 50)
        self.assertEqual(scale_for_dpi(40, 144), 60)
        self.assertEqual(scale_for_dpi(40, 192), 80)

    def test_owner_draw_menu_keeps_native_tracking_and_releases_resources(self) -> None:
        api = FakeApi()
        api.dpi = 144
        api.command = 2
        menu = ModernContextMenu(77, api=api)

        self.assertEqual(menu.show_at(600, 420), 2)

        track = next(call for call in api.calls if call[0] == "track_popup_menu")
        self.assertEqual(track, ("track_popup_menu", 101, TPM_RIGHTBUTTON | TPM_RETURNCMD, 600, 420, 77))
        inserts = [call for call in api.calls if call[0] == "insert_owner_item"]
        self.assertEqual([call[3] for call in inserts], [1, 2, 3])
        self.assertEqual(len([call for call in api.calls if call[0] == "append_separator"]), 1)

        created = [call[1] for call in api.calls if call[0] in {"create_brush", "create_pen", "create_font"}]
        deleted = [call[1] for call in api.calls if call[0] == "delete_object"]
        self.assertCountEqual(created, deleted)
        self.assertLess(
            api.calls.index(("destroy_menu", 101)),
            min(i for i, call in enumerate(api.calls) if call[0] == "delete_object"),
        )

    def test_high_contrast_falls_back_to_system_string_menu(self) -> None:
        api = FakeApi()
        api.high_contrast = True
        api.command = 1
        menu = ModernContextMenu(88, api=api)

        self.assertEqual(menu.show_at(10, 20), 1)

        labels = [call[3] for call in api.calls if call[0] == "append_string_item"]
        self.assertEqual(labels, ["设置与历史记录", "打开日志目录", "退出语点"])
        self.assertFalse(any(call[0] == "insert_owner_item" for call in api.calls))
        self.assertFalse(any(call[0].startswith("create_") and call[0] != "create_popup_menu" for call in api.calls))
        self.assertIn(("destroy_menu", 101), api.calls)

    def test_owner_draw_data_exposes_chinese_names_through_msaa(self) -> None:
        api = FakeApi()
        menu = ModernContextMenu(99, api=api)
        captured: list[tuple[int, int, str]] = []

        def inspect_active_items() -> None:
            for stored in menu._active_items.values():
                info = stored.data.msaa
                captured.append(
                    (
                        int(info.dwMSAASignature),
                        int(info.cchWText),
                        ctypes.wstring_at(info.pszWText, info.cchWText),
                    )
                )

        api.track_hook = inspect_active_items
        menu.show_at(20, 30)

        self.assertEqual(
            captured,
            [(MSAA_MENU_SIG, len(item.label), item.label) for item in MENU_ITEMS],
        )

    def test_measure_and_draw_messages_use_current_dpi_and_selected_style(self) -> None:
        api = FakeApi()
        api.dpi = 192
        menu = ModernContextMenu(55, api=api)
        results: dict[str, object] = {}

        def dispatch_messages() -> None:
            address, stored = next(iter(menu._active_items.items()))
            measure = MEASUREITEMSTRUCT()
            measure.CtlType = ODT_MENU
            measure.itemData = address
            results["measure_handled"] = menu.handle_message(
                WM_MEASUREITEM, 0, ctypes.addressof(measure)
            )
            results["measure_size"] = (measure.itemWidth, measure.itemHeight)

            drawing = DRAWITEMSTRUCT()
            drawing.CtlType = ODT_MENU
            drawing.itemID = stored.spec.command_id
            drawing.itemState = ODS_SELECTED
            drawing.hDC = 700
            drawing.rcItem = wintypes.RECT(0, 0, measure.itemWidth, measure.itemHeight)
            drawing.itemData = address
            results["draw_handled"] = menu.handle_message(
                WM_DRAWITEM, 0, ctypes.addressof(drawing)
            )

        api.track_hook = dispatch_messages
        menu.show_at(20, 30)

        self.assertTrue(results["measure_handled"])
        self.assertEqual(results["measure_size"], (448, 80))
        self.assertTrue(results["draw_handled"])
        self.assertTrue(any(call[0] == "round_rect" for call in api.calls))
        self.assertIn(
            "设置与历史记录", [call[2] for call in api.calls if call[0] == "draw_text"]
        )
        self.assertIn("palette", [call[2] for call in api.calls if call[0] == "draw_icon"])

    def test_cancel_returns_zero_without_losing_cleanup(self) -> None:
        api = FakeApi()
        menu = ModernContextMenu(1, api=api)
        self.assertEqual(menu.show_at_cursor(), 0)
        self.assertIn(("get_cursor_position",), api.calls)
        self.assertIn(("destroy_menu", 101), api.calls)
        self.assertFalse(menu._showing)
        self.assertFalse(menu._active_items)

    def test_partial_insert_failure_still_destroys_menu_and_every_gdi_object(self) -> None:
        api = FakeApi()
        api.fail_insert_at = 2
        menu = ModernContextMenu(1, api=api)

        with self.assertRaisesRegex(OSError, "模拟插入失败"):
            menu.show_at(1, 2)

        self.assertIn(("destroy_menu", 101), api.calls)
        created = [call[1] for call in api.calls if call[0] in {"create_brush", "create_pen", "create_font"}]
        deleted = [call[1] for call in api.calls if call[0] == "delete_object"]
        self.assertCountEqual(created, deleted)
        self.assertFalse(menu._active_items)

    def test_cleanup_failure_is_reported_without_replacing_selected_command(self) -> None:
        class CleanupFailApi(FakeApi):
            def destroy_menu(self, menu: int) -> bool:
                super().destroy_menu(menu)
                return False

            def delete_object(self, handle: int) -> bool:
                super().delete_object(handle)
                return False

        api = CleanupFailApi()
        api.command = 3
        errors: list[Exception] = []
        menu = ModernContextMenu(1, api=api, on_cleanup_error=errors.append)

        self.assertEqual(menu.show_at(1, 2), 3)
        self.assertEqual(len(errors), 5)
        self.assertTrue(all(isinstance(error, OSError) for error in errors))

    def test_source_never_steals_foreground_or_adds_global_hooks(self) -> None:
        source = inspect.getsource(context_menu)
        for forbidden in (
            "SetForegroundWindow",
            "SetActiveWindow",
            "SetFocus",
            "SetCapture",
            "SetWindowsHookEx",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
