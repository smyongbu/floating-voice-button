import unittest
from pathlib import Path
from unittest.mock import patch

import realtime_asr


class PackagedModelPathTests(unittest.TestCase):
    def test_packaged_realtime_model_uses_models_next_to_executable(self):
        executable = Path("C:/Apps/语点/语点.exe")
        with (
            patch.object(realtime_asr.sys, "frozen", True, create=True),
            patch.object(realtime_asr.sys, "executable", str(executable)),
        ):
            self.assertEqual(
                realtime_asr._default_model_repository(),
                executable.parent / "models",
            )


if __name__ == "__main__":
    unittest.main()
