import sys
import threading
import time
import unittest
from collections import deque
from unittest.mock import MagicMock, patch

import app
from recognition_router import RecognitionResult
from realtime_asr import RealtimeUpdate


SAMPLE_RATE = 16_000


def _sample(value: int) -> bytes:
    return int(value).to_bytes(2, "little", signed=True)


def _alternating_pcm(amplitude: int, sample_count: int = SAMPLE_RATE) -> bytes:
    pair = _sample(amplitude) + _sample(-amplitude)
    return pair * (sample_count // 2)


VALID_PCM = _alternating_pcm(800)


def _result(text: str) -> RecognitionResult:
    return RecognitionResult(
        text=text,
        requested_engine="local:test",
        actual_engine="local:test",
        device_label="测试模型",
    )


class RecognitionQueueTests(unittest.TestCase):
    @staticmethod
    def _instance() -> app.VoiceButtonApp:
        instance = app.VoiceButtonApp.__new__(app.VoiceButtonApp)
        instance.config = {
            "auto_paste_enabled": False,
            "paste_wait_ms": 0,
            "live_transcript_visible": False,
            "standby_enabled": False,
        }
        instance.lock = threading.Lock()
        instance.pipeline_lock = threading.RLock()
        instance.side_effect_lock = threading.RLock()
        instance.recognition_condition = threading.Condition(instance.lock)
        instance.stop_event = threading.Event()
        instance.recognition_jobs = deque()
        instance.active_batch_id = ""
        instance.batch_results = []
        instance.batch_errors = []
        instance.pending_batch_deliveries = deque()
        instance.queued_router_counts = {}
        instance.active_recognition_job = None
        instance.pending_history_operations = set()
        instance.recording = False
        instance.busy = False
        instance.closed = False
        instance.operation_id = ""
        instance.origin_hwnd = 456
        instance.standby_operation = False
        instance.standby_end_cue_pending = False
        instance.standby_stop_at_ms = None
        instance.realtime_session = None
        instance.realtime_revision = 0
        instance.active_router = None
        instance.recognition_router = None
        instance.history_store = MagicMock()
        instance.run_log = MagicMock()
        instance.error_log = MagicMock()
        instance.window = MagicMock(hwnd=777)
        instance.transcript_window = MagicMock()
        instance.audio_monitor = MagicMock()
        instance.audio_monitor.continuous = False
        instance.standby_listener = MagicMock()
        instance._play_recording_cue = MagicMock()
        instance._restore_resting_pipeline = MagicMock()
        instance._warning = MagicMock()
        return instance

    @staticmethod
    def _job(
        operation_id: str,
        batch_id: str,
        *,
        pcm: bytes = VALID_PCM,
        origin_hwnd: int = 456,
        router=None,
        session=None,
    ) -> app.RecognitionJob:
        return app.RecognitionJob(
            operation_id=operation_id,
            batch_id=batch_id,
            pcm=pcm,
            sample_rate=SAMPLE_RATE,
            origin_hwnd=origin_hwnd,
            standby=False,
            session=session,
            router=router,
            created_at=time.monotonic(),
        )

    @staticmethod
    def _stop_workers(
        instance: app.VoiceButtonApp, *workers: threading.Thread
    ) -> None:
        instance.stop_event.set()
        with instance.recognition_condition:
            instance.recognition_condition.notify_all()
        for worker in workers:
            worker.join(timeout=2.0)

    def test_three_jobs_keep_recording_order_and_deliver_batch_once(self):
        instance = self._instance()
        batch_id = "batch-three"
        router = MagicMock()
        router.transcribe_pcm16.side_effect = [
            _result("第一段"),
            _result("第二段"),
            _result("第三段"),
        ]
        jobs = [
            self._job(f"op-{index}", batch_id, router=router)
            for index in range(1, 4)
        ]
        instance.recognition_jobs.extend(jobs)
        instance.active_batch_id = batch_id
        instance.pending_history_operations.update(job.operation_id for job in jobs)
        instance.queued_router_counts[id(router)] = len(jobs)
        instance.recognition_router = router
        delivered = threading.Event()
        instance._ensure_clipboard_text = MagicMock(
            side_effect=lambda *_args: delivered.set()
        )

        worker = threading.Thread(target=instance._recognition_worker, daemon=True)
        delivery_worker = threading.Thread(
            target=instance._batch_delivery_worker, daemon=True
        )
        worker.start()
        delivery_worker.start()
        try:
            self.assertTrue(delivered.wait(2.0), "三段识别没有按时完成整批输出")
        finally:
            self._stop_workers(instance, worker, delivery_worker)

        self.assertFalse(worker.is_alive())
        self.assertFalse(delivery_worker.is_alive())
        self.assertEqual(router.transcribe_pcm16.call_count, 3)
        instance._ensure_clipboard_text.assert_called_once_with(
            "第一段\n第二段\n第三段", "op-1", "整批识别完成"
        )
        self.assertEqual(instance.batch_results, [])
        self.assertEqual(instance.active_batch_id, "")

    def test_history_reserve_mark_and_complete_failures_do_not_block_recognition(self):
        instance = self._instance()
        instance.operation_id = "history-errors"
        instance.origin_hwnd = 456
        instance.recording = True
        instance.busy = True
        instance.audio_monitor.stop.return_value = (VALID_PCM, SAMPLE_RATE)
        instance.history_store.reserve.side_effect = OSError("reserve locked")
        instance.history_store.mark_recognizing.side_effect = OSError("mark locked")
        instance.history_store.complete.side_effect = OSError("complete locked")
        router = MagicMock()
        router.transcribe_pcm16.return_value = _result("数据库失败也要输出")
        instance.recognition_router = router
        instance.active_router = router

        instance._finish()

        self.assertEqual(len(instance.recognition_jobs), 1)
        job = instance.recognition_jobs.popleft()
        instance._process_recognition_job(job)

        router.transcribe_pcm16.assert_called_once_with(VALID_PCM, SAMPLE_RATE)
        self.assertEqual(
            [(item.operation_id, item.text) for item in instance.batch_results],
            [("history-errors", "数据库失败也要输出")],
        )
        self.assertGreaterEqual(instance.error_log.error.call_count, 3)
        instance.history_store.fail.assert_not_called()

    def test_finish_transfers_old_router_reference_before_it_can_close(self):
        instance = self._instance()
        instance.operation_id = "router-transfer"
        instance.recording = True
        instance.busy = True
        instance.audio_monitor.stop.return_value = (VALID_PCM, SAMPLE_RATE)
        old_router = MagicMock()
        new_router = MagicMock()
        instance.active_router = old_router
        instance.recognition_router = new_router

        instance._finish()

        self.assertEqual(len(instance.recognition_jobs), 1)
        job = instance.recognition_jobs.popleft()
        self.assertIs(job.router, old_router)
        self.assertEqual(instance.queued_router_counts[id(old_router)], 1)
        old_router.close.assert_not_called()
        instance._release_job_router(old_router)
        old_router.close.assert_called_once_with()

    def test_finish_cannot_enqueue_after_cleanup_has_started(self):
        instance = self._instance()
        instance.operation_id = "shutdown-race"
        instance.recording = True
        instance.busy = True
        capture_started = threading.Event()
        allow_capture_to_finish = threading.Event()
        session = MagicMock()
        instance.realtime_session = session
        instance.active_router = MagicMock()
        instance.recognition_router = MagicMock()

        def finish_capture():
            capture_started.set()
            self.assertTrue(allow_capture_to_finish.wait(2.0))
            return VALID_PCM, SAMPLE_RATE

        instance.audio_monitor.stop.side_effect = finish_capture
        finish_thread = threading.Thread(target=instance._finish, daemon=True)
        cleanup_thread = threading.Thread(target=instance.cleanup, daemon=True)
        finish_thread.start()
        self.assertTrue(capture_started.wait(1.0))
        cleanup_thread.start()
        self.assertTrue(instance.stop_event.wait(1.0))
        allow_capture_to_finish.set()
        finish_thread.join(timeout=2.0)
        cleanup_thread.join(timeout=2.0)

        self.assertFalse(finish_thread.is_alive())
        self.assertFalse(cleanup_thread.is_alive())
        self.assertEqual(len(instance.recognition_jobs), 0)
        instance.history_store.reserve.assert_not_called()
        instance.history_store.fail_pending.assert_called_once_with(
            "程序已退出，识别任务未完成。"
        )
        session.cancel.assert_called_once_with()

    def test_auto_paste_batches_are_split_by_origin_window(self):
        instance = self._instance()
        instance.config["auto_paste_enabled"] = True
        instance.active_batch_id = "window-safe-batch"
        instance.batch_results = [
            app.RecognitionBatchItem("a-1", 111, False, "窗口A第一段"),
            app.RecognitionBatchItem("b-1", 222, False, "窗口B第一段"),
            app.RecognitionBatchItem("a-2", 111, False, "窗口A第二段"),
        ]

        with patch.object(app, "BATCH_SETTLE_SECONDS", 0):
            instance._finish_batch_when_idle("window-safe-batch")

        deliveries = list(instance.pending_batch_deliveries)
        self.assertEqual(len(deliveries), 2)
        self.assertEqual(
            [(item.origin_hwnd, item.text) for item in deliveries[0].results],
            [(111, "窗口A第一段"), (111, "窗口A第二段")],
        )
        self.assertEqual(
            [(item.origin_hwnd, item.text) for item in deliveries[1].results],
            [(222, "窗口B第一段")],
        )
        self.assertTrue(deliveries[0].auto_paste_enabled)
        self.assertTrue(deliveries[1].auto_paste_enabled)

    def test_mixed_origin_delivery_never_pastes_everything_to_first_window(self):
        instance = self._instance()
        instance.config["auto_paste_enabled"] = True
        instance._ensure_clipboard_text = MagicMock()
        items = [
            app.RecognitionBatchItem("a", 111, False, "窗口A"),
            app.RecognitionBatchItem("b", 222, False, "窗口B"),
        ]

        with patch.object(app, "activate_window_and_wait") as activate, patch.object(
            app, "paste"
        ) as paste_text:
            instance._deliver_recognition_batch("mixed", items, [])

        instance._ensure_clipboard_text.assert_called_once_with(
            "窗口A\n窗口B", "a", "整批识别完成"
        )
        activate.assert_not_called()
        paste_text.assert_not_called()
        instance._warning.assert_called_once()

    def test_failed_first_window_delivery_blocks_later_clipboard_overwrite(self):
        instance = self._instance()
        first = app.CompletedRecognitionBatch(
            "two-windows",
            [app.RecognitionBatchItem("a", 111, False, "窗口A")],
            [],
            auto_paste_enabled=True,
        )
        second = app.CompletedRecognitionBatch(
            "two-windows",
            [app.RecognitionBatchItem("b", 222, False, "窗口B")],
            [],
            auto_paste_enabled=True,
        )
        instance.pending_batch_deliveries.extend([first, second])
        clipboard_writes: list[str] = []
        instance._ensure_clipboard_text = MagicMock(
            side_effect=lambda text, *_args: clipboard_writes.append(text)
        )
        attempted = threading.Event()

        def cannot_activate(_hwnd):
            attempted.set()
            return False

        with patch.object(app, "activate_window_and_wait", side_effect=cannot_activate):
            worker = threading.Thread(
                target=instance._batch_delivery_worker, daemon=True
            )
            worker.start()
            try:
                self.assertTrue(attempted.wait(1.0))
                deadline = time.monotonic() + 1.0
                while first.attempts < 1 and time.monotonic() < deadline:
                    time.sleep(0.01)
            finally:
                self._stop_workers(instance, worker)

        self.assertGreaterEqual(first.attempts, 1)
        self.assertEqual(list(instance.pending_batch_deliveries), [first, second])
        self.assertEqual(clipboard_writes, ["窗口A"])

    def test_completed_batch_drops_pcm_payload_after_recognition(self):
        instance = self._instance()
        router = MagicMock()
        router.transcribe_pcm16.return_value = _result("轻量结果")
        job = self._job("drop-pcm", "memory-batch", router=router)
        instance.pending_history_operations.add(job.operation_id)
        instance.queued_router_counts[id(router)] = 1

        instance._process_recognition_job(job)

        self.assertEqual(
            instance.batch_results,
            [app.RecognitionBatchItem("drop-pcm", 456, False, "轻量结果")],
        )
        self.assertFalse(any(hasattr(item, "pcm") for item in instance.batch_results))

    def test_idle_worker_releases_the_last_job_pcm(self):
        instance = self._instance()
        job = self._job("release-worker-pcm", "release-batch")
        instance.recognition_jobs.append(job)
        instance._process_recognition_job = MagicMock()
        finished = threading.Event()
        instance._finish_batch_when_idle = MagicMock(
            side_effect=lambda _batch_id: finished.set()
        )
        worker = threading.Thread(target=instance._recognition_worker, daemon=True)
        worker.start()
        try:
            self.assertTrue(finished.wait(1.0))
            deadline = time.monotonic() + 1.0
            retained = True
            while time.monotonic() < deadline:
                frame = sys._current_frames().get(worker.ident)
                retained = False
                while frame is not None:
                    if frame.f_code.co_name == "_recognition_worker":
                        retained = frame.f_locals.get("job") is job
                        break
                    frame = frame.f_back
                if not retained:
                    break
                time.sleep(0.01)
        finally:
            self._stop_workers(instance, worker)

        self.assertFalse(retained, "空闲识别线程不应继续持有上一段 PCM")

    def test_short_recording_always_cancels_unfinished_realtime_session(self):
        instance = self._instance()
        session = MagicMock()
        session.wait_closed.return_value = False
        job = self._job(
            "short",
            "batch-short",
            pcm=_alternating_pcm(800, 1_000),
            session=session,
        )
        instance.pending_history_operations.add(job.operation_id)

        instance._process_recognition_job(job)

        session.finish.assert_not_called()
        session.wait_closed.assert_called_once_with(timeout=0)
        session.cancel.assert_called_once_with()
        self.assertEqual(instance.batch_results, [])
        self.assertEqual(len(instance.batch_errors), 1)

    def test_batch_waits_while_recording_or_recording_start_is_busy(self):
        for state_name in ("recording", "busy"):
            with self.subTest(state=state_name):
                instance = self._instance()
                instance.active_batch_id = f"batch-{state_name}"
                setattr(instance, state_name, True)
                delivered = threading.Event()
                instance._deliver_recognition_batch = MagicMock(
                    side_effect=lambda *_args, **_kwargs: delivered.set()
                )
                delivery_worker = threading.Thread(
                    target=instance._batch_delivery_worker,
                    daemon=True,
                )
                delivery_worker.start()
                finisher = threading.Thread(
                    target=instance._finish_batch_when_idle,
                    args=(instance.active_batch_id,),
                    daemon=True,
                )
                finisher.start()
                try:
                    time.sleep(0.08)
                    self.assertTrue(finisher.is_alive())
                    instance._deliver_recognition_batch.assert_not_called()
                    with instance.recognition_condition:
                        setattr(instance, state_name, False)
                        instance.recognition_condition.notify_all()
                    self.assertTrue(delivered.wait(1.0))
                finally:
                    instance.stop_event.set()
                    with instance.recognition_condition:
                        instance.recognition_condition.notify_all()
                    finisher.join(timeout=1.0)
                    delivery_worker.join(timeout=1.0)

                self.assertFalse(finisher.is_alive())
                instance._deliver_recognition_batch.assert_called_once()

    def test_worker_continues_after_one_batch_delivery_raises(self):
        instance = self._instance()
        jobs = [
            self._job("first", "batch-first"),
            self._job("second", "batch-second"),
        ]
        instance.recognition_jobs.extend(jobs)
        instance._process_recognition_job = MagicMock()
        finished_batches = []

        def finish_batch(batch_id):
            finished_batches.append(batch_id)
            if len(finished_batches) == 1:
                raise RuntimeError("剪贴板暂时不可用")
            instance.stop_event.set()

        instance._finish_batch_when_idle = MagicMock(side_effect=finish_batch)
        worker = threading.Thread(target=instance._recognition_worker, daemon=True)
        worker.start()
        worker.join(timeout=2.0)
        if worker.is_alive():
            self._stop_workers(instance, worker)

        self.assertFalse(worker.is_alive())
        self.assertEqual(
            [call.args[0].operation_id for call in instance._process_recognition_job.call_args_list],
            ["first", "second"],
        )
        self.assertEqual(finished_batches, ["batch-first", "batch-second"])
        instance.error_log.exception.assert_called_once()

    def test_delivery_worker_retries_without_losing_the_batch(self):
        instance = self._instance()
        delivered = threading.Event()
        batch = app.CompletedRecognitionBatch(
            "retry-batch",
            [app.RecognitionBatchItem("op", 456, False, "不可丢失的文字")],
            [],
        )
        instance.pending_batch_deliveries.append(batch)
        attempts = 0

        def deliver(*_args, **_kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("剪贴板繁忙")
            delivered.set()

        instance._deliver_recognition_batch = MagicMock(side_effect=deliver)

        worker = threading.Thread(target=instance._batch_delivery_worker, daemon=True)
        worker.start()
        try:
            self.assertTrue(delivered.wait(2.5))
        finally:
            self._stop_workers(instance, worker)

        self.assertEqual(instance._deliver_recognition_batch.call_count, 2)
        self.assertEqual(len(instance.pending_batch_deliveries), 0)

    def test_cleanup_broadcasts_session_cancel_and_fails_history_once(self):
        instance = self._instance()
        sessions = [MagicMock() for _ in range(12)]
        for session in sessions:
            session.wait_closed.return_value = True
        instance.recognition_jobs.extend(
            self._job(f"queued-{index}", "batch", session=session)
            for index, session in enumerate(sessions)
        )
        instance.recognition_router = MagicMock()

        started = time.monotonic()
        instance.cleanup()
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 1.0)
        for session in sessions:
            session.request_cancel.assert_called_once_with()
            session.cancel.assert_not_called()
        instance.history_store.fail_pending.assert_called_once_with(
            "程序已退出，识别任务未完成。"
        )

    def test_realtime_updates_write_actual_model_text_to_pending_history(self):
        instance = self._instance()
        instance.operation_id = "newer-recording"
        instance.pending_history_operations.add("pending-op")
        updates = [
            RealtimeUpdate("pending-op", 1, "", "真", 120, False),
            RealtimeUpdate("pending-op", 2, "真实", "文字", 240, False),
        ]

        for update in updates:
            instance._on_realtime_update(update)

        self.assertEqual(
            instance.history_store.mark_recognizing.call_args_list,
            [
                unittest.mock.call("pending-op", "真"),
                unittest.mock.call("pending-op", "真实文字"),
            ],
        )
        instance.transcript_window.update.assert_not_called()

    def test_silence_noise_and_single_impulse_are_rejected_but_voice_is_kept(self):
        digital_silence = bytes(SAMPLE_RATE * 2)
        low_noise = _alternating_pcm(30)
        impulse = bytearray(digital_silence)
        impulse[4_000:4_002] = _sample(4_000)
        sustained_voice = _alternating_pcm(800, SAMPLE_RATE // 5)

        self.assertFalse(app.has_effective_pcm16_audio(digital_silence, SAMPLE_RATE))
        self.assertFalse(app.has_effective_pcm16_audio(low_noise, SAMPLE_RATE))
        self.assertFalse(app.has_effective_pcm16_audio(bytes(impulse), SAMPLE_RATE))
        self.assertTrue(app.has_effective_pcm16_audio(sustained_voice, SAMPLE_RATE))

    def test_separated_click_frames_do_not_accumulate_as_continuous_voice(self):
        active_frame = _alternating_pcm(800, SAMPLE_RATE // 50)
        silent_frame = bytes(len(active_frame))
        separated_clicks = b"".join(
            active_frame if index % 2 == 0 else silent_frame
            for index in range(10)
        )

        self.assertFalse(
            app.has_effective_pcm16_audio(separated_clicks, SAMPLE_RATE),
            "不连续的短脉冲不能累计成有效语音",
        )


if __name__ == "__main__":
    unittest.main()
