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
load_dotenv(REPO / "backend" / ".env", override=True)
SCHEMA_FILES = [
    REPO / "backend" / "migrations" / "cce_control" / "001_registry.sql",
    REPO / "backend" / "migrations" / "cce_control" / "002_metadata.sql",
    REPO / "backend" / "migrations" / "cce_control" / "002_metadata_01_details.sql",
    REPO / "backend" / "migrations" / "cce_control" / "002_metadata_02_relationships.sql",
    REPO / "backend" / "migrations" / "cce_control" / "003_governance.sql",
    REPO / "backend" / "migrations" / "cce_control" / "004_context.sql",
    REPO / "backend" / "migrations" / "cce_control" / "005_runtime.sql",
    REPO / "backend" / "migrations" / "cce_control" / "006_audit.sql",
    REPO / "backend" / "migrations" / "cce_control" / "007_source_config.sql",
    REPO / "backend" / "migrations" / "cce_control" / "008_local_index.sql",
    REPO / "backend" / "migrations" / "cce_control" / "009_local_index_exact_search.sql",
    REPO / "backend" / "migrations" / "cce_control" / "011_agentic_plane_refs.sql",
]


def build_dsn() -> str:
    return os.environ.get(
        "CCE_CONTROL_DATABASE_URL",
        os.environ.get(
            "CCE_METADATA_DATABASE_URL",
        "postgresql://{user}:{password}@{host}:{port}/{db}".format(
            user=os.environ.get("POSTGRES_USER", "cce_admin"),
            password=os.environ.get("POSTGRES_PASSWORD", "cce_password"),
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=os.environ.get("POSTGRES_PORT", "5434"),
            db=os.environ.get("POSTGRES_DB", "cce_control"),
        ),
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
