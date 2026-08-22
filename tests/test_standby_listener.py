import inspect
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import standby_listener as standby_listener_module
from standby_listener import (
    StandbyVoiceListener,
    classify_standby_control_phrase,
    normalize_standby_control_phrase,
    standby_control_match,
)


def update(
    *,
    partial_text: str = "",
    endpoint_text: str = "",
    endpoint_reached: bool = False,
    segment_start_ms: int = 0,
):
    return SimpleNamespace(
        operation_id="test",
        revision=1,
        stable_text="",
        partial_text=partial_text,
        audio_ms=0,
        endpoint_text=endpoint_text,
        endpoint_reached=endpoint_reached,
        segment_start_ms=segment_start_ms,
        segment_end_ms=segment_start_ms + 100,
        is_final=False,
    )


class FakeSession:
    def __init__(self, callback, events=None):
        self.callback = callback
        self.events = events if events is not None else []
        self.cancelled = False
        self._done = threading.Event()
        self.feed_result = True
        self.fed = []

    def feed_pcm16(self, pcm, sample_rate=16000):
        self.fed.append((pcm, sample_rate))
        return self.feed_result

    def cancel(self):
        self.events.append("取消旧会话")
        self.cancelled = True
        self._done.set()

    def emit(self, value):
        self.callback(value)


class FakeRecognizer:
    def __init__(self, events=None):
        self.events = events if events is not None else []
        self.sessions = []
        self.calls = []
        self.failure = None

    def create_session(self, operation_id, callback, **kwargs):
        if self.failure is not None:
            raise self.failure
        session = FakeSession(callback, self.events)
        self.sessions.append(session)
        self.calls.append((operation_id, kwargs))
        return session


class NeverDone:
    def set(self):
        pass

    def wait(self, _timeout):
        return False


class StandbyListenerTests(unittest.TestCase):
    @staticmethod
    def make_listener(recognizer=None, **overrides):
        recognizer = recognizer or FakeRecognizer()
        callbacks = {
            "on_word": MagicMock(),
            "on_ready": MagicMock(),
            "on_update": MagicMock(),
            "on_ignored": MagicMock(),
            "on_error": MagicMock(),
        }
        callbacks.update(overrides)
        listener = StandbyVoiceListener(recognizer=recognizer, **callbacks)
        return listener, recognizer, callbacks

    def test_waiting_session_is_bounded_and_listener_never_opens_microphone(self):
        listener, recognizer, callbacks = self.make_listener()
        self.assertTrue(listener.resume_waiting())
        self.assertEqual(recognizer.calls[0][1], {"max_stable_segments": 0})
        self.assertEqual(listener.state, "waiting")
        self.assertTrue(listener.running)
        callbacks["on_ready"].assert_called_once_with()

        text = inspect.getsource(standby_listener_module)
        self.assertNotIn("sounddevice", text)
        self.assertNotIn("RawInputStream", text)
        self.assertNotIn("powershell", text.casefold())
        self.assertNotIn("subprocess", text)

    def test_partial_exact_word_does_not_trigger_without_endpoint(self):
        listener, recognizer, callbacks = self.make_listener()
        listener.resume_waiting()
        recognizer.sessions[-1].emit(update(partial_text="开始"))
        callbacks["on_word"].assert_not_called()
        callbacks["on_ignored"].assert_not_called()

    def test_endpoint_uses_strict_complete_phrase_match(self):
        listener, recognizer, callbacks = self.make_listener()
        listener.resume_waiting()
        recognizer.sessions[-1].emit(
            update(endpoint_text="请开始整理", endpoint_reached=True)
        )
        callbacks["on_word"].assert_not_called()
        callbacks["on_ignored"].assert_called_once_with(len("请开始整理"))

    def test_start_command_cancels_old_session_before_app_callback(self):
        events = []
        delivered = threading.Event()

        def on_word(word, start_ms):
            events.append(("回调应用", word, start_ms))
            delivered.set()

        recognizer = FakeRecognizer(events)
        listener, recognizer, _callbacks = self.make_listener(
            recognizer, on_word=on_word
        )
        listener.resume_waiting()
        recognizer.sessions[-1].emit(
            update(
                endpoint_text=" 开始。 ",
                endpoint_reached=True,
                segment_start_ms=1234,
            )
        )
        self.assertTrue(delivered.wait(1.0))
        self.assertEqual(
            events,
            ["取消旧会话", ("回调应用", "开始", 1234)],
        )
        self.assertEqual(listener.state, "paused")

    def test_command_is_not_dispatched_if_old_decoder_did_not_exit(self):
        delivered = threading.Event()
        listener, recognizer, callbacks = self.make_listener(
            on_error=MagicMock(side_effect=lambda *_args: delivered.set())
        )
        listener.resume_waiting()
        recognizer.sessions[-1]._done = NeverDone()
        recognizer.sessions[-1].emit(
            update(endpoint_text="开始", endpoint_reached=True)
        )
        self.assertTrue(delivered.wait(1.0))
        callbacks["on_word"].assert_not_called()
        callbacks["on_error"].assert_called_once()
        self.assertIn("没有按时退出", callbacks["on_error"].call_args.args[0])

    def test_late_callback_from_previous_generation_is_ignored(self):
        listener, recognizer, callbacks = self.make_listener()
        listener.resume_waiting()
        old_session = recognizer.sessions[-1]
        listener.pause()
        listener.resume_waiting()
        old_session.emit(
            update(endpoint_text="开始", endpoint_reached=True, segment_start_ms=90)
        )
        callbacks["on_word"].assert_not_called()
        self.assertEqual(listener.state, "waiting")

    def test_resume_and_prepare_never_create_a_second_session_if_cancel_times_out(self):
        listener, recognizer, callbacks = self.make_listener()
        self.assertTrue(listener.resume_waiting())
        recognizer.sessions[-1]._done = NeverDone()

        self.assertFalse(listener.resume_waiting())
        self.assertEqual(len(recognizer.sessions), 1)
        self.assertEqual(listener.state, "failed")
        callbacks["on_error"].assert_called_once()

        callbacks["on_error"].reset_mock()
        self.assertFalse(listener.prepare_recording("op-after-timeout"))
        self.assertEqual(len(recognizer.sessions), 1)
        self.assertEqual(listener.state, "failed")
        callbacks["on_error"].assert_called_once()

    def test_prepared_recording_rejects_pcm_until_activated(self):
        listener, recognizer, _callbacks = self.make_listener()
        self.assertTrue(listener.prepare_recording("op-1"))
        session = recognizer.sessions[-1]
        self.assertEqual(listener.state, "prepared")
        self.assertFalse(listener.feed_pcm16(bytes(320), 16000))
        self.assertEqual(session.fed, [])

        self.assertTrue(listener.activate_recording())
        self.assertTrue(listener.feed_pcm16(bytes(320), 16000))
        self.assertEqual(session.fed, [(bytes(320), 16000)])

    def test_recording_forwards_body_updates_and_intercepts_exact_end_endpoint(self):
        delivered = threading.Event()
        listener, recognizer, callbacks = self.make_listener(
            on_word=MagicMock(side_effect=lambda *_args: delivered.set())
        )
        listener.prepare_recording("op-body")
        listener.activate_recording()
        session = recognizer.sessions[-1]

        body = update(partial_text="正文内容")
        session.emit(body)
        callbacks["on_update"].assert_called_once_with(body)

        ordinary_endpoint = update(
            endpoint_text="正文包含结束阶段",
            endpoint_reached=True,
            segment_start_ms=700,
        )
        session.emit(ordinary_endpoint)
        self.assertEqual(callbacks["on_update"].call_count, 2)

        stop_endpoint = update(
            endpoint_text="结束！",
            endpoint_reached=True,
            segment_start_ms=1500,
        )
        session.emit(stop_endpoint)
        self.assertTrue(delivered.wait(1.0))
        callbacks["on_word"].assert_called_once_with("结束", 1500)
        self.assertEqual(callbacks["on_update"].call_count, 2)
        self.assertTrue(session.cancelled)

    def test_pause_invalidates_callbacks_and_cancels_session(self):
        listener, recognizer, callbacks = self.make_listener()
        listener.prepare_recording("op-pause")
        listener.activate_recording()
        session = recognizer.sessions[-1]
        listener.pause()
        session.emit(update(partial_text="迟到正文"))
        callbacks["on_update"].assert_not_called()
        self.assertTrue(session.cancelled)
        self.assertFalse(listener.running)

    def test_queue_failure_reports_error_only_after_session_is_cancelled(self):
        events = []
        delivered = threading.Event()

        def on_error(message):
            events.append(("错误", message))
            delivered.set()

        recognizer = FakeRecognizer(events)
        listener, recognizer, _callbacks = self.make_listener(
            recognizer, on_error=on_error
        )
        listener.resume_waiting()
        recognizer.sessions[-1].feed_result = False
        self.assertFalse(listener.feed_pcm16(bytes(320), 16000))
        self.assertTrue(delivered.wait(1.0))
        self.assertEqual(events[0], "取消旧会话")
        self.assertEqual(events[1][0], "错误")
        self.assertEqual(listener.state, "paused")

    def test_failed_model_start_is_visible_and_not_running(self):
        recognizer = FakeRecognizer()
        recognizer.failure = RuntimeError("模型损坏")
        listener, _recognizer, callbacks = self.make_listener(recognizer)
        self.assertFalse(listener.resume_waiting())
        self.assertFalse(listener.running)
        callbacks["on_error"].assert_called_once()
        self.assertIn("模型损坏", callbacks["on_error"].call_args.args[0])

    def test_control_phrase_normalization_and_classification(self):
        self.assertEqual(normalize_standby_control_phrase(" 开始，录音。"), "开始录音")
        self.assertEqual(classify_standby_control_phrase("開始說話！"), "开始")
        self.assertEqual(classify_standby_control_phrase("停止录音。"), "结束")
        self.assertIsNone(classify_standby_control_phrase("现在开始整理正文"))
        self.assertEqual(standby_control_match("开始"), ("开始", 100))
        self.assertEqual(classify_standby_control_phrase("开始了", 80), "开始")
        self.assertIsNone(classify_standby_control_phrase("开始了", 90))

if __name__ == "__main__":
    unittest.main()
