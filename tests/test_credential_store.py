import json
import unittest
from unittest.mock import patch

import credential_store


class CredentialStoreTests(unittest.TestCase):
    def test_target_is_stable_and_provider_is_normalized(self):
        self.assertEqual(
            credential_store.credential_target(" Tencent "),
            "FloatingVoiceButton/CloudASR/tencent",
        )
        with self.assertRaisesRegex(ValueError, "服务标识无效"):
            credential_store.credential_target("../腾讯")

    def test_save_serializes_utf8_credentials_to_windows_store(self):
        captured = {}

        def fake_write(target, username, payload):
            captured.update(target=target, username=username, payload=payload)

        store = credential_store.CredentialStore()
        with patch.object(credential_store, "_write_raw", side_effect=fake_write):
            store.save("iflytek", {"app_id": "中文应用", "api_secret": "仅用于测试"})

        self.assertEqual(captured["username"], "iflytek")
        self.assertEqual(
            json.loads(captured["payload"].decode("utf-8")),
            {"api_secret": "仅用于测试", "app_id": "中文应用"},
        )

    def test_load_delete_and_exists_delegate_to_credential_manager(self):
        store = credential_store.CredentialStore()
        payload = json.dumps({"secret_key": "测试密钥"}, ensure_ascii=False).encode("utf-8")
        with patch.object(credential_store, "_read_raw", return_value=payload):
            self.assertEqual(store.load("tencent"), {"secret_key": "测试密钥"})
            self.assertTrue(store.exists("tencent"))
        with patch.object(credential_store, "_delete_raw", return_value=True) as delete:
            self.assertTrue(store.delete("tencent"))
            delete.assert_called_once_with("FloatingVoiceButton/CloudASR/tencent")

    def test_corrupted_value_error_never_contains_stored_bytes(self):
        sensitive = b"REAL_SECRET_SHOULD_NOT_APPEAR"
        with patch.object(credential_store, "_read_raw", return_value=sensitive):
            with self.assertRaises(credential_store.CredentialStoreError) as raised:
                credential_store.CredentialStore().load("aliyun")
        self.assertNotIn("REAL_SECRET_SHOULD_NOT_APPEAR", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
