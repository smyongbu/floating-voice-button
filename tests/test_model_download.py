from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from model_download import (
    DownloadSpec,
    ModelDownloadManager,
    ResourceVerificationError,
    ensure_resource_verified,
    get_resource_verification,
    is_resource_verified,
    verification_receipt_path,
)


class _DownloadHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, payload: bytes, *, mode: str = "range", delay_seconds: float = 0.0):
        super().__init__(("127.0.0.1", 0), _DownloadHandler)
        self.payload = payload
        self.mode = mode
        self.delay_seconds = delay_seconds
        self.ranges: list[str | None] = []
        self.request_count = 0
        self._request_lock = threading.Lock()

    def record_request(self, range_header: str | None) -> None:
        with self._request_lock:
            self.request_count += 1
            self.ranges.append(range_header)


class _DownloadHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 固定接口
        server: _DownloadHttpServer = self.server  # type: ignore[assignment]
        range_header = self.headers.get("Range")
        server.record_request(range_header)
        payload = server.payload

        if server.mode == "http_error":
            self.send_error(503, "temporary failure")
            return

        status = 200
        start = 0
        if range_header and server.mode != "ignore_range":
            start = int(range_header.removeprefix("bytes=").removesuffix("-"))
            if start >= len(payload):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(payload)}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206

        body = payload[start:]
        if server.mode == "short":
            body = body[: max(1, len(body) // 2)]

        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        if status == 206:
            range_start = start + 1 if server.mode == "bad_range" else start
            self.send_header(
                "Content-Range",
                f"bytes {range_start}-{range_start + len(body) - 1}/{len(payload)}",
            )
        self.end_headers()
        try:
            for index in range(0, len(body), 4096):
                self.wfile.write(body[index : index + 4096])
                self.wfile.flush()
                if server.delay_seconds:
                    time.sleep(server.delay_seconds)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def log_message(self, _format: str, *args: object) -> None:
        return


class _ServerContext:
    def __init__(self, payload: bytes, *, mode: str = "range", delay_seconds: float = 0.0):
        self.server = _DownloadHttpServer(payload, mode=mode, delay_seconds=delay_seconds)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> _DownloadHttpServer:
        self.thread.start()
        return self.server

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


class _CaptureLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)

    def warning(self, message: str) -> None:
        self.messages.append(message)

    def error(self, message: str) -> None:
        self.messages.append(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _wait_for_state(
    manager: ModelDownloadManager,
    resource_id: str,
    expected: set[str],
    *,
    timeout: float = 8.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = manager.status(resource_id)
        if status["state"] in expected:
            return status
        time.sleep(0.01)
    raise AssertionError(
        f"等待状态 {sorted(expected)} 超时，当前为 {manager.status(resource_id)}"
    )


class ModelDownloadManagerTests(unittest.TestCase):
    def _spec(self, server: _DownloadHttpServer, target: Path, payload: bytes, **changes) -> DownloadSpec:
        values = {
            "resource_id": "qwen3-asr-1.7b-q5km",
            "url": f"http://127.0.0.1:{server.server_port}/model.gguf?token=top-secret-token",
            "target_path": target,
            "version": "1.0-test",
            "total_size": len(payload),
            "sha256": _sha256(payload),
        }
        values.update(changes)
        return DownloadSpec(**values)

    def test_download_verifies_and_atomically_replaces_old_file(self):
        payload = (b"qwen3-asr-model-data-" * 16384) + b"end"
        with tempfile.TemporaryDirectory() as temp, _ServerContext(payload) as server:
            target = Path(temp) / "中文模型" / "model.gguf"
            target.parent.mkdir(parents=True)
            previous = b"previous-working-version"
            target.write_bytes(previous)
            run_log = _CaptureLogger()
            error_log = _CaptureLogger()
            spec = self._spec(server, target, payload)
            manager = ModelDownloadManager({spec.resource_id: spec}, run_log, error_log)

            manager.start(spec.resource_id)
            status = _wait_for_state(manager, spec.resource_id, {"completed", "failed"})

            self.assertEqual("completed", status["state"])
            self.assertEqual(payload, target.read_bytes())
            self.assertFalse(spec.part_path.exists())
            self.assertEqual(len(payload), status["downloaded_bytes"])
            self.assertEqual(len(payload), status["total_bytes"])
            self.assertEqual(100.0, status["percent"])
            self.assertEqual(0.0, status["speed_bps"])
            self.assertEqual(0.0, status["remaining_seconds"])
            self.assertIsNone(status["error"])
            self.assertEqual("1.0-test", status["version"])
            self.assertTrue(status["verified"])
            self.assertTrue(status["target_exists"])
            self.assertTrue(status["installed"])
            receipt = json.loads(spec.verification_path.read_text(encoding="utf-8"))
            self.assertEqual(spec.resource_id, receipt["resource_id"])
            self.assertEqual(spec.version, receipt["version"])
            self.assertEqual(spec.total_size, receipt["size_bytes"])
            self.assertEqual(spec.sha256, receipt["sha256"])
            self.assertEqual(target.stat().st_mtime_ns, receipt["mtime_ns"])
            self.assertTrue(
                is_resource_verified(
                    spec.resource_id,
                    target,
                    spec.version,
                    spec.total_size,
                    spec.sha256,
                )
            )
            restarted = ModelDownloadManager({spec.resource_id: spec})
            restarted_status = restarted.status(spec.resource_id)
            self.assertEqual("completed", restarted_status["state"])
            self.assertTrue(restarted_status["verified"])
            json.dumps(status, ensure_ascii=False)
            all_logs = "\n".join(run_log.messages + error_log.messages)
            self.assertNotIn("top-secret-token", all_logs)
            self.assertNotIn("?token=", all_logs)

    def test_pause_keeps_part_and_resume_uses_http_range(self):
        payload = b"0123456789abcdef" * (512 * 1024)
        with tempfile.TemporaryDirectory() as temp, _ServerContext(
            payload, delay_seconds=0.0008
        ) as server:
            target = Path(temp) / "model.gguf"
            spec = self._spec(server, target, payload)
            manager = ModelDownloadManager({spec.resource_id: spec})

            manager.start(spec.resource_id)
            deadline = time.monotonic() + 5
            while manager.status(spec.resource_id)["downloaded_bytes"] < 256 * 1024:
                if time.monotonic() >= deadline:
                    self.fail("下载未产生可暂停的进度")
                time.sleep(0.01)
            manager.pause(spec.resource_id)
            paused = _wait_for_state(manager, spec.resource_id, {"paused", "failed"})

            self.assertEqual("paused", paused["state"])
            self.assertTrue(spec.part_path.exists())
            self.assertFalse(target.exists())
            paused_size = spec.part_path.stat().st_size
            self.assertGreater(paused_size, 0)
            self.assertLess(paused_size, len(payload))

            manager.resume(spec.resource_id)
            completed = _wait_for_state(manager, spec.resource_id, {"completed", "failed"}, timeout=12)
            self.assertEqual("completed", completed["state"])
            self.assertEqual(payload, target.read_bytes())
            resumed_ranges = [value for value in server.ranges if value]
            self.assertTrue(resumed_ranges)
            self.assertIn(f"bytes={paused_size}-", resumed_ranges)

    def test_server_ignoring_range_restarts_only_part_file(self):
        payload = b"range-ignored-but-safe" * 8192
        with tempfile.TemporaryDirectory() as temp, _ServerContext(
            payload, mode="ignore_range"
        ) as server:
            target = Path(temp) / "model.gguf"
            spec = self._spec(server, target, payload)
            spec.part_path.write_bytes(payload[:12345])
            error_log = _CaptureLogger()
            manager = ModelDownloadManager({spec.resource_id: spec}, error_log=error_log)

            manager.start(spec.resource_id)
            status = _wait_for_state(manager, spec.resource_id, {"completed", "failed"})

            self.assertEqual("completed", status["state"])
            self.assertEqual(payload, target.read_bytes())
            self.assertIn("bytes=12345-", server.ranges)
            self.assertTrue(any("未接受 Range" in message for message in error_log.messages))

    def test_checksum_failure_preserves_old_target_and_redacts_url_query(self):
        payload = b"new-but-invalid" * 32768
        with tempfile.TemporaryDirectory() as temp, _ServerContext(payload) as server:
            target = Path(temp) / "model.gguf"
            previous = b"old-version-that-must-survive"
            target.write_bytes(previous)
            error_log = _CaptureLogger()
            spec = self._spec(server, target, payload, sha256="0" * 64)
            manager = ModelDownloadManager({spec.resource_id: spec}, error_log=error_log)

            manager.start(spec.resource_id)
            status = _wait_for_state(manager, spec.resource_id, {"failed", "completed"})

            self.assertEqual("failed", status["state"])
            self.assertIn("SHA-256", status["error"])
            self.assertEqual(previous, target.read_bytes())
            self.assertFalse(spec.part_path.exists())
            logs = "\n".join(error_log.messages)
            self.assertIn(status["operation_id"], logs)
            self.assertNotIn("top-secret-token", logs)
            self.assertNotIn("?token=", logs)

    def test_invalid_content_range_fails_without_corrupting_part(self):
        payload = b"bad-range" * 32768
        with tempfile.TemporaryDirectory() as temp, _ServerContext(
            payload, mode="bad_range"
        ) as server:
            target = Path(temp) / "model.gguf"
            spec = self._spec(server, target, payload)
            prefix = payload[:4096]
            spec.part_path.write_bytes(prefix)
            manager = ModelDownloadManager({spec.resource_id: spec})

            manager.start(spec.resource_id)
            status = _wait_for_state(manager, spec.resource_id, {"failed", "completed"})

            self.assertEqual("failed", status["state"])
            self.assertIn("断点范围", status["error"])
            self.assertEqual(prefix, spec.part_path.read_bytes())
            self.assertFalse(target.exists())

    def test_short_response_stays_resumable_and_does_not_replace_target(self):
        payload = b"short-response" * 32768
        with tempfile.TemporaryDirectory() as temp, _ServerContext(payload, mode="short") as server:
            target = Path(temp) / "model.gguf"
            previous = b"old-model"
            target.write_bytes(previous)
            spec = self._spec(server, target, payload)
            manager = ModelDownloadManager({spec.resource_id: spec})

            manager.start(spec.resource_id)
            status = _wait_for_state(manager, spec.resource_id, {"failed", "completed"})

            self.assertEqual("failed", status["state"])
            self.assertIn("下载不完整", status["error"])
            self.assertTrue(status["resumable"])
            self.assertEqual(previous, target.read_bytes())

    def test_delete_during_download_removes_only_exact_target_and_part(self):
        payload = b"delete-test" * (512 * 1024)
        with tempfile.TemporaryDirectory() as temp, _ServerContext(
            payload, delay_seconds=0.0008
        ) as server:
            target = Path(temp) / "model.gguf"
            spec = self._spec(server, target, payload)
            neighbor = Path(f"{target}.keep")
            part_neighbor = Path(f"{spec.part_path}.keep")
            receipt_neighbor = Path(f"{spec.verification_path}.keep")
            neighbor.write_bytes(b"keep-target-neighbor")
            part_neighbor.write_bytes(b"keep-part-neighbor")
            receipt_neighbor.write_bytes(b"keep-receipt-neighbor")
            spec.verification_path.write_text("{}", encoding="utf-8")
            spec.verification_temp_path.write_text("stale", encoding="utf-8")
            manager = ModelDownloadManager({spec.resource_id: spec})

            manager.start(spec.resource_id)
            deadline = time.monotonic() + 5
            while manager.status(spec.resource_id)["downloaded_bytes"] == 0:
                if time.monotonic() >= deadline:
                    self.fail("下载未启动")
                time.sleep(0.01)
            delete_started_at = time.monotonic()
            status = manager.delete(spec.resource_id)
            delete_elapsed = time.monotonic() - delete_started_at

            self.assertEqual("deleting", status["state"])
            self.assertLess(delete_elapsed, 0.5)
            status = _wait_for_state(manager, spec.resource_id, {"not_started", "failed"})
            self.assertEqual("not_started", status["state"])
            self.assertFalse(target.exists())
            self.assertFalse(spec.part_path.exists())
            self.assertFalse(spec.verification_path.exists())
            self.assertFalse(spec.verification_temp_path.exists())
            self.assertEqual(b"keep-target-neighbor", neighbor.read_bytes())
            self.assertEqual(b"keep-part-neighbor", part_neighbor.read_bytes())
            self.assertEqual(b"keep-receipt-neighbor", receipt_neighbor.read_bytes())

    def test_repeated_start_does_not_create_parallel_downloads(self):
        payload = b"single-worker" * (256 * 1024)
        with tempfile.TemporaryDirectory() as temp, _ServerContext(
            payload, delay_seconds=0.0005
        ) as server:
            target = Path(temp) / "model.gguf"
            spec = self._spec(server, target, payload)
            manager = ModelDownloadManager({spec.resource_id: spec})

            manager.start(spec.resource_id)
            manager.start(spec.resource_id)
            status = _wait_for_state(manager, spec.resource_id, {"completed", "failed"}, timeout=10)

            self.assertEqual("completed", status["state"])
            self.assertEqual(1, server.request_count)

    def test_existing_file_is_hashed_once_and_receipt_restores_verified_state(self):
        payload = b"existing-model-that-needs-first-load-verification" * 4096
        with tempfile.TemporaryDirectory() as temp, _ServerContext(payload) as server:
            target = Path(temp) / "model.gguf"
            target.write_bytes(payload)
            spec = self._spec(server, target, payload)
            manager = ModelDownloadManager({spec.resource_id: spec})

            initial = manager.status(spec.resource_id)
            self.assertEqual("installed", initial["state"])
            self.assertTrue(initial["installed"])
            self.assertFalse(initial["verified"])

            manager.start(spec.resource_id)
            completed = _wait_for_state(manager, spec.resource_id, {"completed", "failed"})
            self.assertEqual("completed", completed["state"])
            self.assertTrue(completed["verified"])
            self.assertEqual(0, server.request_count)
            self.assertIsNotNone(
                get_resource_verification(
                    spec.resource_id,
                    target,
                    spec.version,
                    spec.total_size,
                    spec.sha256,
                )
            )

            restored = ModelDownloadManager({spec.resource_id: spec}).status(spec.resource_id)
            self.assertEqual("completed", restored["state"])
            self.assertTrue(restored["verified"])

    def test_public_verification_rehashes_after_mtime_change_and_rejects_corruption(self):
        payload = b"public-verification-api" * 4096
        with tempfile.TemporaryDirectory() as temp, _ServerContext(payload) as server:
            target = Path(temp) / "model.gguf"
            target.write_bytes(payload)
            spec = self._spec(server, target, payload)

            self.assertEqual(
                verification_receipt_path(target),
                spec.verification_path,
            )
            self.assertIsNone(
                get_resource_verification(
                    spec.resource_id,
                    target,
                    spec.version,
                    spec.total_size,
                    spec.sha256,
                )
            )
            receipt = ensure_resource_verified(
                spec.resource_id,
                target,
                spec.version,
                spec.total_size,
                spec.sha256,
            )
            self.assertEqual(target.stat().st_mtime_ns, receipt["mtime_ns"])

            stat = target.stat()
            os.utime(
                target,
                ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000),
            )
            self.assertFalse(
                is_resource_verified(
                    spec.resource_id,
                    target,
                    spec.version,
                    spec.total_size,
                    spec.sha256,
                )
            )
            refreshed = ensure_resource_verified(
                spec.resource_id,
                target,
                spec.version,
                spec.total_size,
                spec.sha256,
            )
            self.assertEqual(target.stat().st_mtime_ns, refreshed["mtime_ns"])

            corrupted = bytearray(payload)
            corrupted[len(corrupted) // 2] ^= 0xFF
            target.write_bytes(corrupted)
            stat = target.stat()
            os.utime(
                target,
                ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000),
            )
            self.assertFalse(
                is_resource_verified(
                    spec.resource_id,
                    target,
                    spec.version,
                    spec.total_size,
                    spec.sha256,
                )
            )
            with self.assertRaises(ResourceVerificationError):
                ensure_resource_verified(
                    spec.resource_id,
                    target,
                    spec.version,
                    spec.total_size,
                    spec.sha256,
                )
            self.assertFalse(spec.verification_path.exists())
            self.assertFalse(spec.verification_temp_path.exists())

    def test_wrong_size_target_exists_but_is_not_installed(self):
        payload = b"expected-model-size" * 4096
        with tempfile.TemporaryDirectory() as temp, _ServerContext(payload) as server:
            target = Path(temp) / "model.gguf"
            target.write_bytes(payload[:-1])
            spec = self._spec(server, target, payload)
            status = ModelDownloadManager({spec.resource_id: spec}).status(spec.resource_id)

            self.assertTrue(status["target_exists"])
            self.assertFalse(status["installed"])
            self.assertEqual(len(payload) - 1, status["installed_bytes"])
            self.assertFalse(status["verified"])

    def test_shutdown_pauses_workers_and_rejects_future_start(self):
        payload = b"shutdown-model" * (512 * 1024)
        with tempfile.TemporaryDirectory() as temp, _ServerContext(
            payload, delay_seconds=0.0008
        ) as server:
            target = Path(temp) / "model.gguf"
            spec = self._spec(server, target, payload)
            manager = ModelDownloadManager({spec.resource_id: spec})
            manager.start(spec.resource_id)
            deadline = time.monotonic() + 5
            while manager.status(spec.resource_id)["downloaded_bytes"] == 0:
                if time.monotonic() >= deadline:
                    self.fail("下载未启动")
                time.sleep(0.01)

            statuses = manager.shutdown(wait_seconds=2.0)
            self.assertIn(statuses[spec.resource_id]["state"], {"paused", "pausing"})
            paused = _wait_for_state(manager, spec.resource_id, {"paused", "failed"})
            self.assertEqual("paused", paused["state"])
            self.assertTrue(spec.part_path.exists())
            with self.assertRaises(RuntimeError):
                manager.start(spec.resource_id)

    def test_thread_start_failure_rolls_back_queued_state(self):
        payload = b"thread-start-failure"
        with tempfile.TemporaryDirectory() as temp, _ServerContext(payload) as server:
            target = Path(temp) / "model.gguf"
            spec = self._spec(server, target, payload)
            manager = ModelDownloadManager({spec.resource_id: spec})

            with patch(
                "model_download.threading.Thread.start",
                side_effect=RuntimeError("thread unavailable"),
            ):
                status = manager.start(spec.resource_id)

            self.assertEqual("failed", status["state"])
            self.assertIn("thread unavailable", status["error"])
            self.assertNotEqual("queued", manager.status(spec.resource_id)["state"])

    def test_unknown_resource_and_invalid_spec_are_rejected(self):
        payload = b"validation"
        with tempfile.TemporaryDirectory() as temp, _ServerContext(payload) as server:
            target = Path(temp) / "model.gguf"
            spec = self._spec(server, target, payload)
            manager = ModelDownloadManager({spec.resource_id: spec})
            with self.assertRaises(KeyError):
                manager.status("missing")
            with self.assertRaises(ValueError):
                DownloadSpec(
                    resource_id="bad",
                    url="file:///tmp/model.gguf",
                    target_path=target,
                    version="1",
                    total_size=len(payload),
                    sha256=_sha256(payload),
                )
            with self.assertRaises(ValueError):
                DownloadSpec(
                    resource_id="bad",
                    url=f"http://127.0.0.1:{server.server_port}/model.gguf",
                    target_path=Path("relative-model.gguf"),
                    version="1",
                    total_size=len(payload),
                    sha256=_sha256(payload),
                )


if __name__ == "__main__":
    unittest.main()
