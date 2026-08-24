from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model_resource_groups import MODEL_FILES  # noqa: E402
from tools.build_windows import APP_VERSION, MODEL_CACHE_NAMESPACE  # noqa: E402

MODEL_DIRECTORIES = {
    "streaming-paraformer-bilingual-zh-en": "sherpa-onnx-streaming-paraformer-bilingual-zh-en",
    "zipformer-bilingual-zh-en-exp32-int8": "k2fsa-zipformer-bilingual-zh-en-t-exp32-int8-2024-03-20",
    "faster-whisper-small": "faster-whisper-small",
    "qwen3-asr-0.6b-int8": "sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25",
    "qwen3-asr-1.7b-q5km": "qwen3-asr-1.7b-gguf/92282af1610a2db19d66f2bef1e260f5deca782d",
}


@dataclass(frozen=True)
class DownloadItem:
    model_id: str
    relative_path: PurePosixPath
    url: str
    size: int
    sha256: str


def download_plan() -> list[DownloadItem]:
    if set(MODEL_FILES) != set(MODEL_DIRECTORIES):
        raise RuntimeError("模型清单与完整版目录映射不一致")
    result: list[DownloadItem] = []
    for model_id, metadata in MODEL_FILES.items():
        root = PurePosixPath(MODEL_DIRECTORIES[model_id])
        for relative, (size, digest, remote) in metadata["files"].items():
            target = root / PurePosixPath(relative)
            if target.is_absolute() or ".." in target.parts:
                raise RuntimeError(f"非法模型路径：{target}")
            result.append(DownloadItem(model_id, target, f"{metadata['base']}{remote}?download=true", int(size), str(digest)))
    if len({str(item.relative_path) for item in result}) != len(result):
        raise RuntimeError("完整版模型目标路径重复")
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def valid(path: Path, item: DownloadItem) -> bool:
    return path.is_file() and path.stat().st_size == item.size and sha256_file(path) == item.sha256


def fetch(models_dir: Path, item: DownloadItem) -> str:
    target = models_dir.joinpath(*item.relative_path.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    if valid(target, item):
        return str(item.relative_path)
    part = target.with_name(target.name + ".part")
    for attempt in range(1, 5):
        offset = part.stat().st_size if part.exists() else 0
        request = urllib.request.Request(item.url, headers={"User-Agent": "Yudian-GitHub-Release/0.16.11", "Accept-Encoding": "identity"})
        if offset:
            request.add_header("Range", f"bytes={offset}-")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                append = offset > 0 and response.status == 206
                with part.open("ab" if append else "wb") as output:
                    while chunk := response.read(4 * 1024 * 1024):
                        output.write(chunk)
            if valid(part, item):
                os.replace(part, target)
                return str(item.relative_path)
            part.unlink(missing_ok=True)
            raise RuntimeError("大小或 SHA-256 不符")
        except Exception:
            if attempt == 4:
                part.unlink(missing_ok=True)
                raise
            time.sleep(attempt * 3)
    raise AssertionError("unreachable")


def prepare(package_dir: Path) -> dict:
    models_dir = package_dir / "models"
    plan = download_plan()
    with ThreadPoolExecutor(max_workers=3) as executor:
        paths = list(executor.map(lambda item: fetch(models_dir, item), plan))
    expected = {Path(*item.relative_path.parts) for item in plan}
    unexpected = [p for p in models_dir.rglob("*") if p.is_file() and p.relative_to(models_dir) not in expected and p.name != "模型放置说明.txt"]
    if unexpected or list(models_dir.rglob("*.part")):
        raise RuntimeError(f"模型目录存在意外文件：{unexpected}")
    total = sum(item.size for item in plan)
    (models_dir / "模型放置说明.txt").write_text("本完整版附带语点支持的全部五个模型；所有文件均已按精确字节数和 SHA-256 校验。\n", encoding="utf-8")
    (package_dir / "使用说明.txt").write_text(
        "语点 Windows 五模型完整版\n\n本包附带全部五个模型，可直接使用。请下载同一 Release 的全部 7z 分卷，放在同一目录，并使用 7-Zip 打开 .7z.001 解压。\n运行入口：语点.exe\n",
        encoding="utf-8",
    )
    info = {
        "schemaVersion": 1, "appName": "语点", "appVersion": APP_VERSION.removeprefix("v"),
        "variant": "full-with-5-models", "includesModels": True,
        "modelIds": list(MODEL_DIRECTORIES), "modelCount": len(MODEL_DIRECTORIES),
        "modelFiles": paths, "modelBytes": total, "modelCacheNamespace": MODEL_CACHE_NAMESPACE,
        "upgradeKeepsLocalModels": True, "developmentCacheExcluded": True,
    }
    (package_dir / "build-info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", type=Path, required=True)
    info = prepare(parser.parse_args().package_dir.resolve())
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
