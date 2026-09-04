#!/usr/bin/env python3
"""Deterministic source connector backed by caller-provided reader functions."""
from typing import Callable, Dict, Optional

from cce.connectors.base.source import SourceConnection, SourceConnector


class DeterministicSourceConnector(SourceConnector):
    """A small adapter for source integrations whose I/O is injected by code."""

    def __init__(self, source_id: str, adapter: str,
                 object_lister: Optional[Callable[[Optional[str]], Dict]] = None,
                 object_fetcher: Optional[Callable[[str], bytes]] = None):
        self.source_id = source_id
        self.adapter = adapter
        self._object_lister = object_lister
        self._object_fetcher = object_fetcher
        self._connected = False

    def connect(self) -> SourceConnection:
        self._connected = True
        return SourceConnection(
            connector=self,
            connection_id="src_conn_%s" % self.source_id,
            source_id=self.source_id,
            adapter=self.adapter,
        )

    def list_objects(self, cursor: Optional[str] = None) -> Dict:
        if not self._connected:
            raise RuntimeError("list_objects called before connect()")
        if self._object_lister is None:
            raise RuntimeError("no object_lister configured for adapter %r" % self.adapter)
        return self._object_lister(cursor)

    def fetch_object(self, object_id: str) -> bytes:
        if not self._connected:
            raise RuntimeError("fetch_object called before connect()")
        if self._object_fetcher is None:
            raise RuntimeError("no object_fetcher configured for adapter %r" % self.adapter)
        return self._object_fetcher(object_id)

    def close(self) -> None:
        self._connected = False
