"""Typed backend settings loaded from environment variables."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051
    database_url: str | None = None
    environment: str = "local"


def load_settings() -> Settings:
    return Settings(
        grpc_host=os.environ.get("CCE_GRPC_HOST", "0.0.0.0"),
        grpc_port=int(os.environ.get("CCE_GRPC_PORT", "50051")),
        database_url=os.environ.get("CCE_CONTROL_DATABASE_URL")
        or os.environ.get("CCE_METADATA_DATABASE_URL"),
        environment=os.environ.get("CCE_ENVIRONMENT", "local"),
    )
