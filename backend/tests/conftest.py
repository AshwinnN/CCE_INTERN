"""Pytest path setup for the backend src layout."""

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def isolate_process_global_test_state():
    from cce.connectors.factory import ConnectorFactory
    from cce.skills.loader import _CACHE as skill_loader_cache

    skill_cache_snapshot = dict(skill_loader_cache)
    structured_connectors = dict(ConnectorFactory._connectors)
    unstructured_connectors = dict(ConnectorFactory._unstructured_connectors)
    try:
        yield
    finally:
        skill_loader_cache.clear()
        skill_loader_cache.update(skill_cache_snapshot)
        ConnectorFactory._connectors.clear()
        ConnectorFactory._connectors.update(structured_connectors)
        ConnectorFactory._unstructured_connectors.clear()
        ConnectorFactory._unstructured_connectors.update(unstructured_connectors)
