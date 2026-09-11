"""Typed backend settings loaded from environment variables."""

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

from dotenv import load_dotenv

from cce.security.credentials import load_credential


@dataclass(frozen=True)
class Settings:
    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051
    database_url: str = ""
    environment: str = "local"
    migrate_on_startup: bool = True
    postgres_wait_timeout_seconds: int = 60
    readiness_message: str = "starting"
    http_enabled: bool = True
    http_port: int = 8080
    index_backend: str = "local"
    agenticplane_base_url: str = ""
    agenticplane_api_key: str = field(default="", repr=False)
    agenticplane_timeout: int = 30
    agenticplane_max_retries: int = 3
    agenticplane_agent_id: str = "cce-ingestion"
    agenticplane_graph_enabled: bool = True
    ingestion_max_concurrency: int = 5
    domain_detection_min_confidence: float = 0.7
    domain_max_matches: int = 3
    domain_min_confidence: float = 0.7
    retrieval_top_k: int = 10
    retrieval_oversample_factor: int = 3
    retrieval_min_score: float = 0.7
    graph_max_hops: int = 2
    sql_generation_enabled: bool = True
    sql_max_retries: int = 2
    sql_timeout_seconds: int = 30
    sql_max_rows: int = 1000
    context_off_enabled: bool = True
    query_include_rows: bool = True
    job_lease_seconds: int = 120
    job_poll_seconds: int = 2
    llm_provider: str = "gemini"
    llm_model: str = "gemini-3.1-flash-lite"
    llm_domain_model: str = ""
    llm_extraction_model: str = ""
    llm_sql_model: str = ""
    llm_answer_model: str = ""
    llm_proof_model: str = ""
    llm_api_key: str = field(default="", repr=False)
    llm_base_url: str = ""
    llm_timeout: int = 300
    llm_max_retries: int = 1

    def __post_init__(self):
        for name in (
            "ingestion_max_concurrency",
            "domain_max_matches",
            "retrieval_top_k",
            "retrieval_oversample_factor",
            "sql_timeout_seconds",
            "sql_max_rows",
            "job_lease_seconds",
            "job_poll_seconds",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")
        for name in (
            "domain_detection_min_confidence",
            "domain_min_confidence",
            "retrieval_min_score",
        ):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.sql_max_retries < 0 or self.graph_max_hops < 0:
            raise ValueError("Retries and graph hops must be nonnegative")


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _build_database_url() -> str:
    credential_ref = os.environ.get("CCE_CONTROL_DATABASE_CREDENTIAL_REF")
    if credential_ref:
        credential = load_credential(credential_ref)
        parsed = urlparse(credential)
        if parsed.scheme in {"postgresql", "postgres"} and parsed.netloc:
            return credential
        user = os.environ.get("POSTGRES_USER", "cce_admin")
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5434")
        db = os.environ.get("POSTGRES_DB", "cce_control")
        return f"postgresql://{user}:{credential}@{host}:{port}/{db}"

    explicit = os.environ.get("CCE_CONTROL_DATABASE_URL") or os.environ.get(
        "CCE_METADATA_DATABASE_URL"
    )
    if explicit:
        return explicit

    environment_value = os.environ.get("CCE_ENVIRONMENT") or os.environ.get("CCE_ENV")
    environment = environment_value.strip().lower() if environment_value else ""
    if environment != "local":
        raise RuntimeError(
            "missing CCE_CONTROL_DATABASE_CREDENTIAL_REF or CCE_CONTROL_DATABASE_URL"
        )

    user = os.environ.get("POSTGRES_USER", "cce_admin")
    password = os.environ.get("POSTGRES_PASSWORD", "cce_password")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5434")
    db = os.environ.get("POSTGRES_DB", "cce_control")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _resolve_agenticplane_api_key(value: str) -> str:
    if value.startswith(("env://", "azure-kv://")):
        return load_credential(value)
    return value


def load_settings() -> Settings:
    load_dotenv(".env", override=False)
    load_dotenv("backend/.env", override=False)

    index_backend = os.environ.get("CCE_INDEX_BACKEND", "local").strip().lower()
    agenticplane_base_url = os.environ.get("CCE_AGENTICPLANE_BASE_URL", "").strip()
    api_key_value = os.environ.get("CCE_AGENTICPLANE_API_KEY", "").strip()
    if index_backend == "agentic_plane":
        missing = []
        if not agenticplane_base_url:
            missing.append("CCE_AGENTICPLANE_BASE_URL")
        if not api_key_value:
            missing.append("CCE_AGENTICPLANE_API_KEY")
        if missing:
            raise RuntimeError(
                "CCE_INDEX_BACKEND=agentic_plane requires " + ", ".join(missing)
            )
        api_key_value = _resolve_agenticplane_api_key(api_key_value)

    return Settings(
        ingestion_max_concurrency=int(
            os.environ.get("CCE_INGESTION_MAX_CONCURRENCY", "5")
        ),
        domain_detection_min_confidence=float(
            os.environ.get("CCE_DOMAIN_DETECTION_MIN_CONFIDENCE", "0.7")
        ),
        domain_max_matches=int(os.environ.get("CCE_DOMAIN_MAX_MATCHES", "3")),
        domain_min_confidence=float(os.environ.get("CCE_DOMAIN_MIN_CONFIDENCE", "0.7")),
        retrieval_top_k=int(os.environ.get("CCE_RETRIEVAL_TOP_K", "10")),
        retrieval_oversample_factor=int(
            os.environ.get("CCE_RETRIEVAL_OVERSAMPLE_FACTOR", "3")
        ),
        retrieval_min_score=float(os.environ.get("CCE_RETRIEVAL_MIN_SCORE", "0.7")),
        graph_max_hops=int(os.environ.get("CCE_GRAPH_MAX_HOPS", "2")),
        sql_generation_enabled=_bool_env("CCE_SQL_GENERATION_ENABLED", True),
        sql_max_retries=int(os.environ.get("CCE_SQL_MAX_RETRIES", "2")),
        sql_timeout_seconds=int(os.environ.get("CCE_SQL_TIMEOUT_SECONDS", "30")),
        sql_max_rows=int(os.environ.get("CCE_SQL_MAX_ROWS", "1000")),
        context_off_enabled=_bool_env("CCE_CONTEXT_OFF_ENABLED", True),
        query_include_rows=_bool_env("CCE_QUERY_INCLUDE_ROWS", True),
        job_lease_seconds=int(os.environ.get("CCE_JOB_LEASE_SECONDS", "120")),
        job_poll_seconds=int(os.environ.get("CCE_JOB_POLL_SECONDS", "2")),
        llm_provider=str(os.environ.get("CCE_LLM_PROVIDER", "gemini")),
        llm_model=str(os.environ.get("CCE_LLM_MODEL", "gemini-3.1-flash-lite")),
        llm_domain_model=str(os.environ.get("CCE_LLM_DOMAIN_MODEL", "")),
        llm_extraction_model=str(os.environ.get("CCE_LLM_EXTRACTION_MODEL", "")),
        llm_sql_model=str(os.environ.get("CCE_LLM_SQL_MODEL", "")),
        llm_answer_model=str(os.environ.get("CCE_LLM_ANSWER_MODEL", "")),
        llm_proof_model=str(os.environ.get("CCE_LLM_PROOF_MODEL", "")),
        llm_api_key=str(os.environ.get("CCE_LLM_API_KEY", "")),
        llm_base_url=str(os.environ.get("CCE_LLM_BASE_URL", "")),
        llm_timeout=int(os.environ.get("CCE_LLM_TIMEOUT", "300")),
        llm_max_retries=int(os.environ.get("CCE_LLM_MAX_RETRIES", "1")),
        grpc_host=os.environ.get("CCE_GRPC_HOST", "0.0.0.0"),
        grpc_port=int(os.environ.get("CCE_GRPC_PORT", "50051")),
        database_url=_build_database_url(),
        environment=os.environ.get("CCE_ENVIRONMENT", "local"),
        migrate_on_startup=_bool_env("CCE_MIGRATE_ON_STARTUP", True),
        postgres_wait_timeout_seconds=int(
            os.environ.get("CCE_POSTGRES_WAIT_TIMEOUT_SECONDS", "60")
        ),
        http_enabled=_bool_env("CCE_HTTP_ENABLED", True),
        http_port=int(os.environ.get("CCE_HTTP_PORT", "8080")),
        index_backend=index_backend,
        agenticplane_base_url=agenticplane_base_url,
        agenticplane_api_key=api_key_value,
        agenticplane_timeout=int(os.environ.get("CCE_AGENTICPLANE_TIMEOUT", "30")),
        agenticplane_max_retries=int(
            os.environ.get("CCE_AGENTICPLANE_MAX_RETRIES", "3")
        ),
        agenticplane_agent_id=os.environ.get(
            "CCE_AGENTICPLANE_AGENT_ID", "cce-ingestion"
        ).strip(),
        agenticplane_graph_enabled=_bool_env("CCE_AGENTICPLANE_GRAPH_ENABLED", True),
    )
