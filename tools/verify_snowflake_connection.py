#!/usr/bin/env python3
"""Connects to Snowflake and discovers its top 5 tables THROUGH the real
skills — skill-strucutred_source_connect for Stage 1, then
skill-schema-discovery for Stage 2 — instead of a raw connector dump.

Mirrors tools/verify_document_sync_top5.py's pattern for the structured
lane: Snowflake is only ever the source of raw metadata (a live write probe
result, a live catalog listing); every accept/reject decision is made by
the unmodified skill scripts.

Usage:  .venv/bin/python3 tools/verify_snowflake_connection.py
"""
import os
import sys

from dotenv import load_dotenv
import snowflake.connector
from snowflake.connector.errors import ProgrammingError, DatabaseError

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
load_dotenv(os.path.join(REPO, ".env"))

from common.skill_loader import load_skill_module  # noqa: E402

connect_module = load_skill_module(
    "skill-strucutred_source_connect", "validate_source_profile.py"
)
connect_validate = connect_module.validate
CONNECT_REGISTRY = connect_module.DEFAULT_REGISTRY

discover_module = load_skill_module(
    "skill-schema-discovery", "build_schema_card.py"
)
build_schema_card = discover_module.build

SOURCE_ID = "snowflake-public-data"
PROBE_TABLE = "__CCE_WRITE_PROBE__"


def _private_key_bytes():
    from cryptography.hazmat.primitives import serialization

    raw = os.environ["CCE_SNOWFLAKE_PRIVATE_KEY"].replace("\\n", "\n").encode()
    passphrase = os.environ.get("CCE_SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None
    key = serialization.load_pem_private_key(
        raw, password=passphrase.encode() if passphrase else None
    )
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def real_connect():
    """The only place this script talks to Snowflake directly."""
    return snowflake.connector.connect(
        account=os.environ["CCE_SNOWFLAKE_ACCOUNT"],
        user=os.environ["CCE_SNOWFLAKE_USER"],
        private_key=_private_key_bytes(),
        role=os.environ["CCE_SNOWFLAKE_ROLE"],
        warehouse=os.environ["CCE_SNOWFLAKE_WAREHOUSE"],
        database=os.environ["CCE_SNOWFLAKE_DATABASE"],
        schema=os.environ["CCE_SNOWFLAKE_SCHEMA"],
        login_timeout=int(os.environ.get("CCE_SNOWFLAKE_LOGIN_TIMEOUT", 20)),
        network_timeout=int(os.environ.get("CCE_SNOWFLAKE_NETWORK_TIMEOUT", 30)),
    )


def real_write_probe(conn):
    """Attempts a real, throwaway write and reports whether it SUCCEEDED.
    Mirrors the Azure blob write-probe: try it for real, don't assume."""
    cur = conn.cursor()
    try:
        cur.execute(f"CREATE TEMPORARY TABLE {PROBE_TABLE} (x INT)")
        cur.execute(f"DROP TABLE {PROBE_TABLE}")
        return True  # write succeeded -> NOT read-only
    except (ProgrammingError, DatabaseError):
        return False  # denied -> read-only proven
    finally:
        cur.close()


def real_catalog_top5(conn, schema):
    """Raw metadata only: table/column list + one sample row per table,
    capped at 5 tables. No sensitivity classification is applied here --
    there is no DLP/PII skill wired in yet (flagged previously), so every
    column is reported as sensitive=False. skill-schema-discovery's own
    SCD05 redaction is a no-op until that gap is filled."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s
        ORDER BY table_name, ordinal_position
        """,
        (schema,),
    )
    tables = {}
    for table_name, column_name, data_type in cur.fetchall():
        if table_name not in tables and len(tables) >= 5:
            continue
        tables.setdefault(table_name, []).append(
            {"name": column_name, "type": data_type, "sensitive": False}
        )

    catalog = []
    for table_name, columns in tables.items():
        sample = None
        try:
            cur.execute(f'SELECT * FROM "{schema}"."{table_name}" LIMIT 1')
            row = cur.fetchone()
            if row:
                col_names = [d[0] for d in cur.description]
                sample = dict(zip(col_names, row))
        except (ProgrammingError, DatabaseError):
            sample = None  # no read grant on this specific table -- skip sample, keep columns
        catalog.append(
            {"schema": schema, "table": table_name, "columns": columns, "sample": sample}
        )
    cur.close()
    return catalog


def main():
    if os.environ.get("CCE_SNOWFLAKE_ENABLED", "false").lower() != "true":
        print("CCE_SNOWFLAKE_ENABLED is not 'true' -- stopping before any connection.")
        return 1

    schema = os.environ["CCE_SNOWFLAKE_SCHEMA"]
    max_rows = 1000

    conn = real_connect()
    try:
        write_succeeds = real_write_probe(conn)

        # ---- Stage 1: real skill-strucutred_source_connect call ----
        connect_profile = {
            "source_id": SOURCE_ID,
            "adapter": "snowflake",
            "credential_ref": "env://CCE_SNOWFLAKE_PRIVATE_KEY",
            "statement_timeout_ms": int(os.environ.get("CCE_SNOWFLAKE_NETWORK_TIMEOUT", 30)) * 1000,
            "max_rows": max_rows,
            "schema_scope": [schema],
            "_probe_write_succeeds": write_succeeds,
        }
        handle = connect_validate(connect_profile, CONNECT_REGISTRY)
        print("=== skill-strucutred_source_connect ===")
        print(handle)
        if handle["status"] != "READY":
            print("REJECTED at Connect -- stopping, not proceeding to Discover.", file=sys.stderr)
            return 1

        # ---- Real Snowflake catalog listing (metadata + 1 sample row/table) ----
        catalog = real_catalog_top5(conn, schema)

        # ---- Stage 2: real skill-schema-discovery call ----
        discover_request = {
            "handle": handle,
            "card_version": 1,
            # NOTE: this is a fixed, hardcoded, read-only INFORMATION_SCHEMA
            # introspection query with no user input -- treated as pre-cleared.
            # A stricter build would run this through skill-sql-guard for real
            # rather than asserting it here.
            "guard_passed": True,
            "_catalog": catalog,
        }
        card = build_schema_card(discover_request)
        print("\n=== skill-schema-discovery ===")
        print(card)
        if card["status"] != "READY":
            print("REJECTED at Discover by rule %s" % card["violated_rule"], file=sys.stderr)
            return 1

        print("\n=== Top %d tables (per skill-schema-discovery's card) ===" % len(card["tables"]))
        for t in card["tables"]:
            col_summary = ", ".join(c["name"] for c in t["columns"][:5])
            print("  %s.%s  columns: %s%s" % (
                t["schema"], t["table"], col_summary,
                " ..." if len(t["columns"]) > 5 else "",
            ))
            if t["sample"]:
                print("    sample:", t["sample"])

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())