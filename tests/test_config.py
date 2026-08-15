import unittest

import app
from config_store import (
    DEFAULT_LOCAL_MODEL,
    DEFAULT_RECOGNITION_ENGINE,
    _normalize,
    normalize_fallback_model,
    normalize_hex_color,
    normalize_recognition_engine,
    normalize_recognition_mode,
)
from global_hotkey import parse_hotkey


class ConfigTests(unittest.TestCase):
    def test_default_paste_wait_is_non_negative(self):
        self.assertGreaterEqual(app.DEFAULT_CONFIG["paste_wait_ms"], 0)

    def test_button_size_is_in_supported_range(self):
        self.assertGreaterEqual(app.DEFAULT_CONFIG["button_size"], 48)
        self.assertLessEqual(app.DEFAULT_CONFIG["button_size"], 96)

    def test_appearance_defaults_are_valid(self):
        self.assertEqual(normalize_hex_color(app.DEFAULT_CONFIG["button_color"]), "#2563EB")
        self.assertGreaterEqual(app.DEFAULT_CONFIG["button_opacity"], 30)
        self.assertLessEqual(app.DEFAULT_CONFIG["button_opacity"], 100)

    def test_default_global_hotkey_is_safe_and_valid(self):
        parsed = parse_hotkey(app.DEFAULT_CONFIG["global_hotkey"])
        self.assertEqual(parsed.label, "Ctrl+Alt+Space")
        self.assertTrue(parsed.modifiers & 0x4000)

    def test_standby_mode_defaults_to_off(self):
        self.assertIs(app.DEFAULT_CONFIG["standby_enabled"], False)

    def test_recognition_defaults_to_local_without_network(self):
        self.assertEqual(
            app.DEFAULT_CONFIG["recognition_engine"], DEFAULT_RECOGNITION_ENGINE
        )
        self.assertEqual(app.DEFAULT_CONFIG["fallback_model"], DEFAULT_LOCAL_MODEL)
        self.assertEqual(app.DEFAULT_CONFIG["recognition_mode"], "realtime")

    def test_recognition_mode_accepts_only_realtime_or_batch(self):
        self.assertEqual(normalize_recognition_mode("realtime"), "realtime")
        self.assertEqual(normalize_recognition_mode("batch"), "batch")
        self.assertEqual(normalize_recognition_mode("未知"), "realtime")

    def test_old_online_and_xfyun_names_are_migrated(self):
        self.assertEqual(
            normalize_recognition_engine("online:xfyun"), "cloud:iflytek"
        )
        self.assertEqual(
            normalize_recognition_engine("cloud:xfyun"), "cloud:iflytek"
        )
        self.assertEqual(
            normalize_recognition_engine("online:aliyun"), "cloud:aliyun"
        )

    def test_valid_local_models_and_invalid_values_are_normalized(self):
        self.assertEqual(
            normalize_recognition_engine("local:paraformer-zh-small-int8"),
            "local:paraformer-zh-small-int8",
        )
        self.assertEqual(
            normalize_recognition_engine("local:faster-whisper-small"),
            "local:faster-whisper-small",
        )
        self.assertEqual(
            normalize_recognition_engine("cloud:unknown"),
            DEFAULT_RECOGNITION_ENGINE,
        )
        self.assertEqual(
            normalize_fallback_model("local:qwen3-asr-0.6b-int8"),
            "qwen3-asr-0.6b-int8",
        )
        self.assertEqual(normalize_fallback_model("unknown"), DEFAULT_LOCAL_MODEL)

    def test_secret_fields_are_never_kept_in_plain_config(self):
        config = _normalize({
            "recognition_engine": "cloud:tencent",
            "api_key": "绝不能保存",
            "secret_id": "绝不能保存",
            "credentials": {"token": "绝不能保存"},
        })
        self.assertEqual(config["recognition_engine"], "cloud:tencent")
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
