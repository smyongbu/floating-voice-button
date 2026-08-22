from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


__all__ = [
    "DownloadSpec",
    "ModelDownloadManager",
    "ResourceVerificationError",
    "ensure_resource_verified",
    "get_resource_verification",
    "is_resource_verified",
    "verification_receipt_path",
]


_CHUNK_SIZE = 256 * 1024
_REQUEST_TIMEOUT_SECONDS = 30
_VERIFICATION_SCHEMA_VERSION = 1
_MAX_VERIFICATION_FILE_BYTES = 64 * 1024
_CONTENT_RANGE_RE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$", re.IGNORECASE)
_URL_WITH_QUERY_RE = re.compile(r"((?:https?|ftp)://[^\s?#]+)\?[^\s#]*", re.IGNORECASE)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_VERIFICATION_WRITE_LOCK = threading.RLock()


class ResourceVerificationError(RuntimeError):
    """本地资源无法通过清单大小或 SHA-256 校验。"""


def verification_receipt_path(target_path: str | Path) -> Path:
    """返回资源可信校验凭据的固定路径。"""
    return Path(f"{Path(target_path)}.verified.json")


def _verification_temp_path(target_path: str | Path) -> Path:
    return Path(f"{verification_receipt_path(target_path)}.tmp")


def _normalize_verification_fields(
    resource_id: str,
    target_path: str | Path,
    version: str,
    total_size: int,
    sha256: str,
) -> tuple[str, Path, str, int, str]:
    resource_id = str(resource_id).strip()
    target = Path(target_path)
    version = str(version).strip()
    sha256 = str(sha256).strip().lower()
    if not resource_id:
        raise ValueError("resource_id 不能为空")
    if not target.is_absolute():
        raise ValueError("target_path 必须是绝对路径")
    if not version:
        raise ValueError("version 不能为空")
    if isinstance(total_size, bool) or not isinstance(total_size, int) or total_size <= 0:
        raise ValueError("total_size 必须是正整数")
    if not _SHA256_RE.fullmatch(sha256):
        raise ValueError("sha256 必须是 64 位十六进制字符")
    return resource_id, target, version, total_size, sha256


def _regular_file_stat(path: Path) -> os.stat_result | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return path.stat()
    except OSError:
        return None


def _path_exists(path: Path) -> bool:
    try:
        return path.is_symlink() or path.exists()
    except OSError:
        return False


def _verification_payload(
    resource_id: str,
    version: str,
    total_size: int,
    sha256: str,
    mtime_ns: int,
) -> dict[str, Any]:
    return {
        "schema_version": _VERIFICATION_SCHEMA_VERSION,
        "resource_id": resource_id,
        "version": version,
        "size_bytes": total_size,
        "sha256": sha256,
        "mtime_ns": mtime_ns,
    }


def get_resource_verification(
    resource_id: str,
    target_path: str | Path,
    version: str,
    total_size: int,
    sha256: str,
) -> dict[str, Any] | None:
    """
    查询持久化校验凭据，不重新读取大型模型内容。

    仅当凭据字段与资源清单完全一致，且目标文件当前大小、修改时间仍匹配时
    才返回 JSON 可序列化的凭据；否则返回 ``None``。
    """
    resource_id, target, version, total_size, sha256 = _normalize_verification_fields(
        resource_id, target_path, version, total_size, sha256
    )
    target_before = _regular_file_stat(target)
    if target_before is None or target_before.st_size != total_size:
        return None

    receipt = verification_receipt_path(target)
    try:
        receipt_stat = _regular_file_stat(receipt)
        if receipt_stat is None or receipt_stat.st_size > _MAX_VERIFICATION_FILE_BYTES:
            return None
        payload = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None

    expected = _verification_payload(
        resource_id, version, total_size, sha256, target_before.st_mtime_ns
    )
    for key, value in expected.items():
        actual = payload.get(key)
        if type(actual) is not type(value) or actual != value:
            return None

    target_after = _regular_file_stat(target)
    if (
        target_after is None
        or target_after.st_size != target_before.st_size
        or target_after.st_mtime_ns != target_before.st_mtime_ns
    ):
        return None
    return expected


def is_resource_verified(
    resource_id: str,
    target_path: str | Path,
    version: str,
    total_size: int,
    sha256: str,
) -> bool:
    """快速查询目标资源是否拥有仍可信的持久化校验凭据。"""
    return (
        get_resource_verification(resource_id, target_path, version, total_size, sha256)
        is not None
    )


def _unlink_verification_file(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.exists():
        raise IsADirectoryError(f"拒绝删除非普通校验凭据: {path.name}")


def _remove_verification_files(target_path: Path) -> None:
    _unlink_verification_file(_verification_temp_path(target_path))
    _unlink_verification_file(verification_receipt_path(target_path))


def _write_verification_receipt(
    resource_id: str,
    target_path: Path,
    version: str,
    total_size: int,
    sha256: str,
    verified_stat: os.stat_result,
) -> dict[str, Any]:
    receipt = verification_receipt_path(target_path)
    temp_receipt = _verification_temp_path(target_path)
    payload = _verification_payload(
        resource_id, version, total_size, sha256, verified_stat.st_mtime_ns
    )
    with _VERIFICATION_WRITE_LOCK:
        current_stat = _regular_file_stat(target_path)
        if (
            current_stat is None
            or current_stat.st_size != total_size
            or current_stat.st_size != verified_stat.st_size
            or current_stat.st_mtime_ns != verified_stat.st_mtime_ns
        ):
            raise ResourceVerificationError("模型文件在校验期间发生变化，请重试")
        if temp_receipt.exists() and not (temp_receipt.is_file() or temp_receipt.is_symlink()):
            raise ResourceVerificationError("校验凭据临时路径不是普通文件")
        try:
            _unlink_verification_file(temp_receipt)
            with temp_receipt.open("w", encoding="utf-8", newline="\n") as output:
                json.dump(payload, output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp_receipt, receipt)
        except OSError as exc:
            raise ResourceVerificationError(f"无法保存模型校验凭据: {exc}") from exc
        finally:
            try:
                _unlink_verification_file(temp_receipt)
            except OSError:
                pass
    return payload


def ensure_resource_verified(
    resource_id: str,
    target_path: str | Path,
    version: str,
    total_size: int,
    sha256: str,
) -> dict[str, Any]:
    """
    确保本地资源真实通过 SHA-256 校验，并原子保存可信凭据。

    已有可信凭据时快速返回；首次加载、凭据缺失或文件修改时间改变时会
    重新读取整个文件计算 SHA-256。
    """
    resource_id, target, version, total_size, sha256 = _normalize_verification_fields(
        resource_id, target_path, version, total_size, sha256
    )
    cached = get_resource_verification(resource_id, target, version, total_size, sha256)
    if cached is not None:
        return cached

    before = _regular_file_stat(target)
    if before is None:
        raise ResourceVerificationError("模型文件不存在或不是普通文件")
    if before.st_size != total_size:
        raise ResourceVerificationError(
            f"模型文件大小不匹配：当前 {before.st_size} 字节，应为 {total_size} 字节"
        )

    digest = hashlib.sha256()
    try:
        with target.open("rb") as source:
            while True:
                chunk = source.read(_CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise ResourceVerificationError(f"无法读取模型文件: {exc}") from exc

    after = _regular_file_stat(target)
    if (
        after is None
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
    ):
        raise ResourceVerificationError("模型文件在校验期间发生变化，请重试")
    if digest.hexdigest() != sha256:
        try:
            _remove_verification_files(target)
        except OSError:
            pass
        raise ResourceVerificationError("SHA-256 完整性校验失败")
    return _write_verification_receipt(
        resource_id, target, version, total_size, sha256, after
    )


class _DownloadPaused(Exception):
    """下载线程已响应暂停请求。"""


class _DownloadCancelled(Exception):
    """下载线程已响应删除请求。"""


class _DownloadError(RuntimeError):
    """可安全展示给用户的下载错误。"""


class _ChecksumMismatch(_DownloadError):
    """已下载文件的 SHA-256 不匹配。"""


@dataclass(frozen=True, slots=True)
class DownloadSpec:
    """一个可下载模型资源的不可变描述。"""

    resource_id: str
    url: str
    target_path: Path
    version: str
    total_size: int
    sha256: str

    def __post_init__(self) -> None:
        resource_id = str(self.resource_id).strip()
        url = str(self.url).strip()
        version = str(self.version).strip()
        target_path = Path(self.target_path)
        sha256 = str(self.sha256).strip().lower()

        if not resource_id:
            raise ValueError("resource_id 不能为空")
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url 必须是有效的 HTTP/HTTPS 地址")
        if not target_path.is_absolute():
            raise ValueError("target_path 必须是绝对路径")
        if not version:
            raise ValueError("version 不能为空")
        if isinstance(self.total_size, bool) or not isinstance(self.total_size, int):
            raise ValueError("total_size 必须是正整数")
        if self.total_size <= 0:
            raise ValueError("total_size 必须是正整数")
        if not _SHA256_RE.fullmatch(sha256):
            raise ValueError("sha256 必须是 64 位十六进制字符")

        object.__setattr__(self, "resource_id", resource_id)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "target_path", target_path)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "sha256", sha256)

    @property
    def part_path(self) -> Path:
        return Path(f"{self.target_path}.part")

    @property
    def verification_path(self) -> Path:
        return verification_receipt_path(self.target_path)

    @property
    def verification_temp_path(self) -> Path:
        return _verification_temp_path(self.target_path)


@dataclass(slots=True)
class _DownloadRecord:
    total_bytes: int
    state: str = "not_started"
    downloaded_bytes: int = 0
    speed_bps: float = 0.0
    remaining_seconds: float | None = None
    error: str | None = None
    verified: bool = False
    operation_id: str | None = None
    thread: threading.Thread | None = None
    response: Any | None = None
    pause_event: threading.Event = field(default_factory=threading.Event)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    generation: int = 0
    last_progress_log_at: float = 0.0


class ModelDownloadManager:
    """
    线程安全的 Windows 模型资源下载管理器。

    ``start()`` 同时承担首次下载和断点续传。下载数据先写入
    ``<target>.part``；大小和 SHA-256 都校验通过后才使用 ``os.replace``
    原子替换目标。因此失败、暂停或断网均不会覆盖已存在的可用文件。
    """

    _ACTIVE_STATES = frozenset({"queued", "downloading", "verifying", "pausing"})

    def __init__(
        self,
        specs: Mapping[str, DownloadSpec],
        run_log: Any | None = None,
        error_log: Any | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._run_log = run_log
        self._error_log = error_log
        self._specs: dict[str, DownloadSpec] = {}
        self._records: dict[str, _DownloadRecord] = {}
        self._closed = False
        claimed_paths: set[str] = set()

        for key, spec in specs.items():
            if not isinstance(spec, DownloadSpec):
                raise TypeError("资源描述必须是 DownloadSpec")
            if str(key) != spec.resource_id:
                raise ValueError("资源映射键必须与 DownloadSpec.resource_id 一致")
            if spec.resource_id in self._specs:
                raise ValueError(f"重复的资源编号: {spec.resource_id}")
            spec_paths = {
                os.path.normcase(os.path.normpath(str(spec.target_path))),
                os.path.normcase(os.path.normpath(str(spec.part_path))),
                os.path.normcase(os.path.normpath(str(spec.verification_path))),
                os.path.normcase(os.path.normpath(str(spec.verification_temp_path))),
            }
            if claimed_paths.intersection(spec_paths):
                raise ValueError("不同资源不能共用目标文件、临时文件或校验凭据")
            claimed_paths.update(spec_paths)
            self._specs[spec.resource_id] = spec
            self._records[spec.resource_id] = self._initial_record(spec)

    @property
    def resource_ids(self) -> tuple[str, ...]:
        return tuple(self._specs)

    def start(self, resource_id: str) -> dict[str, Any]:
        """启动或继续后台下载，并立即返回当前状态。"""
        spec, record = self._get(resource_id)
        with self._lock:
            if self._closed:
                raise RuntimeError("模型下载管理器已关闭")
            if record.state == "deleting":
                return self._snapshot_locked(spec, record)
            if record.thread is not None and (
                record.thread.is_alive() or record.state in self._ACTIVE_STATES
            ):
                return self._snapshot_locked(spec, record)
            if record.state == "completed" and record.verified:
                if self._is_spec_verified(spec):
                    return self._snapshot_locked(spec, record)
                record.verified = False
                record.state = (
                    "installed"
                    if self._regular_file_size(spec.target_path) == spec.total_size
                    else "not_started"
                )

            record.generation += 1
            generation = record.generation
            record.pause_event = threading.Event()
            record.cancel_event = threading.Event()
            record.response = None
            record.error = None
            record.speed_bps = 0.0
            record.remaining_seconds = None
            record.operation_id = uuid.uuid4().hex[:12]
            record.state = "queued"
            record.last_progress_log_at = time.monotonic()
            operation_id = record.operation_id
            thread = threading.Thread(
                target=self._worker,
                args=(spec, generation, record.pause_event, record.cancel_event),
                name=f"model-download-{spec.resource_id}",
                daemon=True,
            )
            record.thread = thread
            snapshot = self._snapshot_locked(spec, record)

        try:
            thread.start()
        except Exception as exc:
            message = self._safe_error_message(exc)
            with self._lock:
                if record.generation == generation and record.thread is thread:
                    record.state = "failed"
                    record.error = message
                    record.thread = None
                    record.response = None
                    record.speed_bps = 0.0
                    record.remaining_seconds = None
                    record.verified = False
                snapshot = self._snapshot_locked(spec, record)
            self._log(
                self._error_log,
                "error",
                f"模型资源任务启动失败 | 编号={operation_id} | 资源={spec.resource_id} "
                f"| 错误类型={type(exc).__name__} | 原因={message}",
            )
            return snapshot

        self._log(
            self._run_log,
            "info",
            f"模型资源任务开始 | 编号={operation_id} | 资源={spec.resource_id} "
            f"| 版本={spec.version} | 文件={spec.target_path.name}",
        )
        return snapshot

    def resume(self, resource_id: str) -> dict[str, Any]:
        """``start`` 的语义化别名。"""
        return self.start(resource_id)

    def pause(self, resource_id: str) -> dict[str, Any]:
        """请求暂停；``.part`` 文件会保留，下次 ``start`` 将断点续传。"""
        spec, record = self._get(resource_id)
        response = None
        with self._lock:
            if record.state in self._ACTIVE_STATES and record.thread is not None:
                record.pause_event.set()
                record.state = "pausing"
                response = record.response
            snapshot = self._snapshot_locked(spec, record)

        self._close_response(response)
        return snapshot

    def pause_all(self, wait_seconds: float = 2.0) -> dict[str, dict[str, Any]]:
        """有序请求暂停全部任务，并在一个共享的短超时内等待后台线程退出。"""
        if isinstance(wait_seconds, bool) or not isinstance(wait_seconds, (int, float)):
            raise ValueError("wait_seconds 必须是非负数字")
        wait_seconds = float(wait_seconds)
        if wait_seconds < 0:
            raise ValueError("wait_seconds 必须是非负数字")

        responses: list[Any] = []
        threads: list[threading.Thread] = []
        with self._lock:
            for record in self._records.values():
                if record.state in self._ACTIVE_STATES and record.thread is not None:
                    record.pause_event.set()
                    record.state = "pausing"
                    responses.append(record.response)
                if record.thread is not None:
                    threads.append(record.thread)

        for response in responses:
            self._close_response(response)

        deadline = time.monotonic() + wait_seconds
        current = threading.current_thread()
        for thread in threads:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if thread is current:
                continue
            try:
                if thread.is_alive():
                    thread.join(timeout=remaining)
            except RuntimeError:
                # 尚未成功启动的线程不应阻断关闭流程。
                continue

        with self._lock:
            return {
                resource_id: self._snapshot_locked(self._specs[resource_id], record)
                for resource_id, record in self._records.items()
            }

    def shutdown(self, wait_seconds: float = 2.0) -> dict[str, dict[str, Any]]:
        """禁止新下载，并有序暂停当前任务；适合应用退出时调用。"""
        with self._lock:
            self._closed = True
        return self.pause_all(wait_seconds=wait_seconds)

    def status(self, resource_id: str) -> dict[str, Any]:
        """返回可直接交给 JSON 编码器的状态字典。"""
        spec, record = self._get(resource_id)
        with self._lock:
            return self._snapshot_locked(spec, record)

    def get_status(self, resource_id: str) -> dict[str, Any]:
        """``status`` 的兼容别名。"""
        return self.status(resource_id)

    def delete(self, resource_id: str) -> dict[str, Any]:
        """
        后台停止对应任务，并仅删除目标、``.part`` 与对应校验凭据。

        本方法不会同步无限等待下载线程；删除期间状态为 ``deleting``。
        不递归删除目录，不使用通配符，也不会触碰同目录其他文件。
        """
        spec, record = self._get(resource_id)
        response = None
        previous_thread = None
        operation_id = uuid.uuid4().hex[:12]
        with self._lock:
            if record.state == "deleting":
                return self._snapshot_locked(spec, record)
            record.generation += 1
            generation = record.generation
            record.pause_event.set()
            record.cancel_event.set()
            record.state = "deleting"
            record.error = None
            record.speed_bps = 0.0
            record.remaining_seconds = None
            record.operation_id = operation_id
            response = record.response
            record.response = None
            previous_thread = record.thread
            delete_thread = threading.Thread(
                target=self._delete_worker,
                args=(spec, generation, previous_thread, operation_id),
                name=f"model-delete-{spec.resource_id}",
                daemon=True,
            )
            record.thread = delete_thread
            snapshot = self._snapshot_locked(spec, record)

        self._close_response(response)
        try:
            delete_thread.start()
        except Exception as exc:
            message = self._safe_error_message(exc)
            with self._lock:
                if record.generation == generation and record.thread is delete_thread:
                    record.state = "failed"
                    record.error = message
                    record.thread = previous_thread
                snapshot = self._snapshot_locked(spec, record)
            self._log(
                self._error_log,
                "error",
                f"模型资源删除任务启动失败 | 编号={operation_id} | 资源={spec.resource_id} "
                f"| 错误类型={type(exc).__name__} | 原因={message}",
            )
            return snapshot

        self._log(
            self._run_log,
            "info",
            f"模型资源删除任务开始 | 编号={operation_id} | 资源={spec.resource_id} "
            f"| 文件={spec.target_path.name}",
        )
        return snapshot

    def _delete_worker(
        self,
        spec: DownloadSpec,
        generation: int,
        previous_thread: threading.Thread | None,
        operation_id: str,
    ) -> None:
        try:
            if (
                previous_thread is not None
                and previous_thread is not threading.current_thread()
                and previous_thread.is_alive()
            ):
                previous_thread.join()

            # 先让可信状态失效，再移除数据；只操作清单推导出的四个精确路径。
            self._unlink_exact_file(spec.verification_temp_path)
            self._unlink_exact_file(spec.verification_path)
            self._unlink_exact_file(spec.part_path)
            self._unlink_exact_file(spec.target_path)
        except Exception as exc:
            message = self._safe_error_message(exc)
            with self._lock:
                record = self._records[spec.resource_id]
                if record.generation == generation:
                    record.state = "failed"
                    record.error = message
                    record.thread = None
                    record.response = None
                    record.speed_bps = 0.0
                    record.remaining_seconds = None
                    record.verified = False
            self._log(
                self._error_log,
                "error",
                f"模型资源删除失败 | 编号={operation_id} | 资源={spec.resource_id} "
                f"| 错误类型={type(exc).__name__} | 原因={message}",
            )
            return

        with self._lock:
            record = self._records[spec.resource_id]
            if record.generation != generation:
                return
            record.state = "not_started"
            record.downloaded_bytes = 0
            record.speed_bps = 0.0
            record.remaining_seconds = None
            record.error = None
            record.verified = False
            record.operation_id = operation_id
            record.thread = None
            record.response = None
            record.pause_event = threading.Event()
            record.cancel_event = threading.Event()
        self._log(
            self._run_log,
            "info",
            f"模型资源已删除 | 编号={operation_id} | 资源={spec.resource_id} "
            f"| 文件={spec.target_path.name}",
        )

    def _initial_record(self, spec: DownloadSpec) -> _DownloadRecord:
        target_size = self._regular_file_size(spec.target_path)
        part_size = self._regular_file_size(spec.part_path)
        record = _DownloadRecord(total_bytes=spec.total_size)
        if target_size == spec.total_size:
            record.verified = self._is_spec_verified(spec)
            record.state = "completed" if record.verified else "installed"
            record.downloaded_bytes = spec.total_size
            if record.verified:
                record.remaining_seconds = 0.0
        elif part_size is not None:
            if part_size <= spec.total_size:
                record.state = "paused"
                record.downloaded_bytes = part_size
            else:
                record.state = "failed"
                record.error = "临时文件大小超过资源清单"
                record.downloaded_bytes = part_size
        return record

    def _get(self, resource_id: str) -> tuple[DownloadSpec, _DownloadRecord]:
        key = str(resource_id)
        try:
            return self._specs[key], self._records[key]
        except KeyError:
            raise KeyError(f"未知模型资源: {key}") from None

    def _worker(
        self,
        spec: DownloadSpec,
        generation: int,
        pause_event: threading.Event,
        cancel_event: threading.Event,
    ) -> None:
        outcome = "completed"
        error: str | None = None
        error_type: str | None = None
        operation_id = self._operation_id(spec.resource_id, generation)
        verified = False
        try:
            self._check_control_events(pause_event, cancel_event)
            if self._regular_file_size(spec.target_path) == spec.total_size:
                self._set_phase(spec, generation, "verifying", spec.total_size)
                before = _regular_file_stat(spec.target_path)
                digest = self._hash_file(spec.target_path, pause_event, cancel_event)
                after = _regular_file_stat(spec.target_path)
                if (
                    before is None
                    or after is None
                    or before.st_size != after.st_size
                    or before.st_mtime_ns != after.st_mtime_ns
                ):
                    raise _DownloadError("已安装模型在校验期间发生变化，请重试")
                if digest == spec.sha256:
                    self._write_spec_verification(spec, after)
                    verified = True
                    return
                try:
                    _remove_verification_files(spec.target_path)
                except OSError:
                    pass
                self._log(
                    self._error_log,
                    "warning",
                    f"已安装资源校验未通过，保留旧文件并重新下载 | 编号={operation_id} "
                    f"| 资源={spec.resource_id} | 阶段=校验",
                )
            self._download_and_install(spec, generation, pause_event, cancel_event)
            verified = True
        except _DownloadPaused:
            outcome = "paused"
        except _DownloadCancelled:
            outcome = "cancelled"
        except _ChecksumMismatch as exc:
            outcome = "failed"
            error = self._safe_error_message(exc)
            error_type = type(exc).__name__
            try:
                self._unlink_exact_file(spec.part_path)
            except OSError:
                pass
        except Exception as exc:  # 后台线程的最后防线，避免静默退出
            if cancel_event.is_set():
                outcome = "cancelled"
            elif pause_event.is_set():
                outcome = "paused"
            else:
                outcome = "failed"
                error = self._safe_error_message(exc)
                error_type = type(exc).__name__
        finally:
            response = None
            with self._lock:
                record = self._records[spec.resource_id]
                if record.generation == generation:
                    response = record.response
                    record.response = None
                    record.thread = None
                    record.speed_bps = 0.0
                    if outcome == "completed":
                        record.state = "completed"
                        record.downloaded_bytes = spec.total_size
                        record.remaining_seconds = 0.0
                        record.error = None
                        record.verified = verified
                    elif outcome == "paused":
                        record.state = "paused"
                        record.downloaded_bytes = self._resume_size(spec)
                        record.remaining_seconds = None
                        record.error = None
                        record.verified = False
                    elif outcome == "failed":
                        record.state = "failed"
                        record.downloaded_bytes = self._regular_file_size(spec.part_path) or 0
                        record.remaining_seconds = None
                        record.error = error or "下载失败"
                        record.verified = False
            self._close_response(response)

            if outcome == "completed":
                self._log(
                    self._run_log,
                    "info",
                    f"模型资源任务完成 | 编号={operation_id} | 资源={spec.resource_id} "
                    f"| 版本={spec.version} | 字节={spec.total_size}",
                )
            elif outcome == "paused":
                self._log(
                    self._run_log,
                    "info",
                    f"模型资源任务已暂停 | 编号={operation_id} | 资源={spec.resource_id} "
                    f"| 已下载={self._resume_size(spec)}",
                )
            elif outcome == "failed":
                self._log(
                    self._error_log,
                    "error",
                    f"模型资源任务失败 | 编号={operation_id} | 资源={spec.resource_id} "
                    f"| 阶段=下载或校验 | 错误类型={error_type or '_DownloadError'} "
                    f"| 原因={error or '下载失败'}",
                )

    def _download_and_install(
        self,
        spec: DownloadSpec,
        generation: int,
        pause_event: threading.Event,
        cancel_event: threading.Event,
    ) -> None:
        spec.target_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_regular_or_missing(spec.target_path, "目标路径")
        self._ensure_regular_or_missing(spec.part_path, "临时路径")

        offset = self._regular_file_size(spec.part_path) or 0
        if offset > spec.total_size:
            self._unlink_exact_file(spec.part_path)
            offset = 0
            self._log(
                self._error_log,
                "warning",
                f"临时文件超出清单大小，已仅重置临时文件 | 编号={self._operation_id(spec.resource_id, generation)} "
                f"| 资源={spec.resource_id}",
            )

        if offset < spec.total_size:
            response, offset, mode = self._open_response(spec, offset, generation)
            self._attach_response(spec.resource_id, generation, response)
            session_started_at = time.monotonic()
            session_start_bytes = offset
            downloaded = offset
            self._set_phase(spec, generation, "downloading", downloaded)
            try:
                with spec.part_path.open(mode) as output:
                    while True:
                        self._check_control_events(pause_event, cancel_event)
                        chunk = response.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        if downloaded + len(chunk) > spec.total_size:
                            raise _DownloadError("服务器返回的数据超过资源清单大小")
                        output.write(chunk)
                        downloaded += len(chunk)
                        self._update_progress(
                            spec,
                            generation,
                            downloaded,
                            session_start_bytes,
                            session_started_at,
                        )
                    output.flush()
                    os.fsync(output.fileno())
            finally:
                self._detach_and_close_response(spec.resource_id, generation, response)

            if downloaded != spec.total_size:
                raise _DownloadError(
                    f"下载不完整：已收到 {downloaded} 字节，应为 {spec.total_size} 字节"
                )

        self._check_control_events(pause_event, cancel_event)
        self._set_phase(spec, generation, "verifying", spec.total_size)
        part_before = _regular_file_stat(spec.part_path)
        digest = self._hash_file(spec.part_path, pause_event, cancel_event)
        part_after = _regular_file_stat(spec.part_path)
        if (
            part_before is None
            or part_after is None
            or part_before.st_size != part_after.st_size
            or part_before.st_mtime_ns != part_after.st_mtime_ns
        ):
            raise _DownloadError("临时模型在校验期间发生变化，请重试")
        if digest != spec.sha256:
            raise _ChecksumMismatch("SHA-256 完整性校验失败，已放弃该临时文件")

        self._check_control_events(pause_event, cancel_event)
        os.replace(spec.part_path, spec.target_path)
        installed_stat = _regular_file_stat(spec.target_path)
        if installed_stat is None or installed_stat.st_size != spec.total_size:
            raise _DownloadError("模型安装后大小异常")
        if installed_stat.st_mtime_ns != part_after.st_mtime_ns:
            raise _DownloadError("模型安装后发生变化，请重试")
        self._write_spec_verification(spec, installed_stat)

    def _open_response(
        self,
        spec: DownloadSpec,
        offset: int,
        generation: int,
    ) -> tuple[Any, int, str]:
        headers = {
            "Accept-Encoding": "identity",
            "User-Agent": "FloatingVoiceButton-ModelDownloader/1",
        }
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = Request(spec.url, headers=headers, method="GET")
        try:
            response = urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS)
        except HTTPError as exc:
            if exc.code != 416 or offset <= 0:
                raise
            self._close_response(exc)
            self._unlink_exact_file(spec.part_path)
            self._log(
                self._error_log,
                "warning",
                f"服务器拒绝断点位置，已仅重置临时文件 | 编号={self._operation_id(spec.resource_id, generation)} "
                f"| 资源={spec.resource_id}",
            )
            request = Request(
                spec.url,
                headers={
                    "Accept-Encoding": "identity",
                    "User-Agent": "FloatingVoiceButton-ModelDownloader/1",
                },
                method="GET",
            )
            response = urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS)
            status_value = getattr(response, "status", None)
            status = int(response.getcode() if status_value is None else status_value)
            if status == 206:
                try:
                    self._validate_content_range(
                        response.headers.get("Content-Range"), 0, spec.total_size
                    )
                except Exception:
                    self._close_response(response)
                    raise
            elif status != 200:
                self._close_response(response)
                raise _DownloadError(f"服务器返回非预期状态码 HTTP {status}")
            return response, 0, "wb"

        status_value = getattr(response, "status", None)
        status = int(response.getcode() if status_value is None else status_value)
        if offset > 0 and status == 206:
            try:
                self._validate_content_range(response.headers.get("Content-Range"), offset, spec.total_size)
            except Exception:
                self._close_response(response)
                raise
            return response, offset, "ab"
        if offset > 0 and status == 200:
            self._log(
                self._error_log,
                "warning",
                f"服务器未接受 Range，已从头写入临时文件 | 编号={self._operation_id(spec.resource_id, generation)} "
                f"| 资源={spec.resource_id}",
            )
            return response, 0, "wb"
        if offset == 0 and status == 206:
            try:
                self._validate_content_range(response.headers.get("Content-Range"), 0, spec.total_size)
            except Exception:
                self._close_response(response)
                raise
            return response, 0, "wb"
        if status != 200:
            self._close_response(response)
            raise _DownloadError(f"服务器返回非预期状态码 HTTP {status}")
        return response, 0, "wb"

    @staticmethod
    def _validate_content_range(value: str | None, expected_start: int, total_size: int) -> None:
        match = _CONTENT_RANGE_RE.fullmatch((value or "").strip())
        if not match:
            raise _DownloadError("服务器返回了无效的 Content-Range")
        start = int(match.group(1))
        end = int(match.group(2))
        declared_total = match.group(3)
        if start != expected_start or end < start:
            raise _DownloadError("服务器返回的断点范围与请求不一致")
        if declared_total != "*" and int(declared_total) != total_size:
            raise _DownloadError("服务器返回的资源总大小与清单不一致")

    def _set_phase(
        self,
        spec: DownloadSpec,
        generation: int,
        state: str,
        downloaded_bytes: int,
    ) -> None:
        with self._lock:
            record = self._records[spec.resource_id]
            if record.generation != generation:
                raise _DownloadCancelled()
            record.state = state
            record.downloaded_bytes = downloaded_bytes
            record.error = None
            if state == "verifying":
                record.speed_bps = 0.0
                record.remaining_seconds = 0.0

    def _update_progress(
        self,
        spec: DownloadSpec,
        generation: int,
        downloaded: int,
        session_start_bytes: int,
        session_started_at: float,
    ) -> None:
        now = time.monotonic()
        elapsed = max(now - session_started_at, 1e-6)
        speed = max(0.0, (downloaded - session_start_bytes) / elapsed)
        remaining = None if speed <= 0 else max(0.0, (spec.total_size - downloaded) / speed)
        should_log = False
        operation_id = None
        with self._lock:
            record = self._records[spec.resource_id]
            if record.generation != generation:
                raise _DownloadCancelled()
            record.state = "downloading"
            record.downloaded_bytes = downloaded
            record.speed_bps = speed
            record.remaining_seconds = remaining
            if now - record.last_progress_log_at >= 5.0:
                record.last_progress_log_at = now
                should_log = True
                operation_id = record.operation_id
        if should_log:
            self._log(
                self._run_log,
                "info",
                f"模型资源下载进度 | 编号={operation_id} | 资源={spec.resource_id} "
                f"| 已下载={downloaded} | 总大小={spec.total_size} | 速度={int(speed)}B/s",
            )

    def _attach_response(self, resource_id: str, generation: int, response: Any) -> None:
        with self._lock:
            record = self._records[resource_id]
            if record.generation != generation or record.cancel_event.is_set():
                self._close_response(response)
                raise _DownloadCancelled()
            record.response = response

    def _detach_and_close_response(self, resource_id: str, generation: int, response: Any) -> None:
        with self._lock:
            record = self._records[resource_id]
            if record.generation == generation and record.response is response:
                record.response = None
        self._close_response(response)

    def _operation_id(self, resource_id: str, generation: int) -> str:
        with self._lock:
            record = self._records[resource_id]
            if record.generation == generation and record.operation_id:
                return record.operation_id
        return "unknown"

    @staticmethod
    def _check_control_events(
        pause_event: threading.Event,
        cancel_event: threading.Event,
    ) -> None:
        if cancel_event.is_set():
            raise _DownloadCancelled()
        if pause_event.is_set():
            raise _DownloadPaused()

    @classmethod
    def _hash_file(
        cls,
        path: Path,
        pause_event: threading.Event,
        cancel_event: threading.Event,
    ) -> str:
        cls._ensure_regular_or_missing(path, "校验路径")
        if not path.is_file():
            raise _DownloadError("待校验文件不存在")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while True:
                cls._check_control_events(pause_event, cancel_event)
                chunk = source.read(_CHUNK_SIZE)
                if not chunk:
                    return digest.hexdigest()
                digest.update(chunk)

    def _resume_size(self, spec: DownloadSpec) -> int:
        part_size = self._regular_file_size(spec.part_path)
        if part_size is not None:
            return part_size
        if self._regular_file_size(spec.target_path) == spec.total_size:
            return spec.total_size
        return 0

    @staticmethod
    def _is_spec_verified(spec: DownloadSpec) -> bool:
        return is_resource_verified(
            spec.resource_id,
            spec.target_path,
            spec.version,
            spec.total_size,
            spec.sha256,
        )

    @staticmethod
    def _write_spec_verification(
        spec: DownloadSpec,
        verified_stat: os.stat_result,
    ) -> dict[str, Any]:
        try:
            return _write_verification_receipt(
                spec.resource_id,
                spec.target_path,
                spec.version,
                spec.total_size,
                spec.sha256,
                verified_stat,
            )
        except ResourceVerificationError as exc:
            raise _DownloadError(str(exc)) from exc

    def _snapshot_locked(self, spec: DownloadSpec, record: _DownloadRecord) -> dict[str, Any]:
        installed_bytes = self._regular_file_size(spec.target_path)
        part_bytes = self._regular_file_size(spec.part_path)
        target_exists = _path_exists(spec.target_path)
        installed = installed_bytes == spec.total_size
        receipt_verified = installed and self._is_spec_verified(spec)

        if record.state not in self._ACTIVE_STATES and record.state != "deleting":
            if record.verified and not receipt_verified:
                record.verified = False
                if record.state == "completed":
                    if installed:
                        record.state = "installed"
                        record.downloaded_bytes = spec.total_size
                    elif part_bytes is not None:
                        record.state = "paused"
                        record.downloaded_bytes = part_bytes
                    else:
                        record.state = "not_started"
                        record.downloaded_bytes = 0
                    record.remaining_seconds = None
            elif receipt_verified and record.state in {"installed", "completed"}:
                record.verified = True
                record.state = "completed"
                record.downloaded_bytes = spec.total_size
                record.error = None
                record.remaining_seconds = 0.0

        downloaded = max(0, int(record.downloaded_bytes))
        total = spec.total_size
        percent = min(100.0, round((downloaded / total) * 100.0, 2))
        return {
            "resource_id": spec.resource_id,
            "state": record.state,
            "downloaded_bytes": downloaded,
            "total_bytes": total,
            "percent": percent,
            "speed_bps": round(max(0.0, float(record.speed_bps)), 2),
            "remaining_seconds": (
                None
                if record.remaining_seconds is None
                else round(max(0.0, float(record.remaining_seconds)), 2)
            ),
            "error": record.error,
            "version": spec.version,
            "target_exists": target_exists,
            "installed": installed,
            "installed_bytes": installed_bytes or 0,
            "verified": bool(record.verified),
            "resumable": part_bytes is not None and part_bytes > 0,
            "operation_id": record.operation_id,
        }

    @staticmethod
    def _regular_file_size(path: Path) -> int | None:
        try:
            if path.is_symlink() or not path.is_file():
                return None
            return path.stat().st_size
        except OSError:
            return None

    @staticmethod
    def _ensure_regular_or_missing(path: Path, label: str) -> None:
        if path.is_symlink():
            raise _DownloadError(f"{label}不能是符号链接")
        if path.exists() and not path.is_file():
            raise _DownloadError(f"{label}不是普通文件")

    @staticmethod
    def _unlink_exact_file(path: Path) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink()
            return
        if path.exists():
            raise IsADirectoryError(f"拒绝删除非普通文件: {path.name}")

    @staticmethod
    def _close_response(response: Any | None) -> None:
        if response is None:
            return
        try:
            response.close()
        except Exception:
            pass

    @classmethod
    def _safe_error_message(cls, exc: BaseException) -> str:
        if isinstance(exc, HTTPError):
            reason = cls._redact_url_queries(str(exc.reason or "请求失败"))
            return f"HTTP {exc.code}: {reason}"
        if isinstance(exc, URLError):
            reason = cls._redact_url_queries(str(exc.reason or "网络连接失败"))
            return f"网络连接失败: {reason}"
        text = cls._redact_url_queries(str(exc).strip())
        return text or type(exc).__name__

    @staticmethod
    def _redact_url_queries(text: str) -> str:
        return _URL_WITH_QUERY_RE.sub(r"\1?<查询参数已隐藏>", text)

    @staticmethod
    def _log(logger: Any | None, level: str, message: str) -> None:
        if logger is None:
            return
        try:
            method = getattr(logger, level, None)
            if callable(method):
                method(message)
        except Exception:
            # 日志异常不应中断模型下载。
            pass
