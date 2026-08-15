from __future__ import annotations

import hashlib
import os
import queue
import shutil
import threading
import time
import uuid
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from config_store import APP_DATA_DIR, REALTIME_MODEL_ID


PROJECT_DIR = Path(__file__).resolve().parent
MODEL_DIRECTORY_NAME = "sherpa-onnx-streaming-zipformer-small-ctc-zh-int8-2025-04-01"
MODEL_SOURCE_DIR = PROJECT_DIR / "models" / MODEL_DIRECTORY_NAME
MODEL_LOCAL_DIR = APP_DATA_DIR / "models" / REALTIME_MODEL_ID
MODEL_FILES = {
    "model.int8.onnx": (
        26_342_340,
        "68c9c943840f7d9cf3e8a4970ba50f404feb5277f611fa82b7e72267786fa84a",
    ),
    "tokens.txt": (
        13_366,
        "6fed8c6c248516f38e7faa19404b57413e8ce259f1cbc1fa4aebc86eac32fdfd",
    ),
    "bbpe.model": (
        255_180,
        "503204e0690eff065e30d0e01898c9ab06d0e6dc376a741eb6846198f95b2f82",
    ),
}
MODEL_DOWNLOAD_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-streaming-zipformer-small-ctc-zh-int8-2025-04-01.tar.bz2"
)
MODEL_ARCHIVE_SHA256 = "b3b309f7ce4a737195fcc6963ea19b0653a7d3401580af5ae0d3e284cbb71f0b"
_END = object()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _valid_model_file(path: Path, size: int, digest: str) -> bool:
    try:
        return path.is_file() and path.stat().st_size == size and _sha256(path) == digest
    except OSError:
        return False


def _complete_by_size(base_dir: Path) -> bool:
    try:
        return all(
            (base_dir / name).is_file() and (base_dir / name).stat().st_size == size
            for name, (size, _digest) in MODEL_FILES.items()
        )
    except OSError:
        return False


def install_realtime_model_locally() -> Path:
    """校验共享模型后原子复制到当前电脑，避免实时识别依赖网络读取。"""
    if all(
        _valid_model_file(MODEL_LOCAL_DIR / name, size, digest)
        for name, (size, digest) in MODEL_FILES.items()
    ):
        return MODEL_LOCAL_DIR

    for name, (size, digest) in MODEL_FILES.items():
        source = MODEL_SOURCE_DIR / name
        if not _valid_model_file(source, size, digest):
            raise FileNotFoundError(f"实时中文模型文件缺失或校验失败：{name}")

    MODEL_LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    for name, (size, digest) in MODEL_FILES.items():
        source = MODEL_SOURCE_DIR / name
        target = MODEL_LOCAL_DIR / name
        if _valid_model_file(target, size, digest):
            continue
        temporary = target.parent / (
            f".{target.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
        )
        try:
            shutil.copyfile(source, temporary)
            if not _valid_model_file(temporary, size, digest):
                raise OSError(f"实时模型复制校验失败：{name}")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return MODEL_LOCAL_DIR


def get_realtime_model_status() -> dict[str, object]:
    source_ready = _complete_by_size(MODEL_SOURCE_DIR)
    local_ready = _complete_by_size(MODEL_LOCAL_DIR)
    try:
        import sherpa_onnx

        runtime_ready = hasattr(sherpa_onnx.OnlineRecognizer, "from_zipformer2_ctc")
    except (ImportError, AttributeError):
        runtime_ready = False
    available = bool((source_ready or local_ready) and runtime_ready)
    return {
        "model_id": REALTIME_MODEL_ID,
        "name": "Zipformer 中文实时轻量版 INT8",
        "available": available,
        "installed": source_ready or local_ready,
        "runtime_ready": runtime_ready,
        "size_bytes": sum(item[0] for item in MODEL_FILES.values()),
        "status": "已就绪" if available else "不可用",
        "status_message": (
            "实时模型已就绪，可在讲话过程中显示文字。"
            if available
            else "实时模型文件或 sherpa-onnx 运行组件不完整。"
        ),
        "minimum": "双核 64 位处理器、4 GB 内存",
        "recommended": "4 核处理器、8 GB 内存",
        "gpu": "使用处理器运行，不需要显卡",
        "download_url": MODEL_DOWNLOAD_URL,
        "archive_sha256": MODEL_ARCHIVE_SHA256,
    }


@dataclass(frozen=True)
class RealtimeUpdate:
    operation_id: str
    revision: int
    stable_text: str
    partial_text: str
    audio_ms: int
    is_final: bool = False
    endpoint_text: str = ""
    segment_start_ms: int = 0
    segment_end_ms: int = 0
    endpoint_reached: bool = False

    @property
    def text(self) -> str:
        return f"{self.stable_text}{self.partial_text}".strip()


def _result_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return str(getattr(value, "text", "") or "").strip()


class RealtimeRecognizer:
    """共享流式模型；每次录音创建独立解码流。"""

    def __init__(
        self,
        num_threads: int = 1,
        *,
        rule1_min_trailing_silence: float = 2.4,
        rule2_min_trailing_silence: float = 1.2,
        rule3_min_utterance_length: float = 20.0,
    ) -> None:
        self.num_threads = max(1, int(num_threads))
        self.rule1_min_trailing_silence = max(
            0.1, float(rule1_min_trailing_silence)
        )
        self.rule2_min_trailing_silence = max(
            0.1, float(rule2_min_trailing_silence)
        )
        self.rule3_min_utterance_length = max(
            1.0, float(rule3_min_utterance_length)
        )
        self.device_label = "CPU"
        self._recognizer: Any = None
        self._lock = threading.RLock()

    def load(self) -> None:
        with self._lock:
            if self._recognizer is not None:
                return
            model_dir = install_realtime_model_locally()
            import sherpa_onnx

            self._recognizer = sherpa_onnx.OnlineRecognizer.from_zipformer2_ctc(
                tokens=str(model_dir / "tokens.txt"),
                model=str(model_dir / "model.int8.onnx"),
                num_threads=self.num_threads,
                sample_rate=16000,
                feature_dim=80,
                enable_endpoint_detection=True,
                rule1_min_trailing_silence=self.rule1_min_trailing_silence,
                rule2_min_trailing_silence=self.rule2_min_trailing_silence,
                rule3_min_utterance_length=self.rule3_min_utterance_length,
                decoding_method="greedy_search",
                provider="cpu",
            )

    def create_session(
        self,
        operation_id: str,
        on_update: Callable[[RealtimeUpdate], None],
        *,
        queue_size: int = 96,
        max_stable_segments: int | None = None,
    ) -> "RealtimeSession":
        self.load()
        session = RealtimeSession(
            operation_id=operation_id,
            recognizer=self._recognizer,
            on_update=on_update,
            queue_size=queue_size,
            max_stable_segments=max_stable_segments,
        )
        session.start()
        return session


class RealtimeSession:
    """音频回调只入队；单独工作线程负责流式解码与局部文字回调。"""

    def __init__(
        self,
        operation_id: str,
        recognizer: Any,
        on_update: Callable[[RealtimeUpdate], None],
        queue_size: int = 96,
        max_stable_segments: int | None = None,
    ) -> None:
        self.operation_id = str(operation_id)
        self._recognizer = recognizer
        self._on_update = on_update
        self._queue: queue.Queue[object] = queue.Queue(maxsize=max(8, int(queue_size)))
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._cancelled = threading.Event()
        self._done = threading.Event()
        self._accepting = False
        self._overloaded = False
        self._error: Exception | None = None
        self._revision = 0
        self._audio_samples = 0
        self._stable_segments: list[str] = []
        self._max_stable_segments = (
            None if max_stable_segments is None else max(0, int(max_stable_segments))
        )
        self._segment_start_sample = 0
        self._last_partial = ""
        self._final_text = ""
        self._final_update: RealtimeUpdate | None = None

    @property
    def overloaded(self) -> bool:
        return self._overloaded

    def wait_closed(self, timeout: float = 0.75) -> bool:
        """等待解码线程完全退出，供会话切换时避免共享模型并发。"""
        return self._done.wait(max(0.0, float(timeout)))

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._accepting = True
            self._thread = threading.Thread(
                target=self._run,
                name=f"实时识别-{self.operation_id}",
                daemon=True,
            )
            self._thread.start()

    def feed_pcm16(self, pcm: bytes, sample_rate: int = 16000) -> bool:
        if not pcm:
            return True
        if len(pcm) % 2 or int(sample_rate) != 16000:
            return False
        with self._lock:
            if not self._accepting or self._cancelled.is_set():
                return False
        try:
            self._queue.put_nowait((bytes(pcm), int(sample_rate)))
            return True
        except queue.Full:
            with self._lock:
                self._overloaded = True
                self._accepting = False
            self._cancelled.set()
            return False

    def _emit(
        self,
        partial: str,
        *,
        final: bool = False,
        endpoint_text: str = "",
        endpoint_reached: bool = False,
        segment_start_sample: int | None = None,
        segment_end_sample: int | None = None,
    ) -> None:
        normalized = str(partial or "").strip()
        normalized_endpoint = str(endpoint_text or "").strip()
        if (
            not final
            and not endpoint_reached
            and normalized == self._last_partial
        ):
            return
        self._last_partial = normalized
        self._revision += 1
        start_sample = (
            self._segment_start_sample
            if segment_start_sample is None
            else max(0, int(segment_start_sample))
        )
        end_sample = (
            self._audio_samples
            if segment_end_sample is None
            else max(start_sample, int(segment_end_sample))
        )
        update = RealtimeUpdate(
            operation_id=self.operation_id,
            revision=self._revision,
            stable_text="".join(self._stable_segments),
            partial_text=normalized,
            audio_ms=round(self._audio_samples / 16000 * 1000),
            is_final=final,
            endpoint_text=normalized_endpoint,
            segment_start_ms=round(start_sample / 16000 * 1000),
            segment_end_ms=round(end_sample / 16000 * 1000),
            endpoint_reached=bool(endpoint_reached),
        )
        if final:
            self._final_text = update.text
            self._final_update = update
        try:
            self._on_update(update)
        except Exception:
            pass

    def _append_stable_segment(self, text: str) -> None:
        normalized = str(text or "").strip()
        if not normalized or self._max_stable_segments == 0:
            return
        self._stable_segments.append(normalized)
        if (
            self._max_stable_segments is not None
            and len(self._stable_segments) > self._max_stable_segments
        ):
            del self._stable_segments[:-self._max_stable_segments]

    @staticmethod
    def _samples(pcm: bytes) -> list[float]:
        values = array("h")
        values.frombytes(pcm)
        if os.sys.byteorder != "little":
            values.byteswap()
        return [value / 32768.0 for value in values]

    def _decode_available(self, stream: Any) -> str:
        while self._recognizer.is_ready(stream):
            self._recognizer.decode_stream(stream)
        return _result_text(self._recognizer.get_result(stream))

    def _run(self) -> None:
        try:
            stream = self._recognizer.create_stream()
            while not self._cancelled.is_set():
                try:
                    item = self._queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                if item is _END:
                    break
                pcm, sample_rate = item
                samples = self._samples(pcm)
                self._audio_samples += len(samples)
                stream.accept_waveform(sample_rate, samples)
                partial = self._decode_available(stream)
                self._emit(partial)
                if self._recognizer.is_endpoint(stream):
                    segment_start_sample = self._segment_start_sample
                    segment_end_sample = self._audio_samples
                    self._append_stable_segment(partial)
                    self._recognizer.reset(stream)
                    self._emit(
                        "",
                        endpoint_text=partial,
                        endpoint_reached=True,
                        segment_start_sample=segment_start_sample,
                        segment_end_sample=segment_end_sample,
                    )
                    self._segment_start_sample = segment_end_sample

            if not self._cancelled.is_set():
                stream.accept_waveform(16000, [0.0] * 4800)
                stream.input_finished()
                partial = self._decode_available(stream)
                segment_start_sample = self._segment_start_sample
                segment_end_sample = self._audio_samples
                self._append_stable_segment(partial)
                self._emit(
                    "",
                    final=True,
                    endpoint_text=partial,
                    endpoint_reached=True,
                    segment_start_sample=segment_start_sample,
                    segment_end_sample=segment_end_sample,
                )
        except Exception as exc:
            self._error = exc
        finally:
            with self._lock:
                self._accepting = False
            self._done.set()

    def finish(self, timeout: float = 5.0) -> RealtimeUpdate:
        with self._lock:
            self._accepting = False
        if not self._cancelled.is_set():
            try:
                self._queue.put(_END, timeout=0.5)
            except queue.Full:
                self._cancelled.set()
        if not self._done.wait(max(0.1, float(timeout))):
            self.cancel()
            raise TimeoutError("实时文字整理超时，已继续使用整段识别。")
        if self._error is not None:
            raise RuntimeError("实时识别暂时不可用，已继续使用整段识别。") from None
        if self._overloaded:
            raise RuntimeError("实时预览速度跟不上录音，已继续使用整段识别。")
        if self._final_update is not None:
            return self._final_update
        return RealtimeUpdate(
            operation_id=self.operation_id,
            revision=self._revision,
            stable_text=self._final_text,
            partial_text="",
            audio_ms=round(self._audio_samples / 16000 * 1000),
            is_final=True,
            segment_start_ms=round(self._segment_start_sample / 16000 * 1000),
            segment_end_ms=round(self._audio_samples / 16000 * 1000),
            endpoint_reached=True,
        )

    def cancel(self) -> None:
        with self._lock:
            self._accepting = False
        self._cancelled.set()
        try:
            self._queue.put_nowait(_END)
        except queue.Full:
            pass
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.5)
