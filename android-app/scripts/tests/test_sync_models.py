import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
APP_ROOT = SCRIPT_DIR.parent
SPEC = importlib.util.spec_from_file_location("android_model_sync", SCRIPT_DIR / "同步安卓模型.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ModelManifestTest(unittest.TestCase):
    def test_manifest_has_expected_verified_resource_sizes(self):
        manifest = APP_ROOT / "app" / "src" / "main" / "assets" / "model-resources.json"
        resources = MODULE.load_resources(manifest)
        totals = {
            resource.resource_id: sum(item.bytes for item in resource.files)
            for resource in resources
        }
        self.assertEqual(60_142_871, totals["zipformer-bilingual"])
        self.assertEqual(81_904_027, totals["paraformer"])
        self.assertTrue(all(len(item.sha256) == 64 for resource in resources for item in resource.files))

    def test_manifest_rejects_path_traversal(self):
        payload = {
            "schemaVersion": 1,
            "resources": [
                {
                    "id": "safe-id",
                    "version": "1",
                    "files": [
                        {
                            "path": "../outside.onnx",
                            "bytes": 1,
                            "sha256": "0" * 64,
                            "url": "https://example.invalid/model.onnx",
                        }
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE.load_resources(path)

    def test_manifest_rejects_unsafe_resource_id_and_absolute_file(self):
        for resource_id, file_path in (("../outside", "model.onnx"), ("safe-id", "/outside.onnx")):
            payload = {
                "schemaVersion": 1,
                "resources": [{
                    "id": resource_id,
                    "version": "1",
                    "files": [{
                        "path": file_path,
                        "bytes": 1,
                        "sha256": "0" * 64,
                        "url": "https://example.invalid/model.onnx",
                    }],
                }],
            }
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "manifest.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ValueError):
                    MODULE.load_resources(path)

    def test_manifest_rejects_bad_hash_and_insecure_url(self):
        for digest, url in (("not-a-hash", "https://example.invalid/model"), ("0" * 64, "http://example.invalid/model")):
            payload = {
                "schemaVersion": 1,
                "resources": [{
                    "id": "safe-id",
                    "version": "1",
                    "files": [{"path": "model.onnx", "bytes": 1, "sha256": digest, "url": url}],
                }],
            }
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "manifest.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ValueError):
                    MODULE.load_resources(path)


if __name__ == "__main__":
    unittest.main()
