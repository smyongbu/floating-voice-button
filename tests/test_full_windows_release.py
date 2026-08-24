from pathlib import Path
import tempfile
import unittest

from tools.prepare_full_windows_package import MODEL_DIRECTORIES, download_plan


class FullWindowsReleaseTests(unittest.TestCase):
    def test_plan_covers_exactly_five_models_and_18_files(self):
        plan = download_plan()
        self.assertEqual(5, len(MODEL_DIRECTORIES))
        self.assertEqual(18, len(plan))
        self.assertEqual(3_288_512_563, sum(item.size for item in plan))
        self.assertEqual(18, len({str(item.relative_path) for item in plan}))

    def test_streaming_package_contains_only_int8_runtime_files(self):
        paths = {Path(*item.relative_path.parts).name for item in download_plan() if item.model_id == "streaming-paraformer-bilingual-zh-en"}
        self.assertEqual({"encoder.int8.onnx", "decoder.int8.onnx", "tokens.txt"}, paths)

    def test_qwen_17_uses_pinned_nested_directory(self):
        item = next(item for item in download_plan() if item.model_id == "qwen3-asr-1.7b-q5km")
        self.assertIn("92282af1610a2db19d66f2bef1e260f5deca782d", item.relative_path.parts)


if __name__ == "__main__":
    unittest.main()
