"""Typed source operation responses shared by HTTP and gRPC."""

from pydantic import BaseModel, ConfigDict


class OperationError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class SourceOperationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_id: str
    status: str
    error: OperationError | None = None


class IngestionRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    ingestion_run_id: str
    status: str
    error: OperationError | None = None
    objects_processed: int = 0
    objects_failed: int = 0
