"""Isolated database for lifecycle invariants; never truncates a configured application DB."""

import os
from uuid import uuid4

import psycopg2
import pytest
from cce.context_packages.builder import PackageBuilder
from cce.persistence.postgres.context_repository import ContextRepository
from cce.persistence.postgres.workspace_repository import WorkspaceRepository
from cce.persistence.postgres.governance_repository import GovernanceRepository
from cce.persistence.postgres.ingestion_repository import IngestionRepository
from cce.persistence.postgres.job_repository import JobRepository
from cce.persistence.postgres.lifecycle_db import LifecycleDB
from cce.persistence.postgres.migrations import apply_control_schema
from cce.persistence.postgres.runtime_repository import RuntimeRepository
from psycopg2 import sql


@pytest.fixture(autouse=True)
def isolate_process_global_test_state():
    # These tests inject provider boundaries and do not use the connector registry.
    yield


@pytest.fixture
def system():
    dsn = os.environ.get("CCE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip(
            "Set CCE_TEST_DATABASE_URL to a disposable PostgreSQL server with CREATE DATABASE permission"
        )
    name = "cce_test_" + uuid4().hex
    admin = psycopg2.connect(dsn)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    params = psycopg2.extensions.parse_dsn(dsn)
    params["dbname"] = name
    test_dsn = psycopg2.extensions.make_dsn(**params)
    apply_control_schema(test_dsn, index_backend="agentic_plane")
    apply_control_schema(
        test_dsn, index_backend="agentic_plane"
    )  # replay-safe forward migration
    db = LifecycleDB(test_dsn)
    context = ContextRepository(db)
    traces = RuntimeRepository(db)
    from types import SimpleNamespace

    obj = SimpleNamespace(
        db=db,
        context=context,
        traces=traces,
        workspaces=WorkspaceRepository(db),
        ingestion=IngestionRepository(db),
        jobs=JobRepository(db, 120),
    )
    obj.governance = GovernanceRepository(
        db, context, PackageBuilder(context, traces.schema)
    )
    yield obj
    with admin.cursor() as cur:
        cur.execute(
            sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
        )
    admin.close()
