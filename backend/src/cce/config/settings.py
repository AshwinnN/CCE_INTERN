"""Typed backend settings loaded from environment variables."""

from dataclasses import dataclass
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


def load_settings() -> Settings:
    load_dotenv(".env", override=False)
    load_dotenv("backend/.env", override=False)

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
        index_backend=os.environ.get("CCE_INDEX_BACKEND", "local"),
    )
