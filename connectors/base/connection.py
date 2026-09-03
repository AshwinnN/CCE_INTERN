#!/usr/bin/env python3
"""A proven-safe handle to a structured source. Only ever constructed after
a real write-probe has denied a write -- see each adapter's connect()."""
from datetime import datetime, timezone


class StructuredConnection:
    def __init__(self, connector: "StructuredConnector", connection_id: str):  # noqa: F821
        self.connector = connector
        self.connection_id = connection_id
        self.read_only_verified = True   # only ever true -- connect() raises rather than
                                          # returning a StructuredConnection when the probe fails
        self.created_at = datetime.now(timezone.utc)
