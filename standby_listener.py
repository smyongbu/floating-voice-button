from __future__ import annotations

import threading
import time
from difflib import SequenceMatcher
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from realtime_asr import RealtimeRecognizer, RealtimeSession, RealtimeUpdate


START_CONTROL_WORDS = frozenset(
    ("开始", "開始", "开始录音", "開始錄音", "开始说话", "開始說話")
)
END_CONTROL_WORDS = frozenset(
    (
        "结束",
        "結束",
        "停止录音",
        "停止錄音",
        "结束录音",
        "結束錄音",
        "结束说话",
        "結束說話",
    )
)
_CONTROL_SEPARATORS = frozenset(
    " \t\r\n，,。.!！?？:：;；、‘’“”\"'（）()【】[]《》<>"
)


def normalize_standby_control_phrase(text: str) -> str:
    """只移除空白与标点，保留所有文字后再做完整短句匹配。"""
    return "".join(
        character
        for character in str(text or "").strip()
        if character not in _CONTROL_SEPARATORS
    )


def standby_control_match(text: str) -> tuple[str | None, int]:
    """返回最接近的控制命令及文字匹配置信度（不是声学概率）。"""
    normalized = normalize_standby_control_phrase(text)
    if not normalized:
        return None, 0
    candidates = [("开始", word) for word in START_CONTROL_WORDS]
    candidates.extend(("结束", word) for word in END_CONTROL_WORDS)
    command, _word, score = max(
        (
            (command, word, round(SequenceMatcher(None, normalized, word).ratio() * 100))
            for command, word in candidates
        ),
        key=lambda item: item[2],
    )
    return command, int(score)


def classify_standby_control_phrase(text: str, confidence_threshold: int = 80) -> str | None:
    """仅把完整端点短句归类为开始或结束，正文中的同名词不会命中。"""
    command, score = standby_control_match(text)
    return command if score >= max(70, min(100, int(confidence_threshold))) else None


class StandbyVoiceListener:
    """纯 Python 流式识别状态机；音频必须由外部唯一麦克风流传入。"""

    def __init__(
        self,
        recognizer: RealtimeRecognizer,
        on_word: Callable[[str, int], None],
        on_ready: Callable[[], None],
        on_update: Callable[[RealtimeUpdate], None],
        on_ignored: Callable[[int], None],
        on_error: Callable[[str], None],
        confidence_threshold: int = 80,
    ) -> None:
        self.recognizer = recognizer
        self.on_word = on_word
        self.on_ready = on_ready
        self.on_update = on_update
        self.on_ignored = on_ignored
        self.on_error = on_error
        self.confidence_threshold = max(70, min(100, int(confidence_threshold)))
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._generation = 0
        self._state = "paused"
        self._session: RealtimeSession | None = None
        self._operation_id = ""

    @property
    def running(self) -> bool:
        with self._lock:
            return self._session is not None and self._state in {
                "waiting",
                "prepared",
                "recording",
            }

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def start(self) -> bool:
        """兼容旧调用；新的待命入口统一由 resume_waiting 管理。"""
        return self.resume_waiting()

    def resume_waiting(self) -> bool:
        """创建只检查“开始”的待命会话；普通文本不会永久累计。"""
        if not self._wait_for_async_transition():
            return False
        generation, old_session = self._begin_transition("starting_wait")
        cancel_error = self._cancel_session(old_session)
        if cancel_error is not None:
            self._preserve_cancel_failure(generation, old_session, cancel_error)
            return False
        try:
            session = self.recognizer.create_session(
                f"standby-{generation}",
                lambda update: self._handle_update(generation, "waiting", update),
                max_stable_segments=0,
            )
        except Exception as exc:
            self._fail_start(generation, f"本地待命识别启动失败：{exc}")
            return False
        if not self._install_session(generation, "waiting", session, f"standby-{generation}"):
            self._cancel_session(session)
            return False
        with self._lock:
            ready = generation == self._generation and self._state == "waiting"
        if ready:
            try:
                self.on_ready()
            except Exception:
                pass
        return ready

    def prepare_recording(self, operation_id: str) -> bool:
        """预建正文会话；activate_recording 前传入的提示音 PCM 会被拒绝。"""
        normalized_id = str(operation_id or "").strip()
        if not normalized_id:
            raise ValueError("录音操作编号不能为空。")
        if not self._wait_for_async_transition():
            return False
        generation, old_session = self._begin_transition("preparing")
        cancel_error = self._cancel_session(old_session)
        if cancel_error is not None:
            self._preserve_cancel_failure(generation, old_session, cancel_error)
            return False
        try:
            session = self.recognizer.create_session(
                normalized_id,
                lambda update: self._handle_update(generation, "recording", update),
            )
        except Exception as exc:
            self._fail_start(generation, f"本地录音控制识别启动失败：{exc}")
            return False
        if not self._install_session(generation, "prepared", session, normalized_id):
            self._cancel_session(session)
            return False
        return True

    def activate_recording(self) -> bool:
        """提示音结束后才允许正文 PCM 进入预建会话。"""
        with self._lock:
            if self._state != "prepared" or self._session is None:
                return False
            self._state = "recording"
            return True

    def pause(self) -> bool:
        """使当前 generation 立即失效，再同步取消旧解码会话。"""
        if not self._wait_for_async_transition():
            return False
        _generation, old_session = self._begin_transition("paused")
        cancel_error = self._cancel_session(old_session)
        if cancel_error is not None:
            self._preserve_cancel_failure(_generation, old_session, cancel_error)
            return False
        return True

    def stop(self) -> bool:
        return self.pause()

    def feed_pcm16(self, pcm: bytes, sample_rate: int = 16000) -> bool:
        """只转发 PCM；本类不创建、查询或关闭任何麦克风设备。"""
        with self._lock:
            if self._state not in {"waiting", "recording"} or self._session is None:
                return False
            generation = self._generation
            session = self._session
        try:
            accepted = bool(session.feed_pcm16(pcm, sample_rate))
        except Exception:
            accepted = False
        if not accepted:
            self._retire_with_error_async(
                generation,
                "本地待命识别速度跟不上音频，监听已暂停。",
            )
        return accepted

    def _begin_transition(
        self, state: str
    ) -> tuple[int, RealtimeSession | None]:
        with self._lock:
            self._generation += 1
            generation = self._generation
            old_session, self._session = self._session, None
            self._operation_id = ""
            self._state = state
            return generation, old_session

    def _wait_for_async_transition(self, timeout: float = 3.0) -> bool:
        """等待命令派发/错误收尾完成，避免新旧解码会话重叠。"""
        deadline = time.monotonic() + max(0.1, float(timeout))
        with self._condition:
            while self._state in {"dispatching", "failing"}:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self._condition.wait(remaining):
                    return False
            return True

    def _preserve_cancel_failure(
        self,
        generation: int,
        session: RealtimeSession | None,
        error: Exception,
    ) -> None:
        with self._condition:
            if generation != self._generation:
                return
            self._session = session
            self._state = "failed"
            self._condition.notify_all()
        message = (
            "旧实时模型解码线程没有按时退出。"
            if isinstance(error, TimeoutError)
            else f"旧实时模型解码会话没有安全退出：{type(error).__name__}"
        )
        try:
            self.on_error(message)
        except Exception:
            pass

    def _install_session(
        self,
        generation: int,
        state: str,
        session: RealtimeSession,
        operation_id: str,
    ) -> bool:
        with self._lock:
            if generation != self._generation:
                return False
            self._session = session
            self._operation_id = operation_id
            self._state = state
            return True

    def _fail_start(self, generation: int, message: str) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._state = "paused"
        try:
            self.on_error(message)
        except Exception:
            pass

    def _handle_update(
        self,
        generation: int,
        mode: str,
        update: RealtimeUpdate,
    ) -> None:
        with self._lock:
            expected_state = "waiting" if mode == "waiting" else "recording"
            if generation != self._generation or self._state != expected_state:
                return

        endpoint_text = str(getattr(update, "endpoint_text", "") or "")
        endpoint_flag = getattr(update, "endpoint_reached", None)
        endpoint_reached = bool(endpoint_text) if endpoint_flag is None else bool(endpoint_flag)
        command = (
            classify_standby_control_phrase(endpoint_text, self.confidence_threshold)
            if endpoint_reached and endpoint_text
            else None
        )

        if mode == "waiting":
            if not endpoint_reached or not endpoint_text:
                return
            if command == "开始":
                self._retire_and_dispatch_command(
                    generation,
                    "开始",
                    self._segment_start_ms(update),
                )
                return
            with self._lock:
                valid = generation == self._generation and self._state == "waiting"
            if valid:
                try:
                    self.on_ignored(len(normalize_standby_control_phrase(endpoint_text)))
                except Exception:
                    pass
            return

        if endpoint_reached and command == "结束":
            self._retire_and_dispatch_command(
                generation,
                "结束",
                self._segment_start_ms(update),
            )
            return
        with self._lock:
            if generation != self._generation or self._state != "recording":
                return
        try:
            self.on_update(update)
        except Exception:
            pass

    @staticmethod
    def _segment_start_ms(update: Any) -> int:
        try:
            return max(0, int(getattr(update, "segment_start_ms", 0) or 0))
        except (TypeError, ValueError):
            return 0

    def _retire_and_dispatch_command(
        self,
        generation: int,
        command: str,
        segment_start_ms: int,
    ) -> None:
        with self._lock:
            if generation != self._generation or self._state not in {
                "waiting",
                "recording",
            }:
                return
            session, self._session = self._session, None
            self._operation_id = ""
            self._state = "dispatching"
        try:
            threading.Thread(
                target=self._cancel_then_dispatch_command,
                args=(generation, session, command, segment_start_ms),
                name=f"本地控制词切换-{command}-{generation}",
                daemon=True,
            ).start()
        except Exception as exc:
            with self._condition:
                if generation == self._generation and self._state == "dispatching":
                    self._session = session
                    self._state = "failed"
                self._condition.notify_all()
            try:
                self.on_error(f"控制词切换线程启动失败：{type(exc).__name__}")
            except Exception:
                pass

    def _cancel_then_dispatch_command(
        self,
        generation: int,
        session: RealtimeSession | None,
        command: str,
        segment_start_ms: int,
    ) -> None:
        error = self._cancel_session(session)
        if error is not None:
            self._preserve_cancel_failure(generation, session, error)
            return
        with self._condition:
            if generation != self._generation or self._state != "dispatching":
                self._condition.notify_all()
                return
        callback_error: Exception | None = None
        try:
            self.on_word(command, segment_start_ms)
        except Exception as exc:
            callback_error = exc
        finally:
            with self._condition:
                if generation == self._generation and self._state == "dispatching":
                    self._state = "paused"
                self._condition.notify_all()
        if callback_error is not None:
            try:
                self.on_error(
                    f"控制词处理失败：{type(callback_error).__name__}"
                )
            except Exception:
                pass

    def _retire_with_error_async(self, generation: int, message: str) -> None:
        with self._lock:
            if generation != self._generation or self._state not in {
                "waiting",
                "recording",
            }:
                return
            session, self._session = self._session, None
            self._operation_id = ""
            self._state = "failing"
        try:
            threading.Thread(
                target=self._cancel_then_report_error,
                args=(generation, session, message),
                name=f"本地待命错误处理-{generation}",
                daemon=True,
            ).start()
        except Exception as exc:
            with self._condition:
                if generation == self._generation and self._state == "failing":
                    self._session = session
                    self._state = "failed"
                self._condition.notify_all()
            try:
                self.on_error(f"待命错误处理线程启动失败：{type(exc).__name__}")
            except Exception:
                pass

    def _cancel_then_report_error(
        self,
        generation: int,
        session: RealtimeSession | None,
        message: str,
    ) -> None:
        cancel_error = self._cancel_session(session)
        if cancel_error is not None:
            self._preserve_cancel_failure(generation, session, cancel_error)
            return
        with self._condition:
            if generation != self._generation or self._state != "failing":
                self._condition.notify_all()
                return
            self._state = "paused"
            self._condition.notify_all()
        try:
            self.on_error(message)
        except Exception:
            pass

    @staticmethod
    def _cancel_session(session: RealtimeSession | None) -> Exception | None:
        if session is None:
            return None
        try:
            session.cancel()
        except Exception as exc:
            return exc
        wait_closed = getattr(session, "wait_closed", None)
        if callable(wait_closed):
            try:
                if not wait_closed(0.75):
                    return TimeoutError("旧实时模型解码线程没有按时退出。")
            except Exception as exc:
                return exc
        else:
            done = getattr(session, "_done", None)
            if done is not None and hasattr(done, "wait"):
                try:
                    if not done.wait(0.75):
                        return TimeoutError("旧实时模型解码线程没有按时退出。")
                except Exception as exc:
                    return exc
        return None
