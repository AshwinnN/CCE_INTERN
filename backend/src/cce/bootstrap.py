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
from cce.retrieval.service import RetrievalService
from cce.sources.service import SourceService
from cce.integrations.agentic_plane.client import AgenticPlaneClient
from cce.integrations.agentic_plane.local_index import LocalIndexClient


@dataclass(frozen=True)
class Application:
    settings: Settings
    query_service: QueryService
    governance_service: GovernanceService
    package_service: ContextPackageService
    source_repository: PostgresSourceRepository
    metadata_repository: PostgreSQLMetadataRepository
    checkpoint_store: IngestionCheckpointStore
    index_client: object
    retrieval_service: RetrievalService
    source_service: SourceService
    ready: bool = False
    readiness_message: str = "starting"

    def close(self) -> None:
        close = getattr(self.index_client, "close", None)
        if close is not None:
            close()


def build_application(settings: Settings) -> Application:
    if settings.migrate_on_startup:
        initialize_control_postgres(
            settings.database_url,
            timeout_seconds=settings.postgres_wait_timeout_seconds,
            index_backend=settings.index_backend,
        )

    source_repository = PostgresSourceRepository(settings.database_url)
    metadata_repository = PostgreSQLMetadataRepository(settings.database_url)
    checkpoint_store = IngestionCheckpointStore()
    index_client = (
        AgenticPlaneClient(
            base_url=settings.agenticplane_base_url,
            api_key=settings.agenticplane_api_key,
            timeout=settings.agenticplane_timeout,
            max_retries=settings.agenticplane_max_retries,
            agent_id=settings.agenticplane_agent_id,
            graph_enabled=settings.agenticplane_graph_enabled,
            dsn=settings.database_url,
        )
        if settings.index_backend == "agentic_plane"
        else LocalIndexClient(settings.database_url)
    )
    source_service = SourceService(
        source_repository=source_repository,
        metadata_repository=metadata_repository,
        checkpoint_store=checkpoint_store,
        index_client=index_client,
    )
    retrieval_service = RetrievalService(
        index_client=index_client,
        backend=settings.index_backend,
    )

    return Application(
        settings=settings,
        query_service=QueryService(),
        governance_service=GovernanceService(),
        package_service=ContextPackageService(),
        source_repository=source_repository,
        metadata_repository=metadata_repository,
        checkpoint_store=checkpoint_store,
        index_client=index_client,
        retrieval_service=retrieval_service,
        source_service=source_service,
        ready=True,
        readiness_message="ready",
    )
