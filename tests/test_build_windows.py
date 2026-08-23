import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import build_windows


class WindowsBuildTests(unittest.TestCase):
    def test_pyinstaller_command_embeds_application_icon(self):
        command = build_windows.pyinstaller_command(Path("python.exe"))
        icon_index = command.index("--icon")
        self.assertEqual(Path(command[icon_index + 1]).name, "app.ico")
        self.assertIn("settings_panel", command)
        self.assertIn("clr", command)
        self.assertIn("--windowed", command)

    def test_lite_package_rejects_model_files(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            model = package / "_internal" / "model.onnx"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"model")
            self.assertEqual(
                build_windows.forbidden_models(package, allow_external_models=False),
                [model],
            )

    def test_first_install_allows_models_only_in_external_model_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            allowed = package / "models" / "demo" / "model.onnx"
            forbidden = package / "_internal" / "model.onnx"
            allowed.parent.mkdir(parents=True)
            forbidden.parent.mkdir(parents=True)
            allowed.write_bytes(b"allowed")
            forbidden.write_bytes(b"forbidden")
            self.assertEqual(
                build_windows.forbidden_models(package, allow_external_models=True),
                [forbidden],
            )

    def test_package_docs_explain_first_install_and_light_upgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            build_windows.write_package_docs(package, "lite", [])
            instructions = (package / "使用说明.txt").read_text(encoding="utf-8")
            info = json.loads((package / "build-info.json").read_text(encoding="utf-8"))
            self.assertIn("解压到本机磁盘", instructions)
            self.assertIn("第一次安装建议使用首次安装版", instructions)
            self.assertIn("轻量升级版", instructions)
            self.assertFalse(info["includesModels"])
            self.assertTrue(info["upgradeKeepsLocalModels"])

    def test_checksum_file_supports_chinese_archive_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "dist" / "语点"
            package.mkdir(parents=True)
            (package / "使用说明.txt").write_text("测试", encoding="utf-8")
            with patch.object(build_windows, "PROJECT_ROOT", root):
                archive, checksum = build_windows.archive_package(
                    package,
                    "lite",
                    "v0.16.0",
                )
            self.assertIn(archive.name, checksum.read_text(encoding="utf-8"))

    def test_manifest_files_are_size_and_hash_verified(self):
        payload = b"verified model"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            model_dir = repository / "demo-model"
            model_dir.mkdir()
            (model_dir / "model.bin").write_bytes(payload)
            manifest = {
                "models": [{
                    "id": "faster-whisper-small",
                    "directory": "demo-model",
                    "files": [{
                        "path": "model.bin",
                        "bytes": len(payload),
                        "sha256": digest,
                    }],
                }]
            }
            (repository / "模型清单.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            verified = build_windows.verified_model_files(
                repository,
                "faster-whisper-small",
            )
            self.assertEqual(verified[0][0], model_dir / "model.bin")


if __name__ == "__main__":
    unittest.main()
