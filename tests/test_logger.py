import logging
import tempfile
import unittest
from pathlib import Path

from logger import build_loggers


class LoggerTests(unittest.TestCase):
    def test_run_and_error_logs_are_separate_and_correlated(self):
        with tempfile.TemporaryDirectory() as temp:
            run, error = build_loggers(Path(temp))
            run.info("操作开始 | 编号=test1234 | 阶段=测试")
            error.warning("操作失败 | 编号=test1234 | 阶段=测试 | 原因=模拟")
            for logger in (run, error):
                for handler in logger.handlers:
                    handler.flush()
            run_text = (Path(temp) / "运行.log").read_text(encoding="utf-8")
            error_text = (Path(temp) / "错误.log").read_text(encoding="utf-8")
            self.assertIn("操作开始", run_text)
            self.assertNotIn("操作失败", run_text)
            self.assertIn("操作失败", error_text)
            self.assertIn("test1234", run_text)
            self.assertIn("test1234", error_text)
            for logger in (run, error):
                for handler in list(logger.handlers):
                    handler.close()
                    logger.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
