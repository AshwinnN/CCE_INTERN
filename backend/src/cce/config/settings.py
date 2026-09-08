"""Typed backend settings loaded from environment variables."""

from dataclasses import dataclass, field
import os
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
