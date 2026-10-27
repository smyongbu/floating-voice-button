import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import windows_model_bundle as bundle
from tools.build_windows import FIRST_INSTALL_MODEL_IDS


class WindowsModelBundleTests(unittest.TestCase):
    def test_three_models_and_chunk_lengths_match(self):
        data = json.loads(bundle.MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual({m["id"] for m in data["models"]}, set(FIRST_INSTALL_MODEL_IDS))
        self.assertEqual(len(data["models"]), 3)
        for model in data["models"]:
            for item in model["files"]:
                self.assertEqual(sum(p["bytes"] for p in item["assets"]), item["bytes"])

    def test_staging_rejects_corrupt_cached_chunk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".parts").mkdir()
            (root / ".parts/model.part001").write_bytes(b"bad")
            spec = {"bytes": 3, "sha256": hashlib.sha256(b"yes").hexdigest()}
            manifest = root / "input.json"
            manifest.write_text(json.dumps({"models": [{"directory": "model", "files": [
                {"path": "model.bin", **spec, "assets": [{"name": "model.part001", **spec}]}]}]}))
            with patch.object(bundle, "MANIFEST", manifest), patch.object(bundle.urllib.request, "urlopen") as network:
                with self.assertRaises(ValueError):
                    bundle.stage(root)
                network.assert_not_called()
            self.assertFalse((root / "model/model.bin").exists())

    def test_rejects_path_outside_resource_root(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                bundle.safe_path(Path(directory), "../outside")
