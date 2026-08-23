from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock

from model_download import (
    DownloadSpec,
    ModelDownloadManager,
    ResourceVerificationError,
    _TargetDownloadLease,
    ensure_resource_verified,
    verification_receipt_path,
)
from model_resource_groups import GroupedModelDownloadManager
from settings_panel import WebSettingsApi


class _LoopbackDownloadServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, payload: bytes, *, delay_seconds: float = 0.0) -> None:
        super().__init__(("127.0.0.1", 0), _LoopbackDownloadHandler)
        self.payload = payload
        self.delay_seconds = delay_seconds
        self.ranges: list[str | None] = []
        self._request_lock = threading.Lock()

    def record_request(self, range_header: str | None) -> None:
        with self._request_lock:
            self.ranges.append(range_header)


class _LoopbackDownloadHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 固定接口
        server: _LoopbackDownloadServer = self.server  # type: ignore[assignment]
        range_header = self.headers.get("Range")
        server.record_request(range_header)
        start = 0
        status = 200
        if range_header:
            start = int(range_header.removeprefix("bytes=").removesuffix("-"))
            status = 206

        body = server.payload[start:]
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        if status == 206:
            self.send_header(
                "Content-Range",
                f"bytes {start}-{len(server.payload) - 1}/{len(server.payload)}",
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
    def __init__(self, payload: bytes, *, delay_seconds: float = 0.0) -> None:
        self.server = _LoopbackDownloadServer(payload, delay_seconds=delay_seconds)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> _LoopbackDownloadServer:
        self.thread.start()
        return self.server

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _wait_for_status(get_status, expected: set[str], *, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    latest = get_status()
    while time.monotonic() < deadline:
        latest = get_status()
        if latest["state"] in expected:
            return latest
        time.sleep(0.01)
    raise AssertionError(f"等待状态 {sorted(expected)} 超时，当前为 {latest}")


def _wait_for_part(path: Path, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if path.is_file() and path.stat().st_size > 0:
                return
        except OSError:
            pass
        time.sleep(0.01)
    raise AssertionError(f"下载临时文件未在限定时间内产生：{path.name}")


class ModelDownloadCancelTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows 命名互斥测试")
    def test_target_lease_uses_global_mutex_and_resolves_directory_junction(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            physical = root / "physical"
            alias = root / "alias"
            physical.mkdir()
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(alias), str(physical)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if result.returncode != 0:
                self.skipTest("当前 Windows 环境无法创建临时目录联接")
            try:
                physical_lease = _TargetDownloadLease(physical / "model.bin")
                alias_lease = _TargetDownloadLease(alias / "model.bin")
                self.assertEqual(physical_lease._key, alias_lease._key)
                self.assertTrue(physical_lease._mutex_name.startswith("Global\\"))
                errors: list[Exception] = []

                def acquire_alias() -> None:
                    try:
                        with alias_lease:
                            pass
                    except Exception as exc:
                        errors.append(exc)

                with physical_lease:
                    contender = threading.Thread(target=acquire_alias)
                    contender.start()
                    contender.join(timeout=1.0)
                self.assertFalse(contender.is_alive())
                self.assertEqual(len(errors), 1)
                self.assertIn("同一模型文件", str(errors[0]))
            finally:
                alias.rmdir()

    def test_settings_api_start_and_cancel_use_real_group_manager(self) -> None:
        payload = b"settings-api-download" * (256 * 1024)
        with tempfile.TemporaryDirectory() as temp, _ServerContext(
            payload, delay_seconds=0.001
        ) as server:
            spec = DownloadSpec(
                resource_id="api-file",
                url=f"http://127.0.0.1:{server.server_port}/api.bin",
                target_path=Path(temp) / "api.bin",
                version="api-v1",
                total_size=len(payload),
                sha256=_sha256(payload),
            )
            manager = GroupedModelDownloadManager(
                {"api-model": [spec]}, run_log=None, error_log=None
            )
            api = WebSettingsApi.__new__(WebSettingsApi)
            api._model_downloads = manager
            api._model_resource_lock = threading.RLock()
            api._voice_test_lock = threading.RLock()
            api._active_test_kind = ""
            api._run_log = MagicMock()
            api._error_log = MagicMock()
            api._operation_id = lambda: "api-test"
            api._recognition_payload = lambda *_args: {
                "realtime_models": [],
                "local_models": [
                    {
                        "model_id": "api-model",
                        "resource_status": manager.status("api-model"),
                    }
                ],
            }

            started = api.manage_local_model_resource("api-model", "start")
            self.assertTrue(started["ok"])
            _wait_for_part(spec.part_path)
            cancelling = api.manage_local_model_resource("api-model", "cancel")
            self.assertTrue(cancelling["ok"])
            cancelled = _wait_for_status(
                lambda: manager.status("api-model"), {"not_started", "failed"}
            )

            self.assertEqual("not_started", cancelled["state"])
            self.assertFalse(spec.part_path.exists())

    def test_download_workers_use_at_most_three_resource_slots(self) -> None:
        payload = b"bounded-concurrency"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = {
                f"resource-{index}": DownloadSpec(
                    resource_id=f"resource-{index}",
                    url=f"http://127.0.0.1:9/resource-{index}",
                    target_path=root / f"resource-{index}.bin",
                    version="v1",
                    total_size=len(payload),
                    sha256=_sha256(payload),
                )
                for index in range(6)
            }
            manager = ModelDownloadManager(specs)
            active = 0
            maximum = 0
            active_lock = threading.Lock()

            def fake_download(
                self, spec, _generation, _pause_event, _cancel_event
            ) -> None:
                nonlocal active, maximum
                with active_lock:
                    active += 1
                    maximum = max(maximum, active)
                try:
                    time.sleep(0.15)
                    spec.target_path.write_bytes(payload)
                    self._write_spec_verification(spec, spec.target_path.stat())
                finally:
                    with active_lock:
                        active -= 1

            manager._download_and_install = types.MethodType(fake_download, manager)
            for resource_id in specs:
                manager.start(resource_id)
            threads = [record.thread for record in manager._records.values()]
            for thread in threads:
                self.assertIsNotNone(thread)
                thread.join(timeout=3.0)

            self.assertEqual(maximum, 3)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertTrue(
                all(manager.status(resource_id)["verified"] for resource_id in specs)
            )

    def test_public_verifier_obeys_the_same_target_lease(self) -> None:
        payload = b"verified-target" * 4096
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "model.bin"
            target.write_bytes(payload)
            errors: list[BaseException] = []

            def verify() -> None:
                try:
                    ensure_resource_verified(
                        "verified", target, "v1", len(payload), _sha256(payload)
                    )
                except BaseException as exc:
                    errors.append(exc)

            with _TargetDownloadLease(target):
                worker = threading.Thread(target=verify)
                worker.start()
                worker.join(timeout=2.0)

            self.assertFalse(worker.is_alive())
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], ResourceVerificationError)
            self.assertFalse(verification_receipt_path(target).exists())
            ensure_resource_verified(
                "verified", target, "v1", len(payload), _sha256(payload)
            )
            self.assertTrue(verification_receipt_path(target).exists())

    def test_two_managers_cannot_write_the_same_target_concurrently(self) -> None:
        payload = b"shared-target-payload-" * (384 * 1024)
        with tempfile.TemporaryDirectory() as temp, _ServerContext(
            payload, delay_seconds=0.001
        ) as server:
            target = Path(temp) / "shared" / "model.bin"
            spec = DownloadSpec(
                resource_id="shared-model",
                url=f"http://127.0.0.1:{server.server_port}/model.bin",
                target_path=target,
                version="shared-version",
                total_size=len(payload),
                sha256=_sha256(payload),
            )
            first = ModelDownloadManager({spec.resource_id: spec})
            second = ModelDownloadManager({spec.resource_id: spec})

            first.start(spec.resource_id)
            _wait_for_part(spec.part_path)
            second.start(spec.resource_id)
            blocked = _wait_for_status(
                lambda: second.status(spec.resource_id), {"failed"}
            )

            self.assertIn("另一个语点", str(blocked["error"]))
            self.assertEqual(1, len(server.ranges))
            second.cancel(spec.resource_id)
            competing_cancel = _wait_for_status(
                lambda: second.status(spec.resource_id), {"failed"}
            )
            self.assertIn("另一个语点", str(competing_cancel["error"]))
            self.assertTrue(spec.part_path.exists())
            first.cancel(spec.resource_id)
            cancelled = _wait_for_status(
                lambda: first.status(spec.resource_id), {"not_started", "failed"}
            )
            self.assertEqual("not_started", cancelled["state"])
            self.assertFalse(spec.part_path.exists())

            second.start(spec.resource_id)
            completed = _wait_for_status(
                lambda: second.status(spec.resource_id), {"completed", "failed"},
                timeout=15,
            )
            self.assertEqual("completed", completed["state"])
            self.assertEqual(payload, target.read_bytes())

    def test_cancel_preserves_existing_target_and_receipt_then_can_restart(self) -> None:
        payload = b"new-model-payload-" * (256 * 1024)
        previous_target = b"previous-complete-model" * 2048
        previous_receipt = b'{"version":"previous-complete-version"}\n'

        with tempfile.TemporaryDirectory() as temp, _ServerContext(
            payload, delay_seconds=0.001
        ) as server:
            target = Path(temp) / "中文模型" / "model.bin"
            target.parent.mkdir(parents=True)
            target.write_bytes(previous_target)
            receipt = verification_receipt_path(target)
            receipt.write_bytes(previous_receipt)
            spec = DownloadSpec(
                resource_id="single-model",
                url=f"http://127.0.0.1:{server.server_port}/model.bin",
                target_path=target,
                version="new-version",
                total_size=len(payload),
                sha256=_sha256(payload),
            )
            manager = ModelDownloadManager({spec.resource_id: spec})

            manager.start(spec.resource_id)
            _wait_for_part(spec.part_path)
            cancelling = manager.cancel(spec.resource_id)
            self.assertEqual("cancelling", cancelling["state"])
            self.assertEqual("cancelling", manager.delete(spec.resource_id)["state"])
            cancelled = _wait_for_status(
                lambda: manager.status(spec.resource_id),
                {"not_started", "installed", "completed", "failed"},
            )

            self.assertEqual("not_started", cancelled["state"])
            self.assertFalse(spec.part_path.exists())
            self.assertEqual(previous_target, target.read_bytes())
            self.assertEqual(previous_receipt, receipt.read_bytes())

            manager.start(spec.resource_id)
            completed = _wait_for_status(
                lambda: manager.status(spec.resource_id),
                {"completed", "failed"},
                timeout=15,
            )

            self.assertEqual("completed", completed["state"])
            self.assertTrue(completed["verified"])
            self.assertFalse(spec.part_path.exists())
            self.assertEqual(payload, target.read_bytes())
            saved_receipt = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(spec.resource_id, saved_receipt["resource_id"])
            self.assertEqual(spec.version, saved_receipt["version"])
            self.assertEqual(spec.sha256, saved_receipt["sha256"])

    def test_group_cancel_clears_every_part_and_returns_not_started(self) -> None:
        payload = b"grouped-model-payload-" * (384 * 1024)
        with tempfile.TemporaryDirectory() as temp, _ServerContext(
            payload, delay_seconds=0.001
        ) as server:
            root = Path(temp) / "grouped"
            specs = [
                DownloadSpec(
                    resource_id=f"group-file-{index}",
                    url=f"http://127.0.0.1:{server.server_port}/file-{index}.bin",
                    target_path=root / f"file-{index}.bin",
                    version=f"group-version-{index}",
                    total_size=len(payload),
                    sha256=_sha256(payload),
                )
                for index in range(2)
            ]
            manager = GroupedModelDownloadManager(
                {"group-model": specs}, run_log=None, error_log=None
            )

            manager.start("group-model")
            for spec in specs:
                _wait_for_part(spec.part_path)
            cancelling = manager.cancel("group-model")
            self.assertEqual("cancelling", cancelling["state"])
            cancelled = _wait_for_status(
                lambda: manager.status("group-model"),
                {"not_started", "failed"},
            )

            self.assertEqual("not_started", cancelled["state"])
            self.assertEqual(sum(spec.total_size for spec in specs), cancelled["total_bytes"])
            self.assertEqual(0, cancelled["downloaded_bytes"])
            self.assertEqual(0.0, cancelled["percent"])
            self.assertFalse(cancelled["verified"])
            for spec in specs:
                self.assertFalse(spec.part_path.exists())
                self.assertFalse(spec.target_path.exists())
                self.assertFalse(spec.verification_path.exists())


if __name__ == "__main__":
    unittest.main()
