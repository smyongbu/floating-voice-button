import unittest
from unittest.mock import MagicMock, patch
from recognition_router import RecognitionError, RecognitionRouter


class RecognitionRouterTests(unittest.TestCase):
    @staticmethod
    def _recognizer():
        recognizer = MagicMock(device_label="CPU")
        recognizer.transcribe_pcm16.return_value = "本地识别结果"
        return recognizer

    def test_legacy_service_choices_only_invoke_local_model_without_network(self):
        for engine in (None, "cloud:aliyun", "cloud:tencent", "cloud:iflytek", "cloud:volcengine", "online:xfyun"):
            with self.subTest(engine=engine), patch("socket.socket", side_effect=AssertionError("不得联网")):
                recognizer = self._recognizer()
                factory = MagicMock(return_value=recognizer)
                router = RecognitionRouter({"recognition_engine": engine}, local_factory=factory)
                result = router.transcribe_pcm16(bytes(32000))
                self.assertEqual(result.text, "本地识别结果")
                self.assertEqual(result.requested_engine, "local:faster-whisper-small")
                self.assertEqual(result.actual_engine, result.requested_engine)
                factory.assert_called_once_with("faster-whisper-small", "auto")

    def test_selected_model_device_preload_and_reuse(self):
        recognizer = self._recognizer()
        factory = MagicMock(return_value=recognizer)
        router = RecognitionRouter({
            "recognition_engine": "local:faster-whisper-small",
            "local_asr_device": "cpu",
        }, local_factory=factory)
        self.assertEqual(router.preload(), ("local:faster-whisper-small", "CPU"))
        router.transcribe_pcm16(bytes(32000))
        router.transcribe_pcm16(bytes(32000))
        factory.assert_called_once_with("faster-whisper-small", "cpu")
        recognizer.load.assert_called_once_with()
        self.assertEqual(recognizer.transcribe_pcm16.call_count, 2)
        router.close()
        router.close()
        recognizer.close.assert_called_once_with()
        with self.assertRaises(RecognitionError):
            router.transcribe_pcm16(bytes(32000))

    def test_local_audio_is_not_subject_to_removed_service_duration_limit(self):
        recognizer = self._recognizer()
        router = RecognitionRouter({}, local_factory=MagicMock(return_value=recognizer))
        pcm = bytes(16000 * 2 * 60)
        router.transcribe_pcm16(pcm)
        recognizer.transcribe_pcm16.assert_called_once_with(pcm, 16000)

    def test_model_errors_have_safe_local_messages(self):
        recognizer = self._recognizer()
        recognizer.transcribe_pcm16.side_effect = RuntimeError("私密正文")
        router = RecognitionRouter({}, local_factory=MagicMock(return_value=recognizer))
        with self.assertRaises(RecognitionError) as captured:
            router.transcribe_pcm16(bytes(32000))
        self.assertEqual(captured.exception.category, "local")
        self.assertNotIn("私密正文", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
