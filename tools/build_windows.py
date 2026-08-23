from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from logging.handlers import RotatingFileHandler
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from version import (  # noqa: E402
    APP_VERSION as SOURCE_APP_VERSION,
    MODEL_CACHE_NAMESPACE,
)


APP_VERSION = f"v{SOURCE_APP_VERSION}"
APP_FOLDER_NAME = "语点"
MODEL_REPOSITORY_ENV = "VOICE_INPUT_MODEL_REPOSITORY"
FIRST_INSTALL_MODEL_IDS = (
    "faster-whisper-small",
    "streaming-paraformer-bilingual-zh-en",
)
FIRST_INSTALL_REALTIME_FILES = {
    "encoder.int8.onnx",
    "decoder.int8.onnx",
    "tokens.txt",
}
MODEL_EXTENSIONS = {
    ".onnx",
    ".ort",
    ".gguf",
    ".safetensors",
    ".pt",
    ".pth",
    ".ckpt",
}


def configure_logs() -> tuple[logging.Logger, logging.Logger]:
    log_dir = PROJECT_ROOT / "build" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    def create(name: str, filename: str) -> logging.Logger:
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        handler = RotatingFileHandler(
            log_dir / filename,
            maxBytes=512 * 1024,
            backupCount=1,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        ))
        logger.addHandler(handler)
        return logger

    return create("语点编译", "运行.log"), create("语点编译错误", "错误.log")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def windows_version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = version.removeprefix("v").split(".")
    if len(parts) not in (3, 4) or any(not part.isdigit() for part in parts):
        raise ValueError(f"Windows 版本号格式无效：{version}")
    numbers = tuple(int(part) for part in parts)
    return (*numbers, 0) if len(numbers) == 3 else numbers


def write_windows_version_file(version: str) -> Path:
    numeric = windows_version_tuple(version)
    display = version.removeprefix("v")
    path = PROJECT_ROOT / "build" / "windows-version-info.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numeric},
    prodvers={numeric},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('080404B0', [
        StringStruct('CompanyName', '语点'),
        StringStruct('FileDescription', '语点 - 悬浮语音输入'),
        StringStruct('FileVersion', '{display}'),
        StringStruct('InternalName', '语点'),
        StringStruct('LegalCopyright', 'Copyright © 2026'),
        StringStruct('OriginalFilename', '语点.exe'),
        StringStruct('ProductName', '语点'),
        StringStruct('ProductVersion', '{display}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""
    path.write_text(content, encoding="utf-8")
    return path


def write_windows_dotnet_config(package_dir: Path) -> Path:
    path = package_dir / f"{APP_FOLDER_NAME}.exe.config"
    path.write_text(
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
        "<configuration>\n"
        "  <runtime>\n"
        "    <loadFromRemoteSources enabled=\"true\" />\n"
        "  </runtime>\n"
        "</configuration>\n",
        encoding="utf-8",
    )
    return path


def default_model_repository() -> Path:
    configured = os.environ.get(MODEL_REPOSITORY_ENV)
    if configured:
        return Path(configured).expanduser()
    return PROJECT_ROOT.parents[1] / "共享模型仓库"


def load_model_manifest(repository: Path) -> dict:
    path = repository / "模型清单.json"
    return json.loads(path.read_text(encoding="utf-8"))


def verified_model_files(repository: Path, model_id: str) -> list[tuple[Path, Path]]:
    manifest = load_model_manifest(repository)
    model = next(
        (item for item in manifest.get("models", []) if item.get("id") == model_id),
        None,
    )
    if model is None:
        raise RuntimeError(f"共享模型清单缺少资源：{model_id}")
    directory = str(model.get("directory") or "")
    files = list(model.get("files") or [])
    if model_id == "streaming-paraformer-bilingual-zh-en":
        files = [item for item in files if item.get("path") in FIRST_INSTALL_REALTIME_FILES]
    if not directory or not files:
        raise RuntimeError(f"共享模型清单不完整：{model_id}")

    verified: list[tuple[Path, Path]] = []
    for item in files:
        relative = Path(str(item["path"]))
        source = repository / directory / relative
        expected_size = int(item["bytes"])
        expected_digest = str(item["sha256"]).lower()
        if not source.is_file() or source.stat().st_size != expected_size:
            raise RuntimeError(f"模型文件大小不符：{source}")
        if sha256_file(source) != expected_digest:
            raise RuntimeError(f"模型文件 SHA-256 不符：{source}")
        verified.append((source, Path(directory) / relative))
    return verified


def copy_first_install_models(package_dir: Path, repository: Path) -> list[str]:
    copied: list[str] = []
    for model_id in FIRST_INSTALL_MODEL_IDS:
        for source, relative in verified_model_files(repository, model_id):
            target = package_dir / "models" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if sha256_file(target) != sha256_file(source):
                raise RuntimeError(f"复制后的模型校验失败：{target}")
            copied.append(relative.as_posix())
    return copied


def is_model_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    return suffix in MODEL_EXTENSIONS or (
        suffix == ".bin"
        and path.name.lower() in {"encoder.bin", "decoder.bin", "joiner.bin", "model.bin"}
    )


def forbidden_models(package_dir: Path, *, allow_external_models: bool) -> list[Path]:
    found: list[Path] = []
    model_root = package_dir / "models"
    for path in package_dir.rglob("*"):
        if not path.is_file() or not is_model_file(path):
            continue
        if allow_external_models and path.is_relative_to(model_root):
            continue
        found.append(path)
    return found


def pyinstaller_command(python: Path) -> list[str]:
    return [
        str(python),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        APP_FOLDER_NAME,
        "--icon",
        str(PROJECT_ROOT / "assets" / "app.ico"),
        "--version-file",
        str(PROJECT_ROOT / "build" / "windows-version-info.txt"),
        "--add-data",
        f"{PROJECT_ROOT / 'web'};web",
        "--add-data",
        f"{PROJECT_ROOT / 'assets'};assets",
        "--hidden-import",
        "settings_panel",
        "--hidden-import",
        "clr",
        "--collect-all",
        "webview",
        "--collect-all",
        "sherpa_onnx",
        "--collect-all",
        "faster_whisper",
        "--collect-all",
        "ctranslate2",
        "--collect-all",
        "transcribe_cpp",
        "--distpath",
        str(PROJECT_ROOT / "dist"),
        "--workpath",
        str(PROJECT_ROOT / "build" / "pyinstaller"),
        "--specpath",
        str(PROJECT_ROOT / "build"),
        str(PROJECT_ROOT / "app.py"),
    ]


def write_package_docs(package_dir: Path, variant: str, copied_models: list[str]) -> None:
    model_dir = package_dir / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    includes_models = variant == "first-install"
    (model_dir / "模型放置说明.txt").write_text(
        "此文件夹用于存放语点的外置语音识别模型。\n"
        "首次安装版附带 Faster-Whisper Small 与 Streaming Paraformer。\n"
        "轻量升级版不附带模型，会复用已有 models 文件夹或正式版模型缓存；不会读取源码开发缓存。\n",
        encoding="utf-8",
    )
    (package_dir / "使用说明.txt").write_text(
        "语点 Windows 编译版\n\n"
        f"当前包：{'首次安装版（带基础模型）' if includes_models else '轻量升级版（不带模型）'}\n"
        "第一次安装建议使用首次安装版。以后升级可下载轻量升级版，"
        "并保留旧版 models 文件夹；正式版也会复用自己的跨版本模型缓存。\n"
        f"正式版模型缓存位于 %LOCALAPPDATA%\\FloatingVoiceButton\\{MODEL_CACHE_NAMESPACE}。\n"
        "请完整解压后运行，可放在本机磁盘或 UNC 网络共享；"
        "不要直接从 ZIP 启动，也不要删除语点.exe.config。\n"
        "运行入口：语点.exe\n"
        "应用、任务管理器和 Windows 通知区域使用同一语点图标。\n",
        encoding="utf-8",
    )
    build_info = {
        "schemaVersion": 1,
        "appName": "语点",
        "appVersion": APP_VERSION.removeprefix("v"),
        "variant": variant,
        "includesModels": includes_models,
        "modelFiles": copied_models,
        "upgradeKeepsLocalModels": True,
        "modelCacheNamespace": MODEL_CACHE_NAMESPACE,
        "developmentCacheExcluded": True,
    }
    (package_dir / "build-info.json").write_text(
        json.dumps(build_info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def archive_package(package_dir: Path, variant: str, version: str) -> tuple[Path, Path]:
    output_dir = PROJECT_ROOT / "发布版本"
    output_dir.mkdir(parents=True, exist_ok=True)
    label = "首次安装版" if variant == "first-install" else "轻量升级版-不带模型"
    archive = output_dir / f"语点-Windows-{version}-{label}.zip"
    if archive.exists():
        archive.unlink()
    archive_root = Path(f"{APP_FOLDER_NAME}-Windows-{version}")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                bundle.write(path, archive_root / path.relative_to(package_dir))
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    checksum.write_text(f"{sha256_file(archive)}  {archive.name}\n", encoding="utf-8")
    return archive, checksum


def build(variant: str, python: Path) -> tuple[Path, Path]:
    version = APP_VERSION
    run_log, error_log = configure_logs()
    operation_id = uuid.uuid4().hex[:8]
    run_log.info("编译开始 | 编号=%s | 版本=%s | 类型=%s", operation_id, version, variant)
    try:
        if sys.version_info[:2] != (3, 11) and Path(sys.executable).resolve() == python.resolve():
            raise RuntimeError("语点 Windows 编译必须使用 Python 3.11。")
        icon = PROJECT_ROOT / "assets" / "app.ico"
        if not icon.is_file():
            raise RuntimeError(f"应用图标不存在：{icon}")
        write_windows_version_file(version)
        subprocess.run(pyinstaller_command(python), cwd=PROJECT_ROOT, check=True)
        package_dir = PROJECT_ROOT / "dist" / APP_FOLDER_NAME
        write_windows_dotnet_config(package_dir)
        vad_model = package_dir / "_internal" / "faster_whisper" / "assets" / "silero_vad_v6.onnx"
        if vad_model.exists():
            vad_model.unlink()

        copied_models: list[str] = []
        if variant == "first-install":
            copied_models = copy_first_install_models(package_dir, default_model_repository())
        write_package_docs(package_dir, variant, copied_models)
        forbidden = forbidden_models(
            package_dir,
            allow_external_models=variant == "first-install",
        )
        if forbidden:
            joined = "、".join(str(path.relative_to(package_dir)) for path in forbidden)
            raise RuntimeError(f"发布包中发现不允许的模型文件：{joined}")
        archive, checksum = archive_package(package_dir, variant, version)
        run_log.info(
            "编译完成 | 编号=%s | 类型=%s | 压缩包=%s | 字节数=%d",
            operation_id,
            variant,
            archive.name,
            archive.stat().st_size,
        )
        return archive, checksum
    except Exception as exc:
        error_log.exception(
            "编译失败 | 编号=%s | 阶段=Windows打包 | 异常类型=%s",
            operation_id,
            type(exc).__name__,
        )
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="编译语点 Windows 版")
    parser.add_argument(
        "--variant",
        choices=("lite", "first-install"),
        default="lite",
        help="lite 为不带模型升级版；first-install 为首次安装版",
    )
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    built_archive, built_checksum = build(
        arguments.variant,
        arguments.python,
    )
    print(built_archive)
    print(built_checksum)
