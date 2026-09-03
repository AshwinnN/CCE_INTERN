#!/usr/bin/env python3
"""Real, deterministic Snowflake connector -- no skill, no simulation.

Replaces skill-strucutred_source_connect for this adapter: that skill's
write-probe was a caller-supplied boolean (`_probe_write_succeeds`) that
production code never actually set, so its STR03 "prove read-only with a
live write probe" guarantee was never enforced end to end. connect() here
runs a real CREATE TEMPORARY TABLE probe against a real connection --
same technique tools/verify_snowflake_connection.py already validated
live -- and raises rather than returning a handle when the probe's write
succeeds.

`driver_connect` is injected (default: the real snowflake.connector.connect)
so tests can supply a fake DB-API connection without live credentials or
network access -- the same fixture-injection convention every other
live-driver touchpoint in this repo already uses (change_capture.py's
object_lister/catalog_lister, ingestion's azure blob client).
"""
import time
from typing import Any, Callable, Dict, List, Optional

from connectors.base.connection import StructuredConnection
from connectors.base.connector import StructuredConnector
from connectors.base.exceptions import ConnectionFailedError, NotConnectedError, WriteAccessDetectedError
from connectors.base.models import ConnectionConfig
from common.tools.credential_loader import load_snowflake_keypair_credential

PROBE_TABLE = "__CCE_WRITE_PROBE__"


def _quote_identifier(value: str) -> str:
    return '"%s"' % value.replace('"', '""')


def _default_driver_connect(**kwargs):
    import snowflake.connector
    return snowflake.connector.connect(**kwargs)


def _private_key_der(pem: str, passphrase: Optional[str]) -> bytes:
    from cryptography.hazmat.primitives import serialization
    raw = pem.replace("\\n", "\n").encode()
    key = serialization.load_pem_private_key(raw, password=passphrase.encode() if passphrase else None)
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


class SnowflakeConnector(StructuredConnector):

    def __init__(self, config: ConnectionConfig,
                 driver_connect: Optional[Callable[..., Any]] = None):
        """Does NOT connect yet -- connect() does that."""
        self.config = config
        self._driver_connect = driver_connect or _default_driver_connect
        self._connection = None

    def connect(self) -> StructuredConnection:
        try:
            credential = load_snowflake_keypair_credential(self.config.credential_ref)
            private_key = _private_key_der(credential["private_key_pem"], credential["passphrase"])
            self._connection = self._driver_connect(
                account=self.config.account_id,
                user=self.config.user,
                private_key=private_key,
                role=self.config.role,
                warehouse=self.config.warehouse,
                database=self.config.database,
                schema=self.config.schema,
                login_timeout=self.config.login_timeout_s,
                network_timeout=self.config.network_timeout_s,
            )
        except Exception as e:
            raise ConnectionFailedError("snowflake connect failed: %s" % e) from e

        if self._run_write_probe():
            # Write succeeded -- this credential is NOT read-only. Close
            # before raising: a rejected connector must not leak a live
            # session, and a caller must never receive a handle for it.
            self.close()
            raise WriteAccessDetectedError(
                "write-probe succeeded on account %r -- credential is not read-only"
                % self.config.account_id)

        connection_id = "conn_%s_%d" % (self.config.account_id, int(time.time()))
        return StructuredConnection(self, connection_id)

    def _run_write_probe(self) -> bool:
        """Attempts CREATE TEMPORARY TABLE. Returns True if the write
        SUCCEEDED (source is NOT read-only), False if it was denied
        (read-only proven)."""
        from snowflake.connector.errors import DatabaseError, ProgrammingError
        cursor = self._connection.cursor()
        try:
            cursor.execute("CREATE TEMPORARY TABLE %s (x INT)" % PROBE_TABLE)
            cursor.execute("DROP TABLE %s" % PROBE_TABLE)
            return True
        except (ProgrammingError, DatabaseError):
            return False
        finally:
            cursor.close()

    def get_information_schema_card(self, schema: str, max_tables: Optional[int] = None) -> Dict[str, Any]:
        if not self._connection:
            raise NotConnectedError("get_information_schema_card called before connect()")

        cursor = self._connection.cursor()
        try:
            database_prefix = ""
            params = [schema.upper()]
            if self.config.database:
                database_prefix = "%s." % _quote_identifier(self.config.database)
                params.insert(0, self.config.database.upper())
                catalog_filter = "table_catalog = %s AND "
            else:
                catalog_filter = ""

            cursor.execute(
                """
                SELECT table_catalog, table_schema, table_name, column_name, data_type, is_nullable
                FROM %sinformation_schema.columns
                WHERE %stable_schema = %%s
                ORDER BY table_name, ordinal_position
                """ % (database_prefix, catalog_filter),
                params,
            )
            tables: Dict[str, Dict[str, Any]] = {}
            for row in cursor.fetchall():
                if len(row) == 6:
                    _, table_schema, table_name, column_name, data_type, is_nullable = row
                else:
                    table_schema = schema
                    table_name, column_name, data_type, is_nullable = row
                if table_name not in tables:
                    if max_tables is not None and len(tables) >= max_tables:
                        continue
                    tables[table_name] = {
                        "schema": table_schema,
                        "name": table_name,
                        "columns": [],
                        "row_count": None,
                        "sample_row": None,
                    }
                tables[table_name]["columns"].append({
                    "name": column_name, "type": data_type, "nullable": is_nullable == "YES",
                })
            return {"schema": schema, "tables": list(tables.values())}
        finally:
            cursor.close()

    def get_schema_card(self, schema: str, max_tables: Optional[int] = None) -> Dict[str, Any]:
        if not self._connection:
            raise NotConnectedError("get_schema_card called before connect()")
        from snowflake.connector.errors import DatabaseError, ProgrammingError

        card = self.get_information_schema_card(schema, max_tables=max_tables)
        cursor = self._connection.cursor()

        for table in card["tables"]:
            table_name = table["name"]
            try:
                cursor.execute('SELECT COUNT(*) FROM "%s"."%s"' % (schema, table_name))
                row = cursor.fetchone()
                table["row_count"] = row[0] if row else None
            except (ProgrammingError, DatabaseError):
                table["row_count"] = None  # no COUNT privilege on this table -- keep columns, skip count

            try:
                cursor.execute('SELECT * FROM "%s"."%s" LIMIT 1' % (schema, table_name))
                row = cursor.fetchone()
                if row:
                    col_names = [d[0] for d in cursor.description]
                    table["sample_row"] = dict(zip(col_names, row))
            except (ProgrammingError, DatabaseError):
                table["sample_row"] = None  # no read grant on this table -- keep columns, skip sample

        cursor.close()
        return card

    def execute_query(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        if not self._connection:
            raise NotConnectedError("execute_query called before connect()")
        cursor = self._connection.cursor()
        try:
            cursor.execute(sql, params or [])
            col_names = [d[0] for d in cursor.description] if cursor.description else []
            return [dict(zip(col_names, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def close(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None
