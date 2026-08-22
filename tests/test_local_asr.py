import hashlib
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import local_asr


class LocalAsrTests(unittest.TestCase):
    def test_windows_models_use_central_shared_repository(self):
        expected_root = local_asr.PROJECT_DIR.parents[1] / "共享模型仓库"
        self.assertEqual(local_asr.MODEL_SOURCE_ROOT, expected_root)
        self.assertTrue(
            str(local_asr.LOCAL_MODELS[local_asr.QWEN3_17_MODEL_ID]["source_directory"])
            .replace("\\", "/")
            .startswith("qwen3-asr-1.7b-gguf/")
        )

    def test_packaged_app_uses_models_folder_next_to_executable(self):
        packaged_executable = Path("C:/Apps/语点/语点.exe")
        with (
            patch.object(local_asr.sys, "frozen", True, create=True),
            patch.object(local_asr.sys, "executable", str(packaged_executable)),
        ):
            self.assertEqual(
                local_asr._default_model_repository(),
                packaged_executable.parent / "models",
            )

    @staticmethod
    def _transcribe_device(
        *,
        device_type: str,
        kind: str,
        device_id: int,
        index: int,
        name: str,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            device_type=device_type,
            kind=kind,
            device_id=device_id,
            index=index,
            name=name,
        )

    @staticmethod
    def _qwen17_metadata_for_payload(payload: bytes) -> dict:
        metadata = deepcopy(local_asr.LOCAL_MODELS[local_asr.QWEN3_17_MODEL_ID])
        digest = hashlib.sha256(payload).hexdigest()
        metadata["size_bytes"] = len(payload)
        metadata["file_sizes"] = {local_asr.QWEN3_17_FILENAME: len(payload)}
        metadata["sha256"] = {local_asr.QWEN3_17_FILENAME: digest}
        metadata["download"] = {
            **metadata["download"],
            "version": "test-resource@receipt-v1",
            "size_bytes": len(payload),
            "sha256": digest,
        }
        return metadata

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

    def test_transcribe_device_fields_follow_backend_device_contract(self):
        cpu = self._transcribe_device(
            device_type="cpu",
            kind="cpu",
            device_id=0,
            index=0,
            name="CPU",
        )
        accelerator = self._transcribe_device(
            device_type="accel",
            kind="accel",
            device_id=3,
            index=3,
            name="NPU",
        )
        fake_transcribe = SimpleNamespace(backends=Mock(return_value=[accelerator, cpu]))
        with patch.dict(sys.modules, {"transcribe_cpp": fake_transcribe}):
            selected, label, provider = local_asr._choose_transcribe_device("cpu")
        self.assertIs(selected, cpu)
        self.assertEqual(label, "CPU")
        self.assertEqual(provider, "cpu")

    def test_transcribe_auto_does_not_bind_an_exact_device(self):
        cpu = self._transcribe_device(
            device_type="cpu",
            kind="cpu",
            device_id=0,
            index=0,
            name="CPU",
        )
        integrated_gpu = self._transcribe_device(
            device_type="igpu",
            kind="vulkan",
            device_id=1,
            index=1,
            name="Integrated GPU",
        )
        fake_transcribe = SimpleNamespace(
            backends=Mock(return_value=[cpu, integrated_gpu])
        )
        with patch.dict(sys.modules, {"transcribe_cpp": fake_transcribe}):
            selected, label, provider = local_asr._choose_transcribe_device("auto")
        self.assertIsNone(selected)
        self.assertIn("自动", label)
        self.assertEqual(provider, "auto")

    def test_transcribe_gpu_excludes_accel_and_prefers_cuda_then_vulkan(self):
        cpu = self._transcribe_device(
            device_type="cpu",
            kind="cpu",
            device_id=0,
            index=0,
            name="CPU",
        )
        accelerator = self._transcribe_device(
            device_type="accel",
            kind="accel",
            device_id=1,
            index=1,
            name="NPU",
        )
        vulkan = self._transcribe_device(
            device_type="igpu",
            kind="vulkan",
            device_id=2,
            index=2,
            name="Integrated GPU",
        )
        cuda = self._transcribe_device(
            device_type="gpu",
            kind="cuda",
            device_id=3,
            index=3,
            name="NVIDIA GPU",
        )
        cases = (
            ([accelerator, vulkan, cpu, cuda], cuda, "cuda"),
            ([accelerator, vulkan, cpu], vulkan, "vulkan"),
        )
        for devices, expected_device, expected_provider in cases:
            with self.subTest(expected_provider=expected_provider):
                fake_transcribe = SimpleNamespace(
                    backends=Mock(return_value=devices)
                )
                with patch.dict(sys.modules, {"transcribe_cpp": fake_transcribe}):
                    selected, label, provider = local_asr._choose_transcribe_device(
                        "gpu"
                    )
                self.assertIs(selected, expected_device)
                self.assertEqual(provider, expected_provider)
                self.assertIn(expected_provider.upper(), label)

    def test_transcribe_auto_model_uses_backend_instead_of_exact_device(self):
        cpu = self._transcribe_device(
            device_type="cpu",
            kind="cpu",
            device_id=0,
            index=0,
            name="CPU",
        )
        actual_device = self._transcribe_device(
            device_type="gpu",
            kind="cuda",
            device_id=1,
            index=1,
            name="NVIDIA GPU",
        )
        model = SimpleNamespace(device=actual_device, close=Mock())
        model_factory = Mock(return_value=model)
        fake_transcribe = SimpleNamespace(
            backends=Mock(return_value=[cpu, actual_device]),
            Model=model_factory,
        )
        with tempfile.TemporaryDirectory() as model_dir:
            with (
                patch.dict(sys.modules, {"transcribe_cpp": fake_transcribe}),
                patch.object(
                    local_asr,
                    "install_model_locally",
                    return_value=Path(model_dir),
                ),
                patch.object(local_asr, "ensure_resource_verified", return_value={}),
            ):
                recognizer = local_asr.LocalModelRecognizer(
                    local_asr.QWEN3_17_MODEL_ID,
                    "auto",
                )
                recognizer.load()
                recognizer.close()
        model_factory.assert_called_once_with(
            str(Path(model_dir) / local_asr.QWEN3_17_FILENAME),
            backend="auto",
        )

    def test_transcribe_loaded_model_label_uses_actual_device_kind(self):
        requested_device = self._transcribe_device(
            device_type="gpu",
            kind="cuda",
            device_id=1,
            index=1,
            name="NVIDIA GPU",
        )
        actual_device = self._transcribe_device(
            device_type="igpu",
            kind="vulkan",
            device_id=2,
            index=2,
            name="Integrated GPU",
        )
        model = SimpleNamespace(device=actual_device, close=Mock())
        fake_transcribe = SimpleNamespace(
            backends=Mock(return_value=[requested_device]),
            Model=Mock(return_value=model),
        )
        with tempfile.TemporaryDirectory() as model_dir:
            with (
                patch.dict(sys.modules, {"transcribe_cpp": fake_transcribe}),
                patch.object(
                    local_asr,
                    "install_model_locally",
                    return_value=Path(model_dir),
                ),
                patch.object(local_asr, "ensure_resource_verified", return_value={}),
            ):
                recognizer = local_asr.LocalModelRecognizer(
                    local_asr.QWEN3_17_MODEL_ID,
                    "gpu",
                )
                recognizer.load()
                self.assertEqual(recognizer.provider, "vulkan")
                self.assertIn("VULKAN", recognizer.device_label)
                self.assertNotIn("CUDA", recognizer.device_label)
                recognizer.close()

    def test_transcribe_recognizer_close_is_idempotent(self):
        cpu = self._transcribe_device(
            device_type="cpu",
            kind="cpu",
            device_id=0,
            index=0,
            name="CPU",
        )
        model = SimpleNamespace(device=cpu, close=Mock())
        fake_transcribe = SimpleNamespace(
            backends=Mock(return_value=[cpu]),
            Model=Mock(return_value=model),
        )
        with tempfile.TemporaryDirectory() as model_dir:
            with (
                patch.dict(sys.modules, {"transcribe_cpp": fake_transcribe}),
                patch.object(
                    local_asr,
                    "install_model_locally",
                    return_value=Path(model_dir),
                ),
                patch.object(local_asr, "ensure_resource_verified", return_value={}),
            ):
                recognizer = local_asr.LocalModelRecognizer(
                    local_asr.QWEN3_17_MODEL_ID,
                    "cpu",
                )
                recognizer.load()
                recognizer.close()
                recognizer.close()
        model.close.assert_called_once_with()

    def test_catalog_is_json_serializable_and_has_hardware_details(self):
        catalog = local_asr.get_local_model_catalog()
        self.assertEqual(
            {item["id"] for item in catalog},
            {
                "qwen3-asr-0.6b-int8",
                "faster-whisper-small",
                "qwen3-asr-1.7b-q5km",
            },
        )
        json.dumps(catalog, ensure_ascii=False)
        for item in catalog:
            self.assertEqual(
                {"minimum", "recommended", "gpu", "note"},
                set(item["hardware"]),
            )
            self.assertIsInstance(item["capabilities"], list)
            self.assertIn("中文", item["language_support"])
            self.assertIn("英文", item["language_support"])
            self.assertIn("installed", item)
            self.assertIn("runtime_ready", item)

    def test_qwen_17_has_one_download_resource(self):
        resources = local_asr.get_downloadable_model_resources()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["size_bytes"], 1_517_290_464)
        self.assertEqual(
            resources[0]["sha256"],
            "034c557fe92ff8fcd9a9c041cbdaad347be0a86a58d3a348f63cf3f0180879d0",
        )

    def test_qwen_17_rejects_partial_file_even_when_nonempty(self):
        with tempfile.TemporaryDirectory() as source_root, tempfile.TemporaryDirectory() as local_root:
            local_dir = Path(local_root) / local_asr.QWEN3_17_RESOURCE_ID
            local_dir.mkdir()
            (local_dir / local_asr.QWEN3_17_FILENAME).write_bytes(b"partial")
            with (
                patch.object(local_asr, "MODEL_SOURCE_ROOT", Path(source_root)),
                patch.object(local_asr, "LOCAL_MODELS_DIR", Path(local_root)),
            ):
                status = local_asr.get_local_model_status(local_asr.QWEN3_17_MODEL_ID)
        self.assertFalse(status["installed"])
        self.assertIn(local_asr.QWEN3_17_FILENAME, status["missing_files"])

    def test_qwen_17_catalog_requires_matching_verification_receipt(self):
        payload = b"verified-qwen17-model"
        metadata = self._qwen17_metadata_for_payload(payload)
        with tempfile.TemporaryDirectory() as source_root, tempfile.TemporaryDirectory() as local_root:
            local_dir = Path(local_root) / local_asr.QWEN3_17_RESOURCE_ID
            local_dir.mkdir()
            (local_dir / local_asr.QWEN3_17_FILENAME).write_bytes(payload)
            with (
                patch.dict(
                    local_asr.LOCAL_MODELS,
                    {local_asr.QWEN3_17_MODEL_ID: metadata},
                ),
                patch.object(local_asr, "MODEL_SOURCE_ROOT", Path(source_root)),
                patch.object(local_asr, "LOCAL_MODELS_DIR", Path(local_root)),
                patch.object(
                    local_asr,
                    "_runtime_status",
                    return_value=(True, "运行组件可用。"),
                ),
            ):
                before = next(
                    item
                    for item in local_asr.get_local_model_catalog()
                    if item["model_id"] == local_asr.QWEN3_17_MODEL_ID
                )
                self.assertTrue(before["installed"])
                self.assertTrue(before["cached_locally"])
                self.assertFalse(before["verified"])
                self.assertFalse(before["available"])
                self.assertEqual(before["status"], "待校验")
                self.assertIn("校验模型", before["status_message"])

                local_asr.install_model_locally(local_asr.QWEN3_17_MODEL_ID)
                after = local_asr.get_local_model_status(
                    local_asr.QWEN3_17_MODEL_ID
                )
            self.assertTrue(after["verified"])
            self.assertTrue(after["available"])
            self.assertEqual(after["status"], "已安装")
            self.assertIn("SHA-256", after["status_message"])

    def test_qwen_17_development_source_remains_installable_without_receipt(self):
        payload = b"development-qwen17-model"
        metadata = self._qwen17_metadata_for_payload(payload)
        with tempfile.TemporaryDirectory() as source_root, tempfile.TemporaryDirectory() as local_root:
            source_dir = Path(source_root) / str(metadata["source_directory"])
            source_dir.mkdir(parents=True)
            (source_dir / local_asr.QWEN3_17_FILENAME).write_bytes(payload)
            with (
                patch.dict(
                    local_asr.LOCAL_MODELS,
                    {local_asr.QWEN3_17_MODEL_ID: metadata},
                ),
                patch.object(local_asr, "MODEL_SOURCE_ROOT", Path(source_root)),
                patch.object(local_asr, "LOCAL_MODELS_DIR", Path(local_root)),
                patch.object(
                    local_asr,
                    "_runtime_status",
                    return_value=(True, "运行组件可用。"),
                ),
            ):
                status = local_asr.get_local_model_status(
                    local_asr.QWEN3_17_MODEL_ID
                )
            self.assertTrue(status["bundled"])
            self.assertFalse(status["cached_locally"])
            self.assertFalse(status["verified"])
            self.assertTrue(status["available"])
            self.assertEqual(status["status"], "可安装")

    def test_qwen_17_install_rejects_same_size_corrupted_cache(self):
        expected_payload = b"correct-qwen17-model"
        corrupted_payload = b"damaged-qwen17-model"
        self.assertEqual(len(expected_payload), len(corrupted_payload))
        metadata = self._qwen17_metadata_for_payload(expected_payload)
        with tempfile.TemporaryDirectory() as source_root, tempfile.TemporaryDirectory() as local_root:
            local_dir = Path(local_root) / local_asr.QWEN3_17_RESOURCE_ID
            local_dir.mkdir()
            (local_dir / local_asr.QWEN3_17_FILENAME).write_bytes(corrupted_payload)
            with (
                patch.dict(
                    local_asr.LOCAL_MODELS,
                    {local_asr.QWEN3_17_MODEL_ID: metadata},
                ),
                patch.object(local_asr, "MODEL_SOURCE_ROOT", Path(source_root)),
                patch.object(local_asr, "LOCAL_MODELS_DIR", Path(local_root)),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "SHA-256.*删除模型后重新下载",
                ):
                    local_asr.install_model_locally(local_asr.QWEN3_17_MODEL_ID)

    def test_qwen_17_install_calls_persistent_verifier_with_fixed_manifest(self):
        payload = b"installable-qwen17-model"
        metadata = self._qwen17_metadata_for_payload(payload)
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as source_root, tempfile.TemporaryDirectory() as local_root:
            source_dir = Path(source_root) / str(metadata["source_directory"])
            source_dir.mkdir(parents=True)
            (source_dir / local_asr.QWEN3_17_FILENAME).write_bytes(payload)
            with (
                patch.dict(
                    local_asr.LOCAL_MODELS,
                    {local_asr.QWEN3_17_MODEL_ID: metadata},
                ),
                patch.object(local_asr, "MODEL_SOURCE_ROOT", Path(source_root)),
                patch.object(local_asr, "LOCAL_MODELS_DIR", Path(local_root)),
                patch.object(
                    local_asr,
                    "ensure_resource_verified",
                    return_value={},
                ) as verifier,
            ):
                installed = local_asr.install_model_locally(
                    local_asr.QWEN3_17_MODEL_ID
                )
            verifier.assert_called_once_with(
                local_asr.QWEN3_17_RESOURCE_ID,
                installed / local_asr.QWEN3_17_FILENAME,
                "test-resource@receipt-v1",
                len(payload),
                digest,
            )

    def test_qwen_17_load_blocks_transcribe_cpp_when_verification_fails(self):
        cpu = self._transcribe_device(
            device_type="cpu",
            kind="cpu",
            device_id=0,
            index=0,
            name="CPU",
        )
        model_factory = Mock()
        fake_transcribe = SimpleNamespace(
            backends=Mock(return_value=[cpu]),
            Model=model_factory,
        )
        with tempfile.TemporaryDirectory() as model_dir:
            with (
                patch.dict(sys.modules, {"transcribe_cpp": fake_transcribe}),
                patch.object(
                    local_asr,
                    "install_model_locally",
                    return_value=Path(model_dir),
                ),
                patch.object(
                    local_asr,
                    "ensure_resource_verified",
                    side_effect=local_asr.ResourceVerificationError(
                        "SHA-256 完整性校验失败"
                    ),
                ),
            ):
                recognizer = local_asr.LocalModelRecognizer(
                    local_asr.QWEN3_17_MODEL_ID,
                    "cpu",
                )
                with self.assertRaisesRegex(
                    RuntimeError,
                    "SHA-256.*重新下载",
                ):
                    recognizer.load()
        model_factory.assert_not_called()

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
                patch.object(local_asr, "ensure_resource_verified") as verifier,
                patch.object(
                    local_asr,
                    "_runtime_status",
                    return_value=(True, "运行组件可用。"),
                ),
            ):
                installed = local_asr.install_model_locally(local_asr.PARAFORMER_MODEL_ID)
                status = local_asr.get_local_model_status(local_asr.PARAFORMER_MODEL_ID)
            self.assertEqual(installed, Path(local_root) / local_asr.PARAFORMER_MODEL_ID)
            self.assertEqual((installed / "model.int8.onnx").read_bytes(), b"paraformer")
            self.assertTrue(status["cached_locally"])
            self.assertEqual(status["status"], "已安装")
            verifier.assert_not_called()

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
