from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import threading
import uuid
from array import array
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any

from config_store import MODEL_CACHE_DIR
from model_download import (
    ResourceVerificationError,
    ensure_resource_verified,
    is_resource_verified,
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


MODEL_SOURCE_ROOT = _model_repository_root()
LOCAL_MODELS_DIR = MODEL_CACHE_DIR

SENSEVOICE_MODEL_ID = "sensevoice-small-int8"
PARAFORMER_MODEL_ID = "paraformer-zh-small-int8"
QWEN3_MODEL_ID = "qwen3-asr-0.6b-int8"
FASTER_WHISPER_MODEL_ID = "faster-whisper-small"
QWEN3_17_MODEL_ID = "qwen3-asr-1.7b-q5km"
QWEN3_17_RESOURCE_ID = QWEN3_17_MODEL_ID
QWEN3_17_FILENAME = "Qwen3-ASR-1.7B-Q5_K_M.gguf"
MODEL_DISPLAY_ORDER = (
    FASTER_WHISPER_MODEL_ID,
    QWEN3_MODEL_ID,
    QWEN3_17_MODEL_ID,
)

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
        "summary": "短句听写，也能识别情感和声音事件",
        "language_support": "支持中文和英文，可识别中英混说",
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
        "summary": "体积小、速度快，兼顾部分中文方言",
        "language_support": "支持中文和英文，适合中英混说",
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
        "summary": "兼顾多种语言、中文方言、歌词和说唱",
        "language_support": "支持中文和英文，也支持多种语言与方言",
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
        "summary": "多语言自动检测，并支持时间戳",
        "language_support": "支持中文和英文；中英混说效果取决于录音内容",
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

_QWEN3_17_METADATA: dict[str, Any] = {
    "id": QWEN3_17_MODEL_ID,
    "name": "Qwen3-ASR 1.7B Q5_K_M",
    "engine": "transcribe_cpp",
    "storage_id": QWEN3_17_RESOURCE_ID,
    "source_directory": (
        "qwen3-asr-1.7b-gguf/"
        "92282af1610a2db19d66f2bef1e260f5deca782d"
    ),
    "required_files": [QWEN3_17_FILENAME],
    "file_sizes": {QWEN3_17_FILENAME: 1_517_290_464},
    "size_bytes": 1_517_290_464,
    "capabilities": [
        "普通话",
        "粤语",
        "中英混说",
        "30 种语言",
        "自动语言检测",
    ],
    "summary": "识别能力更强，可自动检测 30 种语言",
    "language_support": "支持中文和英文混说，并自动检测 30 种语言",
    "hardware": {
        "minimum": "4 核 64 位 CPU、12 GB 内存",
        "recommended": "8 核 CPU、16 GB 内存，或支持 Vulkan 的显卡",
        "gpu": "支持 Vulkan 的 Intel、AMD、NVIDIA 显卡；不可用时可使用 CPU",
        "note": "Q5_K_M 约 1.52 GB。配置要求为工程估算；模型越大，首次加载和最终识别耗时越长。",
    },
    "license": "Apache-2.0（Qwen3-ASR 权重）；MIT（transcribe.cpp）",
    "download": {
        "page": "https://huggingface.co/handy-computer/Qwen3-ASR-1.7B-gguf",
        "url": (
            "https://huggingface.co/handy-computer/Qwen3-ASR-1.7B-gguf/"
            "resolve/92282af1610a2db19d66f2bef1e260f5deca782d/"
            "Qwen3-ASR-1.7B-Q5_K_M.gguf?download=true"
        ),
        "version": (
            "handy-computer/Qwen3-ASR-1.7B-gguf@"
            "92282af1610a2db19d66f2bef1e260f5deca782d"
        ),
        "size_bytes": 1_517_290_464,
        "sha256": "034c557fe92ff8fcd9a9c041cbdaad347be0a86a58d3a348f63cf3f0180879d0",
    },
    "sha256": {
        QWEN3_17_FILENAME: "034c557fe92ff8fcd9a9c041cbdaad347be0a86a58d3a348f63cf3f0180879d0",
    },
}
LOCAL_MODELS[QWEN3_17_MODEL_ID] = deepcopy(_QWEN3_17_METADATA)

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
    storage_id = str(metadata.get("storage_id") or metadata["id"])
    return (
        Path(MODEL_SOURCE_ROOT) / str(metadata["source_directory"]),
        Path(LOCAL_MODELS_DIR) / storage_id,
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
    expected_sizes = metadata.get("file_sizes") or {}
    missing: list[str] = []
    for relative, path in zip(metadata["required_files"], _required_paths(model_id, base_dir)):
        try:
            size = path.stat().st_size if path.is_file() else 0
            expected_size = int(expected_sizes.get(relative) or 0)
            valid = size > 0 and (not expected_size or size == expected_size)
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
    if engine == "transcribe_cpp":
        if importlib.util.find_spec("transcribe_cpp") is None:
            return False, "缺少 Qwen3-ASR 1.7B 运行组件 transcribe-cpp 0.2.1。"
        try:
            import transcribe_cpp  # noqa: F401
        except Exception:
            return False, "Qwen3-ASR 1.7B 运行组件无法加载或版本不匹配。"
        return True, "transcribe.cpp 运行组件可用。"
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


def _download_verification_spec(
    model_id: str,
    base_dir: Path,
) -> dict[str, Any] | None:
    """返回按需下载模型在指定目录中的固定校验清单。"""
    metadata = _model_metadata(model_id)
    download = metadata.get("download") or {}
    version = str(download.get("version") or "").strip()
    sha256 = str(download.get("sha256") or "").strip().lower()
    if not version or not sha256:
        return None
    filename = str(metadata["required_files"][0])
    return {
        "resource_id": str(metadata.get("storage_id") or metadata["id"]),
        "target_path": Path(base_dir) / _safe_relative_path(filename),
        "version": version,
        "size_bytes": int(download["size_bytes"]),
        "sha256": sha256,
    }


def _ensure_download_resource_verified(model_id: str, base_dir: Path) -> None:
    """在按需下载模型进入推理运行时前强制验证固定版本与 SHA-256。"""
    verification = _download_verification_spec(model_id, base_dir)
    if verification is None:
        return
    try:
        ensure_resource_verified(
            verification["resource_id"],
            verification["target_path"],
            verification["version"],
            verification["size_bytes"],
            verification["sha256"],
        )
    except ResourceVerificationError as exc:
        metadata = _model_metadata(model_id)
        raise RuntimeError(
            f"本地模型“{metadata['name']}”未通过固定版本和 SHA-256 完整性校验：{exc}。"
            "请在设置中点击“校验模型”重试；若仍失败，请删除模型后重新下载。"
        ) from exc


def get_local_model_status(model_id: str) -> dict[str, Any]:
    """返回单个模型的 JSON 可序列化元数据和真实安装状态。"""
    metadata = deepcopy(_model_metadata(model_id))
    source_dir, local_dir = _model_directories(metadata["id"])
    source_missing = _missing_files(metadata["id"], source_dir)
    local_missing = _missing_files(metadata["id"], local_dir)
    bundled = not source_missing
    cached_locally = not local_missing
    runtime_ready, runtime_message = _runtime_status(metadata)
    verification = _download_verification_spec(metadata["id"], local_dir)
    downloadable = verification is not None
    verified = bool(
        verification is not None
        and cached_locally
        and is_resource_verified(
            verification["resource_id"],
            verification["target_path"],
            verification["version"],
            verification["size_bytes"],
            verification["sha256"],
        )
    )
    installed = bundled or cached_locally
    usable_files = bundled or cached_locally and (not downloadable or verified)
    available = usable_files and runtime_ready

    if cached_locally and (not downloadable or verified) and runtime_ready:
        status = "已安装"
        status_message = (
            "模型已通过固定版本和 SHA-256 完整性校验，可以离线使用。"
            if downloadable
            else "模型已安装到本机，可以离线使用。"
        )
    elif bundled and runtime_ready:
        status = "可安装"
        status_message = "模型已随软件提供，首次使用时会安全复制到本机。"
    elif not installed:
        status = "未安装"
        status_message = "模型文件尚未下载。"
    elif downloadable and cached_locally and not verified:
        status = "待校验"
        status_message = (
            "模型文件已存在，但没有匹配当前固定版本的 SHA-256 校验凭据。"
            "请点击“校验模型”；若校验失败，请删除模型后重新下载。"
        )
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
            "verified": verified,
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
            "resource_id": str(metadata.get("storage_id") or metadata["id"]),
            "downloadable": downloadable,
        }
    )
    return metadata


def get_model_download_resource(model_id: str) -> dict[str, Any] | None:
    """返回按需下载所需的内部资源描述；两个 1.7B 配置共享同一目标。"""
    metadata = _model_metadata(model_id)
    download = metadata.get("download") or {}
    _source_dir, local_dir = _model_directories(metadata["id"])
    verification = _download_verification_spec(metadata["id"], local_dir)
    if verification is None:
        return None
    return {
        "resource_id": verification["resource_id"],
        "url": str(download["url"]),
        "target_path": str(verification["target_path"]),
        "version": verification["version"],
        "size_bytes": verification["size_bytes"],
        "sha256": verification["sha256"],
    }


def get_downloadable_model_resources() -> list[dict[str, Any]]:
    resources: dict[str, dict[str, Any]] = {}
    for model_id in LOCAL_MODELS:
        incoming = get_model_download_resource(model_id)
        if incoming is not None:
            resources.setdefault(str(incoming["resource_id"]), incoming)
    return list(resources.values())


def get_local_model_catalog() -> list[dict[str, Any]]:
    """返回全部本地模型；结果可直接交给网页面板进行 JSON 序列化。"""
    catalog = [get_local_model_status(model_id) for model_id in MODEL_DISPLAY_ORDER]
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
        _ensure_download_resource_verified(metadata["id"], local_dir)
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
        _ensure_download_resource_verified(metadata["id"], local_dir)
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
    _ensure_download_resource_verified(metadata["id"], local_dir)
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


def _choose_transcribe_device(preference: str) -> tuple[Any, str, str]:
    requested = str(preference or "auto").strip().lower()
    if requested not in ("auto", "cpu", "gpu"):
        raise ValueError("本地识别设备只能选择自动、CPU 或 GPU。")
    try:
        import transcribe_cpp

        devices = list(transcribe_cpp.backends())
    except Exception as exc:
        raise RuntimeError(
            "Qwen3-ASR 1.7B 运行组件 transcribe-cpp 0.2.1 尚未正确安装。"
        ) from exc
    if not devices:
        raise RuntimeError("transcribe.cpp 没有发现可用的 CPU 或 GPU 后端。")

    def device_type(device: Any) -> str:
        return str(getattr(device, "device_type", "") or "unknown").strip().lower()

    def device_kind(device: Any) -> str:
        return str(getattr(device, "kind", "") or "unknown").strip().lower()

    cpu = next((item for item in devices if device_type(item) == "cpu"), None)
    gpu_devices = [
        item for item in devices
        if device_type(item) in {"gpu", "igpu"}
        and device_kind(item) not in {"accel", "cpu_accel"}
    ]
    priority = {"cuda": 0, "rocm": 1, "vulkan": 2, "metal": 3, "sycl": 4}
    gpu_devices.sort(key=lambda item: priority.get(device_kind(item), 9))
    if requested == "cpu":
        if cpu is None:
            raise RuntimeError("transcribe.cpp 的 CPU 后端不可用。")
        return cpu, "CPU", "cpu"
    if requested == "gpu":
        if not gpu_devices:
            raise RuntimeError("当前电脑没有可用的 transcribe.cpp Vulkan 或 CUDA 显卡后端。")
        selected = gpu_devices[0]
        kind = device_kind(selected)
        label_prefix = "集成显卡" if device_type(selected) == "igpu" else "显卡"
        return selected, f"{label_prefix}（{kind.upper()}）", kind
    else:
        if not gpu_devices and cpu is None:
            raise RuntimeError("transcribe.cpp 没有发现可用的识别设备。")
        return None, "自动选择（运行时确定）", "auto"


def choose_model_device(model_id: str, preference: str = "auto") -> tuple[str, str]:
    metadata = _model_metadata(model_id)
    if str(metadata["engine"]) == "transcribe_cpp":
        _device, label, provider = _choose_transcribe_device(preference)
        return provider, label
    return choose_provider(preference)


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
        self._transcribe_device: Any = None
        self._transcribe_run_lock: threading.RLock | None = None
        if str(metadata["engine"]) == "transcribe_cpp":
            (
                self._transcribe_device,
                self.device_label,
                self.provider,
            ) = _choose_transcribe_device(self.device)
        else:
            self.provider, self.device_label = choose_provider(self.device)
        self._recognizer: Any = None
        self._lock = threading.RLock()

    def load(self) -> None:
        with self._lock:
            if self._recognizer is not None:
                return
            model_dir = install_model_locally(self.model_id)
            engine = str(self.metadata["engine"])
            if engine == "transcribe_cpp":
                self._load_transcribe_cpp(model_dir)
                return
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

    def _load_transcribe_cpp(self, model_dir: Path) -> None:
        _ensure_download_resource_verified(self.model_id, model_dir)
        try:
            import transcribe_cpp
        except Exception as exc:
            raise RuntimeError(
                "Qwen3-ASR 1.7B 需要 transcribe-cpp 0.2.1 运行组件。"
            ) from exc
        model_path = model_dir / QWEN3_17_FILENAME
        model_options = (
            {"backend": "auto"}
            if self._transcribe_device is None
            else {"device": self._transcribe_device}
        )
        self._recognizer = transcribe_cpp.Model(str(model_path), **model_options)
        self._transcribe_run_lock = threading.RLock()
        actual_device = getattr(self._recognizer, "device", None)
        actual_type = str(getattr(actual_device, "device_type", "") or "").lower()
        actual_kind = str(
            getattr(actual_device, "kind", "") or self.provider
        ).strip().lower()
        if actual_type == "cpu" or actual_kind == "cpu":
            self.provider = "cpu"
            self.device_label = "CPU"
        elif actual_kind:
            self.provider = actual_kind
            label_prefix = "集成显卡" if actual_type == "igpu" else "显卡"
            self.device_label = f"{label_prefix}（{actual_kind.upper()}）"

    def close(self) -> None:
        """释放模型后端；切换配置后允许 Windows 删除共享 GGUF 文件。"""
        with self._lock:
            recognizer, self._recognizer = self._recognizer, None
            self._transcribe_run_lock = None
            self._transcribe_device = None
        closer = getattr(recognizer, "close", None)
        if callable(closer):
            closer()

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
            if self.metadata["engine"] == "transcribe_cpp":
                if int(sample_rate) != 16000:
                    raise ValueError("Qwen3-ASR 1.7B 的 PCM 输入必须是 16000 Hz。")
                run_lock = self._transcribe_run_lock or self._lock
                with run_lock:
                    with self._recognizer.session() as session:
                        result = session.run(samples)
                return str(getattr(result, "text", "") or "").strip()
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
