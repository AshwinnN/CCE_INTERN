#!/usr/bin/env python3
"""Start from an already-running Postgres container and apply the CCE schema."""
import os
import sys
import time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


REPO = Path(__file__).resolve().parents[1]
load_dotenv(REPO / ".env", override=True)
SCHEMA_FILES = [
    REPO / "schema" / "01_core_hierarchy.sql",
    REPO / "schema" / "02_snapshots.sql",
    REPO / "schema" / "03_metadata.sql",
    REPO / "schema" / "04_relationships.sql",
]


def build_dsn() -> str:
    return os.environ.get(
        "CCE_METADATA_DATABASE_URL",
        "postgresql://{user}:{password}@{host}:{port}/{db}".format(
            user=os.environ.get("POSTGRES_USER", "cce_admin"),
            password=os.environ.get("POSTGRES_PASSWORD", "cce_password"),
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=os.environ.get("POSTGRES_PORT", "5434"),
            db=os.environ.get("POSTGRES_DB", "cce_metadata"),
        ),
    )


def wait_for_postgres(dsn: str, timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            with psycopg2.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return
        except psycopg2.OperationalError as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"Postgres did not become ready within {timeout_seconds}s: {last_error}")


def apply_schema(dsn: str) -> None:
    with psycopg2.connect(dsn) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            for schema_file in SCHEMA_FILES:
                sql = schema_file.read_text(encoding="utf-8")
                print(f"Applying {schema_file.name} ...")
                cur.execute(sql)
        conn.commit()


def main() -> int:
    dsn = build_dsn()
    print(f"Using database {dsn.rsplit('@', 1)[-1]}")
    wait_for_postgres(dsn)
    apply_schema(dsn)
    print("CCE demo Postgres schema is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
