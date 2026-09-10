import json
import logging

from app.core.clock import utc_now


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Application events contain no payloads, credentials, URLs or exception messages.
        output = {
            "timestamp": utc_now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key in ("request_id", "correlation_id", "method", "status_code", "latency_ms"):
            if hasattr(record, key):
                output[key] = getattr(record, key)
        if record.exc_info and record.exc_info[0]:
            output["error_type"] = record.exc_info[0].__name__
        return json.dumps(output, ensure_ascii=False)


def configure_logging(level: str) -> None:
    logger = logging.getLogger("bot_inversiones")
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
