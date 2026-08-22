import inspect
import re
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from config_store import DEFAULT_REALTIME_MODEL, ZIPFORMER_REALTIME_MODEL
from history_store import HistoryEntry
from settings_panel import WebSettingsApi, main as settings_panel_main


PROJECT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_DIR / "web"


class WebSettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.run_log = Mock()
        self.error_log = Mock()
        self.store = Mock()
        self.api = WebSettingsApi(self.run_log, self.error_log, store=self.store)
        realtime_status = patch(
            "settings_panel.get_realtime_model_status",
            return_value={"available": True},
        )
        realtime_status.start()
        self.addCleanup(realtime_status.stop)

    def test_public_bridge_surface_is_strict_allowlist(self):
        expected = {
            "get_initial_state",
            "save_appearance",
            "test_standby_control",
            "test_hotkey",
            "save_recognition_settings",
            "test_local_model",
            "manage_local_model_resource",
            "save_provider_credentials",
            "delete_provider_credentials",
            "get_history",
            "get_history_signature",
            "copy_history",
            "copy_all_history",
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

    def test_copy_all_joins_every_history_body_and_logs_only_metadata(self):
        entries = [
            HistoryEntry("new", "2026-08-18T10:00:00+08:00", "第一段文字"),
            HistoryEntry("old", "2026-08-18T09:00:00+08:00", "Second paragraph"),
        ]
        self.store.snapshot.return_value = (entries, (2, 9))
        with (
            patch.object(WebSettingsApi, "_panel_hwnd", return_value=24680),
            patch("settings_panel.write_clipboard_text", return_value=True) as write_clipboard,
        ):
            response = self.api.copy_all_history()
        self.assertTrue(response["ok"])
        self.store.snapshot.assert_called_once_with("")
        write_clipboard.assert_called_once_with(
            "第一段文字\r\n\r\nSecond paragraph", 24680
        )
        self.assertNotIn("第一段文字", repr(self.run_log.method_calls))
        self.assertNotIn("Second paragraph", repr(self.run_log.method_calls))

    def test_voice_test_records_then_recognizes_without_history_or_clipboard(self):
        monitor = Mock()
        monitor.stop.return_value = (b"\x01\x00" * 5000, 16000)
        recognizer = Mock()
        recognizer.transcribe_pcm16.return_value = "模拟语音测试结果"
        recognizer.device_label = "处理器"
        catalog = [{"model_id": "sensevoice-small-int8", "available": True}]
        with (
            patch("settings_panel.AudioLevelMonitor", return_value=monitor),
            patch("settings_panel.get_local_model_catalog", return_value=catalog),
            patch("settings_panel.LocalModelRecognizer", return_value=recognizer),
            patch.object(self.api, "_recognition_payload", side_effect=lambda *_args, **_kwargs: {}),
            patch("settings_panel.load_config", return_value={"local_asr_device": "auto"}),
            patch.object(self.api, "_main_window_exists", return_value=False),
        ):
            started = self.api.test_local_model("sensevoice-small-int8", "auto", "start")
            blocked = self.api.test_standby_control("start")
            stopped = self.api.test_local_model("sensevoice-small-int8", "auto", "stop")

        self.assertTrue(started["ok"])
        self.assertTrue(started["data"]["voice_test_active"])
        self.assertFalse(blocked["ok"])
        monitor.start.assert_called_once()
        monitor.stop.assert_called_once()
        recognizer.transcribe_pcm16.assert_called_once()
        self.assertEqual(stopped["data"]["voice_test_text"], "模拟语音测试结果")
        self.store.add.assert_not_called()
        self.assertNotIn("模拟语音测试结果", repr(self.run_log.method_calls))
        self.assertFalse(self.api._test_mode_lease.active)

    def test_delete_failure_from_manager_is_not_reported_as_success(self):
        model_id = "qwen3-asr-1.7b-q5km"
        resource_id = "qwen3-asr-1.7b-q5km"
        manager = Mock()
        manager.resource_ids = {resource_id}
        manager.delete.return_value = {
            "resource_id": resource_id,
            "state": "failed",
            "error": "模型文件正被占用",
        }
        self.api._model_downloads = manager
        payload = {
            "local_models": [{
                "model_id": model_id,
                "resource_status": {
                    "state": "failed",
                    "error": "模型文件正被占用",
                },
            }],
        }
        with (
            patch(
                "settings_panel.get_model_download_resource",
                return_value={"resource_id": resource_id},
            ),
            patch.object(self.api, "_resource_is_in_use", return_value=False),
            patch.object(self.api, "_recognition_payload", return_value=payload),
        ):
            response = self.api.manage_local_model_resource(model_id, "delete")

        self.assertFalse(response["ok"])
        manager.delete.assert_called_once_with(resource_id)

    def test_delete_returns_deleting_before_claiming_files_are_deleted(self):
        model_id = "qwen3-asr-1.7b-q5km"
        resource_id = "qwen3-asr-1.7b-q5km"
        manager = Mock()
        manager.resource_ids = {resource_id}
        manager.delete.return_value = {
            "resource_id": resource_id,
            "state": "deleting",
            "error": None,
        }
        self.api._model_downloads = manager
        payload = {
            "local_models": [{
                "model_id": model_id,
                "resource_status": {"state": "deleting"},
            }],
        }
        with (
            patch(
                "settings_panel.get_model_download_resource",
                return_value={"resource_id": resource_id},
            ),
            patch.object(self.api, "_resource_is_in_use", return_value=False),
            patch.object(self.api, "_recognition_payload", return_value=payload),
        ):
            response = self.api.manage_local_model_resource(model_id, "delete")

        self.assertTrue(response["ok"])
        self.assertEqual(
            response["data"]["local_models"][0]["resource_status"]["state"],
            "deleting",
        )
        self.assertNotIn("已删除", response["message"])

    def test_async_delete_failure_seen_in_payload_is_not_reported_as_success(self):
        model_id = "qwen3-asr-1.7b-q5km"
        resource_id = "qwen3-asr-1.7b-q5km"
        manager = Mock()
        manager.resource_ids = {resource_id}
        manager.delete.return_value = {
            "resource_id": resource_id,
            "state": "deleting",
            "error": None,
        }
        self.api._model_downloads = manager
        payload = {
            "local_models": [{
                "model_id": model_id,
                "resource_id": resource_id,
                "resource_status": {
                    "state": "failed",
                    "error": "模型文件正被占用",
                },
            }],
        }
        with (
            patch(
                "settings_panel.get_model_download_resource",
                return_value={"resource_id": resource_id},
            ),
            patch.object(self.api, "_resource_is_in_use", return_value=False),
            patch.object(self.api, "_recognition_payload", return_value=payload),
        ):
            response = self.api.manage_local_model_resource(model_id, "delete")

        self.assertFalse(response["ok"])
        self.assertIn("模型文件正被占用", response["message"])
        self.assertEqual(
            "failed",
            response["data"]["local_models"][0]["resource_status"]["state"],
        )

    def test_downloadable_model_uses_one_resource_status_snapshot_per_payload(self):
        resource_id = "qwen3-asr-1.7b-q5km"
        manager = Mock()
        manager.resource_ids = {resource_id}
        manager.status.return_value = {
            "resource_id": resource_id,
            "state": "downloading",
            "downloaded_bytes": 123,
            "total_bytes": 456,
            "verified": False,
        }
        self.api._model_downloads = manager
        catalog = [
            {
                "model_id": "qwen3-asr-1.7b-q5km",
                "name": "Qwen3-ASR 1.7B",
                "available": False,
                "downloadable": True,
                "resource_id": resource_id,
            },
        ]
        config = {
            "recognition_engine": "local:qwen3-asr-1.7b-q5km",
            "fallback_model": "sensevoice-small-int8",
            "local_asr_device": "auto",
        }
        with (
            patch("settings_panel.get_local_model_catalog", return_value=catalog),
            patch("settings_panel.get_provider_catalog", return_value=[]),
            patch("settings_panel.get_realtime_model_status", return_value={}),
            patch("settings_panel.choose_model_device", return_value=("cpu", "处理器")),
        ):
            payload = self.api._recognition_payload(config)

        manager.status.assert_called_once_with(resource_id)
        self.assertEqual(
            payload["local_models"][0]["resource_status"],
            manager.status.return_value,
        )

    def test_shutdown_still_pauses_downloads_when_other_cleanup_fails(self):
        manager = Mock()
        self.api._model_downloads = manager
        with (
            patch.object(self.api, "_close_voice_test", side_effect=RuntimeError("busy")),
            patch.object(self.api, "_close_control_test") as close_control,
        ):
            self.api._shutdown()

        close_control.assert_called_once_with()
        manager.shutdown.assert_called_once_with(wait_seconds=2.0)
        self.error_log.exception.assert_called()
        self.assertIn("api._shutdown()", inspect.getsource(settings_panel_main))

    def test_delete_is_rejected_while_voice_test_is_in_inference_stage(self):
        model_id = "qwen3-asr-1.7b-q5km"
        resource_id = "qwen3-asr-1.7b-q5km"
        monitor = Mock()
        monitor.stop.return_value = (b"\x01\x00" * 5000, 16000)
        recognizer = Mock(device_label="处理器")
        manager = Mock()
        manager.resource_ids = {resource_id}
        manager.delete.return_value = {"state": "deleting"}
        self.api._model_downloads = manager
        delete_response = {}

        def transcribe(_pcm, _sample_rate):
            delete_response.update(
                self.api.manage_local_model_resource(model_id, "delete")
            )
            return "推理完成"

        recognizer.transcribe_pcm16.side_effect = transcribe
        catalog = [{"model_id": model_id, "available": True}]
        with (
            patch("settings_panel.AudioLevelMonitor", return_value=monitor),
            patch("settings_panel.get_local_model_catalog", return_value=catalog),
            patch("settings_panel.LocalModelRecognizer", return_value=recognizer),
            patch(
                "settings_panel.get_model_download_resource",
                return_value={"resource_id": resource_id},
            ),
            patch("settings_panel.load_config", return_value={"local_asr_device": "auto"}),
            patch.object(self.api, "_resource_is_in_use", return_value=False),
            patch.object(self.api, "_recognition_payload", return_value={}),
            patch.object(self.api, "_main_window_exists", return_value=False),
        ):
            started = self.api.test_local_model(model_id, "auto", "start")
            stopped = self.api.test_local_model(model_id, "auto", "stop")

        self.assertTrue(started["ok"])
        self.assertTrue(stopped["ok"])
        self.assertFalse(delete_response["ok"])
        self.assertIn("语音测试", delete_response["message"])
        manager.delete.assert_not_called()

    def test_save_rejects_every_unready_downloadable_selected_model_state(self):
        model_id = "qwen3-asr-1.7b-q5km"
        resource_id = "qwen3-asr-1.7b-q5km"
        catalog = [
            {"model_id": model_id, "available": True},
            {"model_id": "sensevoice-small-int8", "available": True},
        ]
        manager = Mock()
        manager.resource_ids = {resource_id}
        self.api._model_downloads = manager
        blocked_states = (
            ("queued", False),
            ("downloading", False),
            ("verifying", False),
            ("pausing", False),
            ("deleting", True),
            ("failed", False),
            ("paused", False),
            ("not_started", False),
            ("completed", False),
        )
        with (
            patch("settings_panel.get_local_model_catalog", return_value=catalog),
            patch("settings_panel.get_provider_catalog", return_value=[]),
            patch("settings_panel.choose_model_device", return_value=("cpu", "处理器")),
            patch(
                "settings_panel.get_model_download_resource",
                side_effect=lambda current: (
                    {"resource_id": resource_id} if current == model_id else None
                ),
            ),
            patch("settings_panel.update_config") as update_config,
        ):
            for resource_state, verified in blocked_states:
                with self.subTest(state=resource_state, verified=verified):
                    manager.status.return_value = {
                        "state": resource_state,
                        "verified": verified,
                    }
                    response = self.api.save_recognition_settings(
                        f"local:{model_id}",
                        "sensevoice-small-int8",
                        "auto",
                        DEFAULT_REALTIME_MODEL,
                    )
                    self.assertFalse(response["ok"])
                    self.assertTrue(response["message"])

        update_config.assert_not_called()

    def test_save_rejects_unverified_downloadable_fallback_model(self):
        model_id = "qwen3-asr-1.7b-q5km"
        resource_id = "qwen3-asr-1.7b-q5km"
        catalog = [
            {"model_id": "sensevoice-small-int8", "available": True},
            {"model_id": model_id, "available": True},
        ]
        manager = Mock()
        manager.resource_ids = {resource_id}
        manager.status.return_value = {"state": "completed", "verified": False}
        self.api._model_downloads = manager
        with (
            patch("settings_panel.get_local_model_catalog", return_value=catalog),
            patch("settings_panel.get_provider_catalog", return_value=[]),
            patch("settings_panel.choose_model_device", return_value=("cpu", "处理器")),
            patch(
                "settings_panel.get_model_download_resource",
                side_effect=lambda current: (
                    {"resource_id": resource_id} if current == model_id else None
                ),
            ),
            patch("settings_panel.update_config") as update_config,
        ):
            response = self.api.save_recognition_settings(
                "local:sensevoice-small-int8",
                model_id,
                "auto",
                DEFAULT_REALTIME_MODEL,
            )

        self.assertFalse(response["ok"])
        self.assertIn("本地备用模型", response["message"])
        self.assertIn("SHA-256", response["message"])
        update_config.assert_not_called()

    def test_save_allows_verified_downloadable_model_as_selected_and_fallback(self):
        selected_model = "qwen3-asr-1.7b-q5km"
        fallback_model = selected_model
        resource_id = "qwen3-asr-1.7b-q5km"
        catalog = [
            {"model_id": selected_model, "available": True},
        ]
        manager = Mock()
        manager.resource_ids = {resource_id}
        manager.status.return_value = {"state": "completed", "verified": True}
        self.api._model_downloads = manager
        updated = {
            "recognition_engine": f"local:{selected_model}",
            "fallback_model": fallback_model,
            "local_asr_device": "auto",
            "realtime_model": DEFAULT_REALTIME_MODEL,
        }
        payload = {
            "device": "处理器",
            "realtime_model": DEFAULT_REALTIME_MODEL,
        }
        with (
            patch("settings_panel.get_local_model_catalog", return_value=catalog),
            patch("settings_panel.get_provider_catalog", return_value=[]),
            patch("settings_panel.choose_model_device", return_value=("cpu", "处理器")),
            patch(
                "settings_panel.get_model_download_resource",
                return_value={"resource_id": resource_id},
            ),
            patch("settings_panel.update_config", return_value=updated) as update_config,
            patch.object(self.api, "_recognition_payload", return_value=payload),
        ):
            response = self.api.save_recognition_settings(
                f"local:{selected_model}",
                fallback_model,
                "auto",
                DEFAULT_REALTIME_MODEL,
            )

        self.assertTrue(response["ok"])
        manager.status.assert_called_once_with(resource_id)
        update_config.assert_called_once_with(updated)

    def test_save_and_delete_are_serialized_across_the_config_commit(self):
        model_id = "qwen3-asr-1.7b-q5km"
        resource_id = "qwen3-asr-1.7b-q5km"
        catalog = [
            {"model_id": model_id, "available": True},
            {"model_id": "sensevoice-small-int8", "available": True},
        ]
        manager = Mock()
        manager.resource_ids = {resource_id}
        manager.status.return_value = {"state": "completed", "verified": True}
        manager.delete.return_value = {"state": "deleting"}
        self.api._model_downloads = manager
        entered_update = threading.Event()
        release_update = threading.Event()
        save_response = {}
        delete_response = {}
        updated = {
            "recognition_engine": f"local:{model_id}",
            "fallback_model": "sensevoice-small-int8",
            "local_asr_device": "auto",
            "realtime_model": DEFAULT_REALTIME_MODEL,
        }

        def slow_update(_changes):
            entered_update.set()
            if not release_update.wait(timeout=2):
                raise RuntimeError("测试未释放保存操作")
            return updated

        with (
            patch("settings_panel.get_local_model_catalog", return_value=catalog),
            patch("settings_panel.get_provider_catalog", return_value=[]),
            patch("settings_panel.choose_model_device", return_value=("cpu", "处理器")),
            patch(
                "settings_panel.get_model_download_resource",
                side_effect=lambda current: (
                    {"resource_id": resource_id} if current == model_id else None
                ),
            ),
            patch("settings_panel.update_config", side_effect=slow_update),
            patch.object(self.api, "_recognition_payload", return_value={
                "device": "处理器",
                "realtime_model": DEFAULT_REALTIME_MODEL,
            }),
            patch.object(self.api, "_resource_is_in_use", return_value=True),
        ):
            save_thread = threading.Thread(
                target=lambda: save_response.update(self.api.save_recognition_settings(
                    f"local:{model_id}",
                    "sensevoice-small-int8",
                    "auto",
                    DEFAULT_REALTIME_MODEL,
                ))
            )
            save_thread.start()
            self.assertTrue(entered_update.wait(timeout=2))
            delete_thread = threading.Thread(
                target=lambda: delete_response.update(
                    self.api.manage_local_model_resource(model_id, "delete")
                )
            )
            delete_thread.start()
            time.sleep(0.05)
            manager.delete.assert_not_called()
            release_update.set()
            save_thread.join(timeout=2)
            delete_thread.join(timeout=2)

        self.assertFalse(save_thread.is_alive())
        self.assertFalse(delete_thread.is_alive())
        self.assertTrue(save_response["ok"])
        self.assertFalse(delete_response["ok"])
        manager.delete.assert_not_called()

    def test_recognition_settings_save_selected_realtime_model(self):
        catalog = [{"model_id": "sensevoice-small-int8", "available": True}]
        payload = {
            "device": "处理器",
            "realtime_model": ZIPFORMER_REALTIME_MODEL,
        }
        updated = {
            "recognition_engine": "local:sensevoice-small-int8",
            "fallback_model": "sensevoice-small-int8",
            "local_asr_device": "auto",
            "realtime_model": ZIPFORMER_REALTIME_MODEL,
        }
        with (
            patch("settings_panel.choose_model_device", return_value=("cpu", "处理器")),
            patch("settings_panel.get_local_model_catalog", return_value=catalog),
            patch("settings_panel.get_provider_catalog", return_value=[]),
            patch("settings_panel.get_realtime_model_status", return_value={"available": True}),
            patch("settings_panel.update_config", return_value=updated) as update_config,
            patch.object(self.api, "_recognition_payload", return_value=payload),
        ):
            response = self.api.save_recognition_settings(
                "local:sensevoice-small-int8",
                "sensevoice-small-int8",
                "auto",
                ZIPFORMER_REALTIME_MODEL,
            )

        self.assertTrue(response["ok"])
        update_config.assert_called_once_with(updated)

    def test_unknown_realtime_model_is_rejected(self):
        with patch("settings_panel.update_config") as update_config:
            response = self.api.save_recognition_settings(
                "local:sensevoice-small-int8",
                "sensevoice-small-int8",
                "auto",
                "unknown-streaming-model",
            )
        self.assertFalse(response["ok"])
        self.assertIn("实时显示模型", response["message"])
        update_config.assert_not_called()

    def test_unavailable_realtime_model_is_rejected(self):
        with (
            patch("settings_panel.get_realtime_model_status", return_value={"available": False}),
            patch("settings_panel.update_config") as update_config,
        ):
            response = self.api.save_recognition_settings(
                "local:sensevoice-small-int8",
                "sensevoice-small-int8",
                "auto",
                ZIPFORMER_REALTIME_MODEL,
            )
        self.assertFalse(response["ok"])
        self.assertIn("尚未安装完整", response["message"])
        update_config.assert_not_called()


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
        self.assertNotIn("siriwave.umd.min.js", resources)
        self.assertNotIn("mock-bridge.js", self.html)
        self.assertNotIn("recording-button-lab", self.html)
        self.assertTrue(all(not re.match(r"(?:https?:)?//", item) for item in resources))
        self.assertNotRegex(self.html, r"(?i)<style(?:\s|>)")
        self.assertNotRegex(self.html, r"(?i)\sstyle\s*=")
        self.assertNotRegex(self.html, r"(?i)<script[^>]*>(?:(?!</script>).)+</script>")
        self.assertNotRegex(self.html, r"(?i)\son[a-z]+\s*=")
        self.assertNotIn("innerHTML", self.javascript)
        self.assertNotRegex(self.html + self.css + self.javascript, r"https?://")

    def test_typography_uses_four_shared_sizes_plus_confirmed_larger_brand(self):
        expected_tokens = {
            "small": "13px",
            "body": "14px",
            "heading": "16px",
            "page-title": "32px",
        }
        tokens = dict(re.findall(
            r"--font-size-([a-z-]+)\s*:\s*([^;]+);",
            self.css,
        ))
        self.assertEqual(tokens, expected_tokens)

        declarations = re.findall(r"(?<!-)font-size\s*:\s*([^;]+);", self.css)
        allowed = {f"var(--font-size-{name})" for name in expected_tokens}
        self.assertTrue(declarations)
        self.assertLessEqual(len(tokens), 4)
        self.assertEqual(set(declarations) - {"16px", "18px"}, allowed)
        self.assertEqual(declarations.count("16px"), 1)
        self.assertEqual(declarations.count("18px"), 1)
        self.assertRegex(
            self.css,
            r"\.brand strong\s*\{[^}]*font-size:\s*18px",
        )
        self.assertRegex(
            self.css,
            r"button,\s*input,\s*select,\s*textarea\s*\{\s*font:\s*inherit;",
        )
    def test_brand_uses_product_name_and_local_app_icon(self):
        brand = self.html.split('<div class="brand">', 1)[1].split("</div>", 2)[0]
        self.assertIn("<strong>语点</strong>", self.html)
        self.assertIn('src="app-icon.png"', self.html)
        self.assertNotIn("设置与历史记录", brand)
        self.assertNotIn("<strong>语音识别软件</strong>", brand)
        self.assertNotIn("<strong>悬浮语音按钮</strong>", brand)
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

    def test_preview_matches_shared_recording_button_lab_visual(self):
        self.assertGreaterEqual(self.html.count("<svg"), 2)
        self.assertIn('class="preview-button is-standby"', self.html)
        self.assertIn('class="preview-button is-recording"', self.html)
        self.assertIn('id="recordingLayeredWave"', self.html)
        self.assertEqual(self.html.count("preview-layered-wave-path-back"), 2)
        self.assertEqual(self.html.count("preview-layered-wave-path-middle"), 2)
        self.assertEqual(self.html.count("preview-layered-wave-path-front"), 2)
        self.assertIn('id="previewWaveFrontGradient"', self.html)
        self.assertIn('role="img" aria-label="待机状态按钮预览"', self.html)
        self.assertIn('role="img" aria-label="录音状态按钮预览"', self.html)
        self.assertIn('color-mix(in srgb, var(--button-color) 82%, transparent)', self.css)
        self.assertIn('url("voice-button-background-01.png")', self.css)
        self.assertIn('.preview-button.is-standby .preview-layered-wave-path-middle', self.css)
        self.assertIn("buildRecordingPreviewPoints", self.javascript)
        self.assertIn("renderRecordingPreviewWave", self.javascript)
        self.assertIn("window.requestAnimationFrame(tickRecordingPreview)", self.javascript)
        self.assertIn("initializeRecordingPreviewMotion()", self.javascript)
        self.assertTrue((WEB_DIR / "voice-button-background-01.png").is_file())
        self.assertGreater((WEB_DIR / "voice-button-background-01.png").stat().st_size, 0)

    def test_reduced_motion_is_supported(self):
        self.assertRegex(
            self.css,
            r"@media\s*\(prefers-reduced-motion:\s*reduce\)",
        )
        self.assertIn("animation-duration: .01ms", self.css)
        self.assertIn("transition-duration: .01ms", self.css)
        self.assertIn('matchMedia("(prefers-reduced-motion: reduce)")', self.javascript)
        self.assertIn('document.addEventListener("visibilitychange", syncRecordingPreviewMotion)', self.javascript)
        self.assertIn('window.addEventListener("pagehide"', self.javascript)

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
        self.assertNotIn("把“开始”单独说出即可录音", self.html)
        self.assertNotIn("正文说完稍停，再单独说“结束”", self.html)
        self.assertNotIn("安静时显示平线", self.html)
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
        self.assertIn("本地识别模型", self.html)
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
        self.assertIn('"最低配置"', self.javascript)
        self.assertIn('"建议配置"', self.javascript)

    def test_realtime_models_match_confirmed_local_mode_preview(self):
        self.assertIn('id="realtimeModelOptions"', self.html)
        self.assertIn('class="view local-mode-view local-mode-v3"', self.html)
        self.assertIn('class="card recognition-card local-consistent-card realtime-model-row"', self.html)
        self.assertIn('id="localDeviceHeading"', self.html)
        self.assertIn("实时显示模型", self.html)
        self.assertIn("选择边说边显示文字的模型。", self.html)
        self.assertIn('name="realtimeModel" value="streaming-paraformer-bilingual-zh-en"', self.html)
        self.assertIn('name="realtimeModel" value="zipformer-bilingual-zh-en-exp32-int8"', self.html)
        self.assertIn("Streaming Paraformer", self.html)
        self.assertIn("Zipformer", self.html)
        self.assertIn("selectedRealtimeModel()", self.javascript)
        self.assertIn("state.model.realtime_model", self.javascript)
        self.assertIn('"save_recognition_settings",', self.javascript)
        self.assertIn("selectedRealtimeModel(),", self.javascript)
        self.assertNotIn("识别后自动校正", self.html + self.javascript)
        self.assertNotIn("保留格式原文", self.html + self.javascript)
        self.assertNotIn("autoCorrection", self.html + self.javascript)
        self.assertNotIn("auto_correction_enabled", self.javascript)
        self.assertNotIn("recognition_mode", self.javascript)
        self.assertNotIn("download_local_model", self.javascript)
        self.assertNotIn('id="recognitionModeOptions"', self.html)

    def test_model_resource_panel_is_not_shown_in_local_model_details(self):
        self.assertNotIn('resourcePanel.className = "model-resource-panel"', self.javascript)
        self.assertNotIn(".model-resource-panel", self.css)
        self.assertIn('"button", "model-card-download"', self.javascript)
        self.assertIn('label.style.setProperty("--download-progress"', self.javascript)
        self.assertIn(".engine-option.is-downloadable::before", self.css)
        self.assertIn("width: var(--download-progress, 0%)", self.css)
        self.assertIn(".engine-option.is-unavailable", self.css)
        self.assertIn("border-left: 0", self.css)

    def test_visible_page_resumes_model_resource_status_polling(self):
        self.assertIn(
            'document.addEventListener("visibilitychange", scheduleModelResourcePoll);',
            self.javascript,
        )
        self.assertIn("window.clearTimeout(state.modelResourceTimer)", self.javascript)

    def test_model_resource_poll_applies_failure_payload_and_stops_stale_deleting_ui(self):
        polling = re.search(
            r"function scheduleModelResourcePoll\(\)\s*\{(?P<body>.*?)\n\}",
            self.javascript,
            re.DOTALL,
        )
        self.assertIsNotNone(polling)
        body = polling.group("body")
        self.assertIn("if (error.data)", body)
        self.assertIn("syncModelControls(error.data)", body)
        self.assertIn("showToast(error.message, true)", body)

    def test_live_transcript_window_can_be_hidden(self):
        self.assertIn('id="transcriptToggle"', self.html)
        self.assertIn("实时文字框", self.html)
        self.assertIn("submitted.transcript", self.javascript)

    def test_auto_paste_can_be_disabled_without_disabling_recognition(self):
        self.assertIn('id="autoPasteToggle"', self.html)
        self.assertIn("识别后自动输入", self.html)
        self.assertIn("关闭后只保存历史并复制到剪贴板", self.html)
        self.assertIn("submitted.autoPaste", self.javascript)
        self.assertIn("auto_paste_enabled", self.javascript)

    def test_standby_explanatory_paragraphs_are_removed(self):
        self.assertNotIn("把“开始”单独说出即可录音", self.html)
        self.assertNotIn("安静时显示平线", self.html)

    def test_confidence_and_test_layout_uses_two_compact_rows(self):
        title_row = self.html.split('class="confidence-title-row"', 1)[1].split("</div>", 1)[0]
        range_row = self.html.split('class="confidence-range-row"', 1)[1].split("</div>", 1)[0]
        self.assertIn("匹配置信度", title_row)
        self.assertIn('id="controlWordTestButton"', title_row)
        self.assertIn('id="standbyConfidence"', range_row)
        self.assertIn('id="standbyConfidenceValue"', range_row)
        self.assertIn('for="standbyConfidence"', range_row)
        self.assertIn('aria-pressed="false"', title_row)

    def test_local_models_show_language_support_without_voice_test_button(self):
        self.assertIn('class="local-model-workspace"', self.html)
        self.assertIn(".local-model-workspace", self.css)
        self.assertIn("grid-template-columns: minmax(230px, .72fr) minmax(0, 1.65fr)", self.css)
        self.assertIn("align-items: stretch", self.css)
        self.assertIn("grid-auto-rows: auto", self.css)
        self.assertIn("align-content: start", self.css)
        self.assertIn(".local-model-spec:nth-last-child(-n + 2)", self.css)
        self.assertIn(".local-model-workspace .engine-option", self.css)
        self.assertIn("min-height: 64px", self.css)
        self.assertIn("height: 272px", self.css)
        self.assertIn("height: 368px", self.css)
        self.assertNotIn("height: 271px", self.css)
        self.assertIn("model.language_support", self.javascript)
        self.assertIn("支持中文和英文", str(__import__("local_asr").LOCAL_MODELS))
        self.assertNotIn("热词", self.javascript)
        self.assertIn('row.className = "local-model-row local-model-detail"', self.javascript)
        self.assertIn('headingCopy.className = "local-model-heading-copy"', self.javascript)
        self.assertIn("headingCopy.append(statusCell, name)", self.javascript)
        self.assertNotIn("heading.append(test)", self.javascript)
        self.assertIn(".local-model-heading-copy", self.css)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto", self.css)
        self.assertIn("width: 100%", self.css)
        self.assertIn("padding-top: 8px", self.css)
        self.assertIn("grid-column: 1", self.css)
        self.assertNotIn(".model-test-button", self.css)
        self.assertIn(".status-pill::before", self.css)
        self.assertIn('details.className = "local-model-specs"', self.javascript)

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

    def test_appearance_and_recording_sections_keep_all_existing_controls(self):
        preview = self.html.split('<article class="card preview-card">', 1)[1].split("</article>", 1)[0]
        controls = self.html.split('<article class="card controls-card">', 1)[1].split("</article>", 1)[0]
        self.assertIn("按钮外观", preview)
        self.assertIn('id="colorPicker"', preview)
        self.assertIn('id="opacityRange"', preview)
        self.assertIn("录音控制", controls)
        self.assertIn('id="hotkeyInput"', controls)
        self.assertIn('id="standbyToggle"', controls)
        self.assertIn('id="autoPasteToggle"', controls)
        self.assertEqual(preview.count('class="swatch-'), 8)
        self.assertNotIn('id="colorPicker"', controls)
        self.assertNotIn('id="opacityRange"', controls)

    def test_history_bulk_actions_and_delete_buttons_have_requested_hierarchy(self):
        history = self.html.split('id="historyView"', 1)[1]
        self.assertIn('class="button button-secondary detail-clear-button" id="clearButton"', history)
        self.assertIn('id="copyAllButton"', history)
        self.assertIn("复制全部", history)
        self.assertIn('class="button button-secondary" id="deleteButton"', history)
        self.assertNotIn('class="button button-secondary danger-text" id="deleteButton"', history)
        self.assertIn('callApi("copy_all_history")', self.javascript)

    def test_recording_controls_use_two_compact_subcards(self):
        rules = re.findall(
            r"\.appearance-grid\s*>\s*\.controls-card\s*\{(?P<body>.*?)\}",
            self.css,
            re.DOTALL,
        )
        grid = re.search(r"\.control-card-grid\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        subcard = re.search(r"\.control-setting-card\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        self.assertTrue(rules)
        self.assertIsNotNone(grid)
        self.assertIsNotNone(subcard)
        self.assertRegex(rules[-1], r"background:\s*transparent")
        self.assertRegex(rules[-1], r"border:\s*0")
        self.assertRegex(grid.group("body"), r"grid-template-columns:\s*repeat\(2")
        self.assertRegex(subcard.group("body"), r"background:\s*var\(--surface\)")
        self.assertRegex(subcard.group("body"), r"border:\s*1px solid")
        self.assertRegex(subcard.group("body"), r"border-radius:\s*8px")
        self.assertIn('class="control-setting-card recording-card"', self.html)
        self.assertIn('class="control-setting-card confidence-card"', self.html)

    def test_recording_global_actions_are_outside_confidence_card(self):
        controls = self.html.split('<article class="card controls-card">', 1)[1].split("</article>", 1)[0]
        confidence = re.search(
            r'<section class="control-setting-card confidence-card".*?</section>',
            controls,
            re.DOTALL,
        )
        footer = re.search(
            r'<div class="controls-footer controls-global-footer".*?</div>',
            controls,
            re.DOTALL,
        )
        self.assertIsNotNone(confidence)
        self.assertIsNotNone(footer)
        self.assertNotIn('id="resetButton"', confidence.group(0))
        self.assertNotIn('id="saveButton"', confidence.group(0))
        self.assertIn('id="resetButton"', footer.group(0))
        self.assertIn('id="saveButton"', footer.group(0))
        self.assertIn('grid-area: actions', self.css)
        self.assertIn('grid-area: confidence', self.css)

    def test_recording_labels_share_body_size_and_primary_color(self):
        self.assertRegex(
            self.css,
            r"\.recording-card \.hotkey-group > label\s*\{[^}]*font-size:\s*var\(--font-size-body\)",
        )
        self.assertIn(
            ".confidence-title-row .setting-label { color: var(--text); font-size: var(--font-size-body); }",
            self.css,
        )
    def test_card_containers_are_visually_flat_and_preview_stays_functional(self):
        self.assertNotIn("无白色外圈", self.html)
        self.assertNotIn("录音时保持同一主色", self.html)
        self.assertNotIn(".preview-note", self.css)
        card_rule = re.search(r"\.card\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        checker_rule = re.search(r"\.checkerboard\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        self.assertIsNotNone(card_rule)
        self.assertIsNotNone(checker_rule)
        self.assertRegex(card_rule.group("body"), r"background:\s*transparent")
        self.assertRegex(card_rule.group("body"), r"border:\s*0")
        self.assertRegex(card_rule.group("body"), r"border-radius:\s*0")
        self.assertRegex(card_rule.group("body"), r"box-shadow:\s*none")
        self.assertRegex(checker_rule.group("body"), r"min-height:\s*72px")
        self.assertRegex(checker_rule.group("body"), r"border-radius:\s*0")

    def test_appearance_preview_is_large_and_keeps_all_eight_colors(self):
        preview_card_rules = re.findall(r"\.preview-card\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        checker_rules = re.findall(r"\.checkerboard\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        preview_rules = re.findall(r"\.preview-button\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        color_group_rules = re.findall(r"\.appearance-color-group\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        swatches_rules = re.findall(r"\.appearance-color-group\s*>\s*\.swatches\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        self.assertTrue(preview_card_rules)
        self.assertTrue(checker_rules)
        self.assertTrue(preview_rules)
        self.assertTrue(color_group_rules)
        self.assertTrue(swatches_rules)
        self.assertTrue(any(
            re.search(r"grid-template-columns:\s*142px[^;]*minmax\(202px,\s*1fr\)[^;]*221px", body)
            for body in preview_card_rules
        ))
        self.assertTrue(any(re.search(r"justify-content:\s*flex-start", body) for body in checker_rules))
        self.assertTrue(any(re.search(r"background:\s*transparent", body) for body in checker_rules))
        self.assertTrue(any(re.search(r"width:\s*64px", body) for body in preview_rules))
        self.assertTrue(any(re.search(r"height:\s*64px", body) for body in preview_rules))
        self.assertRegex(color_group_rules[-1], r"width:\s*202px")
        self.assertRegex(swatches_rules[-1], r"width:\s*202px")
        self.assertIn('class="field-group appearance-preview-group"', self.html)
        self.assertIn('class="opacity-control"', self.html)
        self.assertEqual(self.html.count('class="swatch-'), 8)
        self.assertRegex(self.css, r"\.appearance-preview-group\s*>\s*\.checkerboard\s*\{[^}]*grid-column:\s*1[^}]*grid-row:\s*2")
        self.assertRegex(self.css, r"\.appearance-color-group\s*>\s*\.color-control\s*\{[^}]*grid-column:\s*1[^}]*grid-row:\s*2")
        self.assertRegex(self.css, r"\.preview-card\s*>\s*\.appearance-color-group\s*>\s*\.swatches\s*\{[^}]*grid-column:\s*1[^}]*grid-row:\s*3")
        self.assertRegex(self.css, r"\.opacity-control\s*\{[^}]*grid-column:\s*1[^}]*grid-row:\s*2")
        self.assertRegex(self.css, r"\.color-control\s*\{[^}]*width:\s*202px")
        self.assertRegex(self.css, r"\.swatches\s*\{[^}]*justify-content:\s*flex-start")
        self.assertRegex(self.css, r"\.opacity-control\s*\{[^}]*min-height:\s*72px")
        self.assertRegex(self.css, r"@media\s*\(max-width:\s*680px\)[\s\S]*?\.preview-card\s*\{[^}]*grid-template-columns:\s*1fr")

    def test_settings_use_desktop_label_control_rows_and_dividers(self):
        field_rule = re.search(r"^\.field-group\s*\{(?P<body>.*?)\}", self.css, re.DOTALL | re.MULTILINE)
        standby_rule = re.search(r"^\.standby-row\s*\{(?P<body>.*?)\}", self.css, re.DOTALL | re.MULTILINE)
        self.assertIsNotNone(field_rule)
        self.assertIsNotNone(standby_rule)
        for body in (field_rule.group("body"), standby_rule.group("body")):
            self.assertRegex(body, r"display:\s*grid")
            self.assertRegex(body, r"grid-template-columns:\s*minmax\(180px")
        self.assertRegex(field_rule.group("body"), r"border-top:\s*1px solid var\(--border\)")
        self.assertRegex(self.css, r"@media\s*\(max-width:\s*680px\)[\s\S]*?\.field-group,[\s\S]*?grid-template-columns:\s*1fr")

    def test_content_surface_is_white_full_width_and_actions_are_not_floating(self):
        root_rule = re.search(r":root\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        main_rule = re.search(r"\.main-content\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        view_rule = re.search(r"\.view\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        save_rule = re.search(r"\.model-save-bar\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        stack_rule = re.search(r"\.recognition-stack\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        for rule in (root_rule, main_rule, view_rule, save_rule, stack_rule):
            self.assertIsNotNone(rule)
        self.assertRegex(root_rule.group("body"), r"--page:\s*#ffffff")
        self.assertRegex(main_rule.group("body"), r"background:\s*var\(--surface\)")
        self.assertRegex(view_rule.group("body"), r"width:\s*100%")
        self.assertRegex(view_rule.group("body"), r"margin:\s*0")
        self.assertRegex(save_rule.group("body"), r"position:\s*static")
        self.assertRegex(save_rule.group("body"), r"border-top:\s*1px solid var\(--border\)")
        self.assertRegex(save_rule.group("body"), r"border-radius:\s*0")
        self.assertRegex(save_rule.group("body"), r"box-shadow:\s*none")
        self.assertNotRegex(save_rule.group("body"), r"position:\s*sticky")
        self.assertRegex(stack_rule.group("body"), r"padding-bottom:\s*0")

    def test_plain_model_provider_and_notice_rows_use_dividers(self):
        local_row = re.search(r"\.local-model-row\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        provider = re.search(r"\.provider-card\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        notice = re.search(r"\.upload-notice\s*\{(?P<body>.*?)\}", self.css, re.DOTALL)
        for rule in (local_row, provider, notice):
            self.assertIsNotNone(rule)
            self.assertRegex(rule.group("body"), r"background:\s*transparent|border-bottom:\s*1px solid var\(--border\)")
            self.assertRegex(rule.group("body"), r"border-radius:\s*0")
        self.assertRegex(local_row.group("body"), r"border-bottom:\s*1px solid var\(--border\)")
        self.assertRegex(provider.group("body"), r"border-bottom:\s*1px solid var\(--border\)")
        self.assertRegex(notice.group("body"), r"border-left:\s*3px solid")

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
