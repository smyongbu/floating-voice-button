import threading
import unittest
from unittest.mock import MagicMock, patch

import app
from recognition_router import RecognitionResult
from realtime_asr import RealtimeUpdate


class LocalFlowTests(unittest.TestCase):
    def test_effective_audio_detection_rejects_digital_silence(self):
        self.assertFalse(app.has_effective_pcm16_audio(bytes(32000)))
        self.assertFalse(app.has_effective_pcm16_audio(b"\x01"))
        self.assertFalse(app.has_effective_pcm16_audio(b"\x20\x03" * 160))
        self.assertTrue(app.has_effective_pcm16_audio(b"\x20\x03\xe0\xfc" * 1600))

    class _ImmediateThread:
        def __init__(self, target, *args, **kwargs):
            self.target = target

        def start(self):
            self.target()

    class _BrokenThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("无法创建工作线程")

    @staticmethod
    def _instance():
        instance = app.VoiceButtonApp.__new__(app.VoiceButtonApp)
        instance.config = {
            "paste_wait_ms": 0,
            "standby_enabled": False,
            "live_transcript_visible": True,
        }
        instance.operation_id = "local-op"
        instance.origin_hwnd = 456
        instance.recording = False
        instance.busy = True
        instance.standby_operation = False
        instance.standby_end_cue_pending = False
        instance.standby_stop_at_ms = None
        instance.lock = threading.Lock()
        instance.pipeline_lock = threading.RLock()
        instance.side_effect_lock = threading.RLock()
        instance.stop_event = threading.Event()
        instance.closed = False
        instance.run_log = MagicMock()
        instance.error_log = MagicMock()
        instance._play_recording_cue = MagicMock()
        instance.window = MagicMock(hwnd=777)
        instance.audio_monitor = MagicMock()
        instance.audio_monitor.is_open = False
        instance.audio_monitor.continuous = False
        instance.transcript_window = MagicMock()
        instance.standby_listener = MagicMock(running=False)
        instance.standby_listener.resume_waiting.return_value = True
        instance.standby_listener.prepare_recording.return_value = True
        instance.standby_listener.activate_recording.return_value = True
        instance.realtime_session = None
        instance.active_router = None
        instance.realtime_revision = 0
        instance.realtime_overload_logged = False
        instance._standby_level_stream_ready = False
        instance._standby_error_notified = False
        instance._standby_pipeline_starting = False
        instance._test_mode_active = False
        instance.local_recognizer = MagicMock(device_label="CPU")
        instance.realtime_recognizer = MagicMock(model_name="Streaming Paraformer")
        instance.history_store = MagicMock()
        return instance

    def test_test_mode_pauses_idle_floating_recording_and_toggle_is_ignored(self):
        instance = self._instance()
        instance.busy = False
        with (
            patch.object(app, "test_mode_is_active", return_value=True),
            patch.object(app, "signal_test_mode_ready") as ready,
            patch.object(app.threading, "Thread") as worker,
        ):
            instance._sync_test_mode()
            instance.toggle()
        self.assertTrue(instance._test_mode_active)
        instance.standby_listener.stop.assert_called_once()
        instance.audio_monitor.close.assert_called_once()
        instance.window.set_state.assert_called_with("disabled")
        self.assertGreaterEqual(ready.call_count, 1)
        worker.assert_not_called()

    def test_standby_start_plays_cue_before_requesting_recording(self):
        instance = self._instance()
        instance.config["standby_enabled"] = True
        instance.busy = False
        events = []
        instance._play_recording_cue = MagicMock(side_effect=lambda _stage: events.append("提示音"))
        instance._start = MagicMock(side_effect=lambda: events.append("开始录音"))
        with patch.object(app.threading, "Thread", self._ImmediateThread):
            instance._on_standby_word("开始", 0)
        self.assertEqual(events, ["提示音", "开始录音"])
        self.assertTrue(instance.standby_operation)

    def test_standby_end_defers_cue_until_microphone_has_stopped(self):
        instance = self._instance()
        instance.busy = False
        instance.recording = True
        instance.standby_operation = True
        instance._play_recording_cue = MagicMock()
        instance._finish = MagicMock()
        with patch.object(app.threading, "Thread", self._ImmediateThread):
            instance._on_standby_word("结束", 1250)
        instance._play_recording_cue.assert_not_called()
        self.assertTrue(instance.standby_end_cue_pending)
        self.assertEqual(instance.standby_stop_at_ms, 1250)
        instance._finish.assert_called_once_with()

    def test_standby_command_thread_failure_releases_busy_state(self):
        instance = self._instance()
        instance.config["standby_enabled"] = True
        instance.busy = False
        with (
            patch.object(app.threading, "Thread", self._BrokenThread),
            self.assertRaisesRegex(RuntimeError, "无法创建工作线程"),
        ):
            instance._on_standby_word("开始", 0)
        self.assertFalse(instance.busy)
        self.assertFalse(instance.standby_operation)

    def test_end_cue_is_after_capture_stop_and_before_final_recognition(self):
        instance = self._instance()
        instance.recording = True
        instance.standby_operation = True
        instance.standby_end_cue_pending = True
        events = []

        def stop_audio():
            events.append("停止收音")
            return bytes(32000), 16000

        instance.audio_monitor.stop.side_effect = stop_audio
        instance._play_recording_cue = MagicMock(side_effect=lambda _stage: events.append("提示音"))
        instance.local_recognizer.transcribe_pcm16.side_effect = (
            lambda *_args: events.append("最终识别") or "正文内容"
        )
        instance._finish()
        self.assertLess(events.index("停止收音"), events.index("提示音"))
        self.assertLess(events.index("提示音"), events.index("最终识别"))

    def test_start_always_creates_realtime_preview_session(self):
        instance = self._instance()
        with patch.object(app, "foreground_window", return_value=456):
            instance._start()
        instance._play_recording_cue.assert_called_once_with("开始")
        instance.realtime_recognizer.create_session.assert_called_once_with(
            "local-op", instance._on_realtime_update
        )
        instance.audio_monitor.start.assert_called_once_with(
            instance.window.set_waveform, instance._feed_realtime_audio
        )
        self.assertTrue(instance.recording)
        instance.window.set_state.assert_any_call("recording")

    def test_ready_standby_listener_switches_button_to_lines(self):
        instance = self._instance()
        instance.config["standby_enabled"] = True
        instance.busy = False
        instance._on_standby_ready()
        instance.window.set_waveform.assert_called_once_with([0.0] * 7)
        instance.window.set_state.assert_called_once_with("standby")

    def test_standby_audio_moves_lines_only_while_waiting(self):
        instance = self._instance()
        instance.config["standby_enabled"] = True
        levels = [0.0, 0.1, 0.2, 0.5, 0.2, 0.1, 0.0]
        instance.busy = False
        instance.recording = False
        instance._standby_level_stream_ready = False
        instance._on_standby_level(levels)
        instance.window.set_waveform.assert_called_once_with(levels)
        instance._on_standby_level(levels)
        self.assertEqual(instance.run_log.info.call_count, 1)

        instance.window.reset_mock()
        instance.recording = True
        instance._on_standby_level(levels)
        instance.window.set_waveform.assert_not_called()

    def test_standby_pipeline_is_idempotent_and_closed_app_never_reopens_mic(self):
        instance = self._instance()
        instance.config["standby_enabled"] = True
        instance.standby_listener.state = "waiting"
        instance.standby_listener.running = True
        instance.audio_monitor.is_open = True
        instance.audio_monitor.continuous = True

        self.assertTrue(instance._start_standby_pipeline())
        self.assertTrue(instance._start_standby_pipeline())
        instance.standby_listener.resume_waiting.assert_not_called()
        instance.audio_monitor.open_continuous.assert_not_called()

        instance.closed = True
        instance._restore_resting_pipeline()
        instance.audio_monitor.close.assert_called()
        instance.standby_listener.stop.assert_called()

    def test_failed_decoder_error_does_not_recursively_stop_listener(self):
        instance = self._instance()
        instance.busy = False
        instance.standby_listener.state = "failed"
        instance._warning = MagicMock()
        instance._on_standby_error("旧 Zipformer 解码线程没有按时退出。")
        instance.standby_listener.stop.assert_not_called()
        instance.audio_monitor.close.assert_called_once_with()
        instance._warning.assert_called_once()

    def test_cleanup_during_final_recognition_prevents_history_and_paste(self):
        instance = self._instance()
        instance.recording = True
        instance.audio_monitor.stop.return_value = (bytes(32000), 16000)
        instance.local_recognizer.transcribe_pcm16.side_effect = (
            lambda *_args: instance.cleanup() or "不应保存"
        )
        with patch.object(app, "paste") as paste:
            instance._finish()
        instance.history_store.add.assert_not_called()
        paste.assert_not_called()
        self.assertTrue(instance.closed)

    def test_cleanup_during_first_window_activation_prevents_clipboard_and_paste(self):
        instance = self._instance()
        instance.recording = True
        instance.audio_monitor.stop.return_value = (bytes(32000), 16000)
        instance.local_recognizer.transcribe_pcm16.return_value = "最终文字"

        def close_during_activation(_hwnd):
            instance.cleanup()
            return True

        with (
            patch.object(app, "activate_window_and_wait", side_effect=close_during_activation) as activate,
            patch.object(app, "write_clipboard_text") as write,
            patch.object(app, "paste") as paste,
        ):
            instance._finish()
        activate.assert_called_once_with(456)
        write.assert_not_called()
        paste.assert_not_called()

    def test_finish_transcribes_saves_and_pastes(self):
        instance = self._instance()
        instance.recording = True
        instance.audio_monitor.stop.side_effect = [
            (bytes(32000), 16000),
            (b"", 16000),
        ]
        instance.local_recognizer.transcribe_pcm16.return_value = "本地识别文字"
        with (
            patch.object(app, "activate_window_and_wait", return_value=True),
            patch.object(app, "foreground_window", return_value=456),
            patch.object(app, "read_clipboard_text", return_value=None),
            patch.object(app, "write_clipboard_text", return_value=True),
            patch.object(app, "paste") as paste,
        ):
            instance._finish()
        instance.local_recognizer.transcribe_pcm16.assert_called_once()
        instance.history_store.add.assert_called_once_with("local-op", "本地识别文字")
        paste.assert_called_once_with()
        self.assertFalse(instance.recording)

    def test_finish_uses_unified_recognition_router(self):
        instance = self._instance()
        instance.recording = True
        instance.audio_monitor.stop.side_effect = [
            (bytes(32000), 16000),
            (b"", 16000),
        ]
        instance.recognition_router = MagicMock(engine_id="cloud:aliyun")
        instance.recognition_router.transcribe_pcm16.return_value = RecognitionResult(
            text="统一路由识别文字",
            requested_engine="cloud:aliyun",
            actual_engine="local:sensevoice-small-int8",
            fallback_used=True,
            device_label="CPU",
        )
        with (
            patch.object(app, "activate_window_and_wait", return_value=True),
            patch.object(app, "foreground_window", return_value=456),
            patch.object(app, "read_clipboard_text", return_value=None),
            patch.object(app, "write_clipboard_text", return_value=True),
            patch.object(app, "paste") as paste,
        ):
            instance._finish()
        instance.recognition_router.transcribe_pcm16.assert_called_once()
        instance.local_recognizer.transcribe_pcm16.assert_not_called()
        instance.history_store.add.assert_called_once_with(
            "local-op", "统一路由识别文字"
        )
        paste.assert_called_once_with()

    def test_standby_finish_only_saves_history(self):
        instance = self._instance()
        instance.recording = True
        instance.standby_operation = True
        instance.audio_monitor.stop.side_effect = [(bytes(32000), 16000), (b"", 16000)]
        instance.local_recognizer.transcribe_pcm16.return_value = "正文内容"
        with patch.object(app, "paste") as paste:
            instance._finish()
        instance.history_store.add.assert_called_once_with("local-op", "正文内容")
        paste.assert_not_called()

    def test_standby_finish_trims_end_command_at_segment_boundary(self):
        instance = self._instance()
        instance.recording = True
        instance.standby_operation = True
        instance.standby_stop_at_ms = 1000
        instance.audio_monitor.continuous = True
        instance.audio_monitor.finish_capture.side_effect = [
            (bytes(64000), 16000),
            (b"", 16000),
        ]
        seen = []
        instance.local_recognizer.transcribe_pcm16.side_effect = (
            lambda pcm, _rate: seen.append(len(pcm)) or "正文内容"
        )
        instance._finish()
        self.assertEqual(seen, [32000])
        instance.history_store.add.assert_called_once_with("local-op", "正文内容")

    def test_voice_start_reuses_continuous_microphone_and_activates_body_session(self):
        instance = self._instance()
        instance.standby_operation = True
        instance.audio_monitor.is_open = True
        instance.audio_monitor.continuous = True
        with patch.object(app, "foreground_window", return_value=456):
            instance._start()
        instance.standby_listener.prepare_recording.assert_called_once_with("local-op")
        instance.audio_monitor.begin_capture.assert_called_once_with(
            instance.window.set_waveform,
            None,
            instance.standby_listener.activate_recording,
        )
        instance.audio_monitor.start.assert_not_called()
        self.assertTrue(instance.recording)

    def test_finish_preserves_final_model_output_without_text_refinement(self):
        instance = self._instance()
        instance.recording = True
        instance.audio_monitor.stop.side_effect = [
            (bytes(32000), 16000),
            (b"", 16000),
        ]
        original = "今天 , 天气不错 .\n\nPLEASE KEEP API!"
        instance.local_recognizer.transcribe_pcm16.return_value = original
        with (
            patch.object(app, "activate_window_and_wait", return_value=True),
            patch.object(app, "foreground_window", return_value=456),
            patch.object(app, "read_clipboard_text", return_value=None),
            patch.object(app, "write_clipboard_text", return_value=True) as write,
            patch.object(app, "paste"),
        ):
            instance._finish()
        instance.history_store.add.assert_called_once_with("local-op", original)
        write.assert_called_once_with(original, 777)

    def test_realtime_preview_finishes_but_final_text_is_saved_and_pasted_once(self):
        instance = self._instance()
        instance.recording = True
        session = MagicMock()
        session.finish.return_value = RealtimeUpdate(
            operation_id="local-op",
            revision=3,
            stable_text="今天 天气 不错",
            partial_text="",
            audio_ms=1000,
            is_final=True,
        )
        instance.realtime_session = session
        instance.audio_monitor.stop.side_effect = [
            (bytes(32000), 16000),
            (b"", 16000),
        ]
        instance.local_recognizer.transcribe_pcm16.return_value = "今天天气不错。"
        with (
            patch.object(app, "activate_window_and_wait", return_value=True),
            patch.object(app, "foreground_window", return_value=456),
            patch.object(app, "read_clipboard_text", return_value=None),
            patch.object(app, "write_clipboard_text", return_value=True) as write,
            patch.object(app, "paste") as paste,
        ):
            instance._finish()
        session.finish.assert_called_once_with(timeout=5.0)
        instance.local_recognizer.transcribe_pcm16.assert_called_once()
        instance.history_store.add.assert_called_once_with("local-op", "今天天气不错。")
        write.assert_called_once_with("今天天气不错。", 777)
        paste.assert_called_once_with()

    def test_disabled_auto_paste_keeps_history_and_clipboard_without_window_activation(self):
        instance = self._instance()
        instance.config["auto_paste_enabled"] = False
        instance.recording = True
        instance.audio_monitor.stop.return_value = (bytes(32000), 16000)
        instance.local_recognizer.transcribe_pcm16.return_value = "只复制不自动输入"
        with (
            patch.object(app, "activate_window_and_wait") as activate,
            patch.object(app, "write_clipboard_text", return_value=True) as write,
            patch.object(app, "paste") as paste,
        ):
            instance._finish()
        instance.history_store.add.assert_called_once_with("local-op", "只复制不自动输入")
        write.assert_called_once_with("只复制不自动输入", 777)
        activate.assert_not_called()
        paste.assert_not_called()
        self.assertTrue(any(
            "跳过自动输入" in str(call)
            for call in instance.run_log.info.call_args_list
        ))

    def test_stale_realtime_updates_are_ignored_and_never_touch_history(self):
        instance = self._instance()
        instance.operation_id = "current"
        instance._on_realtime_update(RealtimeUpdate(
            operation_id="old", revision=9, stable_text="旧任务", partial_text="", audio_ms=1
        ))
        instance._on_realtime_update(RealtimeUpdate(
            operation_id="current", revision=1, stable_text="", partial_text="当前文字", audio_ms=1
        ))
        instance._on_realtime_update(RealtimeUpdate(
            operation_id="current", revision=1, stable_text="", partial_text="迟到文字", audio_ms=2
        ))
        instance.transcript_window.update.assert_called_once_with("当前文字")
        instance.history_store.add.assert_not_called()

    def test_hidden_live_transcript_never_updates_overlay(self):
        instance = self._instance()
        instance.config["live_transcript_visible"] = False
        instance.operation_id = "current"
        instance._on_realtime_update(RealtimeUpdate(
            operation_id="current", revision=1, stable_text="", partial_text="不应显示", audio_ms=1
        ))
        instance.transcript_window.update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
