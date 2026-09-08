#!/usr/bin/env python3
"""A structured-source handle that records whether read-only access was proven."""
from datetime import datetime, timezone


class StructuredConnection:
    def __init__(
        self,
        connector: "StructuredConnector",  # noqa: F821
        connection_id: str,
        *,
        read_only_verified: bool = True,
    ):
        self.connector = connector
        self.connection_id = connection_id
        self.read_only_verified = read_only_verified
        self.created_at = datetime.now(timezone.utc)
