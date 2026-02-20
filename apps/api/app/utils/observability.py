"""
Phase 4.6: Structured logging for observability.
"""
import json
import logging
from typing import Any


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """
    Emit a single-line JSON log. Drops None values. Safe if fields are missing.
    """
    payload: dict[str, Any] = {"event": event}
    for k, v in fields.items():
        if v is not None:
            payload[k] = v
    try:
        out = json.dumps(payload, default=str)
    except (TypeError, ValueError):
        out = json.dumps({"event": event, "error": "serialization_failed"})
    logger.info(out)
