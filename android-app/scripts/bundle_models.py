"""复用已校验规范模型，准备 GitHub 附件、APK 资源并核验最终 APK。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile

CHUNK_BYTES = 64 * 1024 * 1024

APP_ROOT = Path(__file__).resolve().parents[1]
MODEL_IDS = {
    "streaming-paraformer-bilingual-zh-en",
    "faster-whisper-small-gguf-q8-0",
    "qwen3-asr-1.7b-gguf-q5-k-m",
}
MANIFEST = APP_ROOT / "app/src/main/assets/model-resources.json"


def catalog(path: Path = MANIFEST) -> list[dict]:
    resources = json.loads(path.read_text(encoding="utf-8"))["resources"]
    selected = [r for r in resources if r["id"] in MODEL_IDS]
    if {r["id"] for r in selected} != MODEL_IDS:
        raise ValueError("三模型清单不完整")
    for resource in selected:
        for name in [resource["id"], resource["version"], *[f["path"] for f in resource["files"]]]:
            if Path(name).is_absolute() or ".." in Path(name).parts or "\\" in name:
                raise ValueError("资源路径不安全")
    return selected


def asset_name(resource: dict, item: dict) -> str:
    return resource["id"] + "--" + item["path"].replace("/", "__")


def verify(path: Path, item: dict) -> None:
    if path.stat().st_size != item["bytes"]:
        raise ValueError(f"文件大小不符：{path.name}")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != item["sha256"]:
        raise ValueError(f"SHA-256 不符：{path.name}")


def local_index(root: Path) -> dict[tuple[int, str], Path]:
    result = {}
    data = json.loads((root / "模型清单.json").read_text(encoding="utf-8"))
    for model in data["models"]:
        directory = model.get("directory") or model.get("relativeDirectory")
        if not directory:
            continue
        for item in model.get("files", []):
            path = (root / directory / item["path"]).resolve()
            path.relative_to(root.resolve())
            result.setdefault((item["bytes"], item["sha256"]), path)
    return result


def materialize(source: Path, target: Path, item: dict) -> None:
    verify(source, item)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        verify(target, item)
        return
    part = target.with_name(target.name + ".part")
    # 同盘只读消费链接不重复占用模型空间；写入者不得改写已有权重。
    if part.exists():
        part.unlink()
    try:
        os.link(source, part)
    except OSError:
        shutil.copyfile(source, part)
    verify(part, item)
    os.replace(part, target)


def prepare(destination: Path, *, source_root: Path | None, release_dir: Path | None, export: bool) -> None:
    resources = catalog()
    index = local_index(source_root) if source_root else {}
    distribution = {}
    release_metadata = json.loads((release_dir / "bundled-models.json").read_text(encoding="utf-8")) if release_dir and (release_dir / "bundled-models.json").exists() else {}
    for resource in resources:
        for item in resource["files"]:
            source = release_dir / asset_name(resource, item) if release_dir else index[(item["bytes"], item["sha256"])]
            relative = Path(asset_name(resource, item)) if export else Path("bundled-models") / resource["id"] / resource["version"] / item["path"]
            chunks = release_metadata.get("releaseFiles", {}).get(asset_name(resource, item), [])
            if release_dir and chunks:
                restore_chunks(release_dir, chunks, destination / relative, item)
            elif export and item["bytes"] > 512 * 1024 * 1024:
                verify(source, item)
                distribution[asset_name(resource, item)] = split_file(source, destination, asset_name(resource, item))
            else:
                materialize(source, destination / relative, item)
            print(f"已校验：{resource['id']}/{item['path']}", flush=True)
    metadata = {"schemaVersion": 1, "variant": "three-models", "resources": resources}
    if distribution:
        metadata["releaseFiles"] = distribution
    destination.mkdir(parents=True, exist_ok=True)
    marker = destination / "bundled-models.json"
    part = marker.with_suffix(".json.part")
    part.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(part, marker)


def split_file(source: Path, destination: Path, name: str) -> list[dict]:
    destination.mkdir(parents=True, exist_ok=True)
    parts = []
    with source.open("rb") as stream:
        number = 1
        while data := stream.read(CHUNK_BYTES):
            target = destination / f"{name}.part{number:03d}"
            item = {"name": target.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            if target.exists():
                verify(target, item)
            else:
                temporary = target.with_name(target.name + ".part")
                temporary.write_bytes(data)
                os.replace(temporary, target)
            parts.append(item)
            number += 1
    return parts


def restore_chunks(directory: Path, chunks: list[dict], target: Path, expected: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    count = 0
    with part.open("wb") as output:
        for chunk in chunks:
            name = chunk["name"]
            if Path(name).name != name or "\\" in name or name in (".", ".."):
                raise ValueError("分块资源路径不安全")
            source = directory / name
            verify(source, chunk)
            with source.open("rb") as stream:
                while data := stream.read(1024 * 1024):
                    count += len(data)
                    if count > expected["bytes"]:
                        raise ValueError("分块资源总大小异常")
                    digest.update(data)
                    output.write(data)
    if count != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
        raise ValueError("还原模型的完整大小或哈希不符")
    os.replace(part, target)


def verify_apk(apk: Path) -> None:
    with zipfile.ZipFile(apk) as archive:
        metadata = json.loads(archive.read("assets/bundled-models.json"))
        if metadata["resources"] != catalog() or metadata.get("variant") != "three-models":
            raise ValueError("APK 模型身份清单不一致")
        expected = set()
        for resource in catalog():
            for item in resource["files"]:
                name = f"assets/bundled-models/{resource['id']}/{resource['version']}/{item['path']}"
                expected.add(name)
                if archive.getinfo(name).file_size != item["bytes"]:
                    raise ValueError("APK 模型大小不符：" + name)
                with archive.open(name) as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                if digest != item["sha256"]:
                    raise ValueError("APK 模型哈希不符：" + name)
        actual = {n for n in archive.namelist() if n.startswith("assets/bundled-models/") and not n.endswith("/")}
        if actual != expected:
            raise ValueError("APK 缺失或混入其他模型")
        print("APK 内三个模型的版本、大小和 SHA-256 全部通过")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--export", action="store_true", help="导出用于 GitHub Release 上传的资源")
    mode.add_argument("--stage", action="store_true", help="准备 Gradle 生成资源")
    mode.add_argument("--verify-apk", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--release-dir", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.verify_apk:
        verify_apk(args.verify_apk)
        return
    if bool(args.source_root) == bool(args.release_dir):
        parser.error("必须且只能指定 --source-root 或 --release-dir")
    destination = args.destination or APP_ROOT / ("local-resources/github-model-assets" if args.export else "app/build/generated/bundled-assets")
    prepare(destination, source_root=args.source_root, release_dir=args.release_dir, export=args.export)


if __name__ == "__main__":
    main()
