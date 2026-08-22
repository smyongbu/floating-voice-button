#!/usr/bin/env python3
"""把本机离线模型按资源清单增量同步到已安装的安卓开发版。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse


PACKAGE_NAME = "com.smyongbu.voiceinput"
REMOTE_ROOT = "no_backup/resource-packs"
MAX_LOG_BYTES = 512 * 1024
SAFE_REMOTE = re.compile(r"^[A-Za-z0-9._/-]+$")


class SplitLogger:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.run_file = directory / "模型同步-运行.log"
        self.error_file = directory / "模型同步-错误.log"
        self._lock = threading.Lock()

    def info(self, operation: str, message: str) -> None:
        self._append(self.run_file, "信息", operation, message)

    def error(self, operation: str, message: str) -> None:
        self._append(self.error_file, "错误", operation, message)

    def _append(self, path: Path, level: str, operation: str, message: str) -> None:
        with self._lock:
            if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
                backup = path.with_name(path.name + ".1")
                if backup.exists():
                    backup.unlink()
                path.replace(backup)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(f"{timestamp} [{level}] [操作={operation}] {message}\n")


@dataclass(frozen=True)
class ResourceFile:
    relative_path: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class Resource:
    resource_id: str
    version: str
    files: tuple[ResourceFile, ...]


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    app_root = script_dir.parent
    parser = argparse.ArgumentParser(description="增量同步安卓语音识别模型")
    parser.add_argument("--serial", help="指定 adb 设备序列号；只有一台设备时可省略")
    parser.add_argument("--adb", default="adb", help="adb 可执行文件，默认从 PATH 查找")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(
            os.environ.get(
                "VOICE_INPUT_MODEL_REPOSITORY",
                str(app_root.parents[2] / "共享模型仓库"),
            )
        ).expanduser(),
        help="共享模型仓库根目录；可用 VOICE_INPUT_MODEL_REPOSITORY 覆盖",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=app_root / "app" / "src" / "main" / "assets" / "model-resources.json",
        help="模型资源清单",
    )
    parser.add_argument(
        "--resource",
        action="append",
        dest="resources",
        help="只同步指定资源编号，可重复传入；默认同步全部",
    )
    return parser.parse_args()


def load_resources(path: Path) -> list[Resource]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1:
        raise ValueError("不支持的资源清单版本。")
    result: list[Resource] = []
    seen_resources: set[str] = set()
    for raw in data["resources"]:
        resource_id = str(raw["id"])
        version = str(raw["version"])
        if (
            not SAFE_REMOTE.fullmatch(resource_id)
            or "/" in resource_id
            or resource_id in {".", ".."}
        ):
            raise ValueError(f"资源编号不安全：{resource_id}")
        if resource_id in seen_resources:
            raise ValueError(f"资源编号重复：{resource_id}")
        seen_resources.add(resource_id)
        if not SAFE_REMOTE.fullmatch(version) or "/" in version or version in {".", ".."}:
            raise ValueError(f"资源版本不安全：{version}")
        files: list[ResourceFile] = []
        seen_files: set[str] = set()
        for raw_file in raw["files"]:
            relative_path = str(raw_file["path"])
            posix_path = PurePosixPath(relative_path)
            if (
                not SAFE_REMOTE.fullmatch(relative_path)
                or posix_path.is_absolute()
                or "\\" in relative_path
                or "//" in relative_path
                or relative_path.endswith("/")
                or any(part in {"", ".", ".."} for part in posix_path.parts)
            ):
                raise ValueError(f"资源文件路径不安全：{relative_path}")
            if relative_path in seen_files:
                raise ValueError(f"资源文件路径重复：{relative_path}")
            seen_files.add(relative_path)
            byte_count = int(raw_file["bytes"])
            digest = str(raw_file["sha256"]).lower()
            url = str(raw_file["url"])
            if byte_count <= 0:
                raise ValueError(f"资源文件大小不正确：{relative_path}")
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(f"资源文件 SHA-256 不正确：{relative_path}")
            if urlparse(url).scheme.lower() != "https":
                raise ValueError(f"资源下载地址必须使用 HTTPS：{relative_path}")
            files.append(
                ResourceFile(
                    relative_path=relative_path,
                    bytes=byte_count,
                    sha256=digest,
                )
            )
        result.append(Resource(resource_id, version, tuple(files)))
    return result


def load_repository_index(source_root: Path) -> dict[tuple[int, str], Path]:
    manifest_path = source_root / "模型清单.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1:
        raise ValueError("不支持的共享模型仓库清单版本。")
    index: dict[tuple[int, str], Path] = {}
    for model in data.get("models", []):
        directory = model.get("directory") or model.get("relativeDirectory")
        if not directory:
            continue
        for raw_file in model.get("files", []):
            relative_path = str(raw_file["path"])
            candidate = (source_root / str(directory) / Path(relative_path)).resolve()
            try:
                candidate.relative_to(source_root)
            except ValueError as error:
                raise ValueError(f"共享仓库模型路径越界：{relative_path}") from error
            key = (int(raw_file["bytes"]), str(raw_file["sha256"]).lower())
            index.setdefault(key, candidate)
    return index


def resolve_local_file(
    source_root: Path,
    resource: Resource,
    spec: ResourceFile,
    repository_index: dict[tuple[int, str], Path],
) -> Path:
    legacy_path = (source_root / resource.resource_id / Path(spec.relative_path)).resolve()
    try:
        legacy_path.relative_to(source_root)
    except ValueError as error:
        raise ValueError(f"本机模型路径越界：{spec.relative_path}") from error
    if legacy_path.is_file():
        return legacy_path
    candidate = repository_index.get((spec.bytes, spec.sha256))
    if candidate is None:
        raise FileNotFoundError(
            f"共享模型仓库中缺少资源：{resource.resource_id}/{spec.relative_path}"
        )
    return candidate


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )


def select_device(adb: str, requested: str | None) -> str:
    result = run([adb, "devices"])
    devices = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    if requested:
        if requested not in devices:
            raise RuntimeError("指定的手机未连接或未授权调试。")
        return requested
    if len(devices) != 1:
        raise RuntimeError(f"需要恰好连接一台已授权手机，当前检测到 {len(devices)} 台。")
    return devices[0]


def adb_command(adb: str, serial: str, *parts: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run([adb, "-s", serial, *parts], check=check)


def local_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def validate_local_file(path: Path, spec: ResourceFile) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"缺少本机模型文件：{spec.relative_path}")
    if path.stat().st_size != spec.bytes:
        raise RuntimeError(f"本机模型文件大小不正确：{spec.relative_path}")
    if local_sha256(path) != spec.sha256:
        raise RuntimeError(f"本机模型文件校验失败：{spec.relative_path}")


def ensure_device_space(adb: str, serial: str, required_file_bytes: int) -> None:
    result = adb_command(adb, serial, "shell", "df", "-Pk", "/data/local/tmp")
    lines = [line.split() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2 or len(lines[-1]) < 4:
        raise RuntimeError("无法读取手机可用空间。")
    try:
        available = int(lines[-1][3]) * 1024
    except ValueError as error:
        raise RuntimeError("手机可用空间格式无法识别。") from error
    required = required_file_bytes * 2 + 64 * 1024 * 1024
    if available < required:
        raise RuntimeError("手机可用空间不足，无法安全同步模型。")


def remote_file_info(adb: str, serial: str, relative_path: str) -> tuple[int, str] | None:
    if not SAFE_REMOTE.fullmatch(relative_path):
        raise ValueError("远端路径不安全")
    size_result = adb_command(
        adb,
        serial,
        "shell",
        "run-as",
        PACKAGE_NAME,
        "wc",
        "-c",
        relative_path,
        check=False,
    )
    hash_result = adb_command(
        adb,
        serial,
        "shell",
        "run-as",
        PACKAGE_NAME,
        "sha256sum",
        relative_path,
        check=False,
    )
    if size_result.returncode != 0 or hash_result.returncode != 0:
        return None
    try:
        size = int(size_result.stdout.split()[0])
        digest = hash_result.stdout.split()[0].lower()
    except (ValueError, IndexError):
        return None
    return size, digest


def copy_verified_file(
    adb: str,
    serial: str,
    local_path: Path,
    resource: Resource,
    spec: ResourceFile,
) -> None:
    remote_dir = f"{REMOTE_ROOT}/{resource.resource_id}/{resource.version}"
    remote_final = f"{remote_dir}/{spec.relative_path}"
    remote_part = remote_final + ".part"
    temp_name = f"{resource.resource_id}-{Path(spec.relative_path).name}-{spec.sha256[:12]}.part"
    temp_path = f"/data/local/tmp/{PACKAGE_NAME}/{temp_name}"
    succeeded = False
    try:
        ensure_device_space(adb, serial, spec.bytes)
        adb_command(adb, serial, "shell", "mkdir", "-p", f"/data/local/tmp/{PACKAGE_NAME}")
        adb_command(adb, serial, "shell", "run-as", PACKAGE_NAME, "mkdir", "-p", str(PurePosixPath(remote_final).parent))
        adb_command(adb, serial, "push", str(local_path), temp_path)
        adb_command(adb, serial, "shell", "chmod", "644", temp_path)
        temp_hash = adb_command(adb, serial, "shell", "sha256sum", temp_path).stdout.split()[0].lower()
        if temp_hash != spec.sha256:
            raise RuntimeError(f"传输后的临时文件校验失败：{spec.relative_path}")
        adb_command(adb, serial, "shell", "run-as", PACKAGE_NAME, "cp", temp_path, remote_part)
        part_hash = adb_command(adb, serial, "shell", "run-as", PACKAGE_NAME, "sha256sum", remote_part).stdout.split()[0].lower()
        if part_hash != spec.sha256:
            raise RuntimeError(f"应用目录中的临时文件校验失败：{spec.relative_path}")
        adb_command(adb, serial, "shell", "run-as", PACKAGE_NAME, "mv", "-f", remote_part, remote_final)
        succeeded = True
    finally:
        adb_command(adb, serial, "shell", "rm", "-f", temp_path, check=False)
        if not succeeded:
            adb_command(adb, serial, "shell", "run-as", PACKAGE_NAME, "rm", "-f", remote_part, check=False)


def write_version_marker(adb: str, serial: str, resource: Resource) -> None:
    remote_dir = f"{REMOTE_ROOT}/{resource.resource_id}"
    temp_path = f"/data/local/tmp/{PACKAGE_NAME}/{resource.resource_id}-version.txt"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False) as handle:
        handle.write(resource.version + "\n")
        marker = Path(handle.name)
    try:
        adb_command(adb, serial, "shell", "run-as", PACKAGE_NAME, "mkdir", "-p", remote_dir)
        adb_command(adb, serial, "push", str(marker), temp_path)
        adb_command(adb, serial, "shell", "chmod", "644", temp_path)
        adb_command(adb, serial, "shell", "run-as", PACKAGE_NAME, "cp", temp_path, f"{remote_dir}/.installed-version.part")
        adb_command(adb, serial, "shell", "run-as", PACKAGE_NAME, "mv", "-f", f"{remote_dir}/.installed-version.part", f"{remote_dir}/.installed-version")
        adb_command(adb, serial, "shell", "rm", "-f", temp_path, check=False)
    finally:
        marker.unlink(missing_ok=True)


def sync_resource(
    adb: str,
    serial: str,
    source_root: Path,
    resource: Resource,
    repository_index: dict[tuple[int, str], Path],
    logger: SplitLogger,
    operation: str,
) -> tuple[int, int]:
    copied = 0
    skipped = 0
    for spec in resource.files:
        local_path = resolve_local_file(source_root, resource, spec, repository_index)
        validate_local_file(local_path, spec)
        remote_path = f"{REMOTE_ROOT}/{resource.resource_id}/{resource.version}/{spec.relative_path}"
        remote = remote_file_info(adb, serial, remote_path)
        if remote == (spec.bytes, spec.sha256):
            skipped += 1
            logger.info(operation, f"文件无需同步，资源={resource.resource_id}，文件={spec.relative_path}")
            continue
        copy_verified_file(adb, serial, local_path, resource, spec)
        verified = remote_file_info(adb, serial, remote_path)
        if verified != (spec.bytes, spec.sha256):
            raise RuntimeError(f"最终文件校验失败：{spec.relative_path}")
        copied += 1
        logger.info(operation, f"文件同步完成，资源={resource.resource_id}，文件={spec.relative_path}")
    write_version_marker(adb, serial, resource)
    logger.info(operation, f"资源同步完成，资源={resource.resource_id}，新增或变化={copied}，已复用={skipped}")
    return copied, skipped


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    logger = SplitLogger(script_dir / "logs")
    operation = "model-sync-" + datetime.now().strftime("%Y%m%d%H%M%S")
    serial: str | None = None
    app_stopped = False
    try:
        resources = load_resources(args.manifest.resolve())
        if args.resources:
            requested = set(args.resources)
            known = {resource.resource_id for resource in resources}
            unknown = sorted(requested - known)
            if unknown:
                raise ValueError("未知资源编号：" + "、".join(unknown))
            resources = [resource for resource in resources if resource.resource_id in requested]
        serial = select_device(args.adb, args.serial)
        adb_command(args.adb, serial, "shell", "run-as", PACKAGE_NAME, "pwd")
        adb_command(args.adb, serial, "shell", "am", "force-stop", PACKAGE_NAME)
        app_stopped = True
        logger.info(operation, "已停止开发版 App，避免与模型下载器同时写入资源")
        logger.info(operation, f"开始同步模型资源，资源数={len(resources)}")
        copied_total = 0
        skipped_total = 0
        source_root = args.source_root.resolve()
        repository_index = load_repository_index(source_root)
        for resource in resources:
            copied, skipped = sync_resource(
                args.adb,
                serial,
                source_root,
                resource,
                repository_index,
                logger,
                operation,
            )
            copied_total += copied
            skipped_total += skipped
        logger.info(operation, f"全部模型同步完成，新增或变化={copied_total}，已复用={skipped_total}")
        print(f"模型同步完成：新增或变化 {copied_total} 个文件，复用 {skipped_total} 个文件。")
        return 0
    except Exception as error:  # noqa: BLE001 - 命令行入口需要统一落错误日志
        source_root_text = str(args.source_root.resolve())
        message = str(error)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            message += f"；ADB 错误：{error.stderr.strip()}"
        message = message.replace(source_root_text, "<本机模型目录>")
        details = traceback.format_exc().replace(source_root_text, "<本机模型目录>")
        logger.error(operation, f"{message}\n{details}")
        print(f"模型同步失败：{message}", file=sys.stderr)
        return 1
    finally:
        if serial and app_stopped:
            try:
                restarted = adb_command(
                    args.adb,
                    serial,
                    "shell",
                    "am",
                    "start",
                    "-n",
                    f"{PACKAGE_NAME}/.MainActivity",
                    check=False,
                )
                if restarted.returncode == 0:
                    logger.info(operation, "模型同步结束，已重新打开开发版 App")
                else:
                    logger.error(operation, "模型同步结束后未能自动重新打开开发版 App")
            except Exception as restart_error:  # noqa: BLE001 - 不能覆盖原同步结果
                logger.error(operation, f"重新打开开发版 App 失败：{restart_error}")


if __name__ == "__main__":
    raise SystemExit(main())
