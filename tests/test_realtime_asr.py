import time
import unittest
from unittest.mock import patch

import realtime_asr


class _FakeStream:
    def __init__(self):
        self.samples = 0
        self.ready = False
        self.finished = False

    def accept_waveform(self, _sample_rate, samples):
        self.samples += len(samples)
        self.ready = True

    def input_finished(self):
        self.finished = True


class _FakeRecognizer:
    def create_stream(self):
        return _FakeStream()

    @staticmethod
    def is_ready(stream):
        return stream.ready

    @staticmethod
    def decode_stream(stream):
        stream.ready = False

    @staticmethod
    def get_result(stream):
        return "你好世界" if stream.finished else "你好"

    @staticmethod
    def is_endpoint(_stream):
        return False

    @staticmethod
    def reset(_stream):
        return None


class _EndpointStream(_FakeStream):
    def __init__(self):
        super().__init__()
        self.endpoint = False
        self.segment_index = 0

    def accept_waveform(self, sample_rate, samples):
        super().accept_waveform(sample_rate, samples)
        if not self.finished and any(samples):
            self.endpoint = True


class _EndpointRecognizer(_FakeRecognizer):
    def create_stream(self):
        return _EndpointStream()

    @staticmethod
    def get_result(stream):
        if stream.finished:
            return ""
        return ("第一段", "第二段", "第三段")[min(stream.segment_index, 2)]

    @staticmethod
    def is_endpoint(stream):
        return stream.endpoint

    @staticmethod
    def reset(stream):
        stream.endpoint = False
        stream.segment_index += 1


class RealtimeAsrTests(unittest.TestCase):
    def test_endpoint_silence_rules_can_be_shortened_for_control_words(self):
        recognizer = realtime_asr.RealtimeRecognizer(
            rule1_min_trailing_silence=1.2,
            rule2_min_trailing_silence=0.8,
            rule3_min_utterance_length=18.0,
        )
        self.assertEqual(recognizer.rule1_min_trailing_silence, 1.2)
        self.assertEqual(recognizer.rule2_min_trailing_silence, 0.8)
        self.assertEqual(recognizer.rule3_min_utterance_length, 18.0)

    def test_official_model_manifest_is_complete_and_pinned(self):
        self.assertEqual(
            set(realtime_asr.MODEL_FILES),
            {"model.int8.onnx", "tokens.txt", "bbpe.model"},
        )
        self.assertEqual(len(realtime_asr.MODEL_ARCHIVE_SHA256), 64)
        self.assertTrue(realtime_asr.MODEL_DOWNLOAD_URL.startswith("https://github.com/k2-fsa/"))

    def test_feed_is_non_blocking_and_finish_returns_final_update(self):
        updates = []
        session = realtime_asr.RealtimeSession("op-1", _FakeRecognizer(), updates.append)
        session.start()
        started = time.monotonic()
        self.assertTrue(session.feed_pcm16(bytes(3200), 16000))
        self.assertLess(time.monotonic() - started, 0.05)
        result = session.finish(timeout=2.0)
        self.assertTrue(result.is_final)
        self.assertEqual(result.text, "你好世界")
        self.assertTrue(result.endpoint_reached)
        self.assertEqual(result.endpoint_text, "你好世界")
        self.assertEqual(result.segment_start_ms, 0)
        self.assertEqual(result.segment_end_ms, 100)
        self.assertTrue(any(item.partial_text == "你好" for item in updates))

    def test_endpoint_update_exposes_only_the_independent_segment(self):
        updates = []
        session = realtime_asr.RealtimeSession(
            "standby-op",
            _EndpointRecognizer(),
            updates.append,
            max_stable_segments=0,
        )
        session.start()
        session.feed_pcm16(bytes([1, 0]) * 1600, 16000)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not any(item.endpoint_reached for item in updates):
            time.sleep(0.01)
        endpoint = next(item for item in updates if item.endpoint_reached)
        self.assertEqual(endpoint.endpoint_text, "第一段")
        self.assertEqual(endpoint.stable_text, "")
        self.assertEqual(endpoint.partial_text, "")
        self.assertEqual(endpoint.segment_start_ms, 0)
        self.assertEqual(endpoint.segment_end_ms, 100)
        session.cancel()

    def test_stable_segment_limit_keeps_only_the_requested_tail(self):
        updates = []
        session = realtime_asr.RealtimeSession(
            "limited-op",
            _EndpointRecognizer(),
            updates.append,
            max_stable_segments=1,
        )
        session.start()
        chunk = bytes([1, 0]) * 800
        session.feed_pcm16(chunk, 16000)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and len(
            [item for item in updates if item.endpoint_reached]
        ) < 1:
            time.sleep(0.01)
        session.feed_pcm16(chunk, 16000)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and len(
            [item for item in updates if item.endpoint_reached]
        ) < 2:
            time.sleep(0.01)
        endpoints = [item for item in updates if item.endpoint_reached]
        self.assertEqual(len(endpoints), 2)
        self.assertEqual(endpoints[0].stable_text, "第一段")
        self.assertEqual(endpoints[1].endpoint_text, "第二段")
        self.assertEqual(endpoints[1].stable_text, "第二段")
        self.assertEqual(endpoints[1].segment_start_ms, 50)
        self.assertEqual(endpoints[1].segment_end_ms, 100)
        session.cancel()

    def test_late_or_invalid_audio_is_rejected_after_finish(self):
        session = realtime_asr.RealtimeSession("op-2", _FakeRecognizer(), lambda _value: None)
        session.start()
        session.finish(timeout=2.0)
        self.assertFalse(session.feed_pcm16(bytes(3200), 16000))
        self.assertFalse(session.feed_pcm16(b"\x00", 16000))
        self.assertFalse(session.feed_pcm16(bytes(3200), 48000))

    def test_status_does_not_hash_large_model_during_panel_refresh(self):
        with (
            patch.object(realtime_asr, "_complete_by_size", return_value=True),
            patch.object(realtime_asr, "_sha256", side_effect=AssertionError("不应计算哈希")),
        ):
            status = realtime_asr.get_realtime_model_status()
        self.assertTrue(status["installed"])
        self.assertIn("处理器", status["minimum"])


if __name__ == "__main__":
    unittest.main()
