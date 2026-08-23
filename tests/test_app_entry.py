import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app


class AppEntryTests(unittest.TestCase):
    def test_settings_panel_argument_routes_to_panel_without_main_app(self):
        panel_main = Mock()
        fake_panel = SimpleNamespace(main=panel_main)
        with (
            patch.object(sys, "argv", ["语点.exe", "--settings-panel"]),
            patch.dict(sys.modules, {"settings_panel": fake_panel}),
            patch.object(app, "main") as main_app,
        ):
            app.run_entrypoint()
        panel_main.assert_called_once_with()
        main_app.assert_not_called()

    def test_frozen_app_opens_panel_through_same_executable(self):
        instance = SimpleNamespace(
            panel_process=None,
            run_log=Mock(),
            error_log=Mock(),
            closed=False,
            _check_panel_startup=Mock(),
            _warning=Mock(),
        )
        process = Mock()
        process.poll.return_value=None
        with (
            patch.object(app, "list_windows", return_value=[]),
            patch.object(app.sys, "frozen", True, create=True),
            patch.object(app.sys, "executable", "C:\\Apps\\语点\\语点.exe"),
            patch.object(app.subprocess, "Popen", return_value=process) as popen,
            patch.object(app.threading, "Thread") as thread,
        ):
            app.VoiceButtonApp._open_panel(instance)
        popen.assert_called_once_with(
            ["C:\\Apps\\语点\\语点.exe", "--settings-panel"],
            cwd=str(Path("C:\\Apps\\语点\\语点.exe").resolve().parent),
            creationflags=getattr(app.subprocess, "CREATE_NO_WINDOW", 0),
        )
        thread.assert_called_once()


if __name__ == "__main__":
    unittest.main()
