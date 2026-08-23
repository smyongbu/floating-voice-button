from __future__ import annotations

import hashlib
import os
import queue
import re
import shutil
import sys
import threading
import time
import uuid
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from config_store import (
    DEFAULT_REALTIME_MODEL,
    MODEL_CACHE_DIR,
    ZIPFORMER_REALTIME_MODEL,
    normalize_realtime_model,
)


PROJECT_DIR = Path(__file__).resolve().parent
MODEL_REPOSITORY_ENV = "VOICE_INPUT_MODEL_REPOSITORY"


def _default_model_repository() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "models"
    return PROJECT_DIR.parents[1] / "共享模型仓库"


def _model_repository_root() -> Path:
    default = _default_model_repository()
    if getattr(sys, "frozen", False):
        return default
    return Path(os.environ.get(MODEL_REPOSITORY_ENV, str(default))).expanduser()


MODEL_REPOSITORY_ROOT = _model_repository_root()
REALTIME_MODEL_SPECS: dict[str, dict[str, Any]] = {
    DEFAULT_REALTIME_MODEL: {
        "name": "Streaming Paraformer",
        "directory": "sherpa-onnx-streaming-paraformer-bilingual-zh-en",
        "factory": "from_paraformer",
        "files": {
            "encoder.int8.onnx": (
                165_462_184,
                "81a70226a8934e6ed92aa1d4fc486b428b5398e2f2619ed4897b7294cab90e9a",
            ),
            "decoder.int8.onnx": (
                71_664_561,
                "f3cca9f77bb9d93c8fcbfb63ae617b6b1ee96818df3aa3b151c40658fe38594f",
            ),
            "tokens.txt": (
                75_756,
                "59aba8873a2ed1e122c25fee421e25f283b63290efbde85c1f01a853d83cb6e6",
            ),
        },
        "description": "中英混说更准确",
        "minimum": "4 核 64 位处理器、4 GB 内存",
        "recommended": "6 核处理器、8 GB 内存",
        "download_url": (
            "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
            "sherpa-onnx-streaming-paraformer-bilingual-zh-en.tar.bz2"
        ),
    },
    ZIPFORMER_REALTIME_MODEL: {
        "name": "Zipformer",
        "directory": "k2fsa-zipformer-bilingual-zh-en-t-exp32-int8-2024-03-20",
        "factory": "from_transducer",
        "files": {
            "encoder-epoch-99-avg-1.int8.onnx": (
                42_980_793,
                "db6f51551762e40e549166fe041ea3e45464370b595e9ad23f06478ec3794fbb",
            ),
            "decoder-epoch-99-avg-1.onnx": (
                13_877_276,
                "89be509a83175261695bdef5fd1c7b9ab1129a663d1284e7ba9f8507b21e0906",
            ),
            "joiner-epoch-99-avg-1.int8.onnx": (
                3_228_485,
                "bdda356d6f9b8c2d7cee9ee0e26075fa537490f7fd06520be408d287073667b9",
            ),
            "tokens.txt": (
                56_317,
                "a8e0e4ec53810e433789b54a5c0134a7eaa2ffca595a6334d54c00da858841d3",
            ),
        },
        "description": "响应更快，占用更低",
        "minimum": "双核 64 位处理器、4 GB 内存",
        "recommended": "4 核处理器、8 GB 内存",
        "download_url": (
            "https://huggingface.co/csukuangfj/k2fsa-zipformer-bilingual-zh-en-t/"
            "tree/8a7306b4d4d40c3cb1bdb80e8f2f605167570af3"
        ),
    },
}

# 保留旧常量名称，避免现有诊断和第三方来源测试失去固定清单入口。
MODEL_DIRECTORY_NAME = str(REALTIME_MODEL_SPECS[ZIPFORMER_REALTIME_MODEL]["directory"])
MODEL_SOURCE_DIR = MODEL_REPOSITORY_ROOT / MODEL_DIRECTORY_NAME
MODEL_LOCAL_DIR = MODEL_CACHE_DIR / ZIPFORMER_REALTIME_MODEL
MODEL_FILES = REALTIME_MODEL_SPECS[ZIPFORMER_REALTIME_MODEL]["files"]
MODEL_DOWNLOAD_URL = str(REALTIME_MODEL_SPECS[ZIPFORMER_REALTIME_MODEL]["download_url"])
_END = object()
_INTERNAL_TOKEN = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def clean_realtime_text(text: str) -> str:
    return _WHITESPACE.sub(" ", _INTERNAL_TOKEN.sub(" ", str(text or ""))).strip()


def combine_segments(existing: str, incoming: str) -> str:
    left = clean_realtime_text(existing)
    right = clean_realtime_text(incoming)
    if not left:
        return right
    if not right:
        return left
    last = left[-1]
    first = right[0]
    needs_space = last.isalnum() and first.isalnum() and (
        last.isascii() or first.isascii()
    )
    return f"{left}{' ' if needs_space else ''}{right}"


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


def _complete_by_size(
    base_dir: Path,
    files: dict[str, tuple[int, str]] | None = None,
) -> bool:
    expected_files = MODEL_FILES if files is None else files
    try:
        return all(
            (base_dir / name).is_file() and (base_dir / name).stat().st_size == size
            for name, (size, _digest) in expected_files.items()
        )
    except OSError:
        return False


def _model_paths(model_id: str) -> tuple[str, dict[str, Any], Path, Path]:
    normalized = normalize_realtime_model(model_id)
    spec = REALTIME_MODEL_SPECS[normalized]
    source_dir = MODEL_REPOSITORY_ROOT / str(spec["directory"])
    local_dir = MODEL_CACHE_DIR / normalized
    return normalized, spec, source_dir, local_dir


def install_realtime_model_locally(
    model_id: str = DEFAULT_REALTIME_MODEL,
) -> Path:
    """校验共享模型后原子复制到当前电脑，避免实时识别依赖网络读取。"""
    normalized, spec, source_dir, local_dir = _model_paths(model_id)
    files = spec["files"]
    if all(
        _valid_model_file(local_dir / name, size, digest)
        for name, (size, digest) in files.items()
    ):
        return local_dir

    for name, (size, digest) in files.items():
        source = source_dir / name
        if not _valid_model_file(source, size, digest):
            raise FileNotFoundError(
                f"实时模型 {normalized} 文件缺失或校验失败：{name}"
            )

    local_dir.mkdir(parents=True, exist_ok=True)
    for name, (size, digest) in files.items():
        source = source_dir / name
        target = local_dir / name
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
    return local_dir


def get_realtime_model_status(
    model_id: str = DEFAULT_REALTIME_MODEL,
) -> dict[str, object]:
    normalized, spec, source_dir, local_dir = _model_paths(model_id)
    files = spec["files"]
    source_ready = _complete_by_size(source_dir, files)
    local_ready = _complete_by_size(local_dir, files)
    try:
        import sherpa_onnx

        runtime_ready = hasattr(sherpa_onnx.OnlineRecognizer, str(spec["factory"]))
    except (ImportError, AttributeError):
        runtime_ready = False
    available = bool((source_ready or local_ready) and runtime_ready)
    return {
        "model_id": normalized,
        "name": str(spec["name"]),
        "description": str(spec["description"]),
        "available": available,
        "installed": source_ready or local_ready,
        "runtime_ready": runtime_ready,
        "size_bytes": sum(item[0] for item in files.values()),
        "status": "已就绪" if available else "不可用",
        "status_message": (
            f"{spec['name']} 已就绪，可显示中文、英文和中英混说文字。"
            if available
            else f"{spec['name']} 文件或 sherpa-onnx 运行组件不完整。"
        ),
        "minimum": str(spec["minimum"]),
        "recommended": str(spec["recommended"]),
        "gpu": "使用处理器运行，不需要显卡",
        "download_url": str(spec["download_url"]),
    }


def get_realtime_model_catalog() -> list[dict[str, object]]:
    return [
        get_realtime_model_status(DEFAULT_REALTIME_MODEL),
        get_realtime_model_status(ZIPFORMER_REALTIME_MODEL),
    ]


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
        return combine_segments(self.stable_text, self.partial_text)


@dataclass(frozen=True)
class FinalRecognition:
    text: str
    source: str


def _meaningful_length(text: str) -> int:
    return sum(character.isalnum() for character in text)


def _textual_similarity(left: str, right: str) -> float:
    first = "".join(character.lower() for character in left if character.isalnum())
    second = "".join(character.lower() for character in right if character.isalnum())
    if first == second:
        return 1.0
    if len(first) < 2 or len(second) < 2:
        return 0.0
    first_pairs = {first[index:index + 2] for index in range(len(first) - 1)}
    second_pairs = {second[index:index + 2] for index in range(len(second) - 1)}
    return 2.0 * len(first_pairs & second_pairs) / (
        len(first_pairs) + len(second_pairs)
    )


def _is_english_heavy(text: str) -> bool:
    latin = sum(character.isascii() and character.isalpha() for character in text)
    han = sum("\u4e00" <= character <= "\u9fff" for character in text)
    return latin >= 6 and latin > han * 2


def _fragmented_english_score(text: str) -> int:
    return sum(
        len(word) == 1 and "b" <= word <= "z"
        for word in text.lower().split()
    )


def choose_final_recognition(realtime: str, final_result: str) -> FinalRecognition:
    """只比较两份模型输出；选中整段结果时保持其原始格式。"""
    live = clean_realtime_text(realtime)
    final_original = "" if final_result is None else str(final_result)
    final = clean_realtime_text(final_original)
    if not live and not final:
        return FinalRecognition("", "none")
    if not final:
        return FinalRecognition(live, "realtime")
    if not live:
        return FinalRecognition(final_original, "final")

    live_length = _meaningful_length(live)
    final_length = _meaningful_length(final)
    if final_length * 10 < live_length * 7 or final_length > live_length * 2 + 8:
        return FinalRecognition(live, "realtime")
    if _textual_similarity(live, final) < 0.42:
        return FinalRecognition(live, "realtime")
    if _is_english_heavy(live):
        live_fragments = _fragmented_english_score(live)
        final_fragments = _fragmented_english_score(final)
        if final_fragments > live_fragments + 1 or final_length * 20 < live_length * 17:
            return FinalRecognition(live, "realtime")
    return FinalRecognition(final_original, "final")


def _result_text(value: Any) -> str:
    if isinstance(value, str):
        return clean_realtime_text(value)
    return clean_realtime_text(getattr(value, "text", "") or "")


class RealtimeRecognizer:
    """共享流式模型；每次录音创建独立解码流。"""

    def __init__(
        self,
        num_threads: int = 2,
        *,
        model_id: str = DEFAULT_REALTIME_MODEL,
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
        self.model_id = normalize_realtime_model(model_id)
        self.device_label = "CPU"
        self._recognizer: Any = None
        self._lock = threading.RLock()

    @property
    def model_name(self) -> str:
        return str(REALTIME_MODEL_SPECS[self.model_id]["name"])

    def select_model(self, model_id: str) -> bool:
        """切换后续会话使用的模型；已经创建的会话继续安全使用旧实例。"""
        normalized = normalize_realtime_model(model_id)
        with self._lock:
            if normalized == self.model_id:
                return False
            self.model_id = normalized
            self._recognizer = None
            return True

    def load(self) -> None:
        with self._lock:
            if self._recognizer is not None:
                return
            model_id = self.model_id
            spec = REALTIME_MODEL_SPECS[model_id]
            model_dir = install_realtime_model_locally(model_id)
            import sherpa_onnx

            shared_options = {
                "tokens": str(model_dir / "tokens.txt"),
                "num_threads": self.num_threads,
                "sample_rate": 16000,
                "feature_dim": 80,
                "enable_endpoint_detection": True,
                "rule1_min_trailing_silence": self.rule1_min_trailing_silence,
                "rule2_min_trailing_silence": self.rule2_min_trailing_silence,
                "rule3_min_utterance_length": self.rule3_min_utterance_length,
                "provider": "cpu",
            }
            if spec["factory"] == "from_paraformer":
                self._recognizer = sherpa_onnx.OnlineRecognizer.from_paraformer(
                    encoder=str(model_dir / "encoder.int8.onnx"),
                    decoder=str(model_dir / "decoder.int8.onnx"),
                    decoding_method="greedy_search",
                    **shared_options,
                )
            else:
                self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                    encoder=str(model_dir / "encoder-epoch-99-avg-1.int8.onnx"),
                    decoder=str(model_dir / "decoder-epoch-99-avg-1.onnx"),
                    joiner=str(model_dir / "joiner-epoch-99-avg-1.int8.onnx"),
                    decoding_method="modified_beam_search",
                    max_active_paths=4,
                    model_type="zipformer",
                    **shared_options,
                )

    def create_session(
        self,
        operation_id: str,
        on_update: Callable[[RealtimeUpdate], None],
        *,
        queue_size: int = 96,
        max_stable_segments: int | None = None,
    ) -> "RealtimeSession":
        with self._lock:
            self.load()
            recognizer = self._recognizer
        session = RealtimeSession(
            operation_id=operation_id,
            recognizer=recognizer,
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
            raise TimeoutError("实时识别结束超时，已继续使用整段识别。")
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
