from __future__ import annotations

import logging
import sys
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler


class LoggingConfigurator:
    def __init__(self, log_dir: Path, level: str = "INFO") -> None:
        self.log_dir = log_dir
        self.level = getattr(logging, level.upper(), logging.INFO)
        self._configured = False

    def configure(self) -> None:
        if self._configured:
            return

        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.log_dir / f"tgpassure_{datetime.now().strftime('%Y%m%d')}.log"

        root_logger = logging.getLogger()
        root_logger.setLevel(self.level)

        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5
        )
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = logging.Formatter(
            '%(levelname)s: %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

        self._configured = True

    def get_logger(self, name: str) -> logging.Logger:
        return logging.getLogger(name)