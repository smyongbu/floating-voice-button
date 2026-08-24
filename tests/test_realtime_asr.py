import time
import types
import unittest
import threading
from pathlib import Path
from unittest.mock import Mock, patch

from config_store import DEFAULT_REALTIME_MODEL, ZIPFORMER_REALTIME_MODEL
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


class _EmptyFinalRecognizer(_FakeRecognizer):
    @staticmethod
    def get_result(stream):
        return "" if stream.finished else "实时识别到了"


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
    def test_sessions_created_from_one_recognizer_share_decode_lock(self):
        recognizer = realtime_asr.RealtimeRecognizer.__new__(
            realtime_asr.RealtimeRecognizer
        )
        recognizer._lock = threading.RLock()
        recognizer._session_lock = threading.Lock()
        recognizer._recognizer = _FakeRecognizer()
        recognizer.load = Mock()
        with patch.object(realtime_asr.RealtimeSession, "start"):
            first = recognizer.create_session("one", Mock())
            second = recognizer.create_session("two", Mock())
        self.assertIs(first._decode_lock, second._decode_lock)

    def test_idle_session_does_not_block_later_session_from_decoding(self):
        first_stream_created = threading.Event()

        class NotifyingRecognizer(_FakeRecognizer):
            def create_stream(self):
                first_stream_created.set()
                return super().create_stream()

        shared_lock = threading.Lock()
        recognizer = NotifyingRecognizer()
        first = realtime_asr.RealtimeSession(
            "first", recognizer, Mock(), decode_lock=shared_lock
        )
        second = realtime_asr.RealtimeSession(
            "second", recognizer, Mock(), decode_lock=shared_lock
        )
        first.start()
        self.assertTrue(first_stream_created.wait(1.0))
        second.start()
        self.assertTrue(second.feed_pcm16(b"\x20\x03\xe0\xfc" * 320))
        result = second.finish(timeout=1.0)
        first.cancel()

        self.assertTrue(result.is_final)
        self.assertTrue(second.wait_closed(timeout=0.1))

    def test_source_run_uses_shared_realtime_model_without_copying(self):
        source = Path("O:/程序/共享模型仓库/streaming-paraformer")
        cache = Path("C:/Users/test/AppData/Local/FloatingVoiceButton/models/streaming-paraformer")
        spec = realtime_asr.REALTIME_MODEL_SPECS[DEFAULT_REALTIME_MODEL]
        with (
            patch.object(realtime_asr, "_running_frozen", return_value=False),
            patch.object(realtime_asr, "_model_paths", return_value=(DEFAULT_REALTIME_MODEL, spec, source, cache)),
            patch.object(realtime_asr, "_valid_model_file", return_value=True) as valid,
            patch.object(realtime_asr.shutil, "copyfile") as copyfile,
        ):
            self.assertEqual(realtime_asr.install_realtime_model_locally(), source)
        self.assertEqual(valid.call_count, len(spec["files"]))
        copyfile.assert_not_called()

    def test_endpoint_silence_rules_can_be_shortened_for_control_words(self):
        recognizer = realtime_asr.RealtimeRecognizer(
            rule1_min_trailing_silence=1.2,
            rule2_min_trailing_silence=0.8,
            rule3_min_utterance_length=18.0,
        )
        self.assertEqual(recognizer.rule1_min_trailing_silence, 1.2)
        self.assertEqual(recognizer.rule2_min_trailing_silence, 0.8)
        self.assertEqual(recognizer.rule3_min_utterance_length, 18.0)

    def test_official_model_manifests_are_complete_and_pinned(self):
        paraformer_files = realtime_asr.REALTIME_MODEL_SPECS[
            DEFAULT_REALTIME_MODEL
        ]["files"]
        zipformer_files = realtime_asr.REALTIME_MODEL_SPECS[
            ZIPFORMER_REALTIME_MODEL
        ]["files"]
        self.assertEqual(
            set(paraformer_files),
            {"encoder.int8.onnx", "decoder.int8.onnx", "tokens.txt"},
        )
        self.assertEqual(
            set(zipformer_files),
            {
                "encoder-epoch-99-avg-1.int8.onnx",
                "decoder-epoch-99-avg-1.onnx",
                "joiner-epoch-99-avg-1.int8.onnx",
                "tokens.txt",
            },
        )
        for model_id in (DEFAULT_REALTIME_MODEL, ZIPFORMER_REALTIME_MODEL):
            spec = realtime_asr.REALTIME_MODEL_SPECS[model_id]
            self.assertTrue(str(spec["download_url"]).startswith("https://"))
            self.assertTrue(all(size > 0 and len(digest) == 64 for size, digest in spec["files"].values()))

    def test_realtime_output_only_removes_internal_tokens_and_extra_spaces(self):
        self.assertEqual(
            realtime_asr.clean_realtime_text("<nuk>  HELLO WORLD 和 OPEN-AI "),
            "HELLO WORLD 和 OPEN-AI",
        )

    def test_mixed_language_segments_have_readable_spacing(self):
        self.assertEqual(
            realtime_asr.combine_segments("请打开", "Wi-Fi"),
            "请打开 Wi-Fi",
        )
        self.assertEqual(
            realtime_asr.combine_segments("Openai", "明天下午"),
            "Openai 明天下午",
        )

    def test_bad_final_result_keeps_realtime_but_related_final_result_wins(self):
        rejected = realtime_asr.choose_final_recognition(
            "The Quick Brown Fox Jumps Over The Lazy Dog",
            "THE QUICK FOX",
        )
        accepted = realtime_asr.choose_final_recognition(
            "Please Open Wifi And Search Open Ai",
            "Please open Wi-Fi and search OpenAI",
        )
        self.assertEqual(rejected.source, "realtime")
        self.assertEqual(accepted.source, "final")

    def test_selected_final_result_preserves_model_case_punctuation_and_lines(self):
        final_result = "第一段。\n\nPLEASE KEEP API, OpenAI!"
        selected = realtime_asr.choose_final_recognition(
            "第一段 PLEASE KEEP API OpenAI",
            final_result,
        )
        self.assertEqual(selected.source, "final")
        self.assertEqual(selected.text, final_result)

    def test_streaming_paraformer_factory_uses_official_online_api(self):
        model_dir = Path("C:/models/paraformer")
        online = types.SimpleNamespace(
            from_paraformer=Mock(return_value=object()),
            from_transducer=Mock(return_value=object()),
        )
        runtime = types.SimpleNamespace(OnlineRecognizer=online)
        with (
            patch.dict("sys.modules", {"sherpa_onnx": runtime}),
            patch.object(realtime_asr, "install_realtime_model_locally", return_value=model_dir),
        ):
            recognizer = realtime_asr.RealtimeRecognizer(model_id=DEFAULT_REALTIME_MODEL)
            recognizer.load()

        online.from_paraformer.assert_called_once()
        online.from_transducer.assert_not_called()
        kwargs = online.from_paraformer.call_args.kwargs
        self.assertEqual(kwargs["encoder"], str(model_dir / "encoder.int8.onnx"))
        self.assertEqual(kwargs["decoder"], str(model_dir / "decoder.int8.onnx"))
        self.assertEqual(kwargs["decoding_method"], "greedy_search")

    def test_zipformer_factory_uses_official_online_api(self):
        model_dir = Path("C:/models/zipformer")
        online = types.SimpleNamespace(
            from_paraformer=Mock(return_value=object()),
            from_transducer=Mock(return_value=object()),
        )
        runtime = types.SimpleNamespace(OnlineRecognizer=online)
        with (
            patch.dict("sys.modules", {"sherpa_onnx": runtime}),
            patch.object(realtime_asr, "install_realtime_model_locally", return_value=model_dir),
        ):
            recognizer = realtime_asr.RealtimeRecognizer(model_id=ZIPFORMER_REALTIME_MODEL)
            recognizer.load()

        online.from_transducer.assert_called_once()
        online.from_paraformer.assert_not_called()
        kwargs = online.from_transducer.call_args.kwargs
        self.assertEqual(
            kwargs["encoder"],
            str(model_dir / "encoder-epoch-99-avg-1.int8.onnx"),
        )
        self.assertEqual(kwargs["model_type"], "zipformer")
        self.assertEqual(kwargs["decoding_method"], "modified_beam_search")

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

    def test_finish_keeps_last_nonempty_partial_when_final_decode_is_empty(self):
        updates = []
        session = realtime_asr.RealtimeSession(
            "empty-final", _EmptyFinalRecognizer(), updates.append
        )
        session.start()
        self.assertTrue(session.feed_pcm16(bytes(3200), 16000))

        result = session.finish(timeout=2.0)

        self.assertTrue(result.is_final)
        self.assertEqual(result.text, "实时识别到了")
        self.assertEqual(session.current_text, "实时识别到了")
        self.assertEqual(updates[-1].text, "实时识别到了")

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
