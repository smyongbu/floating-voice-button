import unittest

import app
from config_store import (
    DEFAULT_LOCAL_MODEL,
    DEFAULT_REALTIME_MODEL,
    DEFAULT_RECOGNITION_ENGINE,
    _normalize,
    normalize_hex_color,
    normalize_recognition_engine,
    normalize_realtime_model,
)
from global_hotkey import parse_hotkey


class ConfigTests(unittest.TestCase):
    def test_default_paste_wait_is_non_negative(self):
        self.assertGreaterEqual(app.DEFAULT_CONFIG["paste_wait_ms"], 0)

    def test_auto_paste_defaults_on_and_can_be_disabled(self):
        self.assertIs(app.DEFAULT_CONFIG["auto_paste_enabled"], True)
        self.assertIs(_normalize({"auto_paste_enabled": False})["auto_paste_enabled"], False)

    def test_button_size_is_in_supported_range(self):
        self.assertGreaterEqual(app.DEFAULT_CONFIG["button_size"], 64)
        self.assertLessEqual(app.DEFAULT_CONFIG["button_size"], 80)

    def test_appearance_defaults_are_valid(self):
        self.assertEqual(normalize_hex_color(app.DEFAULT_CONFIG["button_color"]), "#103E83")
        self.assertGreaterEqual(app.DEFAULT_CONFIG["button_opacity"], 30)
        self.assertLessEqual(app.DEFAULT_CONFIG["button_opacity"], 100)

    def test_deep_theme_migrates_only_old_default_and_preserves_preferences(self):
        old = {"config_version":13,"button_color":"#2563EB","button_size":80,"button_opacity":75,"x":123,"y":456}
        result = _normalize(old)
        self.assertEqual(result["button_color"], "#103E83")
        self.assertEqual(result["button_size"], 80)
        self.assertEqual(result["button_opacity"], 75)
        self.assertEqual(_normalize({**old,"button_color":"#aabbcc"})["button_color"], "#AABBCC")
        self.assertEqual(_normalize({**old,"config_version":14})["button_color"], "#2563EB")
        self.assertEqual(_normalize(result), result)

    def test_default_global_hotkey_is_safe_and_valid(self):
        parsed = parse_hotkey(app.DEFAULT_CONFIG["global_hotkey"])
        self.assertEqual(parsed.label, "Ctrl+Alt+Space")
        self.assertTrue(parsed.modifiers & 0x4000)

    def test_standby_mode_defaults_to_off(self):
        self.assertIs(app.DEFAULT_CONFIG["standby_enabled"], False)
        self.assertEqual(app.DEFAULT_CONFIG["standby_confidence"], 80)
        self.assertEqual(_normalize({"standby_confidence": 20})["standby_confidence"], 70)
        self.assertEqual(_normalize({"standby_confidence": 120})["standby_confidence"], 100)

    def test_live_transcript_window_defaults_to_visible(self):
        self.assertIs(app.DEFAULT_CONFIG["live_transcript_visible"], True)
        self.assertIs(_normalize({"live_transcript_visible": False})["live_transcript_visible"], False)

    def test_recognition_defaults_to_local_without_network(self):
        self.assertEqual(
            app.DEFAULT_CONFIG["recognition_engine"], DEFAULT_RECOGNITION_ENGINE
        )
        self.assertNotIn("fallback_model", app.DEFAULT_CONFIG)
        self.assertEqual(app.DEFAULT_CONFIG["realtime_model"], DEFAULT_REALTIME_MODEL)
        self.assertNotIn("recognition_mode", app.DEFAULT_CONFIG)
        self.assertNotIn("auto_correction_enabled", app.DEFAULT_CONFIG)

    def test_removed_realtime_model_migrates_to_paraformer(self):
        self.assertEqual(normalize_realtime_model(DEFAULT_REALTIME_MODEL), DEFAULT_REALTIME_MODEL)
        self.assertEqual(
            normalize_realtime_model("zipformer-bilingual-zh-en-exp32-int8"),
            DEFAULT_REALTIME_MODEL,
        )
        self.assertEqual(normalize_realtime_model("未知"), DEFAULT_REALTIME_MODEL)

    def test_removed_recognition_and_correction_fields_are_not_migrated(self):
        config = _normalize({
            "recognition_mode": "batch",
            "auto_correction_enabled": True,
        })
        self.assertNotIn("recognition_mode", config)
        self.assertNotIn("auto_correction_enabled", config)
        self.assertEqual(config["realtime_model"], DEFAULT_REALTIME_MODEL)

    def test_old_service_choices_migrate_to_local_and_discard_fallback(self):
        for value in ("online:xfyun", "cloud:xfyun", "online:aliyun", "cloud:tencent", "volcengine", "iflytek"):
            with self.subTest(value=value):
                self.assertEqual(normalize_recognition_engine(value), DEFAULT_RECOGNITION_ENGINE)
                config = _normalize({"recognition_engine": value, "fallback_model": "qwen3-asr-0.6b-int8"})
                self.assertEqual(config["recognition_engine"], DEFAULT_RECOGNITION_ENGINE)
                self.assertNotIn("fallback_model", config)

    def test_valid_local_models_and_invalid_values_are_normalized(self):
        self.assertEqual(
            normalize_recognition_engine("local:paraformer-zh-small-int8"),
            "local:faster-whisper-small",
        )
        self.assertEqual(
            normalize_recognition_engine("local:faster-whisper-small"),
            "local:faster-whisper-small",
        )
        self.assertEqual(
            normalize_recognition_engine("local:qwen3-asr-1.7b-q5km"),
            "local:qwen3-asr-1.7b-q5km",
        )
        self.assertEqual(
            normalize_recognition_engine("local:qwen3-asr-1.7b-q5km-hotwords"),
            "local:qwen3-asr-1.7b-q5km",
        )
        self.assertEqual(
            normalize_recognition_engine("cloud:unknown"),
            DEFAULT_RECOGNITION_ENGINE,
        )

    def test_secret_fields_are_never_kept_in_plain_config(self):
        config = _normalize({
            "recognition_engine": "cloud:tencent",
            "api_key": "绝不能保存",
            "secret_id": "绝不能保存",
            "credentials": {"token": "绝不能保存"},
        })
        self.assertEqual(config["recognition_engine"], DEFAULT_RECOGNITION_ENGINE)
        self.assertNotIn("api_key", config)
        self.assertNotIn("secret_id", config)
        self.assertNotIn("credentials", config)

    def test_unknown_legacy_config_is_removed(self):
        config = _normalize({
            "transcription_wait_ms": 900,
            "transcription_poll_ms": 250,
            "transcription_stable_checks": 3,
            "legacy_window_keywords": ["旧窗口"],
        })
        for key in (
            "transcription_wait_ms", "transcription_poll_ms",
            "transcription_stable_checks", "legacy_window_keywords",
        ):
            self.assertNotIn(key, config)


if __name__ == "__main__":
    unittest.main()


class RemovedModelMigrationTest(unittest.TestCase):
    def test_removed_qwen_selection_migrates_without_changing_other_settings(self):
        config = _normalize({"recognition_engine": "local:qwen3-asr-0.6b-int8", "button_color": "#16A34A"})
        self.assertEqual(config["recognition_engine"], "local:faster-whisper-small")
        self.assertEqual(config["button_color"], "#16A34A")
