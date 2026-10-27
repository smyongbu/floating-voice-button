from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable, Mapping, Protocol

from config_store import (
    DEFAULT_LOCAL_MODEL,
    normalize_recognition_engine,
)


class _Recognizer(Protocol):
    device_label: str

    def load(self) -> None: ...

    def transcribe_pcm16(self, pcm: bytes, sample_rate: int = 16000) -> str: ...


@dataclass(frozen=True)
class RecognitionResult:
    text: str
    requested_engine: str
    actual_engine: str
    device_label: str = ""


class RecognitionError(RuntimeError):
    """只携带可安全显示和记录的本地识别错误。"""

    def __init__(self, message: str, category: str, engine_id: str) -> None:
        super().__init__(message)
        self.public_message = message
        self.category = category
        self.engine_id = engine_id


LocalFactory = Callable[[str, str], _Recognizer]


def _default_local_factory(model_id: str, preference: str) -> _Recognizer:
    try:
        from local_asr import LocalModelRecognizer
    except ImportError:
        # 兼容尚未升级模型适配层的旧版本，仅保留原 SenseVoice 路径。
        if model_id != DEFAULT_LOCAL_MODEL:
            raise RecognitionError(
                "所选本地模型组件尚未安装。", "local", f"local:{model_id}"
            ) from None
        from local_asr import SenseVoiceRecognizer

        return SenseVoiceRecognizer(preference)
    return LocalModelRecognizer(model_id, preference)


class RecognitionRouter:
    """调度本地语音识别，管理模型复用与释放。"""

    def __init__(
        self,
        config: Mapping[str, object],
        *,
        local_factory: LocalFactory | None = None,
    ) -> None:
        self.engine_id = normalize_recognition_engine(config.get("recognition_engine"))
        preference = str(config.get("local_asr_device", "auto")).strip().lower()
        self.local_preference = preference if preference in ("auto", "cpu", "gpu") else "auto"
        self._local_factory = local_factory or _default_local_factory
        self._local_recognizers: dict[tuple[str, str], _Recognizer] = {}
        self._lock = threading.RLock()
        self._closed = False

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def _local_recognizer(self, model_id: str) -> _Recognizer:
        key = (model_id, self.local_preference)
        with self._lock:
            if self._closed:
                raise RecognitionError(
                    "本地识别配置已经切换，请重新录音。",
                    "local",
                    f"local:{model_id}",
                )
            recognizer = self._local_recognizers.get(key)
            if recognizer is None:
                try:
                    recognizer = self._local_factory(model_id, self.local_preference)
                except RecognitionError:
                    raise
                except Exception:
                    raise RecognitionError(
                        "本地识别模型初始化失败，请检查模型是否完整。",
                        "local",
                        f"local:{model_id}",
                    ) from None
                self._local_recognizers[key] = recognizer
            return recognizer

    def preload(self) -> tuple[str, str]:
        """预加载当前本地模型。"""
        model_id = self.engine_id.partition(":")[2]
        engine_id = f"local:{model_id}"
        recognizer = self._local_recognizer(model_id)
        try:
            recognizer.load()
        except RecognitionError:
            raise
        except Exception:
            raise RecognitionError(
                "本地识别模型加载失败，请检查模型文件和运行组件。",
                "local",
                engine_id,
            ) from None
        return engine_id, str(getattr(recognizer, "device_label", "本地"))

    def close(self) -> None:
        """释放已加载的本地模型。"""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            recognizers = list(self._local_recognizers.values())
            self._local_recognizers.clear()
        for recognizer in recognizers:
            closer = getattr(recognizer, "close", None)
            if not callable(closer):
                continue
            try:
                closer()
            except Exception:
                # 退出或切换配置时，释放异常不能中断主流程。
                pass

    def _run_local(
        self,
        model_id: str,
        pcm: bytes,
        sample_rate: int,
        *,
        requested_engine: str,
    ) -> RecognitionResult:
        engine_id = f"local:{model_id}"
        recognizer = self._local_recognizer(model_id)
        try:
            text = recognizer.transcribe_pcm16(pcm, sample_rate)
        except RecognitionError:
            raise
        except Exception:
            raise RecognitionError(
                "本地语音识别失败，请检查模型和识别设备。",
                "local",
                engine_id,
            ) from None
        return RecognitionResult(
            text=str(text or "").strip(),
            requested_engine=requested_engine,
            actual_engine=engine_id,
            device_label=str(getattr(recognizer, "device_label", "本地")),
        )

    def transcribe_pcm16(
        self, pcm: bytes, sample_rate: int = 16000
    ) -> RecognitionResult:
        return self._run_local(
            self.engine_id.partition(":")[2],
            pcm,
            sample_rate,
            requested_engine=self.engine_id,
        )
