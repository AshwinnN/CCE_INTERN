#!/usr/bin/env python3
"""Deterministic structured-source connectors -- replaces
skill-strucutred_source_connect's simulated write-probe with a real one.
See structured_connector_architecture.md and
structured_connector_quick_reference.md for the design.

One interface (connectors.base.StructuredConnector), many implementations
(connectors.snowflake.SnowflakeConnector today). Callers go through
connectors.factory.ConnectorFactory and never import a concrete adapter.
"""
from connectors.base import ConnectionConfig, StructuredConnection, StructuredConnector
from connectors.factory import ConnectorFactory

__all__ = ["ConnectionConfig", "StructuredConnection", "StructuredConnector", "ConnectorFactory"]
