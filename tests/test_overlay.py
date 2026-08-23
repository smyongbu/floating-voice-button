import ctypes
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

import overlay
from overlay import (
    DRAG_TIMER_ID,
    DRAG_TIMER_INTERVAL_MS,
    LayeredButtonWindow,
    SHAPE_TIMER_ID,
    SHAPE_TIMER_INTERVAL_MS,
    SHAPE_TRANSITION_DURATION_SECONDS,
    SHAPE_TRANSITION_MIN_DURATION_SECONDS,
    WM_APP_RENDER,
    WM_CANCELMODE,
    WM_CAPTURECHANGED,
    WM_CLOSE,
    WM_DESTROY,
    button_base_state,
    button_render_color,
    confirmed_button_padding,
    confirmed_button_surface_size,
    extract_light_symbol,
    premultiplied_bgra,
    render_glass_button_base,
    render_standby_layer,
    render_waveform_layer,
    rgb_from_hex,
    tint_button_image,
)


class OverlayTests(unittest.TestCase):
    @staticmethod
    def make_window() -> LayeredButtonWindow:
        window = object.__new__(LayeredButtonWindow)
        window.hwnd = 101
        window.size = 1
        window.x = 10
        window.y = 20
        window.drag_start = None
        window.dragging = False
        window._drag_timer_id = 0
        window._render_request_lock = threading.Lock()
        window._render_pending = False
        window.state_lock = threading.Lock()
        window.state = "idle"
        window.waveform = [0.08] * 7
        window._wave_phase = 0.0
        window._last_waveform_at = time.monotonic()
        window._shape_mix = 0.0
        window._shape_from = 0.0
        window._shape_target = 0.0
        window._shape_started_at = 0.0
        window._shape_duration = 0.0
        window._shape_timer_id = 0
        window._motion_enabled = True
        window.on_click = Mock()
        window.on_move = Mock()
        window.on_open_panel = Mock()
        window.on_open_logs = Mock()
        window.on_close = Mock()
        window.on_error = Mock()
        window._context_menu = Mock()
        window._render = Mock()
        return window

    @staticmethod
    def make_visual_window(state: str) -> LayeredButtonWindow:
        window = object.__new__(LayeredButtonWindow)
        window.dragging = False
        window.hwnd = 0
        window.x = 0
        window.y = 0
        window.size = 64
        window.state_lock = threading.Lock()
        window.state = state
        window.button_color = "#2563EB"
        window.button_opacity = 100
        window.waveform = [0.08] * 7
        window._wave_phase = 0.0
        initial_mix = 1.0 if state == "recording" else 0.0
        window._shape_mix = initial_mix
        window._shape_from = initial_mix
        window._shape_target = initial_mix
        window._shape_started_at = 0.0
        window._shape_duration = 0.0
        window._shape_timer_id = 0
        window._motion_enabled = True
        window._appearance_cache = {}
        empty = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        window.images = {"idle": empty, "busy": empty}
        window._update_layered_pixels = Mock()
        return window

    def test_only_disabled_state_replaces_the_configured_color(self):
        configured = "#2563EB"
        self.assertEqual(button_render_color("disabled", configured), "#8A94A6")
        for state in ("idle", "standby", "busy", "recording"):
            with self.subTest(state=state):
                self.assertEqual(button_render_color(state, configured), configured)

    def test_apply_size_keeps_the_center_and_requests_render(self):
        window = self.make_window()
        window.size = 72
        window.x = 100
        window.y = 200
        window._appearance_cache = {("cached",): Mock()}
        window._request_render = Mock()
        with patch.object(overlay.user32, "SetWindowPos", return_value=True) as resize:
            applied = window._apply_size(80)

        self.assertEqual(applied, 80)
        self.assertEqual((window.x, window.y, window.size), (96, 196, 80))
        self.assertEqual(window._appearance_cache, {})
        resize.assert_called_once_with(
            window.hwnd, None, 96, 196, 80, 80,
            overlay.SWP_NOZORDER | overlay.SWP_NOACTIVATE,
        )
        window.on_move.assert_called_once_with(96, 196)
        window._request_render.assert_called_once()

    def test_standby_uses_plain_recording_base(self):
        self.assertEqual(button_base_state("standby"), "recording")
        self.assertEqual(button_base_state("disabled"), "idle")
        self.assertEqual(button_base_state("idle"), "idle")

    def test_premultiplied_bgra_has_zero_rgb_for_transparent_pixel(self):
        image = Image.new("RGBA", (1, 1), (200, 100, 50, 0))
        self.assertEqual(premultiplied_bgra(image), bytes((0, 0, 0, 0)))

    def test_premultiplied_channels_do_not_exceed_alpha(self):
        image = Image.new("RGBA", (1, 1), (255, 128, 64, 128))
        blue, green, red, alpha = premultiplied_bgra(image)
        self.assertLessEqual(max(blue, green, red), alpha)
        self.assertEqual(alpha, 128)

    def test_recording_red_is_tinted_to_configured_blue(self):
        image = Image.new("RGBA", (2, 1))
        image.putdata([(230, 35, 45, 210), (255, 255, 255, 180)])
        tinted = tint_button_image(image, "#2563EB")
        colored, white = tinted.getpixel((0, 0)), tinted.getpixel((1, 0))
        self.assertGreater(colored[2], colored[0])
        self.assertEqual(colored[3], 210)
        self.assertEqual(white, (255, 255, 255, 180))

    def test_hex_color_accepts_hash(self):
        self.assertEqual(rgb_from_hex("#12ABEF"), (0x12, 0xAB, 0xEF))

    def test_glass_base_has_transparent_corners_and_directional_highlight(self):
        image = render_glass_button_base(72, "#2563EB")
        self.assertEqual(image.size, (72, 72))
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        self.assertGreater(image.getpixel((36, 36))[3], 240)

        top_left = image.getpixel((24, 21))
        bottom_right = image.getpixel((49, 51))
        self.assertGreater(sum(top_left[:3]), sum(bottom_right[:3]))
        self.assertGreater(bottom_right[2], bottom_right[0])

    def test_glass_base_scales_without_clipping_its_corners(self):
        for size in (64, 72, 96):
            with self.subTest(size=size):
                image = render_glass_button_base(size, "#2563EB")
                self.assertEqual(image.size, (size, size))
                self.assertTrue(all(image.getpixel(point)[3] == 0 for point in (
                    (0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)
                )))
                self.assertIsNotNone(image.getbbox())

    def test_confirmed_background_uses_the_same_layering_as_web_preview(self):
        source = Image.new("RGBA", (84, 84), (220, 80, 40, 200))
        image = render_glass_button_base(64, "#2563EB", source)

        self.assertEqual(confirmed_button_padding(64), 10)
        self.assertEqual(confirmed_button_surface_size(64), 84)
        self.assertEqual(image.size, (64, 64))
        self.assertTrue(all(image.getpixel(point)[3] == 0 for point in (
            (0, 0), (63, 0), (0, 63), (63, 63)
        )))
        self.assertGreater(image.getpixel((32, 32))[3], round(255 * 0.82))

    def test_confirmed_background_keeps_state_layer_on_button_surface(self):
        window = self.make_visual_window("idle")
        window.images["background"] = Image.new(
            "RGBA", (24, 24), (0, 0, 0, 0)
        )
        marker = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        marker.putpixel((32, 32), (255, 255, 255, 255))

        with patch.object(
            overlay, "render_waveform_layer", return_value=marker
        ) as render_wave:
            window._render()

        self.assertEqual(render_wave.call_args.kwargs["shape_mix"], 0.0)
        pixels = window._update_layered_pixels.call_args.args[0]
        self.assertEqual(len(pixels), 64 * 64 * 4)
        offset = (32 * 64 + 32) * 4
        self.assertEqual(pixels[offset:offset + 4], bytes((255, 255, 255, 255)))

    def test_recording_wave_has_three_colored_layers_at_all_sizes(self):
        for size in (64, 72, 96):
            with self.subTest(size=size):
                layer = render_waveform_layer(
                    size,
                    [0.2, 0.45, 0.7, 1.0, 0.55, 0.35, 0.15],
                    phase=0.9,
                )
                visible = [
                    pixel for pixel in layer.getdata()
                    if pixel[3] >= 48
                ]
                self.assertGreater(len(visible), size)
                self.assertGreater(len({pixel[:3] for pixel in visible}), 24)
                self.assertTrue(any(blue > red + 18 for red, _green, blue, _alpha in visible))
                self.assertTrue(any(green > red + 18 for red, green, _blue, _alpha in visible))

    def test_recording_wave_grows_with_audio_and_changes_with_phase(self):
        quiet = render_waveform_layer(72, [0.0] * 7, phase=0.0)
        loud = render_waveform_layer(72, [1.0] * 7, phase=0.0)
        shifted = render_waveform_layer(72, [1.0] * 7, phase=1.4)
        self.assertIsNotNone(quiet.getbbox())
        self.assertIsNotNone(loud.getbbox())
        loud_height = loud.getbbox()[3] - loud.getbbox()[1]
        quiet_height = quiet.getbbox()[3] - quiet.getbbox()[1]
        self.assertGreater(loud_height, quiet_height)
        self.assertNotEqual(loud.tobytes(), shifted.tobytes())

    def test_recording_wave_fades_at_both_ends(self):
        layer = render_waveform_layer(72, [0.8] * 7, phase=0.7)

        def maximum_alpha(left: int, right: int) -> int:
            return max(
                layer.getpixel((x, y))[3]
                for x in range(left, right)
                for y in range(72)
            )

        center_alpha = maximum_alpha(30, 42)
        self.assertGreater(center_alpha, 180)
        self.assertLess(maximum_alpha(4, 8), center_alpha * 0.55)
        self.assertLess(maximum_alpha(64, 68), center_alpha * 0.55)

    def test_shape_mix_expands_compact_standby_ring_into_full_wave(self):
        ring = render_waveform_layer(72, [0.6] * 7, shape_mix=0.0)
        middle = render_waveform_layer(72, [0.6] * 7, shape_mix=0.5)
        wave = render_waveform_layer(72, [0.6] * 7, shape_mix=1.0)
        self.assertLessEqual(ring.getbbox()[2] - ring.getbbox()[0], 30)
        self.assertIsNotNone(middle.getbbox())
        self.assertGreater(wave.getbbox()[2] - wave.getbbox()[0], 48)

    def test_standby_layer_is_a_compact_gray_ring_independent_of_audio(self):
        silent = render_standby_layer(72, [0.0] * 7)
        active = render_standby_layer(72, [0.0, 0.1, 0.3, 1.0, 0.3, 0.1, 0.0])
        self.assertEqual(silent.tobytes(), active.tobytes())
        self.assertEqual(silent.getpixel((36, 36))[3], 0)
        self.assertLessEqual(silent.getbbox()[2] - silent.getbbox()[0], 30)
        visible = [pixel for pixel in silent.getdata() if pixel[3] >= 48]
        self.assertTrue(visible)
        self.assertTrue(
            all(max(red, green, blue) - min(red, green, blue) <= 30
                for red, green, blue, _alpha in visible)
        )

    def test_light_symbol_keeps_white_glyph_and_removes_colored_background(self):
        source = Image.new("RGBA", (8, 8), (37, 99, 235, 255))
        source.putpixel((4, 4), (255, 255, 255, 255))
        symbol = extract_light_symbol(8, source)
        self.assertEqual(symbol.getpixel((0, 0))[3], 0)
        self.assertEqual(symbol.getpixel((4, 4)), (255, 255, 255, 255))

    def test_idle_and_standby_both_use_the_confirmed_gray_ring(self):
        transparent = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        for state in ("idle", "standby"):
            with self.subTest(state=state):
                window = self.make_visual_window(state)
                with (
                    patch.object(
                        overlay, "render_glass_button_base", return_value=transparent
                    ),
                    patch.object(
                        overlay, "render_waveform_layer", return_value=transparent
                    ) as render_ring,
                    patch.object(overlay, "extract_light_symbol") as extract_symbol,
                ):
                    window._render()
                self.assertEqual(render_ring.call_args.kwargs["shape_mix"], 0.0)
                extract_symbol.assert_not_called()

    def test_busy_state_keeps_the_ring_without_three_dot_symbol(self):
        transparent = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        window = self.make_visual_window("busy")
        with (
            patch.object(
                overlay, "render_glass_button_base", return_value=transparent
            ),
            patch.object(overlay, "extract_light_symbol") as extract_symbol,
            patch.object(
                overlay, "render_waveform_layer", return_value=transparent
            ) as render_wave,
        ):
            window._render()
        self.assertEqual(render_wave.call_args.kwargs["shape_mix"], 0.0)
        extract_symbol.assert_not_called()

    def test_recording_renders_current_shape_without_transition_dots(self):
        transparent = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        window = self.make_visual_window("recording")
        with (
            patch.object(
                overlay, "render_glass_button_base", return_value=transparent
            ),
            patch.object(
                overlay, "render_recording_halo", return_value=transparent
            ) as render_halo,
            patch.object(
                overlay, "render_waveform_layer", return_value=transparent
            ) as render_wave,
        ):
            window._render()
        self.assertEqual(render_wave.call_args.kwargs["shape_mix"], 1.0)
        render_halo.assert_not_called()

    def test_shape_transition_is_continuous_in_both_directions(self):
        window = self.make_window()
        with patch.object(window, "_request_render"):
            with patch.object(overlay.time, "monotonic", return_value=10.0):
                window.set_state("recording")

        self.assertEqual(
            window._shape_duration, SHAPE_TRANSITION_DURATION_SECONDS
        )
        with window.state_lock:
            start, start_active = window._shape_mix_at_locked(10.0)
            middle, middle_active = window._shape_mix_at_locked(10.14)
            end, end_active = window._shape_mix_at_locked(10.281)
        self.assertEqual(start, 0.0)
        self.assertAlmostEqual(middle, 0.5, places=6)
        self.assertEqual(end, 1.0)
        self.assertTrue(start_active)
        self.assertTrue(middle_active)
        self.assertFalse(end_active)

        window.state = "recording"
        window._shape_mix = 1.0
        window._shape_from = 1.0
        window._shape_target = 1.0
        with patch.object(window, "_request_render"):
            with patch.object(overlay.time, "monotonic", return_value=20.0):
                window.set_state("busy")
        with window.state_lock:
            reverse_middle, reverse_active = window._shape_mix_at_locked(20.14)
            reverse_end, reverse_finished = window._shape_mix_at_locked(20.281)
        self.assertAlmostEqual(reverse_middle, 0.5, places=6)
        self.assertEqual(reverse_end, 0.0)
        self.assertTrue(reverse_active)
        self.assertFalse(reverse_finished)

    def test_shape_transition_reverses_from_the_current_frame(self):
        window = self.make_window()
        with patch.object(window, "_request_render"):
            with patch.object(overlay.time, "monotonic", return_value=30.0):
                window.set_state("recording")
            with patch.object(overlay.time, "monotonic", return_value=30.112):
                window.set_state("busy")

        interrupted = 0.4 * 0.4 * (3.0 - 2.0 * 0.4)
        self.assertAlmostEqual(window._shape_from, interrupted, places=6)
        self.assertAlmostEqual(window._shape_mix, interrupted, places=6)
        self.assertEqual(window._shape_target, 0.0)
        self.assertEqual(
            window._shape_duration, SHAPE_TRANSITION_MIN_DURATION_SECONDS
        )
        with window.state_lock:
            reverse_middle, transitioning = window._shape_mix_at_locked(30.172)
        self.assertAlmostEqual(reverse_middle, interrupted * 0.5, places=6)
        self.assertTrue(transitioning)

    def test_reduced_motion_draws_the_target_shape_without_a_timer(self):
        window = self.make_window()
        window._motion_enabled = False
        with (
            patch.object(overlay.time, "monotonic", return_value=40.0),
            patch.object(window, "_request_render"),
        ):
            window.set_state("recording")

        self.assertEqual(window._shape_mix, 1.0)
        self.assertEqual(window._shape_target, 1.0)
        self.assertEqual(window._shape_duration, 0.0)

    def test_shape_timer_runs_once_and_each_tick_requests_a_frame(self):
        window = self.make_window()
        with (
            patch.object(
                overlay.user32, "SetTimer", return_value=SHAPE_TIMER_ID
            ) as set_timer,
            patch.object(
                overlay.user32, "KillTimer", return_value=True
            ) as kill_timer,
            patch.object(window, "_request_render") as request_render,
        ):
            window._sync_shape_timer(True)
            window._sync_shape_timer(True)
            self.assertEqual(
                window._wnd_proc(window.hwnd, overlay.WM_TIMER, SHAPE_TIMER_ID, 0),
                0,
            )
            window._sync_shape_timer(False)

        set_timer.assert_called_once_with(
            window.hwnd, SHAPE_TIMER_ID, SHAPE_TIMER_INTERVAL_MS, None
        )
        request_render.assert_called_once_with()
        kill_timer.assert_called_once_with(window.hwnd, SHAPE_TIMER_ID)
        self.assertEqual(window._shape_timer_id, 0)

    def test_non_recording_levels_do_not_request_static_repaints(self):
        window = self.make_window()
        for state in ("idle", "standby", "busy", "disabled"):
            with self.subTest(state=state), patch.object(
                window, "_request_render"
            ) as request_render:
                window.state = state
                window.set_waveform([0.7] * 7)
                request_render.assert_not_called()
                self.assertEqual(window.waveform, [0.7] * 7)

    def test_recording_levels_advance_phase_and_request_repaint(self):
        window = self.make_window()
        window.state = "recording"
        window._last_waveform_at = 10.0
        with (
            patch.object(overlay.time, "monotonic", return_value=10.05),
            patch.object(window, "_request_render") as request_render,
        ):
            window.set_waveform([0.6] * 7)
        self.assertGreater(window._wave_phase, 0.0)
        request_render.assert_called_once_with()

    def test_repeated_recording_state_does_not_restart_transition(self):
        window = self.make_window()
        window.state = "standby"
        with (
            patch.object(overlay.time, "monotonic", side_effect=[50.0, 50.1]),
            patch.object(window, "_request_render") as request_render,
        ):
            window.set_state("recording")
            window._wave_phase = 1.25
            window.set_state("recording")
        self.assertEqual(window._shape_started_at, 50.0)
        self.assertEqual(window._shape_target, 1.0)
        self.assertEqual(window._wave_phase, 1.25)
        self.assertEqual(request_render.call_count, 2)

    def test_expensive_visual_generation_runs_outside_state_lock(self):
        window = self.make_visual_window("busy")

        def assert_unlocked(*_args, **_kwargs):
            acquired = window.state_lock.acquire(blocking=False)
            self.assertTrue(acquired)
            window.state_lock.release()
            return Image.new("RGBA", (64, 64), (0, 0, 0, 0))

        with (
            patch.object(overlay, "render_glass_button_base", side_effect=assert_unlocked),
            patch.object(overlay, "extract_light_symbol", side_effect=assert_unlocked),
        ):
            window._render()
        window._update_layered_pixels.assert_called_once()

    def test_pointer_click_uses_short_timer_without_dragging(self):
        window = self.make_window()
        window._cursor_position = Mock(side_effect=[(100, 100), (101, 101)])
        window._window_position = Mock(return_value=(10, 20))
        with (
            patch.object(overlay.user32, "SetTimer", return_value=DRAG_TIMER_ID) as set_timer,
            patch.object(overlay.user32, "KillTimer", return_value=True) as kill_timer,
            patch.object(overlay.user32, "SetWindowPos", return_value=True) as set_position,
        ):
            window._begin_pointer_action(window.hwnd)
            window._finish_pointer_action(window.hwnd)

        set_timer.assert_called_once_with(
            window.hwnd, DRAG_TIMER_ID, DRAG_TIMER_INTERVAL_MS, None
        )
        kill_timer.assert_called_once_with(window.hwnd, DRAG_TIMER_ID)
        set_position.assert_not_called()
        window.on_click.assert_called_once_with()
        window.on_move.assert_not_called()
        self.assertIsNone(window.drag_start)
        self.assertFalse(window.dragging)

    def test_drag_is_limited_to_timer_ticks_and_finishes_once(self):
        window = self.make_window()
        window._cursor_position = Mock(
            side_effect=[(100, 100), (120, 130), (120, 130)]
        )
        window._window_position = Mock(return_value=(10, 20))
        with (
            patch.object(overlay.user32, "SetTimer", return_value=DRAG_TIMER_ID),
            patch.object(overlay.user32, "KillTimer", return_value=True),
            patch.object(overlay.user32, "GetAsyncKeyState", return_value=0x8000),
            patch.object(overlay.user32, "SetWindowPos", return_value=True) as set_position,
        ):
            window._begin_pointer_action(window.hwnd)
            window._handle_drag_timer(window.hwnd)
            window._finish_pointer_action(window.hwnd)

        set_position.assert_called_once_with(
            window.hwnd,
            None,
            30,
            50,
            0,
            0,
            overlay.SWP_NOSIZE | overlay.SWP_NOZORDER | overlay.SWP_NOACTIVATE,
        )
        window.on_move.assert_called_once_with(30, 50)
        window.on_click.assert_not_called()
        window._render.assert_called_once_with()

    def test_timer_finishes_when_release_happens_outside_window(self):
        window = self.make_window()
        window._cursor_position = Mock(side_effect=[(100, 100), (115, 125)])
        window._window_position = Mock(return_value=(10, 20))
        with (
            patch.object(overlay.user32, "SetTimer", return_value=DRAG_TIMER_ID),
            patch.object(overlay.user32, "KillTimer", return_value=True),
            patch.object(overlay.user32, "GetAsyncKeyState", return_value=0),
            patch.object(overlay.user32, "SetWindowPos", return_value=True),
        ):
            window._begin_pointer_action(window.hwnd)
            window._handle_drag_timer(window.hwnd)

        window.on_move.assert_called_once_with(25, 45)
        window.on_click.assert_not_called()
        self.assertEqual(window._drag_timer_id, 0)
        self.assertIsNone(window.drag_start)

    def test_cancel_messages_clear_drag_idempotently_without_callbacks(self):
        for message in (WM_CANCELMODE, WM_CAPTURECHANGED):
            with self.subTest(message=message):
                window = self.make_window()
                window.drag_start = (1, 2, 3, 4)
                window.dragging = True
                window._drag_timer_id = DRAG_TIMER_ID
                with patch.object(
                    overlay.user32, "KillTimer", return_value=True
                ) as kill_timer:
                    self.assertEqual(
                        window._wnd_proc(window.hwnd, message, 0, 0), 0
                    )
                    window._cancel_pointer_action(window.hwnd)

                kill_timer.assert_called_once_with(window.hwnd, DRAG_TIMER_ID)
                window.on_click.assert_not_called()
                window.on_move.assert_not_called()
                self.assertIsNone(window.drag_start)
                self.assertFalse(window.dragging)
                self.assertEqual(window._drag_timer_id, 0)

    def test_close_and_destroy_clear_drag_before_window_teardown(self):
        for message in (WM_CLOSE, WM_DESTROY):
            with self.subTest(message=message):
                window = self.make_window()
                window.drag_start = (1, 2, 3, 4)
                window.dragging = True
                window._drag_timer_id = DRAG_TIMER_ID
                window._shape_timer_id = SHAPE_TIMER_ID
                window._unregister_hotkey = Mock()
                with (
                    patch.object(
                        overlay.user32, "KillTimer", return_value=True
                    ) as kill_timer,
                    patch.object(
                        overlay.user32, "DestroyWindow", return_value=True
                    ) as destroy_window,
                    patch.object(
                        overlay.user32, "PostQuitMessage", return_value=None
                    ) as post_quit,
                ):
                    self.assertEqual(
                        window._wnd_proc(window.hwnd, message, 0, 0), 0
                    )

                self.assertIsNone(window.drag_start)
                self.assertFalse(window.dragging)
                self.assertEqual(window._drag_timer_id, 0)
                self.assertEqual(window._shape_timer_id, 0)
                self.assertCountEqual(
                    [call.args for call in kill_timer.call_args_list],
                    [
                        (window.hwnd, DRAG_TIMER_ID),
                        (window.hwnd, SHAPE_TIMER_ID),
                    ],
                )
                if message == WM_CLOSE:
                    destroy_window.assert_called_once_with(window.hwnd)
                    window._unregister_hotkey.assert_not_called()
                    post_quit.assert_not_called()
                else:
                    destroy_window.assert_not_called()
                    window._unregister_hotkey.assert_called_once_with()
                    window.on_close.assert_called_once_with()
                    post_quit.assert_called_once_with(0)

    def test_set_window_position_failure_cancels_drag(self):
        window = self.make_window()
        window.drag_start = (0, 0, 10, 20)
        window._drag_timer_id = DRAG_TIMER_ID
        window._cursor_position = Mock(return_value=(20, 30))
        with (
            patch.object(overlay.user32, "SetWindowPos", return_value=False),
            patch.object(overlay.user32, "KillTimer", return_value=True) as kill_timer,
        ):
            with self.assertRaises(OSError):
                window._advance_pointer_action(window.hwnd)

        kill_timer.assert_called_once_with(window.hwnd, DRAG_TIMER_ID)
        window.on_click.assert_not_called()
        window.on_move.assert_not_called()
        self.assertIsNone(window.drag_start)
        self.assertFalse(window.dragging)

    def test_drag_implementation_has_no_system_capture_or_native_move_loop(self):
        source = Path(overlay.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "SetCapture",
            "ReleaseCapture",
            "HTCAPTION",
            "SC_MOVE",
            "SetWindowsHookEx",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_owner_draw_menu_messages_are_delegated(self):
        for message in (overlay.WM_DRAWITEM, overlay.WM_MEASUREITEM):
            with self.subTest(message=message):
                window = self.make_window()
                window._context_menu.handle_message.return_value = True

                self.assertEqual(window._wnd_proc(window.hwnd, message, 7, 9), 1)
                window._context_menu.handle_message.assert_called_once_with(
                    message, 7, 9
                )

    def test_context_menu_commands_keep_the_existing_callbacks(self):
        for command in (0, 1, 2, 3):
            with self.subTest(command=command):
                window = self.make_window()
                window._context_menu.show_at_cursor.return_value = command
                with patch.object(
                    overlay.user32, "PostMessageW", return_value=True
                ) as post_message:
                    window._show_menu()

                self.assertEqual(
                    window.on_open_panel.call_count, 1 if command == 1 else 0
                )
                self.assertEqual(
                    window.on_open_logs.call_count, 1 if command == 2 else 0
                )
                if command == 3:
                    post_message.assert_called_once_with(window.hwnd, WM_CLOSE, 0, 0)
                else:
                    post_message.assert_not_called()

    def test_window_message_win32_prototypes_are_explicit(self):
        self.assertEqual(
            overlay.user32.ShowWindow.argtypes,
            [overlay.wintypes.HWND, ctypes.c_int],
        )
        self.assertEqual(
            overlay.user32.GetMessageW.argtypes,
            [
                ctypes.POINTER(overlay.MSG),
                overlay.wintypes.HWND,
                overlay.wintypes.UINT,
                overlay.wintypes.UINT,
            ],
        )
        self.assertIs(overlay.user32.GetMessageW.restype, overlay.wintypes.BOOL)
        self.assertIs(overlay.user32.DispatchMessageW.restype, overlay.LRESULT)

    def test_render_requests_are_coalesced_and_new_update_during_render_is_kept(self):
        window = self.make_window()
        with patch.object(
            overlay.user32, "PostMessageW", return_value=True
        ) as post_message:
            window._request_render()
            window._request_render()
            post_message.assert_called_once_with(window.hwnd, WM_APP_RENDER, 0, 0)

            window._render.side_effect = window._request_render
            self.assertEqual(
                window._wnd_proc(window.hwnd, WM_APP_RENDER, 0, 0), 0
            )

        self.assertEqual(post_message.call_count, 2)
        self.assertTrue(window._render_pending)

    def test_failed_render_post_clears_pending_flag(self):
        window = self.make_window()
        with patch.object(overlay.user32, "PostMessageW", return_value=False):
            with self.assertRaises(OSError):
                window._request_render()
        self.assertFalse(window._render_pending)

    def test_layered_render_releases_every_acquired_resource_on_failures(self):
        scenarios = (
            "get_dc",
            "compatible_dc",
            "dib",
            "dib_bits",
            "select",
            "update",
            "success",
        )
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                window = self.make_window()
                pixel_buffer = (ctypes.c_ubyte * 4)()
                get_dc = Mock(return_value=0 if scenario == "get_dc" else 201)
                compatible_dc = Mock(
                    return_value=0 if scenario == "compatible_dc" else 202
                )

                def create_bitmap(_dc, _info, _usage, bits, _section, _offset):
                    if scenario == "dib":
                        return 0
                    if scenario != "dib_bits":
                        ctypes.cast(
                            bits, ctypes.POINTER(ctypes.c_void_p)
                        ).contents.value = ctypes.addressof(pixel_buffer)
                    return 203

                create_dib = Mock(side_effect=create_bitmap)
                select_object = Mock(return_value=0 if scenario == "select" else 204)
                update_layered = Mock(return_value=scenario != "update")
                delete_object = Mock(return_value=True)
                delete_dc = Mock(return_value=True)
                release_dc = Mock(return_value=1)

                with (
                    patch.object(overlay.user32, "GetDC", get_dc),
                    patch.object(overlay.gdi32, "CreateCompatibleDC", compatible_dc),
                    patch.object(overlay.gdi32, "CreateDIBSection", create_dib),
                    patch.object(overlay.gdi32, "SelectObject", select_object),
                    patch.object(overlay.user32, "UpdateLayeredWindow", update_layered),
                    patch.object(overlay.gdi32, "DeleteObject", delete_object),
                    patch.object(overlay.gdi32, "DeleteDC", delete_dc),
                    patch.object(overlay.user32, "ReleaseDC", release_dc),
                ):
                    if scenario == "success":
                        window._update_layered_pixels(bytes(4), 100)
                    else:
                        with self.assertRaises(OSError):
                            window._update_layered_pixels(bytes(4), 100)

                self.assertEqual(release_dc.call_count, scenario != "get_dc")
                self.assertEqual(
                    delete_dc.call_count,
                    scenario not in ("get_dc", "compatible_dc"),
                )
                self.assertEqual(
                    delete_object.call_count,
                    scenario in ("dib_bits", "select", "update", "success"),
                )
                expected_select_calls = 2 if scenario in ("update", "success") else (
                    1 if scenario == "select" else 0
                )
                self.assertEqual(select_object.call_count, expected_select_calls)


if __name__ == "__main__":
    unittest.main()
