from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Callable


def normalized_level_from_int16(data: bytes) -> float:
    """把单声道 int16 PCM 转为 0..1 音量，带基础噪声门。"""
    samples = memoryview(data).cast("h")
    if not samples:
        return 0.0
    sampled = samples[::4]
    rms = math.sqrt(sum(value * value for value in sampled) / len(sampled)) / 32768.0
    return max(0.0, min(1.0, (rms - 0.006) * 9.0))


class AudioLevelMonitor:
    def __init__(self) -> None:
        self.stream = None
        self.callback: Callable[[list[float]], None] | None = None
        self.waiting_level_callback: Callable[[list[float]], None] | None = None
        self.capture_level_callback: Callable[[list[float]], None] | None = None
        self.monitor_pcm_callback: Callable[[bytes, int], bool | None] | None = None
        self.pcm_callback: Callable[[bytes, int], bool | None] | None = None
        self.history: deque[float] = deque([0.08] * 7, maxlen=7)
        self.smoothed = 0.0
        self.last_emit = 0.0
        self.lock = threading.RLock()
        self.lifecycle_lock = threading.RLock()
        self.chunks: list[bytes] = []
        self.sample_rate = 16000
        self._capturing = False
        self.continuous = False

    @property
    def running(self) -> bool:
        with self.lock:
            return self.stream is not None

    @property
    def is_open(self) -> bool:
        with self.lifecycle_lock:
            with self.lock:
                stream = self.stream
            if stream is None:
                return False
            try:
                return bool(getattr(stream, "active", True))
            except Exception:
                return False

    @property
    def capturing(self) -> bool:
        with self.lock:
            return self._capturing

    def start(
        self,
        callback: Callable[[list[float]], None],
        pcm_callback: Callable[[bytes, int], bool | None] | None = None,
    ) -> None:
        """兼容原有的一次性录音：打开输入流并立即开始保存正文。"""
        with self.lifecycle_lock:
            self.open_continuous(callback)
            with self.lock:
                self.continuous = False
            self.begin_capture(callback, pcm_callback)

    def open_continuous(
        self,
        callback: Callable[[list[float]], None],
        monitor_pcm_callback: Callable[[bytes, int], bool | None] | None = None,
    ) -> None:
        """打开唯一的连续麦克风流；待命音频只回调，不写入正文缓存。"""
        with self.lifecycle_lock:
            self._open_continuous(callback, monitor_pcm_callback)

    def _open_continuous(
        self,
        callback: Callable[[list[float]], None],
        monitor_pcm_callback: Callable[[bytes, int], bool | None] | None = None,
    ) -> None:
        import sounddevice as sd

        self.close()
        with self.lock:
            self.callback = callback
            self.waiting_level_callback = callback
            self.capture_level_callback = None
            self.monitor_pcm_callback = monitor_pcm_callback
            self.pcm_callback = None
            self.history = deque([0.08] * 7, maxlen=7)
            self.smoothed = 0.0
            self.last_emit = 0.0
            self.chunks = []
            self._capturing = False
            self.continuous = True

        def on_audio(indata, _frames, _time_info, _status) -> None:
            chunk = bytes(indata)
            with self.lock:
                sample_rate = self.sample_rate
                monitor_target = self.monitor_pcm_callback
                capture_target = self.pcm_callback if self._capturing else None
                level_target = (
                    self.capture_level_callback
                    if self._capturing
                    else self.waiting_level_callback
                )
                if self._capturing:
                    self.chunks.append(chunk)
            if monitor_target:
                try:
                    monitor_target(chunk, sample_rate)
                except Exception:
                    # PortAudio 回调不能被待命识别故障打断。
                    pass
            if capture_target and capture_target is not monitor_target:
                try:
                    capture_target(chunk, sample_rate)
                except Exception:
                    # 实时正文预览失败不能打断完整录音。
                    pass
            level = normalized_level_from_int16(chunk)
            coefficient = 0.62 if level > self.smoothed else 0.22
            self.smoothed += (level - self.smoothed) * coefficient
            now = time.monotonic()
            if now - self.last_emit < 0.045:
                return
            self.last_emit = now
            self.history.append(self.smoothed)
            if level_target:
                try:
                    level_target(list(self.history))
                except Exception:
                    # 窗口关闭或绘制失败不能让 PortAudio 回调线程退出。
                    pass

        attempts: list[dict] = []
        try:
            for host_api in sd.query_hostapis():
                if "wasapi" not in str(host_api.get("name", "")).casefold():
                    continue
                device = int(host_api.get("default_input_device", -1))
                if device < 0:
                    continue
                device_info = sd.query_devices(device)
                attempts.append({
                    "device": device,
                    "samplerate": 16000,
                    "extra_settings": sd.WasapiSettings(exclusive=False),
                })
                break
        except Exception:
            pass
        attempts.append({"samplerate": 16000})

        last_error: Exception | None = None
        for settings in attempts:
            stream = None
            try:
                stream = sd.RawInputStream(
                    channels=1,
                    dtype="int16",
                    blocksize=0,
                    latency="low",
                    callback=on_audio,
                    **settings,
                )
                stream.start()
                with self.lock:
                    self.stream = stream
                    self.sample_rate = int(round(float(stream.samplerate)))
                return
            except Exception as exc:
                last_error = exc
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
        if last_error:
            with self.lock:
                self.callback = None
                self.waiting_level_callback = None
                self.capture_level_callback = None
                self.monitor_pcm_callback = None
                self.continuous = False
            raise last_error
        with self.lock:
            self.callback = None
            self.waiting_level_callback = None
            self.capture_level_callback = None
            self.monitor_pcm_callback = None
            self.continuous = False
        raise RuntimeError("没有可用的麦克风输入设备。")

    def set_waiting_level_callback(
        self,
        callback: Callable[[list[float]], None] | None,
    ) -> None:
        """更新待命波形接收者，不重开麦克风。"""
        with self.lock:
            self.waiting_level_callback = callback
            if not self._capturing:
                self.callback = callback

    def begin_capture(
        self,
        level_callback: Callable[[list[float]], None] | None = None,
        pcm_callback: Callable[[bytes, int], bool | None] | None = None,
        activation_callback: Callable[[], object] | None = None,
    ) -> None:
        """在已打开的连续流上开始一段全新的正文录音。"""
        with self.lifecycle_lock:
            self._begin_capture(level_callback, pcm_callback, activation_callback)

    def _begin_capture(
        self,
        level_callback: Callable[[list[float]], None] | None = None,
        pcm_callback: Callable[[bytes, int], bool | None] | None = None,
        activation_callback: Callable[[], object] | None = None,
    ) -> None:
        with self.lock:
            if self.stream is None:
                raise RuntimeError("麦克风输入流尚未打开。")
            if self._capturing:
                raise RuntimeError("麦克风已经在录音。")
            self.chunks = []
            if activation_callback is not None:
                activation_result = activation_callback()
                if activation_result is False:
                    raise RuntimeError("录音识别会话没有成功启用。")
            self.capture_level_callback = level_callback or self.waiting_level_callback
            self.callback = self.capture_level_callback
            self.pcm_callback = pcm_callback
            self._capturing = True

    def finish_capture(self) -> tuple[bytes, int]:
        """结束并取出当前正文，但保持连续麦克风流继续待命。"""
        with self.lifecycle_lock:
            return self._finish_capture()

    def _finish_capture(self) -> tuple[bytes, int]:
        with self.lock:
            self._capturing = False
            self.pcm_callback = None
            self.capture_level_callback = None
            self.callback = self.waiting_level_callback
            chunks, self.chunks = self.chunks, []
            sample_rate = self.sample_rate
        return b"".join(chunks), sample_rate

    def close(self) -> None:
        """关闭连续输入流并丢弃尚未领取的正文缓存。"""
        with self.lifecycle_lock:
            self._close()

    def _close(self) -> None:
        with self.lock:
            stream, self.stream = self.stream, None
            self.callback = None
            self.waiting_level_callback = None
            self.capture_level_callback = None
            self.monitor_pcm_callback = None
            self.pcm_callback = None
            self._capturing = False
            self.continuous = False
            self.chunks = []
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

    def stop(self) -> tuple[bytes, int]:
        """兼容原有的一次性录音：取出正文并关闭输入流。"""
        with self.lifecycle_lock:
            pcm, sample_rate = self.finish_capture()
            self.close()
            return pcm, sample_rate
