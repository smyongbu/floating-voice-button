from __future__ import annotations

import ctypes
import os
import re
import threading
import time
import traceback
import uuid
from ctypes import wintypes
from pathlib import Path

try:
    import webview
except ImportError:
    webview = None

from automation import write_clipboard_text
from audio_level import AudioLevelMonitor
from cloud_asr import get_provider_catalog, validate_credentials
from config_store import (
    APP_DATA_DIR,
    DEFAULT_REALTIME_MODEL,
    DEFAULT_CONFIG,
    REALTIME_MODEL_IDS,
    load_config,
    normalize_realtime_model,
    update_config,
)
from credential_store import CredentialStore
from history_store import HistoryEntry, HistoryRevisionMismatch, HistoryStore
from global_hotkey import parse_hotkey
from logger import build_loggers
from local_asr import (
    LocalModelRecognizer,
    choose_model_device,
    get_local_model_catalog,
    get_model_download_resource,  # 保留旧测试与外部补丁的兼容挂接点。
)
from model_resource_groups import GroupedModelDownloadManager, build_grouped_download_specs
from realtime_asr import (
    RealtimeRecognizer,
    get_realtime_model_catalog,
    get_realtime_model_status,
)
from standby_listener import standby_control_match
from test_mode_signal import TestModeLease


PANEL_TITLE = "语点 · 设置与历史记录"
APP_NAME = "悬浮语音按钮"
PROJECT_DIR = Path(__file__).resolve().parent
WEB_ENTRY = Path("web") / "index.html"
COLOR_PATTERN = re.compile(r"^#[0-9A-F]{6}$")

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
kernel32 = ctypes.windll.kernel32


def _success(data: dict | list | None = None, message: str = "") -> dict:
    return {"ok": True, "data": data if data is not None else {}, "message": message}


def _failure(message: str, data: dict | list | None = None) -> dict:
    return {"ok": False, "data": data if data is not None else {}, "message": message}


def _serialize_entry(entry: HistoryEntry) -> dict:
    return {
        "id": entry.operation_id,
        "created_at": entry.created_at,
        "text": entry.text,
    }


class WebSettingsApi:
    """只向本地 WebView 暴露设置与历史所需的最小接口。"""

    def __init__(self, run_log, error_log, store: HistoryStore | None = None) -> None:
        # pywebview 会递归暴露所有非下划线成员，因此依赖对象必须保持私有。
        self._run_log = run_log
        self._error_log = error_log
        self._credential_store = CredentialStore()
        self._voice_test_lock = threading.RLock()
        self._model_resource_lock = threading.RLock()
        self._voice_test_monitor: AudioLevelMonitor | None = None
        self._voice_test_model_id = ""
        self._control_test_monitor: AudioLevelMonitor | None = None
        self._control_test_session = None
        self._control_test_result = {"active": False, "word": "", "confidence": 0}
        self._test_mode_lease = TestModeLease()
        self._active_test_kind = ""
        self._model_downloads = GroupedModelDownloadManager(
            build_grouped_download_specs(),
            run_log=self._run_log,
            error_log=self._error_log,
        )
        if store is not None:
            self._store: HistoryStore | None = store
            self._history_error = False
        else:
            try:
                self._store = HistoryStore()
                self._history_error = False
            except Exception as exc:
                self._store = None
                self._history_error = True
                self._error_log.exception(
                    "历史记录初始化失败 | 异常类型=%s", type(exc).__name__
                )

    @staticmethod
    def _operation_id() -> str:
        return uuid.uuid4().hex[:8]

    @staticmethod
    def _panel_hwnd() -> int:
        target_pid = os.getpid()
        result = ctypes.c_void_p()

        @WNDENUMPROC
        def enum_callback(hwnd, _lparam):
            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            if process_id.value != target_pid or not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            if title.value == PANEL_TITLE:
                result.value = int(hwnd)
                return False
            return True

        user32.EnumWindows(enum_callback, 0)
        return int(result.value or 0)

    @staticmethod
    def _main_window_exists() -> bool:
        result = ctypes.c_bool(False)

        @WNDENUMPROC
        def enum_callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            if title.value == APP_NAME:
                result.value = True
                return False
            return True

        user32.EnumWindows(enum_callback, 0)
        return bool(result.value)

    def _history_payload(self, query: str = "") -> dict:
        if self._store is None:
            return {
                "available": False,
                "entries": [],
                "signature": [0, 0],
            }
        entries, signature = self._store.snapshot(str(query))
        return {
            "available": True,
            "entries": [_serialize_entry(entry) for entry in entries],
            "signature": list(signature),
        }

    def get_initial_state(self) -> dict:
        try:
            config = load_config()
            return _success({
                "appearance": {
                    "color": str(config["button_color"]),
                    "opacity": int(config["button_opacity"]),
                    "size": int(config["button_size"]),
                    "default_color": str(DEFAULT_CONFIG["button_color"]),
                    "default_opacity": int(DEFAULT_CONFIG["button_opacity"]),
                    "default_size": int(DEFAULT_CONFIG["button_size"]),
                    "hotkey": str(config["global_hotkey"]),
                    "default_hotkey": str(DEFAULT_CONFIG["global_hotkey"]),
                    "standby_enabled": bool(config["standby_enabled"]),
                    "default_standby_enabled": bool(DEFAULT_CONFIG["standby_enabled"]),
                    "standby_confidence": int(config["standby_confidence"]),
                    "default_standby_confidence": int(DEFAULT_CONFIG["standby_confidence"]),
                    "live_transcript_visible": bool(config["live_transcript_visible"]),
                    "default_live_transcript_visible": bool(
                        DEFAULT_CONFIG["live_transcript_visible"]
                    ),
                    "auto_paste_enabled": bool(config["auto_paste_enabled"]),
                    "default_auto_paste_enabled": bool(
                        DEFAULT_CONFIG["auto_paste_enabled"]
                    ),
                },
                "history": self._history_payload(),
                "model": self._recognition_payload(config),
            })
        except Exception as exc:
            self._error_log.exception(
                "网页面板初始化数据失败 | 异常类型=%s", type(exc).__name__
            )
            return _failure("设置数据读取失败，请查看错误日志。")

    def _recognition_payload(self, config: dict | None = None) -> dict:
        current = config or load_config()
        preference = str(current.get("local_asr_device", "auto"))
        engine_id = str(
            current.get("recognition_engine", "local:faster-whisper-small")
        )
        device_model_id = (
            engine_id.partition(":")[2]
            if engine_id.startswith("local:")
            else str(current.get("fallback_model", "faster-whisper-small"))
        )
        try:
            _provider, device_label = choose_model_device(
                device_model_id, preference
            )
            device_error = ""
        except Exception as exc:
            device_label = "不可用"
            device_error = str(exc)
        local_models = []
        registered_resource_ids = set(self._model_downloads.resource_ids)
        resource_statuses: dict[str, dict] = {}
        for incoming in get_local_model_catalog():
            model = dict(incoming)
            hardware = model.get("hardware") or {}
            model["minimum"] = str(hardware.get("minimum") or model.get("minimum") or "未提供")
            model["recommended"] = str(hardware.get("recommended") or model.get("recommended") or "未提供")
            model["gpu"] = str(hardware.get("gpu") or model.get("gpu") or "非必需")
            capabilities = model.get("capabilities") or model.get("languages") or model.get("summary")
            model["capabilities"] = (
                "、".join(str(item) for item in capabilities)
                if isinstance(capabilities, (list, tuple))
                else str(capabilities or "本地离线识别")
            )
            model["language_support"] = str(
                model.get("language_support") or "语言支持情况未说明"
            )
            resource_id = str(model.get("model_id") or "")
            if resource_id in registered_resource_ids:
                model["downloadable"] = True
                if resource_id not in resource_statuses:
                    resource_statuses[resource_id] = self._model_downloads.status(resource_id)
                # 同一资源可对应多个识别 profile；一次 payload 内必须使用同一快照。
                model["resource_status"] = dict(resource_statuses[resource_id])
            local_models.append(model)
        providers = []
        provider_descriptions = {
            "volcengine": "大模型录音文件极速版，整段上传后同步返回。",
            "iflytek": "语音听写流式接口，录音会按 40 毫秒分帧上传，耗时接近录音长度。",
            "tencent": "一句话识别，整段上传后同步返回。",
            "aliyun": "一句话识别，整段上传后同步返回。",
        }
        for incoming in get_provider_catalog():
            provider_id = str(incoming["id"])
            providers.append({
                "provider_id": provider_id,
                "name": str(incoming["name"]),
                "short_description": str(incoming["service"]),
                "description": provider_descriptions.get(provider_id, str(incoming["service"])),
                "configured": self._credential_store.exists(provider_id),
                "fields": [
                    {
                        "name": str(field["key"]),
                        "label": str(field["label"]),
                        "secret": bool(field.get("secret", True)),
                        "max_length": 512,
                    }
                    for field in incoming["credential_fields"]
                ],
            })
        with self._voice_test_lock:
            voice_test_active = self._voice_test_monitor is not None
            voice_test_model_id = self._voice_test_model_id
        realtime_models = []
        for incoming in get_realtime_model_catalog():
            model = dict(incoming)
            model_id = str(model.get("model_id") or "")
            if model_id in registered_resource_ids:
                model["downloadable"] = True
                model["resource_status"] = self._model_downloads.status(model_id)
            realtime_models.append(model)
        return {
            "engine_id": engine_id,
            "realtime_model": normalize_realtime_model(
                current.get("realtime_model")
            ),
            "realtime_models": realtime_models,
            "fallback_model": str(current.get("fallback_model", "faster-whisper-small")),
            "preference": preference,
            "device": device_label,
            "device_error": device_error,
            "local_models": local_models,
            "providers": providers,
            "voice_test_active": voice_test_active,
            "voice_test_model_id": voice_test_model_id,
        }

    def save_recognition_settings(
        self,
        engine_id: str,
        fallback_model: str,
        device: str,
        realtime_model: str | None = None,
    ) -> dict:
        operation_id = self._operation_id()
        normalized = str(device or "").strip().lower()
        if normalized not in ("auto", "cpu", "gpu"):
            return _failure("识别设备选项无效。")
        selected_realtime_model = str(
            realtime_model or load_config().get("realtime_model", DEFAULT_REALTIME_MODEL)
        ).strip().lower()
        if selected_realtime_model not in REALTIME_MODEL_IDS:
            return _failure("实时显示模型无效。")
        if not bool(
            get_realtime_model_status(selected_realtime_model).get("available")
        ):
            return _failure("所选实时显示模型尚未安装完整或缺少运行组件。")
        try:
            local_catalog = {
                str(item["model_id"]): item for item in get_local_model_catalog()
            }
            local_ids = set(local_catalog)
            provider_ids = {str(item["id"]) for item in get_provider_catalog()}
            selected_engine = str(engine_id or "").strip().lower()
            downloadable_roles: list[tuple[str, str]] = []
            if selected_engine.startswith("local:"):
                selected_local_id = selected_engine.split(":", 1)[1]
                if selected_local_id not in local_ids:
                    return _failure("所选本地模型无效。")
                selected_status = local_catalog[selected_local_id]
                if not bool(selected_status.get("available")):
                    return _failure("所选本地模型尚未安装完整或缺少运行组件。")
                choose_model_device(selected_local_id, normalized)
                downloadable_roles.append(("所选本地模型", selected_local_id))
            elif selected_engine.startswith("cloud:"):
                provider_id = selected_engine.split(":", 1)[1]
                if provider_id not in provider_ids:
                    return _failure("所选在线服务无效。")
                if not self._credential_store.exists(provider_id):
                    return _failure("请先填写并保存所选在线服务的凭据。")
            else:
                return _failure("识别方式无效。")
            normalized_fallback = str(fallback_model or "").strip().lower()
            if normalized_fallback not in local_ids:
                return _failure("本地备用模型无效。")
            fallback_status = local_catalog[normalized_fallback]
            if not bool(fallback_status.get("available")):
                return _failure("本地备用模型尚未安装完整或缺少运行组件。")
            downloadable_roles.append(("本地备用模型", normalized_fallback))
            if selected_engine.startswith("cloud:"):
                choose_model_device(normalized_fallback, normalized)
            changes = {
                "recognition_engine": selected_engine,
                "fallback_model": normalized_fallback,
                "local_asr_device": normalized,
                "realtime_model": selected_realtime_model,
            }
            # 与异步 delete 共用同一把锁：要么先保存成功，使 delete 看到“正在使用”；
            # 要么 delete 先进入 deleting，保存会被可信状态门禁拒绝。
            with self._model_resource_lock:
                resource_error = self._downloadable_models_ready(downloadable_roles)
                if resource_error:
                    return _failure(resource_error)
                updated = update_config(changes)
            payload = self._recognition_payload(updated)
            self._run_log.info(
                "面板操作完成 | 编号=%s | 阶段=保存识别设置 | 引擎=%s | 设备=%s | 实时模型=%s",
                operation_id, selected_engine, payload["device"],
                payload["realtime_model"],
            )
            return _success(payload, "识别设置已保存并应用。")
        except Exception as exc:
            self._error_log.exception(
                "面板操作失败 | 编号=%s | 阶段=保存识别设置 | 异常类型=%s",
                operation_id, type(exc).__name__,
            )
            return _failure("识别设置保存失败，请查看错误日志。")

    def _downloadable_models_ready(
        self,
        model_roles: list[tuple[str, str]],
    ) -> str | None:
        """确认准备保存的按需模型都已完成下载并持有可信校验凭据。"""
        registered_resource_ids = set(self._model_downloads.resource_ids)
        snapshots: dict[str, dict] = {}
        for label, model_id in model_roles:
            resource_id = str(model_id)
            if resource_id not in registered_resource_ids:
                continue
            if resource_id not in snapshots:
                snapshots[resource_id] = self._model_downloads.status(resource_id)
            snapshot = snapshots[resource_id]
            state = str(snapshot.get("state") or "")
            if state == "completed" and snapshot.get("verified") is True:
                continue
            if state == "deleting":
                return f"{label}正在删除，请等待完成后重新下载并校验。"
            if state in {"queued", "downloading", "verifying", "pausing"}:
                return f"{label}仍在下载、校验或暂停处理中，请等待完整性校验完成。"
            if state == "failed":
                return f"{label}资源当前失败，请先重试下载或校验。"
            return f"{label}尚未下载完成并通过 SHA-256 完整性校验。"
        return None

    def _resource_is_in_use(self, resource_id: str) -> bool:
        config = load_config()
        referenced_model_ids = [
            str(config.get("fallback_model") or ""),
            str(config.get("realtime_model") or ""),
        ]
        engine_id = str(config.get("recognition_engine") or "")
        if engine_id.startswith("local:"):
            referenced_model_ids.append(engine_id.partition(":")[2])
        return resource_id in referenced_model_ids

    @staticmethod
    def _resource_status_from_payload(payload: dict, resource_id: str) -> dict | None:
        for collection in ("realtime_models", "local_models"):
            for model in payload.get(collection) or []:
                if str(model.get("model_id") or "") != resource_id:
                    continue
                snapshot = model.get("resource_status")
                if isinstance(snapshot, dict):
                    return snapshot
        return None

    def manage_local_model_resource(
        self, model_id: str, action: str = "status"
    ) -> dict:
        operation_id = self._operation_id()
        normalized_model = str(model_id or "").strip().lower()
        normalized_action = str(action or "status").strip().lower()
        resource_id = normalized_model
        if resource_id not in self._model_downloads.resource_ids:
            return _failure("模型下载资源尚未注册。")
        if normalized_action not in {"status", "start", "pause", "delete"}:
            return _failure("模型资源操作无效。")
        try:
            snapshot = None
            if normalized_action == "start":
                snapshot = self._model_downloads.start(resource_id)
            elif normalized_action == "pause":
                snapshot = self._model_downloads.pause(resource_id)
            elif normalized_action == "delete":
                with self._model_resource_lock:
                    if self._resource_is_in_use(resource_id):
                        return _failure("该模型正在作为当前模型或在线备用模型，请先切换并保存。")
                    with self._voice_test_lock:
                        if self._active_test_kind == "model":
                            return _failure("语音测试正在进行，请先停止后再删除模型。")
                    snapshot = self._model_downloads.delete(resource_id)
            else:
                snapshot = self._model_downloads.status(resource_id)
            payload = self._recognition_payload()
            current_snapshot = (
                self._resource_status_from_payload(payload, resource_id) or snapshot or {}
            )
            state = str(current_snapshot.get("state") or "")
            if state == "failed":
                reason = str(current_snapshot.get("error") or "模型资源操作失败。")
                self._error_log.error(
                    "面板操作失败 | 编号=%s | 阶段=模型资源管理 | 资源=%s | 动作=%s | 原因=%s",
                    operation_id, resource_id, normalized_action, reason,
                )
                return _failure(f"模型资源操作失败：{reason}", payload)
            if normalized_action == "start":
                message = {
                    "completed": "模型已安装并通过完整性校验。",
                    "verifying": "正在校验模型完整性。",
                    "paused": "模型下载仍处于暂停状态，可再次继续。",
                }.get(state, "模型下载已开始；关闭设置窗口后可在下次继续。")
            elif normalized_action == "pause":
                message = (
                    "模型下载已暂停，已下载内容会保留。"
                    if state == "paused"
                    else "正在暂停模型下载，已下载内容会保留。"
                )
            elif normalized_action == "delete":
                message = (
                    "模型文件和未完成下载已删除。"
                    if state == "not_started"
                    else "正在删除模型文件和未完成下载。"
                )
            else:
                message = ""
            if normalized_action != "status":
                self._run_log.info(
                    "面板操作完成 | 编号=%s | 阶段=模型资源管理 | 资源=%s | 动作=%s",
                    operation_id, resource_id, normalized_action,
                )
            return _success(payload, message)
        except Exception as exc:
            self._error_log.exception(
                "面板操作失败 | 编号=%s | 阶段=模型资源管理 | 资源=%s | 动作=%s | 异常类型=%s",
                operation_id, resource_id, normalized_action, type(exc).__name__,
            )
            return _failure(f"模型资源操作失败：{exc}")

    def test_local_model(
        self, model_id: str, device: str = "auto", action: str = "start"
    ) -> dict:
        operation_id = self._operation_id()
        normalized = str(device or "auto").strip().lower()
        normalized_model = str(model_id or "").strip().lower()
        normalized_action = str(action or "start").strip().lower()
        if normalized_action not in ("start", "stop"):
            return _failure("语音测试操作无效。")
        try:
            catalog = {str(item["model_id"]): item for item in get_local_model_catalog()}
            selected = catalog.get(normalized_model)
            if selected is None:
                return _failure("所选本地模型无效。")
            if not bool(selected.get("available")):
                return _failure("所选本地模型尚未安装完整或缺少运行组件。")
            if normalized_action == "start":
                with self._voice_test_lock:
                    if self._active_test_kind:
                        return _failure("已有语音测试正在进行，请先停止。")
                    self._active_test_kind = "model"
                    self._test_mode_lease.acquire()
                    if self._main_window_exists():
                        test_state = self._test_mode_lease.wait_for_host()
                        if test_state != "ready":
                            self._active_test_kind = ""
                            self._test_mode_lease.release()
                            return _failure(
                                "悬浮球正在录音或处理，请结束后再测试。"
                                if test_state == "blocked"
                                else "等待悬浮球暂停超时，请稍后重试。"
                            )
                    monitor = AudioLevelMonitor()
                    monitor.start(lambda _levels: None)
                    self._voice_test_monitor = monitor
                    self._voice_test_model_id = normalized_model
                payload = self._recognition_payload({
                    **load_config(), "local_asr_device": normalized,
                })
                payload.update({
                    "voice_test_active": True,
                    "voice_test_model_id": normalized_model,
                })
                self._run_log.info(
                    "面板操作开始 | 编号=%s | 阶段=本地模型语音测试录音 | 模型=%s",
                    operation_id, normalized_model,
                )
                return _success(payload, "语音测试正在录音，再次点击可停止并识别。")

            with self._voice_test_lock:
                monitor = self._voice_test_monitor
                active_model = self._voice_test_model_id
                if monitor is None or active_model != normalized_model:
                    return _failure("这个模型当前没有正在进行的语音测试。")
                self._voice_test_monitor = None
                self._voice_test_model_id = ""
            pcm, sample_rate = monitor.stop()
            if len(pcm) < sample_rate // 2:
                self._finish_test_kind("model")
                return _failure("录音时间太短，请重新测试。")
            recognizer = LocalModelRecognizer(normalized_model, normalized)
            started = time.monotonic()
            try:
                text = recognizer.transcribe_pcm16(pcm, sample_rate).strip()
                device_label = recognizer.device_label
            finally:
                recognizer.close()
            elapsed = int((time.monotonic() - started) * 1000)
            if not text:
                self._finish_test_kind("model")
                return _failure("没有识别到文字，请靠近麦克风后重试。")
            payload = self._recognition_payload({
                **load_config(), "local_asr_device": normalized,
            })
            payload.update({
                "elapsed_ms": elapsed,
                "voice_test_active": False,
                "voice_test_model_id": "",
                "voice_test_text": text,
            })
            self._run_log.info(
                "面板操作完成 | 编号=%s | 阶段=本地模型语音测试 | 模型=%s | 设备=%s | 耗时毫秒=%d | 字符数=%d",
                operation_id, normalized_model, device_label, elapsed, len(text),
            )
            self._finish_test_kind("model")
            return _success(payload, f"语音测试完成，当前使用 {device_label}。")
        except Exception as exc:
            self._close_voice_test()
            self._error_log.exception(
                "面板操作失败 | 编号=%s | 阶段=本地模型语音测试 | 异常类型=%s",
                operation_id, type(exc).__name__,
            )
            return _failure(f"语音测试失败：{exc}")

    def _close_voice_test(self) -> None:
        with self._voice_test_lock:
            monitor, self._voice_test_monitor = self._voice_test_monitor, None
            self._voice_test_model_id = ""
        if monitor is not None:
            monitor.close()
        self._finish_test_kind("model")

    def test_standby_control(self, action: str = "status") -> dict:
        """录一段控制词并返回文字匹配置信度；不保存音频或正文。"""
        normalized = str(action or "status").strip().lower()
        if normalized not in {"start", "stop", "status"}:
            return _failure("控制词测试操作无效。")
        if normalized == "stop":
            self._close_control_test()
            return _success(dict(self._control_test_result), "控制词测试已停止。")
        with self._voice_test_lock:
            if normalized == "status":
                return _success(dict(self._control_test_result))
            if self._active_test_kind:
                return _failure("已有语音测试正在进行，请先停止。")
            self._active_test_kind = "control"
        try:
            self._test_mode_lease.acquire()
            if self._main_window_exists():
                test_state = self._test_mode_lease.wait_for_host()
                if test_state != "ready":
                    with self._voice_test_lock:
                        self._active_test_kind = ""
                    self._test_mode_lease.release()
                    return _failure(
                        "悬浮球正在录音或处理，请结束后再测试。"
                        if test_state == "blocked"
                        else "等待悬浮球暂停超时，请稍后重试。"
                    )
            recognizer = RealtimeRecognizer(
                model_id=str(load_config().get("realtime_model", DEFAULT_REALTIME_MODEL))
            )
            recognizer.load()

            def on_update(update) -> None:
                if not bool(getattr(update, "endpoint_reached", False)):
                    return
                text = str(getattr(update, "endpoint_text", "") or "")
                word, confidence = standby_control_match(text)
                with self._voice_test_lock:
                    if self._control_test_monitor is None:
                        return
                    self._control_test_result = {
                        "active": True,
                        "word": word or "未命中",
                        "confidence": confidence,
                    }

            session = recognizer.create_session(
                f"control-test-{self._operation_id()}", on_update,
                max_stable_segments=0,
            )
            with self._voice_test_lock:
                still_active = self._active_test_kind == "control"
                if still_active:
                    self._control_test_session = session
            if not still_active:
                session.cancel()
                return _failure("控制词测试已取消。")
            monitor = AudioLevelMonitor()
            monitor.open_continuous(lambda _levels: None, session.feed_pcm16)
            with self._voice_test_lock:
                still_active = (
                    self._active_test_kind == "control"
                    and self._control_test_session is session
                )
                if still_active:
                    self._control_test_monitor = monitor
                    self._control_test_result = {"active": True, "word": "", "confidence": 0}
            if not still_active:
                monitor.close()
                return _failure("控制词测试已取消。")
            return _success(dict(self._control_test_result), "请单独说“开始”或“结束”。")
        except Exception as exc:
            self._close_control_test()
            self._error_log.error(
                "控制词测试失败 | 异常类型=%s", type(exc).__name__
            )
            return _failure("控制词测试启动失败，请检查麦克风和实时模型。")

    def _close_control_test(self) -> None:
        with self._voice_test_lock:
            monitor, self._control_test_monitor = self._control_test_monitor, None
            session, self._control_test_session = self._control_test_session, None
            self._control_test_result = {"active": False, "word": "", "confidence": 0}
        if monitor is not None:
            monitor.close()
        if session is not None:
            try:
                session.cancel()
            except Exception:
                pass
        self._finish_test_kind("control")

    def _finish_test_kind(self, kind: str) -> None:
        with self._voice_test_lock:
            if self._active_test_kind == kind:
                self._active_test_kind = ""
            idle = not self._active_test_kind
        if idle:
            self._test_mode_lease.release()

    def save_provider_credentials(self, provider_id: str, fields: dict) -> dict:
        operation_id = self._operation_id()
        provider = str(provider_id or "").strip().lower()
        try:
            existing = self._credential_store.load(provider)
            submitted = dict(fields) if isinstance(fields, dict) else {}
            merged = dict(existing)
            for key, value in submitted.items():
                text = str(value or "").strip()
                if text:
                    merged[str(key)] = text
            validated = validate_credentials(provider, merged)
            self._credential_store.save(provider, validated)
            self._run_log.info(
                "面板操作完成 | 编号=%s | 阶段=保存在线识别凭据 | 服务=%s",
                operation_id, provider,
            )
            return _success(self._recognition_payload(), "在线服务凭据已安全保存到本机。")
        except Exception as exc:
            self._error_log.error(
                "面板操作失败 | 编号=%s | 阶段=保存在线识别凭据 | 服务=%s | 异常类型=%s",
                operation_id, provider, type(exc).__name__,
            )
            message = str(exc) if type(exc).__name__.endswith("ConfigurationError") else "凭据保存失败，请查看错误日志。"
            return _failure(message)

    def delete_provider_credentials(self, provider_id: str) -> dict:
        operation_id = self._operation_id()
        provider = str(provider_id or "").strip().lower()
        allowed = {str(item["id"]) for item in get_provider_catalog()}
        if provider not in allowed:
            return _failure("在线服务无效。")
        try:
            self._credential_store.delete(provider)
            current = load_config()
            if str(current.get("recognition_engine", "")).endswith(f":{provider}"):
                update_config({"recognition_engine": "local:faster-whisper-small"})
            self._run_log.info(
                "面板操作完成 | 编号=%s | 阶段=删除在线识别凭据 | 服务=%s",
                operation_id, provider,
            )
            return _success(self._recognition_payload(), "在线服务凭据已从本机删除。")
        except Exception as exc:
            self._error_log.error(
                "面板操作失败 | 编号=%s | 阶段=删除在线识别凭据 | 服务=%s | 异常类型=%s",
                operation_id, provider, type(exc).__name__,
            )
            return _failure("凭据删除失败，请查看错误日志。")

    def save_appearance(
        self,
        color: str,
        opacity: int,
        hotkey: str | None = None,
        standby_enabled: bool | None = None,
        live_transcript_visible: bool | None = None,
        standby_confidence: int | None = None,
        auto_paste_enabled: bool | None = None,
        button_size: int | None = None,
    ) -> dict:
        operation_id = self._operation_id()
        try:
            normalized_color = str(color).strip().upper()
            if not normalized_color.startswith("#"):
                normalized_color = f"#{normalized_color}"
            if not COLOR_PATTERN.fullmatch(normalized_color):
                return _failure("颜色格式不正确，请输入例如 #2563EB。")
            normalized_opacity = max(30, min(100, int(opacity)))
            normalized_size = max(64, min(80, int(
                load_config()["button_size"] if button_size is None else button_size
            )))
            if hotkey is None:
                normalized_hotkey = str(load_config()["global_hotkey"])
            else:
                try:
                    normalized_hotkey = parse_hotkey(hotkey).label
                except ValueError as exc:
                    return _failure(str(exc))
            normalized_standby = (
                bool(load_config()["standby_enabled"])
                if standby_enabled is None
                else bool(standby_enabled)
            )
            normalized_transcript = (
                bool(load_config()["live_transcript_visible"])
                if live_transcript_visible is None
                else bool(live_transcript_visible)
            )
            normalized_confidence = max(70, min(100, int(
                load_config()["standby_confidence"]
                if standby_confidence is None else standby_confidence
            )))
            normalized_auto_paste = (
                bool(load_config()["auto_paste_enabled"])
                if auto_paste_enabled is None
                else bool(auto_paste_enabled)
            )
            self._run_log.info(
                "面板操作开始 | 编号=%s | 阶段=保存按钮设置", operation_id
            )
            update_config({
                "button_color": normalized_color,
                "button_opacity": normalized_opacity,
                "button_size": normalized_size,
                "global_hotkey": normalized_hotkey,
                "standby_enabled": normalized_standby,
                "live_transcript_visible": normalized_transcript,
                "standby_confidence": normalized_confidence,
                "auto_paste_enabled": normalized_auto_paste,
            })
            self._run_log.info(
                "面板操作完成 | 编号=%s | 阶段=保存按钮设置 | 颜色=%s | 透明度=%d%% | 大小=%dpx | 快捷键=%s | 自动输入=%s",
                operation_id, normalized_color, normalized_opacity, normalized_size, normalized_hotkey,
                "开启" if normalized_auto_paste else "关闭",
            )
            return _success({
                "color": normalized_color,
                "opacity": normalized_opacity,
                "size": normalized_size,
                "hotkey": normalized_hotkey,
                "standby_enabled": normalized_standby,
                "live_transcript_visible": normalized_transcript,
                "standby_confidence": normalized_confidence,
                "auto_paste_enabled": normalized_auto_paste,
            }, "设置已保存并应用。")
        except Exception as exc:
            self._error_log.exception(
                "面板操作失败 | 编号=%s | 阶段=保存按钮设置 | 异常类型=%s",
                operation_id, type(exc).__name__,
            )
            return _failure("设置保存失败，请查看错误日志。")

    def test_hotkey(self, hotkey: str) -> dict:
        operation_id = self._operation_id()
        try:
            parsed = parse_hotkey(hotkey)
            current = str(load_config()["global_hotkey"])
            test_id = 0xA120
            if user32.RegisterHotKey(None, test_id, parsed.modifiers, parsed.virtual_key):
                user32.UnregisterHotKey(None, test_id)
                self._run_log.info(
                    "面板操作完成 | 编号=%s | 阶段=测试全局快捷键 | 快捷键=%s | 结果=可用",
                    operation_id, parsed.label,
                )
                return _success(
                    {"hotkey": parsed.label, "available": True, "current": False},
                    "这个快捷键可以使用。",
                )

            error_code = int(kernel32.GetLastError())
            if error_code == 1409:
                is_current = parsed.label == current and self._main_window_exists()
                self._run_log.info(
                    "面板操作完成 | 编号=%s | 阶段=测试全局快捷键 | 快捷键=%s | 结果=%s",
                    operation_id, parsed.label, "当前使用" if is_current else "已占用",
                )
                if is_current:
                    return _success(
                        {"hotkey": parsed.label, "available": True, "current": True},
                        "当前正在使用，可以正常生效。",
                    )
                return _success(
                    {"hotkey": parsed.label, "available": False, "current": False},
                    "这个快捷键已被其他程序占用。",
                )
            raise OSError(error_code, "Windows 无法测试这个快捷键")
        except ValueError as exc:
            return _failure(str(exc))
        except Exception as exc:
            self._error_log.exception(
                "面板操作失败 | 编号=%s | 阶段=测试全局快捷键 | 异常类型=%s",
                operation_id, type(exc).__name__,
            )
            return _failure("快捷键测试失败，请查看错误日志。")

    def get_history(self, query: str = "") -> dict:
        try:
            return _success(self._history_payload(str(query)[:200]))
        except Exception as exc:
            self._error_log.exception(
                "历史记录读取失败 | 异常类型=%s", type(exc).__name__
            )
            return _failure("历史记录读取失败，请查看错误日志。")

    def get_history_signature(self) -> dict:
        try:
            if self._store is None:
                return _success({"available": False, "signature": [0, 0]})
            return _success({
                "available": True,
                "signature": list(self._store.signature()),
            })
        except Exception as exc:
            self._error_log.error(
                "历史记录变化检查失败 | 异常类型=%s", type(exc).__name__
            )
            return _failure("历史记录暂时不可用。")

    def copy_history(self, operation_id: str) -> dict:
        action_id = self._operation_id()
        try:
            if self._store is None:
                return _failure("历史数据库暂时不可用。")
            entry = self._store.get(str(operation_id))
            if entry is None:
                return _failure("这条历史记录已经不存在。")
            hwnd = self._panel_hwnd()
            if not hwnd or not write_clipboard_text(entry.text, hwnd):
                raise RuntimeError("系统剪贴板暂时不可用。")
            self._run_log.info(
                "面板操作完成 | 编号=%s | 阶段=复制历史记录 | 字符数=%d",
                action_id, len(entry.text),
            )
            return _success(message="已复制到系统剪贴板，关闭窗口后仍可粘贴。")
        except Exception as exc:
            self._error_log.exception(
                "面板操作失败 | 编号=%s | 阶段=复制历史记录 | 异常类型=%s",
                action_id, type(exc).__name__,
            )
            return _failure("复制失败，请稍后重试。")

    def copy_all_history(self) -> dict:
        action_id = self._operation_id()
        try:
            if self._store is None:
                return _failure("历史数据库暂时不可用。")
            entries, _signature = self._store.snapshot("")
            if not entries:
                return _failure("还没有可复制的历史文字。")
            text = "\r\n\r\n".join(entry.text for entry in entries)
            hwnd = self._panel_hwnd()
            if not hwnd or not write_clipboard_text(text, hwnd):
                raise RuntimeError("系统剪贴板暂时不可用。")
            self._run_log.info(
                "面板操作完成 | 编号=%s | 阶段=复制全部历史文字 | 记录数=%d | 字符数=%d",
                action_id, len(entries), len(text),
            )
            return _success(
                message=f"已复制全部 {len(entries)} 条历史文字，关闭窗口后仍可粘贴。"
            )
        except Exception as exc:
            self._error_log.exception(
                "面板操作失败 | 编号=%s | 阶段=复制全部历史文字 | 异常类型=%s",
                action_id, type(exc).__name__,
            )
            return _failure("复制全部失败，请稍后重试。")

    def delete_history(self, operation_id: str) -> dict:
        action_id = self._operation_id()
        try:
            if self._store is None:
                return _failure("历史数据库暂时不可用。")
            deleted = self._store.delete(str(operation_id))
            self._run_log.info(
                "面板操作完成 | 编号=%s | 阶段=删除历史记录 | 已删除=%s",
                action_id, "是" if deleted else "否",
            )
            return _success(self._history_payload(), "记录已删除。")
        except Exception as exc:
            self._error_log.exception(
                "面板操作失败 | 编号=%s | 阶段=删除历史记录 | 异常类型=%s",
                action_id, type(exc).__name__,
            )
            return _failure("删除失败，请查看错误日志。")

    def clear_history(self, expected_revision: int) -> dict:
        action_id = self._operation_id()
        try:
            if self._store is None:
                return _failure("历史数据库暂时不可用。")
            revision = int(expected_revision)
            if revision < 0:
                return _failure("历史记录版本无效，请刷新后重试。")
            count = self._store.clear(revision)
            self._run_log.info(
                "面板操作完成 | 编号=%s | 阶段=清空历史记录 | 条数=%d",
                action_id, count,
            )
            return _success(self._history_payload(), "历史记录已清空。")
        except HistoryRevisionMismatch:
            self._run_log.info(
                "面板操作取消 | 编号=%s | 阶段=清空历史记录 | 原因=确认后记录已变化",
                action_id,
            )
            return _failure("确认期间出现了新的历史记录，请检查后重新清空。")
        except Exception as exc:
            self._error_log.exception(
                "面板操作失败 | 编号=%s | 阶段=清空历史记录 | 异常类型=%s",
                action_id, type(exc).__name__,
            )
            return _failure("清空失败，请查看错误日志。")

    def _shutdown(self) -> None:
        """关闭面板相关后台任务；单项清理失败不妨碍后续模型下载有序暂停。"""
        cleanups = (
            ("关闭语音测试", self._close_voice_test),
            ("关闭控制词测试", self._close_control_test),
            (
                "暂停模型下载",
                lambda: self._model_downloads.shutdown(wait_seconds=2.0),
            ),
        )
        for phase, cleanup in cleanups:
            try:
                cleanup()
            except Exception as exc:
                self._error_log.exception(
                    "设置窗口退出清理失败 | 阶段=%s | 异常类型=%s",
                    phase,
                    type(exc).__name__,
                )


def enable_dpi_awareness() -> None:
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass


def main() -> None:
    enable_dpi_awareness()
    os.chdir(PROJECT_DIR)
    run_log, error_log = build_loggers(APP_DATA_DIR / "logs", "面板")
    if webview is None:
        raise RuntimeError(
            "缺少网页界面组件。请在程序目录运行：python -m pip install -r requirements.txt"
        )
    api = WebSettingsApi(run_log, error_log)
    webview.settings["ALLOW_FILE_URLS"] = False
    webview.settings["ALLOW_DOWNLOADS"] = False
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
    webview.settings["REMOTE_DEBUGGING_PORT"] = None
    webview.settings["SHOW_DEFAULT_MENUS"] = False
    webview.create_window(
        PANEL_TITLE,
        url=str(WEB_ENTRY),
        js_api=api,
        width=1000,
        height=680,
        min_size=(840, 560),
        resizable=True,
        background_color="#FFFFFF",
        text_select=True,
        zoomable=False,
    )
    run_log.info("设置与历史记录窗口启动 | 界面=HTML/CSS/JavaScript | 引擎=WebView2")
    try:
        webview.start(gui="edgechromium", debug=False, private_mode=True)
    except Exception as exc:
        error_log.exception(
            "设置窗口启动失败 | 阶段=启动网页界面 | 异常类型=%s",
            type(exc).__name__,
        )
        raise RuntimeError(
            "无法启动设置与历史记录窗口。请安装或修复 Microsoft Edge WebView2 Runtime，"
            "并确认已安装 requirements.txt 中的依赖。"
        ) from exc
    finally:
        api._shutdown()
        run_log.info("设置与历史记录窗口退出")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _run_log, _error_log = build_loggers(APP_DATA_DIR / "logs", "面板")
        _error_log.error("设置窗口启动失败\n%s", traceback.format_exc())
        ctypes.windll.user32.MessageBoxW(
            None,
            "网页设置窗口启动失败，请查看错误日志。",
            PANEL_TITLE,
            0x10,
        )
        raise
