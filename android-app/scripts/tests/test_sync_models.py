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
        self.assertEqual(
            {
                "streaming-paraformer-bilingual-zh-en",
                "zipformer-bilingual",
                "faster-whisper-small-gguf-q8-0",
                "qwen3-asr-0.6b-int8",
                "qwen3-asr-1.7b-gguf-q5-k-m",
            },
            set(totals),
        )
        self.assertEqual(237_202_501, totals["streaming-paraformer-bilingual-zh-en"])
        self.assertEqual(60_142_871, totals["zipformer-bilingual"])
        self.assertEqual(269_751_136, totals["faster-whisper-small-gguf-q8-0"])
        self.assertEqual(987_015_347, totals["qwen3-asr-0.6b-int8"])
        self.assertEqual(1_517_290_464, totals["qwen3-asr-1.7b-gguf-q5-k-m"])
        self.assertTrue(all(len(item.sha256) == 64 for resource in resources for item in resource.files))

    def test_transcribe_gguf_resources_pin_model_identity_and_downloads(self):
        manifest = APP_ROOT / "app" / "src" / "main" / "assets" / "model-resources.json"
        resources = json.loads(manifest.read_text(encoding="utf-8"))["resources"]
        whisper = next(item for item in resources if item["id"] == "faster-whisper-small-gguf-q8-0")
        self.assertEqual("c0214bd34be9296695486f838e0142f900803159-q8_0", whisper["version"])
        self.assertEqual("Apache-2.0", whisper["license"])
        self.assertEqual("https://huggingface.co/handy-computer/whisper-small-gguf", whisper["source"])
        self.assertEqual(
            [{
                "path": "whisper-small-Q8_0.gguf",
                "bytes": 269_751_136,
                "sha256": "9b9c8811bbcc82a7766f0fb0925614bdacb0923b2cc630daeac17108b655b860",
                "url": "https://huggingface.co/handy-computer/whisper-small-gguf/resolve/c0214bd34be9296695486f838e0142f900803159/whisper-small-Q8_0.gguf",
            }],
            whisper["files"],
        )
        qwen = next(item for item in resources if item["id"] == "qwen3-asr-1.7b-gguf-q5-k-m")
        self.assertEqual(
            [{
                "path": "Qwen3-ASR-1.7B-Q5_K_M.gguf",
                "bytes": 1_517_290_464,
                "sha256": "034c557fe92ff8fcd9a9c041cbdaad347be0a86a58d3a348f63cf3f0180879d0",
                "url": "https://huggingface.co/handy-computer/Qwen3-ASR-1.7B-gguf/resolve/92282af1610a2db19d66f2bef1e260f5deca782d/Qwen3-ASR-1.7B-Q5_K_M.gguf",
            }],
            qwen["files"],
        )

    def test_transcribe_cpp_source_is_fixed_to_verified_upstream_archive(self):
        cmake = (APP_ROOT / "app" / "src" / "main" / "cpp" / "CMakeLists.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("https://github.com/handy-computer/transcribe.cpp/archive/", cmake)
        self.assertIn("ea077b87590bcfb090d7c38c03ab36cd1c7005d3", cmake)
        self.assertIn("577826A626C85BD07E40EFADA8F9578BC2689132F14AD41B71EE496D9A9711D8", cmake)

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
