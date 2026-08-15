from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def build_loggers(log_dir: Path, component: str = "") -> tuple[logging.Logger, logging.Logger]:
    """创建相互独立、自动轮转的运行日志和错误日志。"""
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger_component = component.strip() or "main"
    file_prefix = f"{component.strip()}-" if component.strip() else ""
    run_logger = logging.getLogger(f"voice_button.{logger_component}.run")
    error_logger = logging.getLogger(f"voice_button.{logger_component}.error")
    for logger in (run_logger, error_logger):
        logger.setLevel(logging.INFO)
        logger.propagate = False
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)

    run_handler = RotatingFileHandler(
        log_dir / f"{file_prefix}运行.log", maxBytes=512 * 1024, backupCount=1, encoding="utf-8"
    )
    error_handler = RotatingFileHandler(
        log_dir / f"{file_prefix}错误.log", maxBytes=512 * 1024, backupCount=1, encoding="utf-8"
    )
    run_handler.setFormatter(formatter)
    error_handler.setFormatter(formatter)
    run_logger.addHandler(run_handler)
    error_logger.addHandler(error_handler)
    return run_logger, error_logger
