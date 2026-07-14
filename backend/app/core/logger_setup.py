import json
import logging
import sys
import time
from contextlib import contextmanager
from typing import Any, Iterator


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if hasattr(record, "extra_payload"):
            payload.update(getattr(record, "extra_payload"))
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


logger = logging.getLogger("ai_sql_assistant")


def log_event(message: str, **payload: Any) -> None:
    logger.info(message, extra={"extra_payload": payload})


# observability - який вузол скільки виконувався, чи помилка при завершенні
@contextmanager
def log_node(session_id: str, thread_id: str, node_name: str) -> Iterator[None]:
    started = time.perf_counter()
    log_event(message="node.enter", session_id=session_id, thread_id=thread_id, node_name=node_name)
    try:
        yield
    except Exception as e:
        duration_ms = int((time.perf_counter() - started) * 1000)
        log_event(
            message="node.exit",
            session_id=session_id,
            thread_id=thread_id,
            node_name=node_name,
            duration_ms=duration_ms,
            status="error",
            error=str(e),
        )
        raise
    else:
        duration_ms = int((time.perf_counter() - started) * 1000)
        log_event(
            message="node.exit",
            session_id=session_id,
            thread_id=thread_id,
            node_name=node_name,
            duration_ms=duration_ms,
            status="ok",
        )
