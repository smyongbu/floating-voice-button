import unittest
from unittest.mock import MagicMock

from recognition_router import (
    ONLINE_MAX_SECONDS,
    RecognitionError,
    RecognitionRouter,
)


class CategorizedCloudError(RuntimeError):
    def __init__(self, category: str, private_detail: str = "敏感服务响应") -> None:
        super().__init__(private_detail)
        self.category = category


class RecognitionRouterTests(unittest.TestCase):
    @staticmethod
    def _recognizer(text: str = "识别结果", device: str = "CPU") -> MagicMock:
        recognizer = MagicMock(device_label=device)
        recognizer.transcribe_pcm16.return_value = text
        return recognizer

    def test_default_local_engine_never_reads_credentials_or_creates_cloud_client(self):
        credential_store = MagicMock()
        cloud_factory = MagicMock()
        local = self._recognizer()
        local_factory = MagicMock(return_value=local)
        router = RecognitionRouter(
            {},
            credential_store=credential_store,
            local_factory=local_factory,
            cloud_factory=cloud_factory,
        )

        result = router.transcribe_pcm16(bytes(32000), 16000)

        self.assertEqual(result.text, "识别结果")
        self.assertEqual(result.actual_engine, "local:sensevoice-small-int8")
        local_factory.assert_called_once_with("sensevoice-small-int8", "auto")
        credential_store.read.assert_not_called()
        credential_store.load.assert_not_called()
        cloud_factory.assert_not_called()

    def test_cloud_engine_reads_selected_credentials_and_returns_result(self):
        credential_store = MagicMock()
        credential_store.read.return_value = {
            "access_key_id": "编号",
            "access_key_secret": "密钥",
            "app_key": "项目",
        }
        cloud = self._recognizer("在线结果", "在线")
        cloud_factory = MagicMock(return_value=cloud)
        local_factory = MagicMock()
        router = RecognitionRouter(
            {"recognition_engine": "cloud:aliyun"},
            credential_store=credential_store,
            local_factory=local_factory,
            cloud_factory=cloud_factory,
        )

        result = router.transcribe_pcm16(bytes(32000), 16000)

        self.assertEqual(result.text, "在线结果")
        self.assertEqual(result.actual_engine, "cloud:aliyun")
        self.assertFalse(result.fallback_used)
        credential_store.read.assert_called_once_with("aliyun")
        cloud_factory.assert_called_once()
        local_factory.assert_not_called()

    def test_transient_cloud_failure_falls_back_to_selected_local_model(self):
        credential_store = MagicMock()
        credential_store.read.return_value = {"api_key": "私密值"}
        cloud = self._recognizer()
        cloud.transcribe_pcm16.side_effect = CategorizedCloudError(
            "transient", "私密值不应出现在结果中"
        )
        local = self._recognizer("本地回退结果")
        local_factory = MagicMock(return_value=local)
        router = RecognitionRouter(
            {
                "recognition_engine": "cloud:volcengine",
                "fallback_model": "paraformer-zh-small-int8",
                "local_asr_device": "cpu",
            },
            credential_store=credential_store,
            local_factory=local_factory,
            cloud_factory=MagicMock(return_value=cloud),
        )

        result = router.transcribe_pcm16(bytes(32000), 16000)

        self.assertEqual(result.text, "本地回退结果")
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.requested_engine, "cloud:volcengine")
        self.assertEqual(result.actual_engine, "local:paraformer-zh-small-int8")
        local_factory.assert_called_once_with("paraformer-zh-small-int8", "cpu")

    def test_non_transient_cloud_failures_never_use_local_fallback(self):
        for category in ("authentication", "quota", "parameter", "service"):
            with self.subTest(category=category):
                credential_store = MagicMock()
                credential_store.read.return_value = {"api_key": "私密值"}
                cloud = self._recognizer()
                cloud.transcribe_pcm16.side_effect = CategorizedCloudError(
                    category, "私密值和服务正文"
                )
                local_factory = MagicMock()
                router = RecognitionRouter(
                    {"recognition_engine": "cloud:volcengine"},
                    credential_store=credential_store,
                    local_factory=local_factory,
                    cloud_factory=MagicMock(return_value=cloud),
                )

                with self.assertRaises(RecognitionError) as captured:
                    router.transcribe_pcm16(bytes(32000), 16000)

                self.assertEqual(captured.exception.category, category)
                self.assertNotIn("私密值", str(captured.exception))
                self.assertNotIn("服务正文", str(captured.exception))
                local_factory.assert_not_called()

    def test_cloud_duration_limit_is_checked_before_credentials_or_network(self):
        credential_store = MagicMock()
        cloud_factory = MagicMock()
        router = RecognitionRouter(
            {"recognition_engine": "cloud:tencent"},
            credential_store=credential_store,
            local_factory=MagicMock(),
            cloud_factory=cloud_factory,
        )
        too_long = bytes(int(ONLINE_MAX_SECONDS * 16000 * 2) + 2)

        with self.assertRaises(RecognitionError) as captured:
            router.transcribe_pcm16(too_long, 16000)

        self.assertEqual(captured.exception.category, "parameter")
        credential_store.read.assert_not_called()
        credential_store.load.assert_not_called()
        cloud_factory.assert_not_called()

    def test_cloud_preload_only_loads_local_fallback_without_network(self):
        credential_store = MagicMock()
        cloud_factory = MagicMock()
        local = self._recognizer()
        local_factory = MagicMock(return_value=local)
        router = RecognitionRouter(
            {
                "recognition_engine": "cloud:iflytek",
                "fallback_model": "qwen3-asr-0.6b-int8",
            },
            credential_store=credential_store,
            local_factory=local_factory,
            cloud_factory=cloud_factory,
        )

        engine_id, device = router.preload()

        self.assertEqual(engine_id, "local:qwen3-asr-0.6b-int8")
        self.assertEqual(device, "CPU")
        local.load.assert_called_once_with()
        credential_store.read.assert_not_called()
        credential_store.load.assert_not_called()
        cloud_factory.assert_not_called()

    def test_missing_credentials_does_not_trigger_fallback(self):
        credential_store = MagicMock()
        credential_store.read.return_value = {}
        local_factory = MagicMock()
        router = RecognitionRouter(
            {"recognition_engine": "cloud:tencent"},
            credential_store=credential_store,
            local_factory=local_factory,
            cloud_factory=MagicMock(),
        )

        with self.assertRaises(RecognitionError) as captured:
            router.transcribe_pcm16(bytes(32000), 16000)

        self.assertEqual(captured.exception.category, "authentication")
        local_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
