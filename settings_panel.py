from __future__ import annotations

import ctypes
import os
import re
import traceback
import uuid
from ctypes import wintypes
from pathlib import Path

try:
    import webview
except ImportError:
    webview = None

from automation import write_clipboard_text
from cloud_asr import get_provider_catalog, validate_credentials
from config_store import (
    APP_DATA_DIR,
    DEFAULT_CONFIG,
    load_config,
    normalize_recognition_mode,
    update_config,
)
from credential_store import CredentialStore
from history_store import HistoryEntry, HistoryRevisionMismatch, HistoryStore
from global_hotkey import parse_hotkey
from logger import build_loggers
from local_asr import LocalModelRecognizer, choose_provider, get_local_model_catalog
from realtime_asr import get_realtime_model_status


PANEL_TITLE = "悬浮语音按钮 · 设置与历史记录"
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


def _failure(message: str) -> dict:
    return {"ok": False, "data": {}, "message": message}


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
                    "default_color": str(DEFAULT_CONFIG["button_color"]),
                    "default_opacity": int(DEFAULT_CONFIG["button_opacity"]),
                    "hotkey": str(config["global_hotkey"]),
                    "default_hotkey": str(DEFAULT_CONFIG["global_hotkey"]),
                    "standby_enabled": bool(config["standby_enabled"]),
                    "default_standby_enabled": bool(DEFAULT_CONFIG["standby_enabled"]),
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
        try:
            _provider, device_label = choose_provider(preference)
            device_error = ""
        except Exception as exc:
            device_label = "不可用"
            device_error = str(exc)
        local_models = []
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
        return {
            "engine_id": str(current.get("recognition_engine", "local:sensevoice-small-int8")),
            "recognition_mode": normalize_recognition_mode(
                current.get("recognition_mode")
            ),
            "realtime_model": get_realtime_model_status(),
            "fallback_model": str(current.get("fallback_model", "sensevoice-small-int8")),
            "preference": preference,
            "device": device_label,
            "device_error": device_error,
            "local_models": local_models,
            "providers": providers,
        }

    def save_recognition_settings(
        self,
        engine_id: str,
        fallback_model: str,
        device: str,
        recognition_mode: str = "batch",
    ) -> dict:
        operation_id = self._operation_id()
        normalized = str(device or "").strip().lower()
        if normalized not in ("auto", "cpu", "gpu"):
            return _failure("识别设备选项无效。")
        normalized_mode = str(recognition_mode or "").strip().lower()
        if normalized_mode not in ("realtime", "batch"):
            return _failure("文字出现方式无效。")
        if normalized_mode == "realtime" and not bool(
            get_realtime_model_status().get("available")
        ):
            return _failure("实时中文模型尚未安装完整或缺少运行组件。")
        try:
            choose_provider(normalized)
            local_ids = {str(item["model_id"]) for item in get_local_model_catalog()}
            provider_ids = {str(item["id"]) for item in get_provider_catalog()}
            selected_engine = str(engine_id or "").strip().lower()
            if selected_engine.startswith("local:"):
                selected_local_id = selected_engine.split(":", 1)[1]
                if selected_local_id not in local_ids:
                    return _failure("所选本地模型无效。")
                selected_status = next(
                    item for item in get_local_model_catalog()
                    if str(item["model_id"]) == selected_local_id
                )
                if not bool(selected_status.get("available")):
                    return _failure("所选本地模型尚未安装完整或缺少运行组件。")
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
            fallback_status = next(
                item for item in get_local_model_catalog()
                if str(item["model_id"]) == normalized_fallback
            )
            if not bool(fallback_status.get("available")):
                return _failure("本地备用模型尚未安装完整或缺少运行组件。")
            update_config({
                "recognition_engine": selected_engine,
                "fallback_model": normalized_fallback,
                "local_asr_device": normalized,
                "recognition_mode": normalized_mode,
            })
            payload = self._recognition_payload()
            self._run_log.info(
                "面板操作完成 | 编号=%s | 阶段=保存识别设置 | 引擎=%s | 设备=%s | 文字模式=%s",
                operation_id, selected_engine, payload["device"],
                "实时识别" if normalized_mode == "realtime" else "整段识别",
            )
            return _success(payload, "识别设置已保存并应用。")
        except Exception as exc:
            self._error_log.exception(
                "面板操作失败 | 编号=%s | 阶段=保存识别设置 | 异常类型=%s",
                operation_id, type(exc).__name__,
            )
            return _failure("识别设置保存失败，请查看错误日志。")

    def test_local_model(self, model_id: str, device: str = "auto") -> dict:
        operation_id = self._operation_id()
        normalized = str(device or "auto").strip().lower()
        try:
            recognizer = LocalModelRecognizer(str(model_id), normalized)
            started = __import__("time").monotonic()
            recognizer.load()
            elapsed = int((__import__("time").monotonic() - started) * 1000)
            payload = self._recognition_payload({
                **load_config(), "local_asr_device": normalized,
            })
            payload["elapsed_ms"] = elapsed
            self._run_log.info(
                "面板操作完成 | 编号=%s | 阶段=测试本地模型 | 模型=%s | 设备=%s | 耗时毫秒=%d",
                operation_id, str(model_id), recognizer.device_label, elapsed,
            )
            return _success(payload, f"模型测试成功，当前使用 {recognizer.device_label}。")
        except Exception as exc:
            self._error_log.exception(
                "面板操作失败 | 编号=%s | 阶段=测试本地模型 | 异常类型=%s",
                operation_id, type(exc).__name__,
            )
            return _failure(f"模型测试失败：{exc}")

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
                update_config({"recognition_engine": "local:sensevoice-small-int8"})
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
    ) -> dict:
        operation_id = self._operation_id()
        try:
            normalized_color = str(color).strip().upper()
            if not normalized_color.startswith("#"):
                normalized_color = f"#{normalized_color}"
            if not COLOR_PATTERN.fullmatch(normalized_color):
                return _failure("颜色格式不正确，请输入例如 #2563EB。")
            normalized_opacity = max(30, min(100, int(opacity)))
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
            self._run_log.info(
                "面板操作开始 | 编号=%s | 阶段=保存按钮设置", operation_id
            )
            update_config({
                "button_color": normalized_color,
                "button_opacity": normalized_opacity,
                "global_hotkey": normalized_hotkey,
                "standby_enabled": normalized_standby,
            })
            self._run_log.info(
                "面板操作完成 | 编号=%s | 阶段=保存按钮设置 | 颜色=%s | 透明度=%d%% | 快捷键=%s",
                operation_id, normalized_color, normalized_opacity, normalized_hotkey,
            )
            return _success({
                "color": normalized_color,
                "opacity": normalized_opacity,
                "hotkey": normalized_hotkey,
                "standby_enabled": normalized_standby,
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
        background_color="#F5F7FB",
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
