"""Azure Blob source configuration."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AzureBlobConfig:
    connection_string: str
    container_name: str
