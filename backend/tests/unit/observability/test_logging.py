import logging
import logging.handlers
from pathlib import Path

import pytest

from cce.observability import logging as obs_logging


@pytest.fixture(autouse=True)
def _isolate_logging_state(monkeypatch):
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", list(root.handlers))
    monkeypatch.setattr(root, "level", root.level)
    monkeypatch.setattr(obs_logging, "_configured", False)
    yield


def test_configure_logging_creates_log_dir_and_handlers(tmp_path, monkeypatch):
    monkeypatch.setattr(obs_logging, "LOG_DIR", tmp_path / "logs")

    obs_logging.configure_logging("DEBUG")

    assert (tmp_path / "logs").is_dir()
    root = logging.getLogger()
    assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    assert any(
        isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers
    )


def test_configure_logging_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(obs_logging, "LOG_DIR", tmp_path / "logs")

    obs_logging.configure_logging("INFO")
    handler_count = len(logging.getLogger().handlers)
    obs_logging.configure_logging("INFO")

    assert len(logging.getLogger().handlers) == handler_count


def test_relative_path_filter_rewrites_pathname_relative_to_repo_root():
    filt = obs_logging._RelativePathFilter()
    traced_file = obs_logging.PROJECT_ROOT / "backend" / "src" / "cce" / "foo.py"
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=str(traced_file),
        lineno=10,
        msg="hello",
        args=(),
        exc_info=None,
    )

    assert filt.filter(record) is True
    assert record.relpath == str(Path("backend") / "src" / "cce" / "foo.py")
