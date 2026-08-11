from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import traceback
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from automation import (
    activate_window,
    find_codex_window,
    foreground_window,
    paste,
    select_all_and_copy,
    start_or_stop_dictation,
)
from logger import build_loggers


APP_NAME = "悬浮语音按钮"
APP_VERSION = "0.1.0"
DATA_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / "FloatingVoiceButton"
CONFIG_PATH = DATA_DIR / "config.json"
DEFAULT_CONFIG = {
    "codex_window_keywords": ["Codex", "ChatGPT"],
    "codex_process_names": ["Codex.exe", "ChatGPT.exe"],
    "transcription_wait_ms": 900,
    "copy_wait_ms": 250,
    "paste_wait_ms": 150,
    "button_size": 64,
    "position_x": None,
    "position_y": None,
}


def load_config() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            incoming = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(incoming, dict):
                config.update(incoming)
        except (OSError, json.JSONDecodeError):
            pass
    # 保留用户自定义项，同时自动兼容 Codex 桌面版的新旧进程名称。
    config["codex_window_keywords"] = list(
        dict.fromkeys([*config.get("codex_window_keywords", []), "Codex", "ChatGPT"])
    )
    config["codex_process_names"] = list(
        dict.fromkeys([*config.get("codex_process_names", []), "Codex.exe", "ChatGPT.exe"])
    )
    return config


class VoiceButtonApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.config = load_config()
        self.run_log, self.error_log = build_loggers(DATA_DIR / "logs")
        self.recording = False
        self.busy = False
        self.origin_hwnd = 0
        self.last_external_hwnd = 0
        self.codex_hwnd = 0
        self.operation_id = ""
        self.drag_origin: tuple[int, int, int, int] | None = None
        self._configure_window()
        self._build_menu()
        self._install_exception_handler()
        self.root.after(100, self._remember_external_window)
        self.run_log.info("应用启动 | 版本=%s", APP_VERSION)

    def _remember_external_window(self) -> None:
        """持续记住悬浮按钮之外的前台窗口，避免点击按钮后丢失来源。"""
        try:
            hwnd = foreground_window()
            own_hwnd = int(self.root.winfo_id())
            if hwnd and hwnd != own_hwnd and not self.recording and not self.busy:
                self.last_external_hwnd = hwnd
        finally:
            self.root.after(150, self._remember_external_window)

    def _configure_window(self) -> None:
        size = max(48, min(96, int(self.config["button_size"])))
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = self.config.get("position_x")
        y = self.config.get("position_y")
        x = screen_w - size - 32 if x is None else int(x)
        y = screen_h // 2 - size // 2 if y is None else int(y)
        self.root.title(APP_NAME)
        self.root.geometry(f"{size}x{size}+{x}+{y}")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.96)
        self.canvas = tk.Canvas(
            self.root, width=size, height=size, bg="#111827", highlightthickness=0, cursor="hand2"
        )
        self.canvas.pack(fill="both", expand=True)
        self.circle = self.canvas.create_oval(4, 4, size - 4, size - 4, fill="#2563EB", outline="#93C5FD", width=2)
        self.icon = self.canvas.create_text(size / 2, size / 2 - 1, text="●", fill="white", font=("Microsoft YaHei UI", 25, "bold"))
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<Button-3>", self._show_menu)

    def _build_menu(self) -> None:
        self.menu = tk.Menu(self.root, tearoff=False, font=("Microsoft YaHei UI", 10))
        self.menu.add_command(label="打开日志目录", command=self._open_logs)
        self.menu.add_command(label="重新查找 Codex", command=lambda: setattr(self, "codex_hwnd", 0))
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=self.close)

    def _install_exception_handler(self) -> None:
        def report(exc_type, exc_value, exc_tb):
            self.error_log.error("未处理异常\n%s", "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
            messagebox.showerror(APP_NAME, "程序发生错误，详情已写入错误日志。")
        self.root.report_callback_exception = report

    def _on_press(self, event) -> None:
        self.drag_origin = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())

    def _on_drag(self, event) -> None:
        if not self.drag_origin:
            return
        start_x, start_y, window_x, window_y = self.drag_origin
        self.root.geometry(f"+{window_x + event.x_root - start_x}+{window_y + event.y_root - start_y}")

    def _on_release(self, event) -> None:
        if self.drag_origin:
            moved = abs(event.x_root - self.drag_origin[0]) + abs(event.y_root - self.drag_origin[1])
            self.drag_origin = None
            if moved > 8:
                self._save_position()
                return
        self.toggle()

    def _show_menu(self, event) -> None:
        self.menu.tk_popup(event.x_root, event.y_root)

    def _set_state(self, state: str) -> None:
        styles = {
            "idle": ("#2563EB", "●"),
            "recording": ("#DC2626", "■"),
            "busy": ("#D97706", "…"),
        }
        color, text = styles[state]
        self.canvas.itemconfigure(self.circle, fill=color)
        self.canvas.itemconfigure(self.icon, text=text)

    def toggle(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.operation_id = uuid.uuid4().hex[:8]
        self._set_state("busy")
        action = self._finish if self.recording else self._start
        threading.Thread(target=action, daemon=True).start()

    def _find_codex(self):
        window = find_codex_window(
            list(self.config["codex_window_keywords"]), list(self.config["codex_process_names"])
        )
        if window:
            self.codex_hwnd = window.hwnd
        return window

    def _start(self) -> None:
        started = time.monotonic()
        op = self.operation_id
        try:
            self.origin_hwnd = self.last_external_hwnd
            if not self.origin_hwnd:
                raise RuntimeError("尚未识别原软件，请先切回原软件停留片刻后再点击。")
            window = self._find_codex()
            if not window:
                raise RuntimeError("没有找到 Codex 窗口，请先打开 Codex。")
            self.run_log.info("操作开始 | 编号=%s | 阶段=开始语音", op)
            if not activate_window(window.hwnd):
                raise RuntimeError("无法切换到 Codex 窗口。")
            time.sleep(0.18)
            start_or_stop_dictation()
            self.recording = True
            elapsed = int((time.monotonic() - started) * 1000)
            self.run_log.info("操作完成 | 编号=%s | 阶段=开始语音 | 耗时毫秒=%d", op, elapsed)
            self.root.after(0, lambda: self._set_state("recording"))
        except Exception as exc:
            self.error_log.exception("操作失败 | 编号=%s | 阶段=开始语音 | 原因=%s", op, exc)
            self.root.after(0, lambda: messagebox.showwarning(APP_NAME, str(exc)))
            self.root.after(0, lambda: self._set_state("idle"))
        finally:
            self.busy = False

    def _finish(self) -> None:
        started = time.monotonic()
        op = self.operation_id
        try:
            self.run_log.info("操作开始 | 编号=%s | 阶段=结束并粘贴", op)
            if not self.codex_hwnd or not activate_window(self.codex_hwnd):
                window = self._find_codex()
                if not window or not activate_window(window.hwnd):
                    raise RuntimeError("无法重新切换到 Codex 窗口。")
            time.sleep(0.15)
            start_or_stop_dictation()
            time.sleep(max(0, int(self.config["transcription_wait_ms"])) / 1000)
            select_all_and_copy()
            time.sleep(max(0, int(self.config["copy_wait_ms"])) / 1000)
            if not activate_window(self.origin_hwnd):
                raise RuntimeError("无法切回原软件，文字已保留在剪贴板中。")
            time.sleep(max(0, int(self.config["paste_wait_ms"])) / 1000)
            paste()
            elapsed = int((time.monotonic() - started) * 1000)
            self.run_log.info("操作完成 | 编号=%s | 阶段=结束并粘贴 | 耗时毫秒=%d", op, elapsed)
        except Exception as exc:
            self.error_log.exception("操作失败 | 编号=%s | 阶段=结束并粘贴 | 原因=%s", op, exc)
            self.root.after(0, lambda: messagebox.showwarning(APP_NAME, str(exc)))
        finally:
            self.recording = False
            self.busy = False
            self.root.after(0, lambda: self._set_state("idle"))

    def _save_position(self) -> None:
        self.config["position_x"] = self.root.winfo_x()
        self.config["position_y"] = self.root.winfo_y()
        CONFIG_PATH.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8")

    def _open_logs(self) -> None:
        log_dir = DATA_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer.exe", str(log_dir)])

    def close(self) -> None:
        self._save_position()
        self.run_log.info("应用退出 | 版本=%s", APP_VERSION)
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = VoiceButtonApp(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
