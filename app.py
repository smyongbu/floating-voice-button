from __future__ import annotations

import atexit
import ctypes
import subprocess
import sys
import threading
import time
import uuid
import winsound
from pathlib import Path

from automation import (
    activate_window,
    activate_window_and_wait,
    foreground_window,
    list_windows,
    paste,
    read_clipboard_text,
    write_clipboard_text,
)
from audio_level import AudioLevelMonitor
from config_store import (
    APP_DATA_DIR,
    CONFIG_PATH,
    DEFAULT_CONFIG,
    MODEL_CACHE_DIR,
    load_and_persist_config,
    load_config,
    update_config,
)
from history_store import HistoryStore
from live_transcript import LiveTranscriptWindow
from logger import build_loggers
from overlay import LayeredButtonWindow
from realtime_asr import (
    RealtimeRecognizer,
    RealtimeSession,
    RealtimeUpdate,
    choose_final_recognition,
)
from recognition_router import RecognitionError, RecognitionResult, RecognitionRouter
from standby_listener import StandbyVoiceListener
from test_mode_signal import (
    signal_test_mode_blocked,
    signal_test_mode_ready,
    test_mode_is_active,
)
from version import APP_VERSION


APP_NAME = "悬浮语音按钮"
PANEL_TITLE = "语点 · 设置与历史记录"
PROJECT_DIR = Path(__file__).resolve().parent
ASSET_DIR = PROJECT_DIR / "assets"
DATA_DIR = APP_DATA_DIR
ERROR_ALREADY_EXISTS = 183
_INSTANCE_MUTEX = None


def acquire_single_instance() -> bool:
    """确保同一 Windows 会话只存在一个悬浮按钮实例。"""
    global _INSTANCE_MUTEX
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, "Local\\FloatingVoiceButton.Main")
    if not handle:
        raise ctypes.WinError()
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _INSTANCE_MUTEX = handle
    return True


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass


class VoiceButtonApp:
    def __init__(self) -> None:
        self.config = load_and_persist_config()
        self.run_log, self.error_log = build_loggers(DATA_DIR / "logs")
        self.recording = False
        self.busy = False
        self.origin_hwnd = 0
        self.operation_id = ""
        self.standby_operation = False
        self.standby_end_cue_pending = False
        self.standby_stop_at_ms: int | None = None
        self.closed = False
        self.lock = threading.Lock()
        self.pipeline_lock = threading.RLock()
        self.side_effect_lock = threading.RLock()
        self.stop_event = threading.Event()
        self.panel_process: subprocess.Popen | None = None
        self.audio_monitor = AudioLevelMonitor()
        self.recognition_router = RecognitionRouter(self.config)
        self.realtime_recognizer = RealtimeRecognizer(
            model_id=str(self.config.get("realtime_model", "")),
            rule1_min_trailing_silence=1.2,
            rule2_min_trailing_silence=0.8,
        )
        self.realtime_session: RealtimeSession | None = None
        self.active_router: RecognitionRouter | None = None
        self.realtime_revision = 0
        self.realtime_overload_logged = False
        self._last_standby_ignored_log = 0.0
        self._standby_level_stream_ready = False
        self._standby_error_notified = False
        self._standby_pipeline_starting = False
        self._test_mode_active = test_mode_is_active()
        try:
            self.history_store: HistoryStore | None = HistoryStore()
        except Exception as history_exc:
            self.history_store = None
            self.error_log.error(
                "历史记录初始化失败 | 异常类型=%s", type(history_exc).__name__
            )
        size = max(64, min(80, int(self.config["button_size"])))
        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)
        x = self.config.get("position_x")
        y = self.config.get("position_y")
        x = screen_w - size - 28 if x is None else int(x)
        y = screen_h // 2 - size // 2 if y is None else int(y)
        images = {
            name: ASSET_DIR / f"button_{name}.png"
            for name in ("idle", "hover", "recording", "busy")
        }
        images["background"] = ASSET_DIR / "button_background_01.png"
        self.window = LayeredButtonWindow(
            APP_NAME, size, x, y, images,
            self.toggle,
            self._save_position,
            self._open_panel,
            self._open_logs,
            self.cleanup,
            self._window_error,
            hotkey=str(self.config["global_hotkey"]),
            button_color=str(self.config["button_color"]),
            button_opacity=int(self.config["button_opacity"]),
            app_icon=ASSET_DIR / "app.ico",
        )
        self.transcript_window = LiveTranscriptWindow(
            self.window.hwnd, size, self._window_error
        )
        self.standby_listener = StandbyVoiceListener(
            self.realtime_recognizer,
            self._on_standby_word,
            self._on_standby_ready,
            self._on_standby_update,
            self._on_standby_ignored,
            self._on_standby_error,
            confidence_threshold=int(self.config.get("standby_confidence", 80)),
        )
        self._config_stamp = self._read_config_stamp()
        threading.Thread(target=self._watch_config, name="配置监测", daemon=True).start()
        self.run_log.info("应用启动 | 版本=%s | 界面=逐像素Alpha分层窗口", APP_VERSION)
        self.run_log.info(
            "模型存储已初始化 | 运行模式=%s | 缓存命名空间=%s",
            "正式版" if getattr(sys, "frozen", False) else "源码开发版",
            MODEL_CACHE_DIR.name,
        )
        threading.Thread(
            target=self._preload_local_model,
            args=(self.recognition_router,),
            daemon=True,
        ).start()
        threading.Thread(target=self._preload_realtime_model, daemon=True).start()
        if self.window.hotkey_registered:
            self.run_log.info("全局快捷键已注册 | 快捷键=%s", self.window.hotkey_label)
        else:
            self.error_log.error(
                "全局快捷键注册失败 | 阶段=应用启动 | 快捷键=%s",
                self.config["global_hotkey"],
            )
            self._warning(
                f"全局快捷键 {self.config['global_hotkey']} 注册失败，可能已被其他程序占用。"
            )
        if self._test_mode_active:
            self.window.set_state("disabled")
        elif bool(self.config.get("standby_enabled")):
            self._set_standby_enabled(True)

    def _preload_local_model(self, router: RecognitionRouter | None = None) -> None:
        operation_id = uuid.uuid4().hex[:8]
        try:
            started = time.monotonic()
            target_router = router or self.recognition_router
            engine_id, device_label = target_router.preload()
            if target_router.closed:
                return
            self.run_log.info(
                "本地模型已就绪 | 编号=%s | 引擎=%s | 设备=%s | 耗时毫秒=%d",
                operation_id, engine_id, device_label,
                int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:
            self.error_log.error(
                "本地模型加载失败 | 编号=%s | 阶段=预加载 | 异常类型=%s",
                operation_id, type(exc).__name__,
            )

    def _preload_realtime_model(self) -> None:
        operation_id = uuid.uuid4().hex[:8]
        try:
            started = time.monotonic()
            self.realtime_recognizer.load()
            self.run_log.info(
                "实时模型已就绪 | 编号=%s | 模型=%s | 设备=CPU | 耗时毫秒=%d",
                operation_id, self.realtime_recognizer.model_name,
                int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:
            self.error_log.error(
                "实时模型加载失败 | 编号=%s | 阶段=预加载 | 异常类型=%s",
                operation_id, type(exc).__name__,
            )

    def _on_standby_ready(self, model_name: str | None = None) -> None:
        self.run_log.info(
            "待命模式已启动 | 监听模型=%s | 设备=CPU | 控制词=开始/结束",
            model_name or self.realtime_recognizer.model_name,
        )
        if (
            not self.closed
            and not self._test_mode_active
            and bool(self.config.get("standby_enabled", False))
            and not self.busy
            and not self.recording
        ):
            self.window.set_waveform([0.0] * 7)
            self.window.set_state("standby")

    def _on_standby_level(self, levels: list[float]) -> None:
        if (
            bool(self.config.get("standby_enabled", False))
            and not self._test_mode_active
            and not self.closed
            and not self.busy
            and not self.recording
        ):
            if not self._standby_level_stream_ready:
                self._standby_level_stream_ready = True
                self.run_log.info("待命麦克风电平已接入 | 状态=正在监听")
            self.window.set_waveform(levels)

    def _on_standby_update(self, update: RealtimeUpdate) -> None:
        """语音唤起录音时，复用同一个流式会话显示临时文字。"""
        if self.recording and self.standby_operation:
            self._on_realtime_update(update)

    def _on_standby_ignored(self, character_count: int = 0) -> None:
        now = time.monotonic()
        if now - self._last_standby_ignored_log < 15.0:
            return
        self._last_standby_ignored_log = now
        self.run_log.info(
            "待命语音未命中控制词 | 阶段=本地控制词监听 | 字符数=%d",
            max(0, int(character_count)),
        )

    def _on_standby_error(self, message: str) -> None:
        operation_id = uuid.uuid4().hex[:8]
        self.error_log.error(
            "待命模式异常 | 编号=%s | 阶段=本地实时模型控制词监听 | 原因=%s",
            operation_id, str(message).replace("\r", " ").replace("\n", " ")[:300],
        )
        if self.closed:
            return
        if self._standby_pipeline_starting or (self.busy and not self.recording):
            return
        if self.recording and self.standby_operation:
            if not self._standby_error_notified:
                self._standby_error_notified = True
                self._warning(
                    "结束语音监听暂时不可用，录音仍在继续。\n"
                    "请点击悬浮按钮或使用全局快捷键停止录音。"
                )
            return
        if not self.busy:
            if self.standby_listener.state != "failed":
                self.standby_listener.stop()
            self.audio_monitor.close()
            self.window.set_state("idle")
        self._warning("待命模式已停止，请检查麦克风、本地实时模型和错误日志。")

    def _start_standby_pipeline(self) -> bool:
        """启动单一麦克风输入和本地控制词解码，不保存待命音频。"""
        with self.pipeline_lock:
            if self.closed or self._test_mode_active:
                self.standby_listener.stop()
                self.audio_monitor.close()
                if not self.closed:
                    self.window.set_state("disabled")
                return False
            if (
                self.standby_listener.state == "waiting"
                and self.standby_listener.running
                and self.audio_monitor.is_open
                and bool(self.audio_monitor.continuous)
            ):
                self.audio_monitor.set_waiting_level_callback(self._on_standby_level)
                self.window.set_state("standby")
                return True
            self._standby_level_stream_ready = False
            self._standby_error_notified = False
            self._standby_pipeline_starting = True
            try:
                if not self.standby_listener.resume_waiting():
                    raise RuntimeError("本地待命模型没有成功启动。")
                if not self.audio_monitor.is_open:
                    self.audio_monitor.open_continuous(
                        self._on_standby_level,
                        self.standby_listener.feed_pcm16,
                    )
                else:
                    self.audio_monitor.set_waiting_level_callback(self._on_standby_level)
                if self.closed:
                    self.standby_listener.stop()
                    self.audio_monitor.close()
                    return False
                self.window.set_waveform([0.0] * 7)
                self.window.set_state("standby")
                return True
            except Exception as exc:
                self.standby_listener.stop()
                self.audio_monitor.close()
                self.error_log.error(
                    "待命模式启动失败 | 阶段=本地实时模型控制词监听 | 异常类型=%s",
                    type(exc).__name__,
                )
                if not self.closed:
                    self.window.set_state("idle")
                return False
            finally:
                self._standby_pipeline_starting = False

    def _restore_resting_pipeline(self) -> None:
        """根据最新设置恢复待命监听；处理中修改的设置在此生效。"""
        with self.pipeline_lock:
            if self.closed:
                self.standby_listener.stop()
                self.audio_monitor.close()
                return
            if self._test_mode_active:
                self.standby_listener.stop()
                self.audio_monitor.close()
                self.window.set_waveform([0.0] * 7)
                self.window.set_state("disabled")
                return
            if bool(self.config.get("standby_enabled", False)):
                if not self._start_standby_pipeline() and not self.closed:
                    self._warning("待命模式启动失败，请检查麦克风、本地实时模型和错误日志。")
            else:
                self.standby_listener.stop()
                self.audio_monitor.close()
                self.window.set_state("idle")

    def _set_standby_enabled(self, enabled: bool) -> None:
        with self.pipeline_lock:
            if self.closed:
                self.standby_listener.stop()
                self.audio_monitor.close()
                return
            if self.busy or self.recording or self._test_mode_active:
                self.run_log.info(
                    "待命设置将在当前操作结束后生效 | 状态=%s",
                    "开启" if enabled else "关闭",
                )
                return
            if enabled:
                if self._start_standby_pipeline():
                    self.run_log.info("待命模式正在启动 | 控制词=开始/结束")
                else:
                    self._warning("待命模式启动失败，请检查麦克风、本地实时模型和错误日志。")
            else:
                self.standby_listener.stop()
                self.audio_monitor.close()
                self.window.set_state("idle")
                self.run_log.info("待命模式已停止")

    def _resting_button_state(self) -> str:
        if self._test_mode_active:
            return "disabled"
        listener = getattr(self, "standby_listener", None)
        config = getattr(self, "config", {})
        if bool(config.get("standby_enabled", False)) and bool(
            listener is not None and listener.running
        ):
            return "standby"
        return "idle"

    def _on_standby_word(self, word: str, segment_start_ms: int = 0) -> None:
        normalized = str(word).strip()
        if normalized in ("开始", "開始"):
            with self.lock:
                should_start = (
                    not self.closed
                    and not self._test_mode_active
                    and bool(self.config.get("standby_enabled", False))
                    and not self.busy
                    and not self.recording
                )
                if should_start:
                    self.busy = True
                    self.operation_id = uuid.uuid4().hex[:8]
                    self.standby_operation = True
                    self.standby_stop_at_ms = None
            if should_start:
                try:
                    self.run_log.info(
                        "待命控制词已识别 | 阶段=开始 | 引擎=%s",
                        self.realtime_recognizer.model_name,
                    )
                    self._play_recording_cue("开始")
                    with self.lock:
                        cancelled = (
                            self.closed
                            or self._test_mode_active
                            or not bool(self.config.get("standby_enabled", False))
                        )
                        if cancelled:
                            self.busy = False
                            self.standby_operation = False
                    if cancelled:
                        if not self.closed:
                            with self.pipeline_lock:
                                self.audio_monitor.close()
                                self.window.set_state("idle")
                        return
                    self.window.set_state("busy")
                    threading.Thread(target=self._start, daemon=True).start()
                except Exception:
                    with self.lock:
                        self.busy = False
                        self.standby_operation = False
                    raise
        elif normalized in ("结束", "結束"):
            with self.lock:
                should_finish = (
                    not self.closed
                    and not self.busy
                    and self.recording
                    and self.standby_operation
                )
                if should_finish:
                    self.busy = True
                    self.standby_end_cue_pending = True
                    self.standby_stop_at_ms = max(0, int(segment_start_ms))
            if should_finish:
                try:
                    self.run_log.info(
                        "待命控制词已识别 | 阶段=结束 | 引擎=%s | 正文截止毫秒=%d",
                        self.realtime_recognizer.model_name, self.standby_stop_at_ms,
                    )
                    self.window.set_state("busy")
                    threading.Thread(target=self._finish, daemon=True).start()
                except Exception:
                    with self.lock:
                        self.busy = False
                        self.standby_end_cue_pending = False
                    raise

    def _play_recording_cue(self, stage: str) -> None:
        """播放录音启停提示音；失败不能阻断录音流程。"""
        frequency, duration = (880, 110) if stage == "开始" else (660, 90)
        try:
            winsound.Beep(frequency, duration)
            self.run_log.info("录音提示音已播放 | 阶段=%s", stage)
        except (OSError, RuntimeError) as exc:
            self.error_log.warning(
                "录音提示音播放失败 | 阶段=%s | 异常类型=%s",
                stage, type(exc).__name__,
            )

    def _window_error(self, exc: Exception) -> None:
        operation_id = uuid.uuid4().hex[:8]
        reason = str(exc).replace("\r", " ").replace("\n", " ")[:300]
        self.error_log.error(
            "窗口异常 | 编号=%s | 阶段=分层窗口 | 异常类型=%s | 原因=%s",
            operation_id,
            type(exc).__name__,
            reason or "未提供详细原因",
        )

    def _save_position(self, x: int, y: int) -> None:
        operation_id = uuid.uuid4().hex[:8]
        self.config = update_config({"position_x": x, "position_y": y})
        self.run_log.info(
            "窗口移动完成 | 编号=%s | 位置=(%d,%d)", operation_id, x, y
        )
        self.transcript_window.follow_anchor()

    def _sync_test_mode(self) -> None:
        """同步设置面板的跨进程测试占用状态。"""
        active = test_mode_is_active()
        with self.pipeline_lock:
            if self.closed:
                return
            if active:
                if self._test_mode_active:
                    signal_test_mode_ready()
                    return
                if self.busy or self.recording:
                    signal_test_mode_blocked()
                    return
                self._test_mode_active = True
                self.standby_listener.stop()
                self.audio_monitor.close()
                self.window.set_waveform([0.0] * 7)
                self.window.set_state("disabled")
                if test_mode_is_active():
                    signal_test_mode_ready()
                    self.run_log.info("悬浮录音已暂停 | 原因=设置面板语音测试")
                else:
                    self._test_mode_active = False
                    self._restore_resting_pipeline()
                return
            if self._test_mode_active:
                self._test_mode_active = False
                self.run_log.info("悬浮录音已恢复 | 原因=设置面板语音测试结束")
                self._restore_resting_pipeline()

    @staticmethod
    def _read_config_stamp() -> int:
        try:
            return CONFIG_PATH.stat().st_mtime_ns
        except OSError:
            return 0

    def _watch_config(self) -> None:
        while not self.stop_event.wait(0.4):
            self._sync_test_mode()
            stamp = self._read_config_stamp()
            if not stamp or stamp == self._config_stamp:
                continue
            self._config_stamp = stamp
            try:
                updated = load_config()
                if self.closed:
                    return
                previous = self.config
                old_appearance = (
                    previous.get("button_color"), previous.get("button_opacity")
                )
                self.config = updated
                new_appearance = (
                    updated.get("button_color"), updated.get("button_opacity")
                )
                if new_appearance != old_appearance:
                    self.window.set_appearance(str(new_appearance[0]), int(new_appearance[1]))
                    self.run_log.info(
                        "外观设置已应用 | 颜色=%s | 透明度=%d%%",
                        new_appearance[0], new_appearance[1],
                    )
                old_size = int(previous.get("button_size", DEFAULT_CONFIG["button_size"]))
                new_size = int(updated.get("button_size", DEFAULT_CONFIG["button_size"]))
                if new_size != old_size:
                    applied_size = self.window.set_size(new_size)
                    self.transcript_window.button_size = applied_size
                    self.run_log.info("按钮大小已应用 | 大小=%dpx", applied_size)
                old_hotkey = str(previous.get("global_hotkey", DEFAULT_CONFIG["global_hotkey"]))
                new_hotkey = str(updated.get("global_hotkey", DEFAULT_CONFIG["global_hotkey"]))
                if new_hotkey != old_hotkey:
                    operation_id = uuid.uuid4().hex[:8]
                    registered, reason = self.window.set_hotkey(new_hotkey)
                    if registered:
                        self.run_log.info(
                            "设置应用完成 | 编号=%s | 阶段=更新全局快捷键 | 快捷键=%s",
                            operation_id, self.window.hotkey_label,
                        )
                    else:
                        self.error_log.error(
                            "设置应用失败 | 编号=%s | 阶段=更新全局快捷键 | 快捷键=%s | 原因=%s",
                            operation_id, new_hotkey, reason,
                        )
                        self.config = update_config({"global_hotkey": old_hotkey})
                        self._config_stamp = self._read_config_stamp()
                        self._warning(f"{reason}\n已继续使用原快捷键 {old_hotkey}。")
                old_standby = bool(previous.get("standby_enabled", False))
                new_standby = bool(updated.get("standby_enabled", False))
                old_realtime_model = str(previous.get("realtime_model", ""))
                new_realtime_model = str(updated.get("realtime_model", ""))
                if new_realtime_model != old_realtime_model:
                    restart_standby = bool(
                        new_standby
                        and self.standby_listener.running
                        and not self.busy
                        and not self.recording
                    )
                    if restart_standby:
                        self.standby_listener.pause()
                    self.realtime_recognizer.select_model(new_realtime_model)
                    self.run_log.info(
                        "实时模型设置已应用 | 模型=%s",
                        self.realtime_recognizer.model_name,
                    )
                    if restart_standby:
                        self._start_standby_pipeline()
                    elif not self.busy and not self.recording:
                        threading.Thread(
                            target=self._preload_realtime_model, daemon=True
                        ).start()
                self.standby_listener.confidence_threshold = int(
                    updated.get("standby_confidence", 80)
                )
                if new_standby != old_standby:
                    self._set_standby_enabled(new_standby)
                if (
                    bool(previous.get("live_transcript_visible", True))
                    and not bool(updated.get("live_transcript_visible", True))
                ):
                    self.transcript_window.hide()
                old_recognition = (
                    previous.get("recognition_engine"),
                    previous.get("fallback_model"),
                    previous.get("local_asr_device"),
                )
                new_recognition = (
                    updated.get("recognition_engine"),
                    updated.get("fallback_model"),
                    updated.get("local_asr_device"),
                )
                if new_recognition != old_recognition:
                    new_router = RecognitionRouter(updated)
                    with self.lock:
                        previous_router = self.recognition_router
                        self.recognition_router = new_router
                        previous_router_in_use = previous_router is self.active_router
                    if not previous_router_in_use:
                        previous_router.close()
                    threading.Thread(
                        target=self._preload_local_model,
                        args=(new_router,),
                        daemon=True,
                    ).start()
            except Exception as exc:
                self.error_log.error(
                    "配置重新加载失败 | 异常类型=%s", type(exc).__name__
                )

    def _open_panel(self) -> None:
        for window in list_windows():
            if window.title == PANEL_TITLE:
                activate_window(window.hwnd)
                return
        if self.panel_process is not None and self.panel_process.poll() is None:
            return
        try:
            if getattr(sys, "frozen", False):
                command = [sys.executable, "--settings-panel"]
                working_directory = Path(sys.executable).resolve().parent
            else:
                command = [sys.executable, str(PROJECT_DIR / "settings_panel.py")]
                working_directory = PROJECT_DIR
            self.panel_process = subprocess.Popen(
                command,
                cwd=str(working_directory),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.run_log.info("设置窗口已打开")
            threading.Thread(
                target=self._check_panel_startup,
                args=(self.panel_process,),
                name="设置窗口启动检查",
                daemon=True,
            ).start()
        except Exception as exc:
            self.error_log.error(
                "设置窗口打开失败 | 异常类型=%s", type(exc).__name__
            )
            self._warning("无法打开设置与历史记录窗口，请查看错误日志。")

    def _check_panel_startup(self, process: subprocess.Popen) -> None:
        """捕获另一台电脑缺少网页组件等导致的静默启动失败。"""
        try:
            return_code = process.wait(timeout=2.5)
        except subprocess.TimeoutExpired:
            return
        if self.closed or process is not self.panel_process:
            return
        operation_id = uuid.uuid4().hex[:8]
        self.error_log.error(
            "设置窗口启动失败 | 编号=%s | 阶段=子进程启动 | 退出代码=%d",
            operation_id, return_code,
        )
        self._warning(
            "设置与历史记录窗口没有成功启动。\n"
            "请安装 Microsoft Edge WebView2 Runtime，并在程序目录运行：\n"
            "python -m pip install -r requirements.txt\n\n"
            "详细原因已写入“面板-错误.log”。"
        )

    def _open_logs(self) -> None:
        log_dir = DATA_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer.exe", str(log_dir)])

    def _warning(self, message: str) -> None:
        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x30)

    def toggle(self) -> None:
        self._sync_test_mode()
        with self.lock:
            if self.closed or self.busy or (self._test_mode_active and not self.recording):
                return
            self.busy = True
            if self.recording:
                action = self._finish
            else:
                self.operation_id = uuid.uuid4().hex[:8]
                if not self.standby_operation:
                    self.standby_operation = False
                action = self._start
        self.window.set_state("busy")
        threading.Thread(target=action, daemon=True).start()

    def _start(self) -> None:
        started = time.monotonic()
        op = self.operation_id
        voice_started = bool(self.standby_operation)
        with self.lock:
            if self.closed:
                self.busy = False
                return
        try:
            self.origin_hwnd = foreground_window()
            if (
                not voice_started
                and (not self.origin_hwnd or self.origin_hwnd == self.window.hwnd)
            ):
                raise RuntimeError("尚未识别原软件，请先切回原软件停留片刻。")
            with self.lock:
                self.active_router = getattr(self, "recognition_router", None)
            self.realtime_session = None
            self.realtime_revision = 0
            self.realtime_overload_logged = False
            pcm_callback = None
            if bool(self.config.get("live_transcript_visible", True)):
                self.transcript_window.show("正在聆听…")
            with self.pipeline_lock:
                if self.closed:
                    return
                if voice_started:
                    if not self.audio_monitor.is_open:
                        raise RuntimeError("待命麦克风已经断开，请重新开启待命模式。")
                    if not self.standby_listener.prepare_recording(op):
                        raise RuntimeError("结束语音监听没有成功启动，请重新尝试。")
                else:
                    if not self.standby_listener.pause():
                        raise RuntimeError("旧的实时识别会话没有安全退出，请重新尝试。")
                    try:
                        self.realtime_session = self.realtime_recognizer.create_session(
                            op, self._on_realtime_update
                        )
                        pcm_callback = self._feed_realtime_audio
                    except Exception as realtime_exc:
                        self.error_log.error(
                            "实时预览启动失败 | 编号=%s | 阶段=开始录音 | 异常类型=%s",
                            op, type(realtime_exc).__name__,
                        )
                        if bool(self.config.get("live_transcript_visible", True)):
                            self.transcript_window.update("实时文字暂时不可用，仍会在停止后识别。")
                if not voice_started:
                    self._play_recording_cue("开始")
                if self.audio_monitor.is_open:
                    self.audio_monitor.begin_capture(
                        self.window.set_waveform,
                        pcm_callback,
                        self.standby_listener.activate_recording if voice_started else None,
                    )
                elif pcm_callback is None:
                    self.audio_monitor.start(self.window.set_waveform)
                else:
                    self.audio_monitor.start(self.window.set_waveform, pcm_callback)
            self.run_log.info(
                "操作开始 | 编号=%s | 阶段=本地录音 | 实时模型=%s",
                op, self.realtime_recognizer.model_name,
            )
            with self.lock:
                if self.closed:
                    return
                self.recording = True
                self.window.set_state("recording")
            self.run_log.info("操作进度 | 编号=%s | 阶段=麦克风录音已启动", op)
            elapsed = int((time.monotonic() - started) * 1000)
            self.run_log.info("操作完成 | 编号=%s | 阶段=开始语音 | 耗时毫秒=%d", op, elapsed)
        except Exception as exc:
            with self.pipeline_lock:
                if bool(getattr(self.audio_monitor, "continuous", False)):
                    self.audio_monitor.finish_capture()
                else:
                    self.audio_monitor.stop()
                if getattr(self, "realtime_session", None) is not None:
                    self.realtime_session.cancel()
                    self.realtime_session = None
            self.standby_listener.pause()
            transcript_window = getattr(self, "transcript_window", None)
            if transcript_window is not None and not self.closed:
                transcript_window.hide()
            self.standby_operation = False
            self.standby_stop_at_ms = None
            if not self.closed:
                self.error_log.error(
                    "操作失败 | 编号=%s | 阶段=开始语音 | 异常类型=%s",
                    op, type(exc).__name__,
                )
                self._warning(str(exc))
        finally:
            self.busy = False
            if not self.recording:
                self._restore_resting_pipeline()

    def _feed_realtime_audio(self, pcm: bytes, sample_rate: int) -> bool:
        session = self.realtime_session
        if session is None:
            return False
        accepted = session.feed_pcm16(pcm, sample_rate)
        if not accepted and session.overloaded and not self.realtime_overload_logged:
            self.realtime_overload_logged = True
            self.error_log.warning(
                "实时预览已降级 | 编号=%s | 阶段=音频队列积压 | 最终整段识别继续",
                self.operation_id,
            )
            if bool(self.config.get("live_transcript_visible", True)):
                self.transcript_window.update("实时预览速度不足，停止后仍会完成识别。")
        return accepted

    def _on_realtime_update(self, update: RealtimeUpdate) -> None:
        if update.operation_id != self.operation_id or update.revision <= self.realtime_revision:
            return
        self.realtime_revision = update.revision
        if (
            bool(self.config.get("live_transcript_visible", True))
            and not update.is_final
        ):
            self.transcript_window.update(update.text or "正在聆听…")

    def _finish(self) -> None:
        started = time.monotonic()
        op = self.operation_id
        live_result = None
        with self.lock:
            if self.closed:
                self.busy = False
                return
        try:
            with self.pipeline_lock:
                if self.closed:
                    return
                if bool(getattr(self.audio_monitor, "continuous", False)):
                    pcm, sample_rate = self.audio_monitor.finish_capture()
                else:
                    pcm, sample_rate = self.audio_monitor.stop()
                if self.standby_operation:
                    self.standby_listener.pause()
            if self.standby_operation:
                stop_at_ms = self.standby_stop_at_ms
                if stop_at_ms is not None:
                    original_bytes = len(pcm)
                    stop_byte = max(0, int(stop_at_ms * sample_rate / 1000) * 2)
                    pcm = pcm[: min(original_bytes, stop_byte)]
                    self.run_log.info(
                        "操作进度 | 编号=%s | 阶段=裁去结束控制词 | 正文毫秒=%d | 裁去字节=%d",
                        op, stop_at_ms, max(0, original_bytes - len(pcm)),
                    )
            self.standby_end_cue_pending = False
            self._play_recording_cue("结束")
            if self.closed:
                return
            self.window.set_state("busy")
            if bool(self.config.get("live_transcript_visible", True)):
                self.transcript_window.update("正在进行最终识别…")
            session = getattr(self, "realtime_session", None)
            self.realtime_session = None
            if session is not None:
                try:
                    live_result = session.finish(timeout=5.0)
                    self.run_log.info(
                        "操作进度 | 编号=%s | 阶段=实时预览结束 | 字符数=%d | 音频毫秒=%d",
                        op, len(live_result.text), live_result.audio_ms,
                    )
                except Exception as realtime_exc:
                    self.error_log.warning(
                        "实时预览结束异常 | 编号=%s | 阶段=停止录音 | 异常类型=%s | 最终整段识别继续",
                        op, type(realtime_exc).__name__,
                    )
            if self.closed or self.stop_event.is_set():
                return
            router = getattr(self, "active_router", None) or getattr(
                self, "recognition_router", None
            )
            requested_engine = getattr(router, "engine_id", "local:legacy")
            self.run_log.info(
                "操作开始 | 编号=%s | 阶段=语音识别 | 请求引擎=%s | 音频毫秒=%d",
                op, requested_engine,
                int(len(pcm) / 2 / max(1, sample_rate) * 1000),
            )
            if len(pcm) < sample_rate // 2:
                raise RuntimeError("录音时间太短，请重新录制。")
            result = self._recognize_pcm(pcm, sample_rate)
            if self.closed or self.stop_event.is_set():
                return
            text = result.text
            if live_result is not None and live_result.text:
                selected = choose_final_recognition(live_result.text, text)
                self.run_log.info(
                    "操作进度 | 编号=%s | 阶段=实时与最终结果择优 | 来源=%s | 实时字符数=%d | 最终字符数=%d",
                    op, selected.source, len(live_result.text), len(text),
                )
                text = selected.text
            if result.fallback_used:
                self.run_log.info(
                    "操作进度 | 编号=%s | 阶段=在线识别瞬时失败并已回退 | 请求引擎=%s | 实际引擎=%s",
                    op, result.requested_engine, result.actual_engine,
                )
            else:
                self.run_log.info(
                    "操作进度 | 编号=%s | 阶段=语音识别完成 | 实际引擎=%s",
                    op, result.actual_engine,
                )
            if not text:
                raise RuntimeError("没有识别到有效语音，请重新录制。")
            self.run_log.info(
                "操作进度 | 编号=%s | 阶段=保留模型识别原文 | 字符数=%d",
                op, len(text),
            )
            if not str(text).strip():
                raise RuntimeError("没有识别到有效语音，请重新录制。")
            if self.history_store is not None:
                with self.side_effect_lock:
                    if self.closed or self.stop_event.is_set():
                        return
                    try:
                        self.history_store.add(op, text)
                        self.run_log.info(
                            "操作进度 | 编号=%s | 阶段=历史记录已保存 | 字符数=%d",
                            op, len(text),
                        )
                    except Exception as history_exc:
                        self.error_log.error(
                            "历史记录保存失败 | 编号=%s | 异常类型=%s",
                            op, type(history_exc).__name__,
                        )
            if self.standby_operation:
                elapsed = int((time.monotonic() - started) * 1000)
                self.run_log.info(
                    "操作完成 | 编号=%s | 阶段=待命识别并保存历史 | 字符数=%d | 耗时毫秒=%d",
                    op, len(text), elapsed,
                )
                return
            if self.closed or self.stop_event.is_set():
                return
            if not bool(self.config.get("auto_paste_enabled", True)):
                with self.side_effect_lock:
                    if self.closed or self.stop_event.is_set():
                        return
                    self._ensure_clipboard_text(text, op, "自动输入已关闭")
                elapsed = int((time.monotonic() - started) * 1000)
                self.run_log.info(
                    "操作完成 | 编号=%s | 阶段=识别完成并按设置跳过自动输入 | 字符数=%d | 耗时毫秒=%d",
                    op, len(text), elapsed,
                )
                return
            with self.side_effect_lock:
                if self.closed or self.stop_event.is_set():
                    return
                activated = activate_window_and_wait(self.origin_hwnd)
                if self.closed or self.stop_event.is_set():
                    return
                if not activated:
                    raise RuntimeError("无法切回原软件，文字已保留在剪贴板中。")
            time.sleep(max(0, int(self.config["paste_wait_ms"])) / 1000)
            with self.side_effect_lock:
                if self.closed or self.stop_event.is_set():
                    return
                activated = activate_window_and_wait(self.origin_hwnd)
                if self.closed or self.stop_event.is_set():
                    return
                if not activated:
                    raise RuntimeError("粘贴前原软件失去焦点，文字已保留在剪贴板中。")
                self._ensure_clipboard_text(text, op, "粘贴前")
                if self.closed or self.stop_event.is_set():
                    return
                if foreground_window() != self.origin_hwnd:
                    raise RuntimeError("粘贴前原软件失去焦点，文字已保留在剪贴板中。")
                if self.closed or self.stop_event.is_set():
                    return
                paste()
            elapsed = int((time.monotonic() - started) * 1000)
            self.run_log.info("操作完成 | 编号=%s | 阶段=结束并粘贴 | 耗时毫秒=%d", op, elapsed)
        except Exception as exc:
            if self.closed:
                return
            if isinstance(exc, RecognitionError):
                self.error_log.error(
                    "操作失败 | 编号=%s | 阶段=结束并粘贴 | 异常类型=%s | 类别=%s | 引擎=%s",
                    op, type(exc).__name__, exc.category, exc.engine_id,
                )
                message = exc.public_message
            else:
                self.error_log.error(
                    "操作失败 | 编号=%s | 阶段=结束并粘贴 | 异常类型=%s",
                    op, type(exc).__name__,
                )
                message = str(exc)
            self._warning(message)
        finally:
            with self.pipeline_lock:
                if bool(getattr(self.audio_monitor, "continuous", False)):
                    self.audio_monitor.finish_capture()
                else:
                    self.audio_monitor.stop()
                if getattr(self, "realtime_session", None) is not None:
                    self.realtime_session.cancel()
                    self.realtime_session = None
                self.standby_listener.pause()
            transcript_window = getattr(self, "transcript_window", None)
            if transcript_window is not None and not self.closed:
                transcript_window.hide()
            stale_router = None
            with self.lock:
                finished_router = getattr(self, "active_router", None)
                current_router = getattr(self, "recognition_router", None)
                self.active_router = None
                if finished_router is not None and finished_router is not current_router:
                    stale_router = finished_router
                self.recording = False
                self.standby_operation = False
                self.standby_end_cue_pending = False
                self.standby_stop_at_ms = None
                self.busy = False
            if stale_router is not None:
                stale_router.close()
            if not self.closed:
                self.window.set_waveform([0.0] * 7)
            self._restore_resting_pipeline()

    def _recognize_pcm(self, pcm: bytes, sample_rate: int) -> RecognitionResult:
        """统一识别入口；保留旧测试夹具和升级中的旧实例兼容。"""
        router = getattr(self, "active_router", None) or getattr(
            self, "recognition_router", None
        )
        if router is not None:
            return router.transcribe_pcm16(pcm, sample_rate)
        recognizer = self.local_recognizer
        text = recognizer.transcribe_pcm16(pcm, sample_rate)
        return RecognitionResult(
            text=str(text or "").strip(),
            requested_engine="local:legacy",
            actual_engine="local:legacy",
            device_label=str(getattr(recognizer, "device_label", "本地")),
        )

    def _ensure_clipboard_text(self, text: str, op: str, stage: str) -> None:
        if read_clipboard_text() == text:
            return
        if not write_clipboard_text(text, self.window.hwnd):
            raise RuntimeError("系统剪贴板内容发生变化，且无法恢复识别文字。")
        self.run_log.info(
            "操作进度 | 编号=%s | 阶段=%s恢复系统剪贴板 | 字符数=%d",
            op, stage, len(text),
        )

    def cleanup(self) -> None:
        with self.lock:
            if self.closed:
                return
            self.closed = True
            self.busy = True
        self.stop_event.set()
        # 等待已经开始的短暂历史/窗口/剪贴板副作用结束；此后 closed
        # 会阻止任何新的副作用进入。
        with self.side_effect_lock:
            pass
        with self.pipeline_lock:
            self.audio_monitor.close()
            if self.realtime_session is not None:
                self.realtime_session.cancel()
                self.realtime_session = None
            self.standby_listener.stop()
        routers = {id(self.recognition_router): self.recognition_router}
        if self.active_router is not None:
            routers[id(self.active_router)] = self.active_router
        self.active_router = None
        for router in routers.values():
            router.close()
        self.transcript_window.close()
        self.run_log.info("应用退出 | 版本=%s", APP_VERSION)

    def run(self) -> None:
        self.window.run()


def main() -> None:
    enable_dpi_awareness()
    if not acquire_single_instance():
        ctypes.windll.user32.MessageBoxW(
            None, "悬浮语音按钮已经在运行。", APP_NAME, 0x40
        )
        return
    app = VoiceButtonApp()
    atexit.register(app.cleanup)
    app.run()


def run_entrypoint() -> None:
    if "--settings-panel" in sys.argv[1:]:
        from settings_panel import main as settings_main

        settings_main()
        return
    main()


if __name__ == "__main__":
    try:
        run_entrypoint()
    except Exception as exc:
        log_dir = DATA_DIR / "logs"
        _, error_log = build_loggers(log_dir)
        error_log.error("启动失败 | 异常类型=%s", type(exc).__name__)
        raise
