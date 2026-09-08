"""Composition root for wiring CCE services and infrastructure."""

from dataclasses import dataclass

from cce.config.settings import Settings
from cce.context_packages.service import ContextPackageService
from cce.governance.service import GovernanceService
from cce.ingestion.checkpoint import IngestionCheckpointStore
from cce.integrations.agentic_plane.local_index import LocalIndexClient
from cce.persistence.postgres.metadata_repository import PostgreSQLMetadataRepository
from cce.persistence.postgres.migrations import initialize_control_postgres
from cce.persistence.postgres.source_repository import PostgresSourceRepository
from cce.retrieval.service import RetrievalService
from cce.runtime.service import QueryService
from cce.sources.service import SourceService


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
    domain_repository: object
    job_runner: object
    ready: bool = False
    readiness_message: str = "starting"

    def close(self) -> None:
        self.job_runner.close()
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

    if settings.index_backend == "agentic_plane":
        from cce.integrations.agentic_plane.client import AgenticPlaneClient
    from cce.context_packages.builder import PackageBuilder
    from cce.ingestion.grounding import GroundingAdapter
    from cce.ingestion.job_runner import JobRunner
    from cce.ingestion.source_graph import SourceGraph
    from cce.integrations.llm.client import StructuredLLM
    from cce.persistence.postgres.context_repository import ContextRepository
    from cce.persistence.postgres.domain_repository import DomainRepository
    from cce.persistence.postgres.governance_repository import GovernanceRepository
    from cce.persistence.postgres.ingestion_repository import IngestionRepository
    from cce.persistence.postgres.job_repository import JobRepository
    from cce.persistence.postgres.lifecycle_db import LifecycleDB
    from cce.persistence.postgres.runtime_repository import RuntimeRepository
    from cce.runtime.orchestrator import RuntimeOrchestrator
    from cce.runtime.sql_executor import SQLExecutor
    from cce.runtime.sql_pipeline import SQLPipeline

    db = LifecycleDB(settings.database_url)
    domains = DomainRepository(db)
    context = ContextRepository(db)
    traces = RuntimeRepository(db)
    ingestion = IngestionRepository(db)
    builder = PackageBuilder(context, traces.schema)
    governance = GovernanceRepository(db, context, builder)
    llm = StructuredLLM(settings)
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
        ingestion_repository=ingestion,
    )
    retrieval_service = RetrievalService(
        index_client=index_client,
        backend=settings.index_backend,
    )

    source_graph = SourceGraph(
        settings,
        ingestion,
        domains,
        context,
        governance,
        GroundingAdapter(source_service),
        index_client,
        llm,
    )
    job_runner = JobRunner(
        JobRepository(db, settings.job_lease_seconds),
        source_graph,
        settings.job_poll_seconds,
    )
    sql = SQLPipeline(settings, llm, SQLExecutor(source_service), traces)
    runtime = RuntimeOrchestrator(
        settings, llm, domains, context, traces, index_client, sql
    )
    return Application(
        settings=settings,
        query_service=QueryService(runtime),
        governance_service=GovernanceService(governance),
        package_service=ContextPackageService(context),
        domain_repository=domains,
        job_runner=job_runner,
        source_repository=source_repository,
        metadata_repository=metadata_repository,
        checkpoint_store=checkpoint_store,
        index_client=index_client,
        retrieval_service=retrieval_service,
        source_service=source_service,
        ready=True,
        readiness_message="ready",
    )
