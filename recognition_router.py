from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable, Mapping, Protocol

from config_store import (
    DEFAULT_LOCAL_MODEL,
    normalize_fallback_model,
    normalize_recognition_engine,
)


ONLINE_MAX_SECONDS = 55.0


class _Recognizer(Protocol):
    device_label: str

    def load(self) -> None: ...

    def transcribe_pcm16(self, pcm: bytes, sample_rate: int = 16000) -> str: ...


@dataclass(frozen=True)
class RecognitionResult:
    text: str
    requested_engine: str
    actual_engine: str
    fallback_used: bool = False
    device_label: str = ""


class RecognitionError(RuntimeError):
    """只携带可安全显示和记录的信息，不包装服务端响应或密钥。"""

    def __init__(self, message: str, category: str, engine_id: str) -> None:
        super().__init__(message)
        self.public_message = message
        self.category = category
        self.engine_id = engine_id


LocalFactory = Callable[[str, str], _Recognizer]
CloudFactory = Callable[[str, Mapping[str, str]], _Recognizer]


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


def _default_cloud_factory(
    provider_id: str, credentials: Mapping[str, str]
) -> _Recognizer:
    from cloud_asr import CloudAsrRecognizer

    return CloudAsrRecognizer(provider_id, credentials=credentials)


def _exception_category(exc: Exception) -> str:
    for attribute in ("category", "error_category", "kind"):
        value = getattr(exc, attribute, None)
        if hasattr(value, "value"):
            value = value.value
        normalized = str(value or "").strip().lower()
        if normalized:
            return normalized
    return "service"


def _safe_cloud_message(category: str) -> str:
    return {
        "transient": "在线识别暂时不可用，已尝试使用本地模型。",
        "authentication": "在线识别凭据无效，请在设置中重新填写。",
        "auth": "在线识别凭据无效，请在设置中重新填写。",
        "quota": "在线识别额度不足，请检查服务账户。",
        "parameter": "在线识别参数无效，请检查服务设置。",
        "invalid_parameter": "在线识别参数无效，请检查服务设置。",
    }.get(category, "在线识别服务调用失败，请稍后重试。")


class RecognitionRouter:
    """统一调度本地和在线语音识别，并严格控制在线回退条件。"""

    def __init__(
        self,
        config: Mapping[str, object],
        *,
        credential_store: object | None = None,
        local_factory: LocalFactory | None = None,
        cloud_factory: CloudFactory | None = None,
    ) -> None:
        self.engine_id = normalize_recognition_engine(config.get("recognition_engine"))
        self.fallback_model = normalize_fallback_model(config.get("fallback_model"))
        preference = str(config.get("local_asr_device", "auto")).strip().lower()
        self.local_preference = preference if preference in ("auto", "cpu", "gpu") else "auto"
        self._credential_store = credential_store
        self._local_factory = local_factory or _default_local_factory
        self._cloud_factory = cloud_factory or _default_cloud_factory
        self._local_recognizers: dict[tuple[str, str], _Recognizer] = {}
        self._lock = threading.RLock()
        self._closed = False

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    @property
    def is_cloud(self) -> bool:
        return self.engine_id.startswith("cloud:")

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

    def _credentials(self, provider_id: str) -> Mapping[str, str]:
        store = self._credential_store
        if store is None:
            from credential_store import CredentialStore

            store = CredentialStore()
            self._credential_store = store
        reader = getattr(store, "read", None) or getattr(store, "load", None)
        if not callable(reader):
            raise RecognitionError(
                "无法读取在线识别凭据，请重新保存服务设置。",
                "authentication",
                f"cloud:{provider_id}",
            )
        try:
            credentials = reader(provider_id)
        except Exception:
            raise RecognitionError(
                "无法读取在线识别凭据，请重新保存服务设置。",
                "authentication",
                f"cloud:{provider_id}",
            ) from None
        if not isinstance(credentials, Mapping) or not credentials:
            raise RecognitionError(
                "尚未保存在线识别凭据，请先在设置中填写。",
                "authentication",
                f"cloud:{provider_id}",
            )
        return {
            str(key): str(value)
            for key, value in credentials.items()
            if str(key).strip() and value is not None
        }

    def preload(self) -> tuple[str, str]:
        """只预加载本地组件；在线服务不会在启动时触网。"""
        model_id = self.fallback_model if self.is_cloud else self.engine_id.partition(":")[2]
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
        """释放已加载的本地模型；不持有或关闭在线服务对象。"""
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
        fallback_used: bool,
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
            fallback_used=fallback_used,
            device_label=str(getattr(recognizer, "device_label", "本地")),
        )

    def transcribe_pcm16(
        self, pcm: bytes, sample_rate: int = 16000
    ) -> RecognitionResult:
        requested_engine = self.engine_id
        if not self.is_cloud:
            return self._run_local(
                requested_engine.partition(":")[2],
                pcm,
                sample_rate,
                requested_engine=requested_engine,
                fallback_used=False,
            )

        provider_id = requested_engine.partition(":")[2]
        if sample_rate <= 0:
            raise RecognitionError(
                "录音采样率无效，请重新录制。", "parameter", requested_engine
            )
        duration = len(pcm) / 2 / sample_rate
        if duration > ONLINE_MAX_SECONDS:
            raise RecognitionError(
                "在线识别最长支持 55 秒，请缩短录音后重试。",
                "parameter",
                requested_engine,
            )

        try:
            credentials = self._credentials(provider_id)
            recognizer = self._cloud_factory(provider_id, credentials)
            text = recognizer.transcribe_pcm16(pcm, sample_rate)
        except RecognitionError as exc:
            if exc.category == "transient":
                return self._run_local(
                    self.fallback_model,
                    pcm,
                    sample_rate,
                    requested_engine=requested_engine,
                    fallback_used=True,
                )
            raise
        except Exception as exc:
            category = _exception_category(exc)
            if category == "transient":
                return self._run_local(
                    self.fallback_model,
                    pcm,
                    sample_rate,
                    requested_engine=requested_engine,
                    fallback_used=True,
                )
            raise RecognitionError(
                _safe_cloud_message(category), category, requested_engine
            ) from None

        return RecognitionResult(
            text=str(text or "").strip(),
            requested_engine=requested_engine,
            actual_engine=requested_engine,
            fallback_used=False,
            device_label="在线",
        )
