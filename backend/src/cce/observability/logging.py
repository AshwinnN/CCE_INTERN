"""Application diagnostic logging.

`configure_logging()` sets up the root logger so every `logging.getLogger(...)`
call anywhere in the codebase writes to both the terminal and a rotating file
under `<repo root>/logs/`, tagged with the file path (relative to the repo
root), line number and function name.

The ingestion/connector/agentic-plane code paths call `logging.getLogger(__name__)`
and log at each meaningful step (connect, list, extract, paginate, send to
index) themselves -- see e.g. `sources/service.py`, `connectors/structured/
snowflake/connector.py`, `connectors/unstructured/azure_blob/connector.py`,
`ingestion/orchestrator.py` and `integrations/agentic_plane/client.py`. This
module only owns the handler/formatter plumbing those loggers write through.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path

# backend/src/cce/observability/logging.py -> repo root is 4 levels up.
PROJECT_ROOT = Path(__file__).resolve().parents[4]
LOG_DIR = Path(os.environ.get("CCE_LOG_DIR", str(PROJECT_ROOT / "logs")))

_configured = False


def _session_log_filename() -> str:
    return "cce_%s.log" % datetime.now().strftime("%Y%m%d_%H%M%S")


class _RelativePathFilter(logging.Filter):
    """Rewrites record.pathname into a repo-root-relative path for display."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.relpath = os.path.relpath(record.pathname, PROJECT_ROOT)
        except ValueError:
            record.relpath = record.pathname
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger with a console handler and a rotating file
    handler under `logs/`. Safe to call more than once."""
    global _configured

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    resolved_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(min(resolved_level, logging.INFO))

    if _configured:
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s %(relpath)s:%(lineno)d %(funcName)s() - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    path_filter = _RelativePathFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(resolved_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(path_filter)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / _session_log_filename(),
        maxBytes=20 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(path_filter)

    root.addHandler(console_handler)
    root.addHandler(file_handler)
    _configured = True
