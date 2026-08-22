from __future__ import annotations

import json
import os
import tempfile
import threading
import ctypes
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path

from global_hotkey import normalize_hotkey


APP_DATA_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / "FloatingVoiceButton"
CONFIG_PATH = APP_DATA_DIR / "config.json"
CONFIG_VERSION = 12
DEFAULT_LOCAL_MODEL = "faster-whisper-small"
LEGACY_LOCAL_MODELS = {
    "sensevoice-small-int8": DEFAULT_LOCAL_MODEL,
    "paraformer-zh-small-int8": DEFAULT_LOCAL_MODEL,
    "qwen3-asr-1.7b-q5km-hotwords": "qwen3-asr-1.7b-q5km",
}
DEFAULT_REALTIME_MODEL = "streaming-paraformer-bilingual-zh-en"
ZIPFORMER_REALTIME_MODEL = "zipformer-bilingual-zh-en-exp32-int8"
REALTIME_MODEL_IDS = frozenset({
    DEFAULT_REALTIME_MODEL,
    ZIPFORMER_REALTIME_MODEL,
})
LOCAL_MODEL_IDS = frozenset({
    DEFAULT_LOCAL_MODEL,
    "qwen3-asr-0.6b-int8",
    "qwen3-asr-1.7b-q5km",
    "faster-whisper-small",
})
CLOUD_PROVIDER_IDS = frozenset({"volcengine", "iflytek", "tencent", "aliyun"})
DEFAULT_RECOGNITION_ENGINE = f"local:{DEFAULT_LOCAL_MODEL}"

# 在线服务密钥只能存入 Windows 凭据管理器。这里同时清理早期版本或
# 手工编辑配置时可能写入的常见密钥字段，防止它们被再次保存到 config.json。
_SECRET_CONFIG_KEYS = frozenset({
    "credentials",
    "provider_credentials",
    "api_key",
    "api_secret",
    "api_token",
    "token",
    "secret_id",
    "secret_key",
    "access_key",
    "access_key_id",
    "access_key_secret",
    "app_id",
    "appid",
    "app_key",
})
DEFAULT_CONFIG = {
    "config_version": CONFIG_VERSION,
    "paste_wait_ms": 150,
    "auto_paste_enabled": True,
    "button_size": 72,
    "button_color": "#2563EB",
    "button_opacity": 100,
    "global_hotkey": "Ctrl+Alt+Space",
    "standby_enabled": False,
    "standby_confidence": 80,
    "live_transcript_visible": True,
    "realtime_model": DEFAULT_REALTIME_MODEL,
    "recognition_engine": DEFAULT_RECOGNITION_ENGINE,
    "fallback_model": DEFAULT_LOCAL_MODEL,
    "local_asr_device": "auto",
    "position_x": None,
    "position_y": None,
}

_lock = threading.RLock()
_kernel32 = ctypes.windll.kernel32
_kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
_kernel32.ReleaseMutex.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
_CONFIG_MUTEX_NAME = "Local\\FloatingVoiceButton_Config_v2"
_WAIT_OBJECT_0 = 0x00000000
_WAIT_ABANDONED = 0x00000080


@contextmanager
def _config_mutex():
    handle = _kernel32.CreateMutexW(None, False, _CONFIG_MUTEX_NAME)
    if not handle:
        raise ctypes.WinError()
    try:
        result = int(_kernel32.WaitForSingleObject(handle, 3000))
        if result not in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
            raise TimeoutError("配置文件暂时被其他窗口占用。")
        try:
            yield
        finally:
            _kernel32.ReleaseMutex(handle)
    finally:
        _kernel32.CloseHandle(handle)


def normalize_hex_color(value: object, fallback: str = "#2563EB") -> str:
    text = str(value or "").strip().upper()
    if not text.startswith("#"):
        text = f"#{text}"
    if len(text) == 7:
        try:
            int(text[1:], 16)
            return text
        except ValueError:
            pass
    return fallback


def normalize_recognition_engine(value: object) -> str:
    """把识别引擎统一为 ``local:模型`` 或 ``cloud:服务``。"""
    text = str(value or "").strip().lower()
    if text.startswith("online:"):
        text = f"cloud:{text.removeprefix('online:')}"
    local_candidate = text.removeprefix("local:")
    if local_candidate in LEGACY_LOCAL_MODELS:
        text = f"local:{LEGACY_LOCAL_MODELS[local_candidate]}"
    if text == "cloud:xfyun":
        text = "cloud:iflytek"
    elif text == "xfyun":
        text = "cloud:iflytek"
    if text in LOCAL_MODEL_IDS:
        text = f"local:{text}"
    elif text in CLOUD_PROVIDER_IDS:
        text = f"cloud:{text}"
    prefix, separator, identifier = text.partition(":")
    if not separator:
        return DEFAULT_RECOGNITION_ENGINE
    if prefix == "local" and identifier in LOCAL_MODEL_IDS:
        return text
    if prefix == "cloud" and identifier in CLOUD_PROVIDER_IDS:
        return text
    return DEFAULT_RECOGNITION_ENGINE


def normalize_fallback_model(value: object) -> str:
    """回退模型只接受本地模型标识，不允许把在线服务串成循环回退。"""
    text = str(value or "").strip().lower()
    if text.startswith("local:"):
        text = text.removeprefix("local:")
    text = LEGACY_LOCAL_MODELS.get(text, text)
    return text if text in LOCAL_MODEL_IDS else DEFAULT_LOCAL_MODEL


def normalize_realtime_model(value: object) -> str:
    """实时文字只允许使用已经接入并登记的两套流式模型。"""
    text = str(value or "").strip().lower()
    return text if text in REALTIME_MODEL_IDS else DEFAULT_REALTIME_MODEL


def _normalize(raw: dict) -> dict:
    sanitized_raw = {
        key: value
        for key, value in raw.items()
        if key in DEFAULT_CONFIG
        and str(key).strip().lower() not in _SECRET_CONFIG_KEYS
    }
    config = DEFAULT_CONFIG.copy()
    config.update(sanitized_raw)

    config["config_version"] = CONFIG_VERSION

    config["button_color"] = normalize_hex_color(config.get("button_color"))
    config["global_hotkey"] = normalize_hotkey(config.get("global_hotkey"))
    config["standby_enabled"] = bool(config.get("standby_enabled", False))
    config["auto_paste_enabled"] = bool(config.get("auto_paste_enabled", True))
    try:
        config["standby_confidence"] = max(
            70, min(100, int(config.get("standby_confidence", 80)))
        )
    except (TypeError, ValueError):
        config["standby_confidence"] = 80
    config["live_transcript_visible"] = bool(
        config.get("live_transcript_visible", True)
    )
    config["realtime_model"] = normalize_realtime_model(
        config.get("realtime_model")
    )
    config["recognition_engine"] = normalize_recognition_engine(
        config.get("recognition_engine")
    )
    config["fallback_model"] = normalize_fallback_model(config.get("fallback_model"))
    device = str(config.get("local_asr_device", "auto")).strip().lower()
    config["local_asr_device"] = device if device in ("auto", "cpu", "gpu") else "auto"
    try:
        config["button_opacity"] = max(30, min(100, int(config.get("button_opacity", 100))))
    except (TypeError, ValueError):
        config["button_opacity"] = 100
    return config


def _read_unlocked() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        incoming = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return incoming if isinstance(incoming, dict) else {}


def _write_unlocked(config: dict) -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=".config-", suffix=".tmp", dir=APP_DATA_DIR
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(config, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, CONFIG_PATH)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def load_config() -> dict:
    with _lock:
        with _config_mutex():
            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            return _normalize(_read_unlocked())


def save_config(config: dict) -> dict:
    with _lock:
        with _config_mutex():
            normalized = _normalize(dict(config))
            _write_unlocked(normalized)
            return normalized


def load_and_persist_config() -> dict:
    """在同一次跨进程锁内读取、升级并写回，避免覆盖并发保存。"""
    with _lock:
        with _config_mutex():
            normalized = _normalize(_read_unlocked())
            _write_unlocked(normalized)
            return normalized


def update_config(changes: dict) -> dict:
    """读取最新配置后只合并指定字段，避免设置窗口与拖动位置互相覆盖。"""
    with _lock:
        with _config_mutex():
            current = _normalize(_read_unlocked())
            current.update(changes)
            normalized = _normalize(current)
            _write_unlocked(normalized)
            return normalized
