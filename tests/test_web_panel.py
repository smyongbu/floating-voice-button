import inspect
import re
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from history_store import HistoryEntry
from settings_panel import WebSettingsApi


PROJECT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_DIR / "web"


class WebSettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.run_log = Mock()
        self.error_log = Mock()
        self.store = Mock()
        self.api = WebSettingsApi(self.run_log, self.error_log, store=self.store)

    def test_public_bridge_surface_is_strict_allowlist(self):
        expected = {
            "get_initial_state",
            "save_appearance",
            "test_hotkey",
            "save_recognition_settings",
            "test_local_model",
            "save_provider_credentials",
            "delete_provider_credentials",
            "get_history",
            "get_history_signature",
            "copy_history",
            "delete_history",
            "clear_history",
        }
        public_callables = {
            name
            for name, member in inspect.getmembers(WebSettingsApi, predicate=callable)
            if not name.startswith("_")
        }
        public_instance_data = {
            name for name in vars(self.api) if not name.startswith("_")
        }

        self.assertEqual(public_callables, expected)
        self.assertEqual(public_instance_data, set())

    def test_invalid_color_never_reaches_config_store(self):
        invalid_colors = ("#12345", "#1234567", "#12GG56", "red", "<script>")
        with patch("settings_panel.update_config") as update_config:
            for color in invalid_colors:
                with self.subTest(color=color):
                    response = self.api.save_appearance(color, 80)
                    self.assertFalse(response["ok"])

        update_config.assert_not_called()

    def test_invalid_hotkey_never_reaches_config_store(self):
        with patch("settings_panel.update_config") as update_config:
            response = self.api.save_appearance("#2563EB", 80, "Shift+A")

        self.assertFalse(response["ok"])
        self.assertIn("Ctrl、Alt 或 Win", response["message"])
        update_config.assert_not_called()

    def test_hotkey_test_reports_available_without_saving(self):
        with (
            patch.object(WebSettingsApi, "_main_window_exists", return_value=False),
            patch("settings_panel.user32.RegisterHotKey", return_value=True) as register,
            patch("settings_panel.user32.UnregisterHotKey") as unregister,
            patch("settings_panel.load_config", return_value={"global_hotkey": "Ctrl+Alt+Space"}),
        ):
            response = self.api.test_hotkey("Ctrl+F12")

        self.assertTrue(response["ok"])
        self.assertTrue(response["data"]["available"])
        register.assert_called_once()
        unregister.assert_called_once()

    def test_hotkey_test_reports_windows_conflict(self):
        with (
            patch.object(WebSettingsApi, "_main_window_exists", return_value=False),
            patch("settings_panel.user32.RegisterHotKey", return_value=False),
            patch("settings_panel.kernel32.GetLastError", return_value=1409),
            patch("settings_panel.load_config", return_value={"global_hotkey": "Ctrl+Alt+Space"}),
        ):
            response = self.api.test_hotkey("F8")

        self.assertTrue(response["ok"])
        self.assertFalse(response["data"]["available"])
        self.assertIn("已被其他程序占用", response["message"])

    def test_hotkey_test_recognizes_current_registered_hotkey(self):
        with (
            patch.object(WebSettingsApi, "_main_window_exists", return_value=True),
            patch("settings_panel.user32.RegisterHotKey", return_value=False),
            patch("settings_panel.kernel32.GetLastError", return_value=1409),
            patch("settings_panel.load_config", return_value={"global_hotkey": "Ctrl+Alt+Space"}),
        ):
            response = self.api.test_hotkey("Ctrl+Alt+Space")

        self.assertTrue(response["ok"])
        self.assertTrue(response["data"]["available"])
        self.assertTrue(response["data"]["current"])
        self.assertIn("当前正在使用", response["message"])

    def test_copy_reads_body_from_store_and_uses_valid_panel_handle(self):
        synthetic_text = "用于单元测试的模拟正文"
        self.store.get.return_value = HistoryEntry(
            operation_id="copy-op",
            created_at="2026-08-12T12:00:00+08:00",
            text=synthetic_text,
        )

        with (
            patch.object(WebSettingsApi, "_panel_hwnd", return_value=24680),
            patch("settings_panel.write_clipboard_text", return_value=True) as write_clipboard,
        ):
            response = self.api.copy_history("copy-op")

        self.assertTrue(response["ok"])
        self.store.get.assert_called_once_with("copy-op")
        write_clipboard.assert_called_once_with(synthetic_text, 24680)
        self.assertNotIn(synthetic_text, repr(self.run_log.method_calls))
        self.assertNotIn(synthetic_text, repr(self.error_log.method_calls))

    def test_copy_fails_closed_when_panel_handle_is_missing(self):
        self.store.get.return_value = HistoryEntry(
            operation_id="copy-op",
            created_at="2026-08-12T12:00:00+08:00",
            text="模拟正文",
        )

        with (
            patch.object(WebSettingsApi, "_panel_hwnd", return_value=0),
            patch("settings_panel.write_clipboard_text") as write_clipboard,
        ):
            response = self.api.copy_history("copy-op")

        self.assertFalse(response["ok"])
        write_clipboard.assert_not_called()


class WebPanelStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        cls.css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")
        cls.javascript = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    def test_panel_uses_local_web_resources_and_has_no_inline_code_or_style(self):
        resources = re.findall(
            r"(?:src|href)\s*=\s*[\"']([^\"']+)[\"']",
            self.html,
            flags=re.IGNORECASE,
        )
        self.assertIn("styles.css", resources)
        self.assertIn("app.js", resources)
        self.assertTrue(all(not re.match(r"(?:https?:)?//", item) for item in resources))
        self.assertNotRegex(self.html, r"(?i)<style(?:\s|>)")
        self.assertNotRegex(self.html, r"(?i)\sstyle\s*=")
        self.assertNotRegex(self.html, r"(?i)<script[^>]*>(?:(?!</script>).)+</script>")
        self.assertNotRegex(self.html, r"(?i)\son[a-z]+\s*=")
        self.assertNotIn("innerHTML", self.javascript)
        self.assertNotRegex(self.html + self.css + self.javascript, r"https?://")

    def test_content_security_policy_blocks_remote_capabilities(self):
        csp_match = re.search(
            r'<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]+)"',
            self.html,
            flags=re.IGNORECASE,
        )
        self.assertIsNotNone(csp_match)
        csp = csp_match.group(1)
        for directive in (
            "default-src 'none'",
            "script-src 'self'",
            "style-src 'self'",
            "connect-src 'none'",
            "object-src 'none'",
            "frame-src 'none'",
            "base-uri 'none'",
            "form-action 'none'",
        ):
            self.assertIn(directive, csp)

    def test_preview_is_inline_vector_with_seven_separated_thin_wave_bars(self):
        self.assertGreaterEqual(self.html.count("<svg"), 2)
        self.assertEqual(self.html.count('<i class="wave-'), 7)

        wave_layout = re.search(r"\.preview-wave\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        wave_bar = re.search(r"\.preview-wave\s+i\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        self.assertIsNotNone(wave_layout)
        self.assertIsNotNone(wave_bar)
        self.assertRegex(wave_layout.group("body"), r"gap:\s*[4-9]px")
        self.assertRegex(wave_bar.group("body"), r"width:\s*2px")
        self.assertRegex(wave_bar.group("body"), r"border-radius:\s*999px")

    def test_reduced_motion_is_supported(self):
        self.assertRegex(
            self.css,
            r"@media\s*\(prefers-reduced-motion:\s*reduce\)",
        )
        self.assertIn("animation-duration: .01ms", self.css)
        self.assertIn("transition-duration: .01ms", self.css)

    def test_chinese_interface_has_no_decorative_english_section_labels(self):
        self.assertNotIn("APPEARANCE", self.html)
        self.assertNotIn("HISTORY", self.html)
        self.assertNotIn("eyebrow", self.html + self.css)

    def test_global_recording_hotkey_is_visible_and_editable(self):
        self.assertIn('id="hotkeyInput"', self.html)
        self.assertIn('id="hotkeyTestButton"', self.html)
        self.assertIn("全局录音快捷键", self.html)
        self.assertIn("F1～F24", self.html)
        self.assertIn('"save_appearance", submitted.color, submitted.opacity, submitted.hotkey', self.javascript)

    def test_standby_mode_is_explicit_and_local_only(self):
        self.assertIn('id="standbyToggle"', self.html)
        self.assertIn("待命模式", self.html)
        self.assertIn("把“开始”单独说出即可录音", self.html)
        self.assertIn("正文说完稍停，再单独说“结束”", self.html)
        self.assertIn("本地 Zipformer 轻量模型", self.html)
        self.assertIn("只用处理器运行", self.html)
        self.assertIn("待命音频不会上传", self.html)
        self.assertNotIn("Windows 本机识别", self.html)

    def test_local_and_online_models_have_separate_navigation_and_views(self):
        self.assertIn('data-view="localModel"', self.html)
        self.assertIn('data-view="onlineModel"', self.html)
        self.assertIn('id="localModelView"', self.html)
        self.assertIn('id="onlineModelView"', self.html)
        self.assertIn(">本地模式<", self.html)
        self.assertIn(">在线模型<", self.html)
        self.assertNotIn(">语言识别模型<", self.html)
        self.assertIn('id="localEngineOptions"', self.html)
        self.assertIn('id="onlineEngineOptions"', self.html)
        self.assertIn('id="localModelList"', self.html)
        self.assertIn("本地模型与性能要求", self.html)
        self.assertIn("火山引擎、科大讯飞、腾讯云和阿里云", self.html)
        self.assertIn("不包含百度", self.html)
        self.assertIn('value="auto"', self.html)
        self.assertIn('value="cpu"', self.html)
        self.assertIn('value="gpu"', self.html)
        self.assertIn('id="localModelSaveButton"', self.html)
        self.assertIn('id="onlineModelSaveButton"', self.html)
        self.assertIn('id="sidebarPrivacyText"', self.html)
        self.assertIn("本地模式不会上传录音", self.html + self.javascript)
        self.assertIn("在线识别会将录音上传至所选服务", self.javascript)
        self.assertIn('callApi(\n      "save_recognition_settings"', self.javascript)
        self.assertIn('callApi("test_local_model"', self.javascript)
        self.assertIn('callApi("save_provider_credentials"', self.javascript)
        self.assertIn('callApi("delete_provider_credentials"', self.javascript)
        self.assertIn("最低：", self.javascript)
        self.assertIn("建议：", self.javascript)

    def test_realtime_mode_is_chinese_and_saved_with_model_settings(self):
        self.assertIn('id="recognitionModeOptions"', self.html)
        self.assertIn("实时识别", self.html)
        self.assertIn("边说边显示文字", self.html)
        self.assertIn("整段识别", self.html)
        self.assertIn("停止录音后再转换", self.html)
        self.assertIn("selectedRecognitionMode()", self.javascript)
        self.assertNotIn("Realtime", self.html)
        self.assertNotIn("Streaming", self.html)

    def test_model_device_validation_rejects_unknown_value(self):
        api = WebSettingsApi(Mock(), Mock(), store=Mock())
        with patch("settings_panel.update_config") as update_config:
            response = api.save_recognition_settings(
                "local:sensevoice-small-int8", "sensevoice-small-int8", "未知设备"
            )
        self.assertFalse(response["ok"])
        update_config.assert_not_called()

    def test_online_privacy_and_credential_storage_are_explicit(self):
        self.assertIn("会把本次完整录音上传", self.html)
        self.assertIn("可能产生费用", self.html)
        self.assertIn("最长 55 秒", self.html)
        self.assertIn("保存到本机", self.javascript)
        self.assertNotIn("get_provider_credentials", self.javascript)

    def test_preview_and_appearance_controls_are_grouped_on_left(self):
        preview = self.html.split('<article class="card preview-card">', 1)[1].split("</article>", 1)[0]
        controls = self.html.split('<article class="card controls-card">', 1)[1].split("</article>", 1)[0]
        self.assertIn("按钮外观", preview)
        self.assertIn('id="colorPicker"', preview)
        self.assertIn('id="opacityRange"', preview)
        self.assertIn("录音控制", controls)
        self.assertIn('id="hotkeyInput"', controls)
        self.assertIn('id="standbyToggle"', controls)
        self.assertNotIn('id="colorPicker"', controls)
        self.assertNotIn('id="opacityRange"', controls)

    def test_appearance_preview_is_compact_and_has_no_redundant_annotations(self):
        self.assertNotIn("无白色外圈", self.html)
        self.assertNotIn("录音时保持同一主色", self.html)
        self.assertNotIn(".preview-note", self.css)
        self.assertRegex(self.css, r"\.checkerboard\s*\{[^}]*min-height:\s*166px")
        self.assertRegex(self.css, r"\.appearance-color-group\s*\{[^}]*border-top:\s*0")

    def test_appearance_headers_and_control_spacing_are_compact(self):
        self.assertNotIn("实时预览并调整按钮颜色与透明度", self.html)
        self.assertNotIn("设置快捷键和语音待命方式", self.html)
        self.assertRegex(self.css, r"\.preview-card \.opacity-group\s*\{[^}]*border-top:\s*0")
        self.assertRegex(self.css, r"\.controls-card\s*\{[^}]*align-self:\s*start")
        self.assertRegex(self.css, r"\.controls-footer\s*\{[^}]*margin-top:\s*0")

    def test_history_detail_uses_flat_full_width_workspace(self):
        self.assertIn('<div class="history-layout">', self.html)
        self.assertNotIn('<div class="history-layout card">', self.html)
        detail_rule = re.search(
            r"\.detail-content\s+pre\s*\{\s*min-width:(?P<body>.*?)\}",
            self.css,
            re.DOTALL,
        )
        self.assertIsNotNone(detail_rule)
        body = detail_rule.group("body")
        self.assertRegex(body, r"background:\s*transparent")
        self.assertRegex(body, r"border:\s*0")
        self.assertRegex(body, r"border-radius:\s*0")

    def test_history_header_controls_are_integrated_into_workspace(self):
        history = self.html.split('id="historyView"', 1)[1].split("</section>", 1)[0]
        self.assertNotIn('class="page-header history-header"', history)
        self.assertNotIn('class="history-toolbar"', history)
        self.assertRegex(
            history,
            r'class="history-list-toolbar"[\s\S]*?id="historySearch"',
        )
        self.assertRegex(
            history,
            r'class="detail-toolbar"[\s\S]*?id="historyCount"'
            r'[\s\S]*?id="refreshButton"[\s\S]*?id="clearButton"',
        )
        self.assertNotIn("本地记录", history)
        self.assertRegex(self.css, r"#historyView\s*\{[^}]*height:\s*100%")
        history_layout_rule = re.search(
            r"\.history-layout\s*\{(?P<body>.*?)\}",
            self.css,
            re.DOTALL,
        )
        self.assertIsNotNone(history_layout_rule)
        self.assertNotIn("border-top", history_layout_rule.group("body"))

    def test_scrollbar_matches_subtle_obsidian_style(self):
        self.assertRegex(self.css, r"::-webkit-scrollbar\s*\{[^}]*width:\s*10px")
        self.assertRegex(
            self.css,
            r"::-webkit-scrollbar-track[^{]*\{[^}]*background:\s*transparent",
        )
        self.assertRegex(
            self.css,
            r"::-webkit-scrollbar-thumb[^{]*\{[^}]*rgba\(100,\s*116,\s*139,\s*\.11\)",
        )
        self.assertRegex(
            self.css,
            r"::-webkit-scrollbar-button[^{]*\{[^}]*display:\s*none",
        )

    def test_python_panel_is_webview_based_not_tk(self):
        source = (PROJECT_DIR / "settings_panel.py").read_text(encoding="utf-8")
        self.assertIn("webview.create_window", source)
        self.assertIn('gui="edgechromium"', source)
        self.assertNotRegex(source, r"(?i)\b(?:tkinter|ttk)\b")


if __name__ == "__main__":
    unittest.main()
