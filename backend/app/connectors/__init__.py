#!/usr/bin/env python3
"""Deterministic source connectors.

One interface (connectors.base.StructuredConnector), many implementations
(connectors.snowflake.SnowflakeConnector today). Callers go through
connectors.factory.ConnectorFactory and never import a concrete adapter.
"""
from connectors.base import ConnectionConfig, StructuredConnection, StructuredConnector
from connectors.factory import ConnectorFactory

__all__ = ["ConnectionConfig", "StructuredConnection", "StructuredConnector", "ConnectorFactory"]
