"""
Logging system with JSON format and rotation
"""
import os
import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Custom formatter for JSON logs"""

    def format(self, record):
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, 'run_id'):
            log_data['run_id'] = record.run_id
        if hasattr(record, 'environment'):
            log_data['environment'] = record.environment
        if hasattr(record, 'test_suite'):
            log_data['test_suite'] = record.test_suite
        if hasattr(record, 'test_case'):
            log_data['test_case'] = record.test_case
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms
        if hasattr(record, 'status'):
            log_data['status'] = record.status
        if hasattr(record, 'details'):
            log_data['details'] = record.details

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


class MonitorLogger:
    """Logger for monitoring system"""

    def __init__(self, name="monitor", log_dir=None, config=None):
        self.name = name
        self.config = config or {}

        # Setup log directory
        if log_dir is None:
            base_dir = Path(__file__).parent.parent
            log_dir = base_dir / "reports"
        else:
            log_dir = Path(log_dir)

        log_dir.mkdir(parents=True, exist_ok=True)

        # Setup logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, self.config.get('level', 'INFO')))
        self.logger.handlers = []  # Clear existing handlers

        # File handler with rotation
        log_file = log_dir / f"{name}.log"
        max_bytes = self.config.get('rotate_size_mb', 10) * 1024 * 1024
        backup_count = self.config.get('keep_days', 30)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )

        if self.config.get('format', 'json') == 'json':
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            )

        self.logger.addHandler(file_handler)

        # Console handler (optional)
        if self.config.get('console_output', True):
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            )
            self.logger.addHandler(console_handler)

    def debug(self, msg, **kwargs):
        """Log debug message"""
        self.logger.debug(msg, extra=kwargs)

    def info(self, msg, **kwargs):
        """Log info message"""
        self.logger.info(msg, extra=kwargs)

    def warning(self, msg, **kwargs):
        """Log warning message"""
        self.logger.warning(msg, extra=kwargs)

    def error(self, msg, **kwargs):
        """Log error message"""
        self.logger.error(msg, extra=kwargs)

    def critical(self, msg, **kwargs):
        """Log critical message"""
        self.logger.critical(msg, extra=kwargs)

    def test_result(self, run_id, environment, test_suite, test_case,
                    status, duration_ms, details=None, error=None):
        """Log test result in structured format"""
        extra = {
            'run_id': run_id,
            'environment': environment,
            'test_suite': test_suite,
            'test_case': test_case,
            'status': status,
            'duration_ms': duration_ms,
        }

        if details:
            extra['details'] = details

        level = logging.INFO if status == 'PASS' else logging.ERROR
        msg = f"Test {test_case}: {status}"

        if error:
            msg += f" - {error}"

        self.logger.log(level, msg, extra=extra)


def get_logger(name="monitor", log_dir=None, config=None):
    """Get or create logger instance"""
    return MonitorLogger(name, log_dir, config)
