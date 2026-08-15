from __future__ import annotations

import importlib.util
import json
import os
import shutil
import threading
import uuid
from array import array
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any

from config_store import APP_DATA_DIR


PROJECT_DIR = Path(__file__).resolve().parent
MODEL_SOURCE_ROOT = PROJECT_DIR / "models"
LOCAL_MODELS_DIR = APP_DATA_DIR / "models"

SENSEVOICE_MODEL_ID = "sensevoice-small-int8"
PARAFORMER_MODEL_ID = "paraformer-zh-small-int8"
QWEN3_MODEL_ID = "qwen3-asr-0.6b-int8"
FASTER_WHISPER_MODEL_ID = "faster-whisper-small"

# 该目录只保存 JSON 可序列化的静态元数据。动态安装状态由
# get_local_model_catalog() / get_local_model_status() 计算。
LOCAL_MODELS: dict[str, dict[str, Any]] = {
    SENSEVOICE_MODEL_ID: {
        "id": SENSEVOICE_MODEL_ID,
        "name": "SenseVoiceSmall INT8",
        "engine": "sense_voice",
        "source_directory": "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17",
        "required_files": ["model.int8.onnx", "tokens.txt"],
        "size_bytes": 239_549_735,
        "capabilities": ["普通话", "粤语", "英语", "日语", "韩语", "情感与声音事件"],
        "hardware": {
            "minimum": "双核 64 位 CPU、4 GB 内存",
            "recommended": "4 核 CPU、8 GB 内存",
            "gpu": "不需要显卡；兼容的 NVIDIA CUDA 运行组件可选",
            "note": "适合短句中文听写；实际速度受 CPU 代际、录音长度和后台负载影响。",
        },
        "license": "SenseVoice 模型许可（随模型 LICENSE 文件提供）",
        "download": {
            "page": "https://k2-fsa.github.io/sherpa/onnx/pretrained_models/sense-voice-models.html",
            "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2",
        },
        "sha256": {},
    },
    PARAFORMER_MODEL_ID: {
        "id": PARAFORMER_MODEL_ID,
        "name": "Paraformer 中文轻量版 INT8",
        "engine": "paraformer",
        "source_directory": "sherpa-onnx-paraformer-zh-small-2024-03-09",
        "required_files": ["model.int8.onnx", "tokens.txt"],
        "size_bytes": 81_875_000,
        "capabilities": ["普通话", "中英混说", "河南话", "天津话", "四川话"],
        "hardware": {
            "minimum": "双核 64 位 CPU、4 GB 内存",
            "recommended": "4 核 CPU、8 GB 内存",
            "gpu": "不需要显卡；兼容的 NVIDIA CUDA 运行组件可选",
            "note": "模型约 82 MB；官方双线程示例的实时率约为 0.076，实际速度因电脑而异。",
        },
        "license": "Apache-2.0（上游 Paraformer / sherpa-onnx）",
        "download": {
            "page": "https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-paraformer/paraformer-models.html",
            "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-paraformer-zh-small-2024-03-09.tar.bz2",
        },
        "sha256": {
            "model.int8.onnx": "3ef6c19369b912f7caf3cef8e545c5ccd1a33d9d7ec792a46668dc41c4b229ec",
        },
    },
    QWEN3_MODEL_ID: {
        "id": QWEN3_MODEL_ID,
        "name": "Qwen3-ASR 0.6B INT8",
        "engine": "qwen3_asr",
        "source_directory": "sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25",
        "required_files": [
            "conv_frontend.onnx",
            "encoder.int8.onnx",
            "decoder.int8.onnx",
            "tokenizer/merges.txt",
            "tokenizer/vocab.json",
            "tokenizer/tokenizer_config.json",
        ],
        "size_bytes": 982_000_000,
        "capabilities": [
            "普通话",
            "粤语",
            "吴语",
            "闽南语",
            "多种中文方言",
            "30 多种语言",
            "歌词与说唱",
        ],
        "hardware": {
            "minimum": "4 核 64 位 CPU、8 GB 内存",
            "recommended": "6 核以上 CPU、16 GB 内存",
            "gpu": "不需要显卡；NVIDIA CUDA 可选，使用前需安装对应运行组件",
            "note": "约 1 GB。最低与推荐配置为工程估算，不是官方硬性门槛；实际速度因 CPU 代际而异。",
        },
        "license": "Apache-2.0",
        "download": {
            "page": "https://k2-fsa.github.io/sherpa/onnx/qwen3-asr/pretrained.html",
            "url": "https://huggingface.co/csukuangfj2/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25/tree/main",
        },
        "sha256": {
            "conv_frontend.onnx": "d22dc4423e0940e49884e903d2ea2f7e5567c14fc1aed97e4e26d6b8f208ef9e",
            "encoder.int8.onnx": "60748d3e6744a57c9c91e1b17424a6c2990567e8adceb0783940c03ed98fa9d9",
            "decoder.int8.onnx": "4f6885be5959ae26af3089d38ee7972c5fafbeeb1cf8d5e76eab6d8b61ca5771",
        },
    },
    FASTER_WHISPER_MODEL_ID: {
        "id": FASTER_WHISPER_MODEL_ID,
        "name": "Faster-Whisper Small",
        "engine": "faster_whisper",
        "source_directory": "faster-whisper-small",
        "required_files": ["model.bin", "config.json", "tokenizer.json", "vocabulary.txt"],
        "size_bytes": 486_000_000,
        "capabilities": ["普通话", "多语言识别", "语言自动检测", "时间戳"],
        "hardware": {
            "minimum": "4 核 64 位 CPU、4 GB 内存",
            "recommended": "6 至 8 核 CPU、8 GB 内存",
            "gpu": "CPU 可用；GPU 需要 NVIDIA CUDA 12 和 cuDNN 9",
            "note": "官方 i7-12700K 八线程 CPU INT8 基准约占 1.48 GB 内存；最低配置为工程估算。",
        },
        "license": "MIT",
        "download": {
            "page": "https://github.com/SYSTRAN/faster-whisper",
            "url": "https://huggingface.co/Systran/faster-whisper-small/tree/2ec96c5472da50d38d40c0cfe0602af2e94b4c8a",
        },
        "sha256": {
            "model.bin": "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671",
        },
    },
}

# 旧设置面板和旧调用仍使用以下名称；保持其含义和可补丁性。
MODEL_NAME = SENSEVOICE_MODEL_ID
MODEL_SOURCE_DIR = MODEL_SOURCE_ROOT / LOCAL_MODELS[MODEL_NAME]["source_directory"]
MODEL_LOCAL_DIR = LOCAL_MODELS_DIR / MODEL_NAME
MODEL_FILE = "model.int8.onnx"
TOKENS_FILE = "tokens.txt"


def _model_metadata(model_id: str) -> dict[str, Any]:
    normalized = str(model_id or "").strip().lower()
    try:
        return LOCAL_MODELS[normalized]
    except KeyError as exc:
        choices = "、".join(LOCAL_MODELS)
        raise ValueError(f"未知的本地识别模型：{model_id}。可选模型：{choices}") from exc


def _model_directories(model_id: str) -> tuple[Path, Path]:
    metadata = _model_metadata(model_id)
    if metadata["id"] == MODEL_NAME:
        return Path(MODEL_SOURCE_DIR), Path(MODEL_LOCAL_DIR)
    return (
        Path(MODEL_SOURCE_ROOT) / str(metadata["source_directory"]),
        Path(LOCAL_MODELS_DIR) / str(metadata["id"]),
    )


def _safe_relative_path(value: str) -> Path:
    raw = str(value or "")
    if not raw or "\\" in raw:
        raise ValueError(f"模型文件相对路径无效：{value!r}")
    pure = PurePosixPath(raw)
    if (
        pure.is_absolute()
        or any(part in ("", ".", "..") for part in pure.parts)
        or any(":" in part for part in pure.parts)
    ):
        raise ValueError(f"模型文件相对路径无效：{value!r}")
    return Path(*pure.parts)


def _required_paths(model_id: str, base_dir: Path) -> list[Path]:
    metadata = _model_metadata(model_id)
    return [base_dir / _safe_relative_path(item) for item in metadata["required_files"]]


def _missing_files(model_id: str, base_dir: Path) -> list[str]:
    metadata = _model_metadata(model_id)
    missing: list[str] = []
    for relative, path in zip(metadata["required_files"], _required_paths(model_id, base_dir)):
        try:
            valid = path.is_file() and path.stat().st_size > 0
        except OSError:
            valid = False
        if not valid:
            missing.append(str(relative))
    return missing


def _directory_size(model_id: str, base_dir: Path) -> int:
    total = 0
    for path in _required_paths(model_id, base_dir):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def _runtime_status(metadata: dict[str, Any]) -> tuple[bool, str]:
    engine = str(metadata["engine"])
    if engine == "faster_whisper":
        if importlib.util.find_spec("faster_whisper") is None:
            return False, "缺少可选运行组件 faster-whisper。"
        return True, "运行组件可用。"
    if importlib.util.find_spec("sherpa_onnx") is None:
        return False, "缺少运行组件 sherpa-onnx。"
    if engine == "qwen3_asr":
        try:
            import sherpa_onnx

            if not hasattr(sherpa_onnx.OfflineRecognizer, "from_qwen3_asr"):
                return False, "当前 sherpa-onnx 版本不支持 Qwen3-ASR，需要 1.13.4 或更高版本。"
        except (ImportError, AttributeError):
            return False, "无法加载 Qwen3-ASR 运行组件。"
    return True, "运行组件可用。"


def get_local_model_status(model_id: str) -> dict[str, Any]:
    """返回单个模型的 JSON 可序列化元数据和真实安装状态。"""
    metadata = deepcopy(_model_metadata(model_id))
    source_dir, local_dir = _model_directories(metadata["id"])
    source_missing = _missing_files(metadata["id"], source_dir)
    local_missing = _missing_files(metadata["id"], local_dir)
    bundled = not source_missing
    cached_locally = not local_missing
    runtime_ready, runtime_message = _runtime_status(metadata)
    installed = bundled or cached_locally
    available = installed and runtime_ready

    if cached_locally and runtime_ready:
        status = "已安装"
        status_message = "模型已安装到本机，可以离线使用。"
    elif bundled and runtime_ready:
        status = "可安装"
        status_message = "模型已随软件提供，首次使用时会安全复制到本机。"
    elif not installed:
        status = "未安装"
        status_message = "模型文件尚未下载。"
    else:
        status = "缺少组件"
        status_message = runtime_message

    metadata.update(
        {
            "model_id": metadata["id"],
            "installed": installed,
            "available": available,
            "bundled": bundled,
            "cached_locally": cached_locally,
            "runtime_ready": runtime_ready,
            "runtime_message": runtime_message,
            "status": status,
            "status_message": status_message,
            "source_path": str(source_dir),
            "local_path": str(local_dir),
            "size_on_disk_bytes": (
                _directory_size(metadata["id"], local_dir)
                if cached_locally
                else _directory_size(metadata["id"], source_dir)
            ),
            "missing_files": [] if installed else source_missing,
        }
    )
    return metadata


def get_local_model_catalog() -> list[dict[str, Any]]:
    """返回全部本地模型；结果可直接交给网页面板进行 JSON 序列化。"""
    catalog = [get_local_model_status(model_id) for model_id in LOCAL_MODELS]
    json.dumps(catalog, ensure_ascii=False)
    return catalog


def install_model_locally(model_id: str = MODEL_NAME) -> Path:
    """按模型文件清单逐文件原子复制到本机目录。"""
    metadata = _model_metadata(model_id)
    source_dir, local_dir = _model_directories(metadata["id"])
    source_paths = _required_paths(metadata["id"], source_dir)
    target_paths = _required_paths(metadata["id"], local_dir)

    missing = _missing_files(metadata["id"], source_dir)
    local_missing = _missing_files(metadata["id"], local_dir)
    if not local_missing and missing:
        # 已完成本机缓存后，即使共享目录临时离线也应继续可用。
        return local_dir
    if missing:
        missing_text = "、".join(missing)
        raise FileNotFoundError(
            f"本地模型“{metadata['name']}”尚未安装，缺少模型文件：{missing_text}。"
        )

    if not local_missing and all(
        target.stat().st_size == source.stat().st_size
        for source, target in zip(source_paths, target_paths)
    ):
        return local_dir

    local_dir.mkdir(parents=True, exist_ok=True)
    for source, target in zip(source_paths, target_paths):
        target.parent.mkdir(parents=True, exist_ok=True)
        source_size = source.stat().st_size
        try:
            if target.is_file() and target.stat().st_size == source_size:
                continue
        except OSError:
            pass

        temporary = target.parent / (
            f".{target.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
        )
        try:
            shutil.copyfile(source, temporary)
            if temporary.stat().st_size != source_size:
                raise OSError(f"模型文件复制后的大小不一致：{source.name}")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return local_dir


def available_providers() -> list[str]:
    """返回当前 sherpa-onnx 构建实际可用的推理设备。"""
    try:
        import sherpa_onnx

        providers = list(sherpa_onnx.get_available_providers())
    except (ImportError, AttributeError):
        providers = []
    return providers or ["cpu"]


def choose_provider(preference: str = "auto") -> tuple[str, str]:
    requested = str(preference or "auto").strip().lower()
    if requested not in ("auto", "cpu", "gpu"):
        raise ValueError("本地识别设备只能选择自动、CPU 或 GPU。")
    providers = {item.lower(): item for item in available_providers()}
    gpu_candidates = ("cuda", "directml", "coreml")
    if requested == "cpu":
        return "cpu", "CPU"
    if requested == "gpu":
        for candidate in gpu_candidates:
            if candidate in providers:
                return providers[candidate], "GPU"
        raise RuntimeError("当前电脑没有可用的本地识别 GPU 运行组件。")
    for candidate in gpu_candidates:
        if candidate in providers:
            return providers[candidate], "GPU"
    return "cpu", "CPU"


class LocalModelRecognizer:
    """统一、线程安全的离线语音识别器。"""

    def __init__(
        self,
        model_id: str = MODEL_NAME,
        device: str = "auto",
        num_threads: int = 2,
    ) -> None:
        metadata = _model_metadata(model_id)
        self.model_id = str(metadata["id"])
        self.metadata = metadata
        self.device = str(device or "auto").strip().lower()
        self.preference = self.device
        self.num_threads = max(1, int(num_threads))
        self.provider, self.device_label = choose_provider(self.device)
        self._recognizer: Any = None
        self._lock = threading.RLock()

    def load(self) -> None:
        with self._lock:
            if self._recognizer is not None:
                return
            model_dir = install_model_locally(self.model_id)
            engine = str(self.metadata["engine"])
            if engine == "faster_whisper":
                self._load_faster_whisper(model_dir)
                return

            import sherpa_onnx

            if engine == "sense_voice":
                self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                    model=str(model_dir / "model.int8.onnx"),
                    tokens=str(model_dir / "tokens.txt"),
                    num_threads=self.num_threads,
                    provider=self.provider,
                    language="zh",
                    use_itn=True,
                )
            elif engine == "paraformer":
                self._recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
                    paraformer=str(model_dir / "model.int8.onnx"),
                    tokens=str(model_dir / "tokens.txt"),
                    num_threads=self.num_threads,
                    provider=self.provider,
                )
            elif engine == "qwen3_asr":
                factory = getattr(sherpa_onnx.OfflineRecognizer, "from_qwen3_asr", None)
                if factory is None:
                    raise RuntimeError(
                        "当前 sherpa-onnx 版本不支持 Qwen3-ASR，需要 1.13.4 或更高版本。"
                    )
                self._recognizer = factory(
                    conv_frontend=str(model_dir / "conv_frontend.onnx"),
                    encoder=str(model_dir / "encoder.int8.onnx"),
                    decoder=str(model_dir / "decoder.int8.onnx"),
                    tokenizer=str(model_dir / "tokenizer"),
                    num_threads=self.num_threads,
                    provider=self.provider,
                    max_new_tokens=512,
                )
            else:  # pragma: no cover
                raise RuntimeError(f"暂不支持模型引擎：{engine}")

    def _load_faster_whisper(self, model_dir: Path) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "Faster-Whisper Small 的模型文件存在，但尚未安装 faster-whisper 运行组件。"
            ) from exc
        use_gpu = self.provider.lower() in ("cuda", "directml", "coreml")
        if use_gpu and self.provider.lower() != "cuda":
            raise RuntimeError("Faster-Whisper 的 GPU 模式只支持 NVIDIA CUDA。")
        self._recognizer = WhisperModel(
            str(model_dir),
            device="cuda" if use_gpu else "cpu",
            compute_type="int8_float16" if use_gpu else "int8",
            cpu_threads=self.num_threads,
        )

    @staticmethod
    def _pcm16_samples(pcm: bytes) -> list[float]:
        samples = array("h")
        samples.frombytes(pcm)
        if os.sys.byteorder != "little":
            samples.byteswap()
        return [value / 32768.0 for value in samples]

    def transcribe_pcm16(self, pcm: bytes, sample_rate: int = 16000) -> str:
        if not pcm:
            return ""
        if int(sample_rate) <= 0:
            raise ValueError("录音采样率必须大于零。")
        if len(pcm) % 2:
            raise ValueError("PCM16 录音数据长度必须是 2 的倍数。")
        self.load()
        samples = self._pcm16_samples(pcm)
        with self._lock:
            if self.metadata["engine"] == "faster_whisper":
                if int(sample_rate) != 16000:
                    raise ValueError("Faster-Whisper 的 PCM 数组输入必须是 16000 Hz。")
                import numpy as np

                segments, _info = self._recognizer.transcribe(
                    np.asarray(samples, dtype=np.float32),
                    language="zh",
                    beam_size=5,
                    vad_filter=False,
                )
                return "".join(str(segment.text) for segment in segments).strip()

            stream = self._recognizer.create_stream()
            stream.accept_waveform(int(sample_rate), samples)
            self._recognizer.decode_stream(stream)
            return str(stream.result.text or "").strip()


class SenseVoiceRecognizer(LocalModelRecognizer):
    """兼容旧调用方式的 SenseVoiceSmall 离线中文识别器。"""

    def __init__(self, preference: str = "auto", num_threads: int = 2) -> None:
        super().__init__(MODEL_NAME, device=preference, num_threads=num_threads)
