"""Composition root for wiring CCE services and infrastructure."""

from dataclasses import dataclass

from cce.config.settings import Settings
from cce.context_packages.service import ContextPackageService
from cce.governance.service import GovernanceService
from cce.ingestion.checkpoint import IngestionCheckpointStore
from cce.persistence.postgres.metadata_repository import PostgreSQLMetadataRepository
from cce.persistence.postgres.migrations import initialize_control_postgres
from cce.persistence.postgres.source_repository import PostgresSourceRepository
from cce.runtime.service import QueryService


@dataclass(frozen=True)
class Application:
    settings: Settings
    query_service: QueryService
    governance_service: GovernanceService
    package_service: ContextPackageService
    source_repository: PostgresSourceRepository
    metadata_repository: PostgreSQLMetadataRepository
    checkpoint_store: IngestionCheckpointStore
    ready: bool = False
    readiness_message: str = "starting"


def build_application(settings: Settings) -> Application:
    if settings.migrate_on_startup:
        initialize_control_postgres(
            settings.database_url,
            timeout_seconds=settings.postgres_wait_timeout_seconds,
        )

    return Application(
        settings=settings,
        query_service=QueryService(),
        governance_service=GovernanceService(),
        package_service=ContextPackageService(),
        source_repository=PostgresSourceRepository(settings.database_url),
        metadata_repository=PostgreSQLMetadataRepository(settings.database_url),
        checkpoint_store=IngestionCheckpointStore(),
        ready=True,
        readiness_message="ready",
    )
