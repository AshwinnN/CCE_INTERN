#!/usr/bin/env python3
"""Exception hierarchy for the connectors/ package.

One base class, adapter-specific subclasses live next to the adapter that
raises them (e.g. connectors/snowflake/errors.py), never here -- this file
must never gain a vendor name (see connectors/base/connector.py's module
docstring for the same discipline applied to the ABC).
"""


class StructuredConnectorException(Exception):
    """Base for every exception this package raises."""


class UnsupportedAdapterError(StructuredConnectorException):
    """Raised by ConnectorFactory.create() for an adapter with no
    registered implementation."""


class ConnectionFailedError(StructuredConnectorException):
    """The driver-level connection attempt itself failed (auth, network,
    timeout) -- distinct from a write-probe failure, which means the
    connection succeeded but proved unsafe."""


class WriteAccessDetectedError(StructuredConnectorException):
    """The write-probe's write succeeded -- the credential is NOT
    read-only. This is the one failure mode connect() must never downgrade
    to a warning: a connection that can write is rejected, not returned."""


class NotConnectedError(StructuredConnectorException):
    """A method that requires an open connection (get_schema_card,
    execute_query) was called before connect() or after close()."""
