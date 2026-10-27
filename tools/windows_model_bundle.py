"""还原 GitHub 上已校验的 Windows 三模型构建资源。"""
from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import urllib.request

MANIFEST = Path(__file__).with_name("windows-models.json")
BASE = "https://github.com/smyongbu/floating-voice-button/releases/download/voice-bundled-models-v1/"


def verify(path, item):
    if path.stat().st_size != item["bytes"]:
        raise ValueError(f"文件大小不符：{path.name}")
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
            raise ValueError(f"文件校验失败：{path.name}")


def safe_path(root, relative):
    path = (root / relative).resolve()
    path.relative_to(root.resolve())
    return path


def stage(root):
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cache = root / ".parts"
    cache.mkdir(parents=True, exist_ok=True)
    parts = {p["name"]: p for m in data["models"] for f in m["files"] for p in f["assets"]}

    def download(item):
        target = safe_path(cache, item["name"])
        if target.exists():
            verify(target, item)
            return
        temporary = target.with_suffix(target.suffix + ".part")
        for attempt in range(3):
            try:
                with urllib.request.urlopen(BASE + item["name"], timeout=120) as response, temporary.open("wb") as stream:
                    while chunk := response.read(1024 * 1024):
                        stream.write(chunk)
                verify(temporary, item)
                temporary.replace(target)
                return
            except Exception:
                temporary.unlink(missing_ok=True)
                if attempt == 2:
                    raise

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(download, parts.values()))
    for model in data["models"]:
        for item in model["files"]:
            target = safe_path(root, model["directory"] + "/" + item["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".part")
            with temporary.open("wb") as output:
                for part in item["assets"]:
                    with safe_path(cache, part["name"]).open("rb") as source:
                        while chunk := source.read(1024 * 1024):
                            output.write(chunk)
            verify(temporary, item)
            temporary.replace(target)
    (root / "模型清单.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("三模型大小与 SHA-256 全部通过", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    stage(parser.parse_args().root)
