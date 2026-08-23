import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config_store
import local_asr
import realtime_asr


class PackagedModelPathTests(unittest.TestCase):
    def test_packaged_model_sources_ignore_development_override(self):
        executable = Path("C:/Apps/语点/语点.exe")
        with (
            patch.object(realtime_asr.sys, "frozen", True, create=True),
            patch.object(realtime_asr.sys, "executable", str(executable)),
            patch.dict(
                realtime_asr.os.environ,
                {realtime_asr.MODEL_REPOSITORY_ENV: "D:/development-models"},
            ),
        ):
            self.assertEqual(
                realtime_asr._model_repository_root(),
                executable.parent / "models",
            )
            self.assertEqual(
                local_asr._model_repository_root(),
                executable.parent / "models",
            )

    def test_packaged_cache_uses_release_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            app_data = Path(directory) / "FloatingVoiceButton"
            with (
                patch.object(config_store.sys, "frozen", True, create=True),
                patch.object(config_store, "APP_DATA_DIR", app_data),
            ):
                self.assertEqual(
                    config_store._default_model_cache_dir(),
                    app_data / config_store.MODEL_CACHE_NAMESPACE,
                )
            with patch.object(config_store.sys, "frozen", False, create=True):
                self.assertEqual(
                    config_store._default_model_cache_dir(),
                    config_store.APP_DATA_DIR / "models",
                )

    def test_packaged_catalog_ignores_development_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "package-models"
            release_cache = root / config_store.MODEL_CACHE_NAMESPACE
            development_model = root / "models" / local_asr.QWEN3_MODEL_ID
            development_model.mkdir(parents=True)
            metadata = local_asr.LOCAL_MODELS[local_asr.QWEN3_MODEL_ID]
            for relative in metadata["required_files"]:
                path = development_model / Path(relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"development-cache")

            with (
                patch.object(local_asr, "MODEL_SOURCE_ROOT", source_root),
                patch.object(local_asr, "LOCAL_MODELS_DIR", release_cache),
                patch.object(
                    local_asr,
                    "_runtime_status",
                    return_value=(True, "运行组件可用。"),
                ),
            ):
                status = local_asr.get_local_model_status(local_asr.QWEN3_MODEL_ID)

            self.assertFalse(status["installed"])
            self.assertFalse(status["available"])
            self.assertEqual(status["status"], "未安装")
            self.assertEqual(
                Path(status["local_path"]),
                release_cache / local_asr.QWEN3_MODEL_ID,
            )
            with patch.object(realtime_asr, "MODEL_CACHE_DIR", release_cache):
                _model_id, _spec, _source, local_dir = realtime_asr._model_paths(
                    config_store.DEFAULT_REALTIME_MODEL
                )
            self.assertEqual(
                local_dir,
                release_cache / config_store.DEFAULT_REALTIME_MODEL,
            )

    def test_frozen_first_import_captures_release_paths(self):
        script = """
import os
import sys
from pathlib import Path

sys.frozen = True
import config_store
import local_asr
import realtime_asr

expected_cache = (
    Path(os.environ["LOCALAPPDATA"])
    / "FloatingVoiceButton"
    / config_store.MODEL_CACHE_NAMESPACE
)
expected_source = Path(sys.executable).resolve().parent / "models"
assert config_store.MODEL_CACHE_DIR == expected_cache
assert local_asr.LOCAL_MODELS_DIR == expected_cache
assert realtime_asr.MODEL_CACHE_DIR == expected_cache
assert local_asr.MODEL_SOURCE_ROOT == expected_source
assert realtime_asr.MODEL_REPOSITORY_ROOT == expected_source
"""
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment["LOCALAPPDATA"] = directory
            environment["VOICE_INPUT_MODEL_REPOSITORY"] = str(
                Path(directory) / "development-models"
            )
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
