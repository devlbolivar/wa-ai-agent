import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict

class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings after parsing the LogRecord.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_record: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra_info"):
            log_record["extra"] = record.extra_info  # type: ignore

        return json.dumps(log_record)

def setup_logging(level: int = logging.INFO) -> None:
    """
    Configures the root logger to use the JSON formatter.
    """
    logger = logging.getLogger()
    logger.setLevel(level)

    # Remove all default handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JSONFormatter())
    logger.addHandler(console_handler)

    # Disable uvicorn access logs from duplicating if needed, 
    # but normally uvicorn has its own loggers. We can intercept them.
    # We apply our formatter to uvicorn loggers as well:
    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.handlers = []
        uvicorn_logger.addHandler(console_handler)
        uvicorn_logger.propagate = False
