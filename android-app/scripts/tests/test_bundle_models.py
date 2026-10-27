import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

MODULE_PATH = Path(__file__).resolve().parents[1] / "bundle_models.py"
SPEC = importlib.util.spec_from_file_location("bundle_models", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BundledModelsTest(unittest.TestCase):
    def fixture(self, root):
        resources = []
        for number, model_id in enumerate(sorted(MODULE.MODEL_IDS)):
            data = f"测试模型-{number}".encode()
            item = {"path": "model.gguf", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            resource = {"id": model_id, "version": "fixed-v1", "files": [item]}
            (root / MODULE.asset_name(resource, item)).write_bytes(data)
            resources.append(resource)
        return resources

    def test_stage_from_release_and_verify_apk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = self.fixture(root)
            output = root / "staged"
            with patch.object(MODULE, "catalog", return_value=resources):
                MODULE.prepare(output, source_root=None, release_dir=root, export=False)
                apk = root / "test.apk"
                with zipfile.ZipFile(apk, "w") as archive:
                    for file in output.rglob("*"):
                        if file.is_file():
                            archive.write(file, "assets/" + file.relative_to(output).as_posix())
                MODULE.verify_apk(apk)
                with zipfile.ZipFile(apk, "a") as archive:
                    archive.writestr("assets/bundled-models/unexpected/extra.gguf", b"bad")
                with self.assertRaises(ValueError):
                    MODULE.verify_apk(apk)

    def test_corrupt_source_does_not_replace_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            source.write_bytes(b"bad")
            target.write_bytes(b"old")
            with self.assertRaises(ValueError):
                MODULE.materialize(source, target, {"bytes": 3, "sha256": "0" * 64})
            self.assertEqual(b"old", target.read_bytes())

    def test_shared_index_ignores_metadata_without_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "模型清单.json").write_text(json.dumps({"models": [{"id": "metadata", "directory": "a"}]}))
            self.assertEqual({}, MODULE.local_index(root))

    def test_chunk_restore_checks_overall_hash_and_keeps_old_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.write_bytes(b"abcdefghi")
            target = root / "restored"
            with patch.object(MODULE, "CHUNK_BYTES", 4):
                chunks = MODULE.split_file(source, root, "large-model")
            expected = {"bytes": 9, "sha256": hashlib.sha256(b"abcdefghi").hexdigest()}
            MODULE.restore_chunks(root, chunks, target, expected)
            self.assertEqual(b"abcdefghi", target.read_bytes())
            (root / chunks[1]["name"]).write_bytes(b"xxxx")
            with self.assertRaises(ValueError):
                MODULE.restore_chunks(root, chunks, target, expected)
            self.assertEqual(b"abcdefghi", target.read_bytes())

    def test_chunk_paths_cannot_escape_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                MODULE.restore_chunks(root, [{"name": "../outside"}], root / "target", {"bytes": 1, "sha256": "0" * 64})


if __name__ == "__main__":
    unittest.main()
