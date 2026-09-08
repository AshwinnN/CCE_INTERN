#!/usr/bin/env python3
"""Unit tests for connectors/snowflake/connector.py -- no live Snowflake
credentials or network access anywhere in this file. `driver_connect` is
injected with a fake DB-API connection, and credential loading is mocked,
the same fixture-injection convention every live-driver touchpoint in this
repo already uses (see agents/connector_agent/change_capture.py's
object_lister/catalog_lister)."""
import os
import sys
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from snowflake.connector.errors import ProgrammingError  # noqa: E402

from cce.connectors.base.exceptions import (  # noqa: E402
    ConnectionFailedError, NotConnectedError, WriteAccessDetectedError,
)
from cce.connectors.base.models import ConnectionConfig  # noqa: E402
from cce.connectors.structured.snowflake.connector import SnowflakeConnector  # noqa: E402


class FakeCursor:
    def __init__(self, script):
        self._script = script
        self.description = None
        self._result = None

    def execute(self, sql, params=None):
        self._result, self.description = self._script(sql, params)

    def fetchall(self):
        return self._result or []

    def fetchone(self):
        return self._result[0] if self._result else None

    def close(self):
        pass


class FakeConnection:
    def __init__(self, script):
        self._script = script
        self.closed = False

    def cursor(self):
        return FakeCursor(self._script)

    def close(self):
        self.closed = True


def denied_write_script(sql, params=None):
    if "CREATE TEMPORARY TABLE" in sql:
        raise ProgrammingError("SQL access control error: Insufficient privileges")
    return [], None


def succeeding_write_script(sql, params=None):
    if "CREATE TEMPORARY TABLE" in sql or "DROP TABLE" in sql:
        return [], None
    return [], None


def make_config():
    return ConnectionConfig(adapter="snowflake", account_id="acct1", user="svc",
                             credential_ref="env://X", database="D", schema="S")


def _patched_credential():
    return mock.patch("cce.connectors.structured.snowflake.connector.load_snowflake_keypair_credential",
                       return_value={"private_key_pem": "pem", "passphrase": None})


def _patched_key_der():
    return mock.patch("cce.connectors.structured.snowflake.connector._private_key_der", return_value=b"der-bytes")


class ConnectTests(unittest.TestCase):

    def test_disabled_write_probe_returns_unverified_connection(self):
        def no_probe_script(sql, params=None):
            if "CREATE TEMPORARY TABLE" in sql:
                raise AssertionError("write probe must not run")
            return [], None

        config = make_config()
        config.write_probe_enabled = False
        connector = SnowflakeConnector(
            config,
            driver_connect=lambda **kw: FakeConnection(no_probe_script),
        )
        with _patched_credential(), _patched_key_der():
            connection = connector.connect()

        self.assertFalse(connection.read_only_verified)

    def test_write_denied_returns_a_read_only_connection(self):
        fake_conn = FakeConnection(denied_write_script)
        connector = SnowflakeConnector(make_config(), driver_connect=lambda **kw: fake_conn)
        with _patched_credential(), _patched_key_der():
            connection = connector.connect()
        self.assertTrue(connection.read_only_verified)
        self.assertTrue(connection.connection_id.startswith("conn_acct1_"))

    def test_write_succeeding_raises_and_closes_the_connection(self):
        fake_conn = FakeConnection(succeeding_write_script)
        connector = SnowflakeConnector(make_config(), driver_connect=lambda **kw: fake_conn)
        with _patched_credential(), _patched_key_der():
            with self.assertRaises(WriteAccessDetectedError):
                connector.connect()
        self.assertTrue(fake_conn.closed)

    def test_driver_connect_receives_der_encoded_private_key_and_config_fields(self):
        captured = {}

        def driver_connect(**kwargs):
            captured.update(kwargs)
            return FakeConnection(denied_write_script)

        connector = SnowflakeConnector(make_config(), driver_connect=driver_connect)
        with _patched_credential(), _patched_key_der():
            connector.connect()
        self.assertEqual(captured["account"], "acct1")
        self.assertEqual(captured["user"], "svc")
        self.assertEqual(captured["private_key"], b"der-bytes")
        self.assertEqual(captured["database"], "D")
        self.assertEqual(captured["schema"], "S")

    def test_credential_resolution_failure_raises_connection_failed_error(self):
        connector = SnowflakeConnector(make_config(), driver_connect=lambda **kw: FakeConnection(denied_write_script))
        with self.assertRaises(ConnectionFailedError):
            connector.connect()  # no credential mocked -> real env lookup fails for "env://X"

    def test_driver_level_connect_failure_raises_connection_failed_error(self):
        def boom(**kwargs):
            raise RuntimeError("network unreachable")

        connector = SnowflakeConnector(make_config(), driver_connect=boom)
        with _patched_credential(), _patched_key_der():
            with self.assertRaises(ConnectionFailedError):
                connector.connect()


class SchemaCardTests(unittest.TestCase):

    def _connected(self):
        def script(sql, params=None):
            if "information_schema.columns" in sql:
                rows = [("T1", "A", "VARCHAR", "YES"), ("T1", "B", "NUMBER", "NO")]
                return rows, None
            if "COUNT" in sql:
                return [(7,)], None
            if "LIMIT 1" in sql:
                return [("hi", 1)], [("A",), ("B",)]
            if "CREATE TEMPORARY TABLE" in sql:
                raise ProgrammingError("Insufficient privileges")
            return [], None

        fake_conn = FakeConnection(script)
        connector = SnowflakeConnector(make_config(), driver_connect=lambda **kw: fake_conn)
        with _patched_credential(), _patched_key_der():
            connector.connect()
        return connector

    def test_get_schema_card_before_connect_raises_not_connected(self):
        connector = SnowflakeConnector(make_config())
        with self.assertRaises(NotConnectedError):
            connector.get_schema_card("S")

    def test_get_schema_card_groups_columns_by_table_with_row_count_and_sample(self):
        connector = self._connected()
        card = connector.get_schema_card("S")
        self.assertEqual(card["schema"], "S")
        self.assertEqual(len(card["tables"]), 1)
        table = card["tables"][0]
        self.assertEqual(table["name"], "T1")
        self.assertEqual(len(table["columns"]), 2)
        self.assertEqual(table["columns"][0], {"name": "A", "type": "VARCHAR", "nullable": True})
        self.assertEqual(table["row_count"], 7)
        self.assertEqual(table["sample_row"], {"A": "hi", "B": 1})

    def test_get_information_schema_card_never_queries_source_tables(self):
        observed_sql = []

        def script(sql, params=None):
            observed_sql.append(sql)
            if "CREATE TEMPORARY TABLE" in sql:
                raise ProgrammingError("Insufficient privileges")
            if "information_schema.columns" in sql:
                rows = [("D", "S", "T1", "A", "VARCHAR", "YES")]
                return rows, None
            if "COUNT" in sql or "LIMIT 1" in sql:
                raise AssertionError("metadata-only schema card must not query source tables")
            return [], None

        fake_conn = FakeConnection(script)
        connector = SnowflakeConnector(make_config(), driver_connect=lambda **kw: fake_conn)
        with _patched_credential(), _patched_key_der():
            connector.connect()
        card = connector.get_information_schema_card("S")
        self.assertEqual(card["schema"], "S")
        self.assertEqual(card["tables"][0]["name"], "T1")
        self.assertIsNone(card["tables"][0]["row_count"])
        self.assertIsNone(card["tables"][0]["sample_row"])
        self.assertFalse(any("COUNT" in sql or "LIMIT 1" in sql for sql in observed_sql))

    def test_max_tables_caps_the_number_of_tables_returned(self):
        def script(sql, params=None):
            if "CREATE TEMPORARY TABLE" in sql:
                raise ProgrammingError("Insufficient privileges")
            if "information_schema.columns" in sql:
                rows = [("T1", "A", "INT", "YES"), ("T2", "B", "INT", "YES")]
                return rows, None
            return [], None

        fake_conn = FakeConnection(script)
        connector = SnowflakeConnector(make_config(), driver_connect=lambda **kw: fake_conn)
        with _patched_credential(), _patched_key_der():
            connector.connect()
        card = connector.get_schema_card("S", max_tables=1)
        self.assertEqual(len(card["tables"]), 1)


class ExecuteQueryTests(unittest.TestCase):

    def test_before_connect_raises_not_connected(self):
        connector = SnowflakeConnector(make_config())
        with self.assertRaises(NotConnectedError):
            connector.execute_query("SELECT 1")

    def test_returns_rows_as_dicts(self):
        def script(sql, params=None):
            if "CREATE TEMPORARY TABLE" in sql:
                raise ProgrammingError("denied")
            return [(1, "a")], [("ID",), ("NAME",)]

        fake_conn = FakeConnection(script)
        connector = SnowflakeConnector(make_config(), driver_connect=lambda **kw: fake_conn)
        with _patched_credential(), _patched_key_der():
            connector.connect()
        rows = connector.execute_query("SELECT id, name FROM t")
        self.assertEqual(rows, [{"ID": 1, "NAME": "a"}])


class CloseTests(unittest.TestCase):

    def test_close_is_idempotent(self):
        connector = SnowflakeConnector(make_config())
        connector.close()
        connector.close()  # must not raise when never connected


if __name__ == "__main__":
    unittest.main()
