"""核验三模型压缩包并准备版本化 GitHub 附件。"""
import hashlib
import json
from pathlib import Path
import zipfile
from tools.build_windows import APP_VERSION, PROJECT_ROOT


def main():
    archive = PROJECT_ROOT / "发布版本" / f"语点-Windows-{APP_VERSION}-首次安装版.zip"
    manifest = json.loads((PROJECT_ROOT / "tools/windows-models.json").read_text(encoding="utf-8"))
    root = f"语点-Windows-{APP_VERSION}"
    with zipfile.ZipFile(archive) as bundle:
        info = json.loads(bundle.read(root + "/build-info.json"))
        assert info["appVersion"] == APP_VERSION.removeprefix("v") and info["includesModels"]
        expected = {m["directory"] + "/" + f["path"] for m in manifest["models"] for f in m["files"]}
        assert set(info["modelFiles"]) == expected
        for m in manifest["models"]:
            for f in m["files"]:
                name = root + "/models/" + m["directory"] + "/" + f["path"]
                assert bundle.getinfo(name).file_size == f["bytes"]
                with bundle.open(name) as stream:
                    assert hashlib.file_digest(stream, "sha256").hexdigest() == f["sha256"]
        assert not any("zipformer" in n.lower() or "0.6b" in n.lower() for n in info["modelFiles"])
    output = PROJECT_ROOT / "发布版本/github"
    output.mkdir(parents=True, exist_ok=True)
    filename = f"Yudian-Windows-{APP_VERSION}-three-models.zip"
    chunks = []
    split = archive.stat().st_size >= 1900 * 1024 * 1024
    with archive.open("rb") as source:
        number = 0
        while source.tell() < archive.stat().st_size:
            number += 1
            name = filename + (f".{number:03}" if split else "")
            target = output / name
            remaining = 1024 * 1024 * 1024 if split else archive.stat().st_size
            with target.open("wb") as sink:
                while remaining and (chunk := source.read(min(1024 * 1024, remaining))):
                    sink.write(chunk)
                    remaining -= len(chunk)
            with target.open("rb") as stream:
                chunks.append(hashlib.file_digest(stream, "sha256").hexdigest() + "  " + name)
    (output / f"Yudian-Windows-{APP_VERSION}-SHA256SUMS.txt").write_text("\n".join(chunks) + "\n", encoding="utf-8")
    (output / f"Yudian-Windows-{APP_VERSION}-verification.txt").write_text(
        "三个模型逐文件大小与SHA-256通过；版本清单通过。\n"
        "若有.001/.002分卷，全部下载到同一文件夹，用7-Zip打开.001解压。\n"
        "请完整解压后运行语点.exe；模型位于同目录models中。\n", encoding="utf-8")
    print("三模型交付核验通过")


if __name__ == "__main__":
    main()
