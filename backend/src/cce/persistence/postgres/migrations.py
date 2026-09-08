"""Control-plane PostgreSQL readiness and schema initialization."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Iterable

import psycopg2

DEFAULT_MIGRATION_DIR = (
    Path(__file__).resolve().parents[4] / "migrations" / "cce_control"
)
CONTAINER_MIGRATION_DIR = Path("/app/backend/migrations/cce_control")
MIGRATION_FILES = (
    "001_registry.sql",
    "002_metadata.sql",
    "002_metadata_01_details.sql",
    "002_metadata_02_relationships.sql",
    "003_governance.sql",
    "004_context.sql",
    "005_runtime.sql",
    "006_audit.sql",
    "007_source_config.sql",
    "008_local_index.sql",
    "009_local_index_exact_search.sql",
    "011_agentic_plane_refs.sql",
    "012_domain_governance_lifecycle.sql",
    "013_runtime_and_jobs.sql",
)
LOCAL_INDEX_MIGRATION_FILES = {
    "008_local_index.sql",
    "009_local_index_exact_search.sql",
}


def migration_paths(index_backend: str = "local") -> Iterable[Path]:
    migration_dir = Path(
        os.environ.get(
            "CCE_MIGRATION_DIR",
            str(
                CONTAINER_MIGRATION_DIR
                if CONTAINER_MIGRATION_DIR.exists()
                else DEFAULT_MIGRATION_DIR
            ),
        )
    )
    for name in MIGRATION_FILES:
        if index_backend != "local" and name in LOCAL_INDEX_MIGRATION_FILES:
            continue
        yield migration_dir / name


def wait_for_postgres(dsn: str, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg2.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return
        except psycopg2.OperationalError as exc:
            last_error = exc
            time.sleep(2)

    raise RuntimeError(
        f"Postgres did not become ready within {timeout_seconds}s: {last_error}"
    )


def apply_control_schema(dsn: str, index_backend: str = "local") -> None:
    with psycopg2.connect(dsn) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            for path in migration_paths(index_backend):
                sql = path.read_text(encoding="utf-8")
                if not sql.strip():
                    continue
                try:
                    cur.execute(sql)
                except psycopg2.Error as exc:
                    if path.name == "008_local_index.sql":
                        raise RuntimeError(
                            "pgvector extension is required for local indexing. "
                            "Install pgvector on the target Postgres instance or "
                            "set CCE_INDEX_BACKEND=agentic_plane."
                        ) from exc
                    raise
        conn.commit()


def initialize_control_postgres(
    dsn: str, timeout_seconds: int, index_backend: str = "local"
) -> None:
    wait_for_postgres(dsn, timeout_seconds)
    apply_control_schema(dsn, index_backend)
