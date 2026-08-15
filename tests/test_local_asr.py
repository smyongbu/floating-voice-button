import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import local_asr


class LocalAsrTests(unittest.TestCase):
    def test_auto_falls_back_to_cpu(self):
        with patch.object(local_asr, "available_providers", return_value=["cpu"]):
            self.assertEqual(local_asr.choose_provider("auto"), ("cpu", "CPU"))

    def test_gpu_request_fails_clearly_when_unavailable(self):
        with patch.object(local_asr, "available_providers", return_value=["cpu"]):
            with self.assertRaisesRegex(RuntimeError, "没有可用"):
                local_asr.choose_provider("gpu")

    def test_invalid_device_fails_clearly(self):
        with self.assertRaisesRegex(ValueError, "只能选择"):
            local_asr.choose_provider("显卡")

    def test_catalog_is_json_serializable_and_has_hardware_details(self):
        catalog = local_asr.get_local_model_catalog()
        self.assertEqual(
            {item["id"] for item in catalog},
            {
                "sensevoice-small-int8",
                "paraformer-zh-small-int8",
                "qwen3-asr-0.6b-int8",
                "faster-whisper-small",
            },
        )
        json.dumps(catalog, ensure_ascii=False)
        for item in catalog:
            self.assertEqual(
                {"minimum", "recommended", "gpu", "note"},
                set(item["hardware"]),
            )
            self.assertIsInstance(item["capabilities"], list)
            self.assertIn("installed", item)
            self.assertIn("runtime_ready", item)

    def test_missing_qwen_model_is_reported_as_not_installed(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            with (
                patch.object(local_asr, "MODEL_SOURCE_ROOT", Path(source_dir)),
                patch.object(local_asr, "LOCAL_MODELS_DIR", Path(target_dir)),
            ):
                status = local_asr.get_local_model_status(local_asr.QWEN3_MODEL_ID)
        self.assertFalse(status["installed"])
        self.assertFalse(status["available"])
        self.assertEqual(status["status"], "未安装")
        self.assertIn("decoder.int8.onnx", status["missing_files"])

    def test_model_install_reuses_complete_local_copy(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source = Path(source_dir)
            target = Path(target_dir)
            (source / local_asr.MODEL_FILE).write_bytes(b"model")
            (source / local_asr.TOKENS_FILE).write_bytes(b"tokens")
            with (
                patch.object(local_asr, "MODEL_SOURCE_DIR", source),
                patch.object(local_asr, "MODEL_LOCAL_DIR", target),
                patch.object(local_asr.shutil, "copyfile", wraps=local_asr.shutil.copyfile) as copier,
            ):
                self.assertEqual(local_asr.install_model_locally(), target)
                self.assertEqual((target / local_asr.MODEL_FILE).read_bytes(), b"model")
                self.assertEqual(copier.call_count, 2)
                local_asr.install_model_locally()
                self.assertEqual(copier.call_count, 2)

    def test_paraformer_install_uses_its_complete_file_list(self):
        with tempfile.TemporaryDirectory() as source_root, tempfile.TemporaryDirectory() as local_root:
            source_dir = (
                Path(source_root)
                / local_asr.LOCAL_MODELS[local_asr.PARAFORMER_MODEL_ID]["source_directory"]
            )
            source_dir.mkdir()
            (source_dir / "model.int8.onnx").write_bytes(b"paraformer")
            (source_dir / "tokens.txt").write_bytes(b"tokens")
            with (
                patch.object(local_asr, "MODEL_SOURCE_ROOT", Path(source_root)),
                patch.object(local_asr, "LOCAL_MODELS_DIR", Path(local_root)),
            ):
                installed = local_asr.install_model_locally(local_asr.PARAFORMER_MODEL_ID)
                status = local_asr.get_local_model_status(local_asr.PARAFORMER_MODEL_ID)
            self.assertEqual(installed, Path(local_root) / local_asr.PARAFORMER_MODEL_ID)
            self.assertEqual((installed / "model.int8.onnx").read_bytes(), b"paraformer")
            self.assertTrue(status["cached_locally"])
            self.assertEqual(status["status"], "已安装")

    def test_install_rejects_incomplete_model_before_copying(self):
        with tempfile.TemporaryDirectory() as source_root, tempfile.TemporaryDirectory() as local_root:
            source_dir = (
                Path(source_root)
                / local_asr.LOCAL_MODELS[local_asr.PARAFORMER_MODEL_ID]["source_directory"]
            )
            source_dir.mkdir()
            (source_dir / "model.int8.onnx").write_bytes(b"paraformer")
            with (
                patch.object(local_asr, "MODEL_SOURCE_ROOT", Path(source_root)),
                patch.object(local_asr, "LOCAL_MODELS_DIR", Path(local_root)),
            ):
                with self.assertRaisesRegex(FileNotFoundError, "tokens.txt"):
                    local_asr.install_model_locally(local_asr.PARAFORMER_MODEL_ID)
            self.assertFalse((Path(local_root) / local_asr.PARAFORMER_MODEL_ID).exists())

    def test_complete_local_cache_survives_unavailable_source(self):
        with tempfile.TemporaryDirectory() as source_root, tempfile.TemporaryDirectory() as local_root:
            local_dir = Path(local_root) / local_asr.PARAFORMER_MODEL_ID
            local_dir.mkdir()
            (local_dir / "model.int8.onnx").write_bytes(b"paraformer")
            (local_dir / "tokens.txt").write_bytes(b"tokens")
            with (
                patch.object(local_asr, "MODEL_SOURCE_ROOT", Path(source_root)),
                patch.object(local_asr, "LOCAL_MODELS_DIR", Path(local_root)),
            ):
                self.assertEqual(
                    local_asr.install_model_locally(local_asr.PARAFORMER_MODEL_ID),
                    local_dir,
                )

    def test_unsafe_registered_path_is_rejected(self):
        for unsafe_path in ("../outside.onnx", "C:/outside.onnx", "/outside.onnx"):
            with self.subTest(unsafe_path=unsafe_path):
                metadata = dict(local_asr.LOCAL_MODELS[local_asr.PARAFORMER_MODEL_ID])
                metadata["required_files"] = [unsafe_path]
                with patch.dict(
                    local_asr.LOCAL_MODELS,
                    {local_asr.PARAFORMER_MODEL_ID: metadata},
                ):
                    with self.assertRaisesRegex(ValueError, "相对路径无效"):
                        local_asr.install_model_locally(local_asr.PARAFORMER_MODEL_ID)

    def test_paraformer_recognizer_loads_real_sherpa_factory(self):
        fake_recognizer = Mock()
        offline = SimpleNamespace(
            from_paraformer=Mock(return_value=fake_recognizer),
            from_sense_voice=Mock(),
            from_qwen3_asr=Mock(),
        )
        fake_sherpa = SimpleNamespace(
            OfflineRecognizer=offline,
            get_available_providers=lambda: ["cpu"],
        )
        with tempfile.TemporaryDirectory() as model_dir:
            with (
                patch.dict(sys.modules, {"sherpa_onnx": fake_sherpa}),
                patch.object(local_asr, "install_model_locally", return_value=Path(model_dir)),
                patch.object(local_asr, "available_providers", return_value=["cpu"]),
            ):
                recognizer = local_asr.LocalModelRecognizer(
                    local_asr.PARAFORMER_MODEL_ID,
                    "cpu",
                    num_threads=3,
                )
                recognizer.load()
                recognizer.load()
        offline.from_paraformer.assert_called_once_with(
            paraformer=str(Path(model_dir) / "model.int8.onnx"),
            tokens=str(Path(model_dir) / "tokens.txt"),
            num_threads=3,
            provider="cpu",
        )
        self.assertEqual(recognizer.device_label, "CPU")

    def test_paraformer_recognizer_transcribes_pcm16(self):
        stream = SimpleNamespace(
            accept_waveform=Mock(),
            result=SimpleNamespace(text="  本地识别成功。  "),
        )
        fake_recognizer = SimpleNamespace(
            create_stream=Mock(return_value=stream),
            decode_stream=Mock(),
        )
        with patch.object(local_asr, "available_providers", return_value=["cpu"]):
            recognizer = local_asr.LocalModelRecognizer(local_asr.PARAFORMER_MODEL_ID)
        recognizer._recognizer = fake_recognizer
        result = recognizer.transcribe_pcm16(b"\x00\x00\xff\x7f", sample_rate=16000)
        self.assertEqual(result, "本地识别成功。")
        stream.accept_waveform.assert_called_once_with(16000, [0.0, 32767 / 32768.0])
        fake_recognizer.decode_stream.assert_called_once_with(stream)

    def test_sensevoice_legacy_class_keeps_old_constructor(self):
        with patch.object(local_asr, "available_providers", return_value=["cpu"]):
            recognizer = local_asr.SenseVoiceRecognizer("auto", num_threads=4)
        self.assertIsInstance(recognizer, local_asr.LocalModelRecognizer)
        self.assertEqual(recognizer.model_id, local_asr.SENSEVOICE_MODEL_ID)
        self.assertEqual(recognizer.preference, "auto")
        self.assertEqual(recognizer.num_threads, 4)

    def test_empty_audio_does_not_load_model(self):
        with patch.object(local_asr, "available_providers", return_value=["cpu"]):
            recognizer = local_asr.LocalModelRecognizer(local_asr.SENSEVOICE_MODEL_ID)
        with patch.object(recognizer, "load") as loader:
            self.assertEqual(recognizer.transcribe_pcm16(b""), "")
        loader.assert_not_called()

    def test_odd_pcm16_byte_count_is_rejected(self):
        with patch.object(local_asr, "available_providers", return_value=["cpu"]):
            recognizer = local_asr.LocalModelRecognizer(local_asr.SENSEVOICE_MODEL_ID)
        with self.assertRaisesRegex(ValueError, "2 的倍数"):
            recognizer.transcribe_pcm16(b"\x00")


if __name__ == "__main__":
    unittest.main()
