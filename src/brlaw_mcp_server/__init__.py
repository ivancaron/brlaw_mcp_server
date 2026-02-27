"""A MCP server for agentic legal research on Brazilian law using official sources."""

import logging
import sys
import traceback
from pathlib import Path
from types import TracebackType
from typing import Any, override

from pythonjsonlogger.json import JsonFormatter

__all__ = []


class _Formatter(JsonFormatter):
    @override
    def add_fields(
        self,
        log_record: dict[str, Any],  # pyright: ignore[reportExplicitAny]
        record: logging.LogRecord,
        message_dict: dict[str, Any],  # pyright: ignore[reportExplicitAny]
    ) -> None:
        super().add_fields(log_record, record, message_dict)

        if record.exc_info:
            exc_type, exc_value, exc_traceback = record.exc_info

            log_record["exception"] = {
                "exc_type": exc_type.__name__ if exc_type else None,
                "exc_value": str(exc_value),
                "traceback": traceback.format_exception(
                    exc_type, exc_value, exc_traceback
                ),
            }

            log_record.pop("exc_info", None)
            log_record.pop("exc_text", None)


_formatter = _Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")

# To avoid losing important information, logs with WARNING level and above are also written to a
# persistent file.
_file_handler = logging.FileHandler(Path(__file__).parent.parent.parent / "mcp.log")
_file_handler.setLevel(logging.INFO)

_stream_handler = logging.StreamHandler()

_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)

for handler in [_stream_handler, _file_handler]:
    handler.setFormatter(_formatter)
    _root_logger.addHandler(handler)


def handle_uncaught_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType,
) -> None:
    """Handle uncaught exceptions."""

    _root_logger.critical(
        "Uncaught exception, application will exit",
        exc_info=(exc_type, exc_value, exc_traceback),
    )


sys.excepthook = handle_uncaught_exception
