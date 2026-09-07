"""Source registration, connection testing and ingestion orchestration."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import traceback
import uuid
from cce.connectors.base.models import ConnectionConfig
from cce.connectors.factory import ConnectorFactory
from cce.ingestion.orchestrator import run_ingestion
from cce.security.credentials import load_credential


@dataclass(frozen=True)
class SourceOperationResult:
    source_id: str
    status: str
    error: dict | None = None


@dataclass(frozen=True)
class IngestionRunResult:
    ingestion_run_id: str
    status: str
    error: dict | None = None
    objects_processed: int = 0
    objects_failed: int = 0


class SourceService:
    def __init__(
        self,
        *,
        source_repository,
        metadata_repository,
        checkpoint_store,
        index_client,
        run_async: bool = True,
    ):
        self.source_repository = source_repository
        self.metadata_repository = metadata_repository
        self.checkpoint_store = checkpoint_store
        self.index_client = index_client
        self.run_async = run_async

    def register_source(
        self,
        *,
        adapter: str,
        source_id: str,
        credential_ref: str = "",
        kind: str | None = None,
        config: dict | None = None,
    ) -> SourceOperationResult:
        resolved_kind = kind or _kind_for_adapter(adapter)
        saved_id = self.source_repository.save_source(
            adapter=adapter,
            source_id=source_id,
            credential_ref=credential_ref or None,
            kind=resolved_kind,
            config=config or {},
            enabled=True,
        )
        return SourceOperationResult(source_id=saved_id, status="REGISTERED")

    def list_sources(self) -> list[dict]:
        return [_public_source(source) for source in self.source_repository.list_sources()]

    def test_connection(self, source_id: str) -> SourceOperationResult:
        try:
            source = self._require_source(source_id)
        except Exception as exc:
            return SourceOperationResult(
                source_id=source_id,
                status="FAILED",
                error={"code": "SOURCE_NOT_FOUND", "message": str(exc), "retryable": False},
            )
        connector = self._build_connector(source)
        try:
            connector.connect()
            if source["kind"] == "structured":
                schema = (source.get("config") or {}).get("schema")
                if schema and hasattr(connector, "get_schema_card"):
                    connector.get_schema_card(schema, max_tables=1)
            else:
                connector.list_objects()
            return SourceOperationResult(
                source_id=str(source["source_id"]),
                status="CONNECTED",
            )
        except Exception as exc:
            return SourceOperationResult(
                source_id=str(source["source_id"]),
                status="FAILED",
                error={
                    "code": "CONNECTION_FAILED",
                    "message": str(exc),
                    "retryable": True,
                },
            )
        finally:
            try:
                connector.close()
            except Exception:
                pass

    def trigger_ingestion(self, source_id: str) -> IngestionRunResult:
        try:
            source = self._require_source(source_id)
        except Exception as exc:
            return IngestionRunResult(
                ingestion_run_id="",
                status="FAILED",
                error={"code": "SOURCE_NOT_FOUND", "message": str(exc), "retryable": False},
            )
        trace_id = "trc_%s" % uuid.uuid4().hex
        run_id = self.source_repository.create_ingestion_run(
            str(source["source_id"]), trace_id=trace_id
        )
        if self.run_async:
            thread = threading.Thread(
                target=self._execute_ingestion,
                args=(run_id, source, trace_id),
                daemon=True,
            )
            thread.start()
            return IngestionRunResult(ingestion_run_id=run_id, status="RUNNING")

        self._execute_ingestion(run_id, source, trace_id)
        return self.get_ingestion_status(run_id)

    def get_ingestion_status(self, run_id: str) -> IngestionRunResult:
        row = self.source_repository.get_ingestion_run(run_id)
        if row is None:
            return IngestionRunResult(
                ingestion_run_id=run_id,
                status="NOT_FOUND",
                error={
                    "code": "NOT_FOUND",
                    "message": "ingestion run %r was not found" % run_id,
                    "retryable": False,
                },
            )
        return IngestionRunResult(
            ingestion_run_id=str(row["run_id"]),
            status=row["status"],
            error={
                "code": "INGESTION_FAILED",
                "message": row["error_message"],
                "retryable": False,
            }
            if row.get("error_message")
            else None,
            objects_processed=row.get("objects_processed", 0),
            objects_failed=row.get("objects_failed", 0),
        )

    def _execute_ingestion(self, run_id: str, source: dict, trace_id: str) -> None:
        processed = 0
        failed = 0
        errors: list[str] = []
        connector = self._build_connector(source)
        try:
            connector.connect()
            if source["kind"] == "structured":
                success, state = self._run_structured(source, connector, trace_id)
                processed += 1 if success else 0
                failed += 0 if success else 1
                errors.extend(state.get("errors", []))
            else:
                listed = connector.list_objects((source.get("config") or {}).get("prefix"))
                for obj in listed.get("objects", []):
                    success, state = self._run_unstructured(source, connector, obj, trace_id)
                    processed += 1 if success else 0
                    failed += 0 if success else 1
                    errors.extend(state.get("errors", []))
            status = "SUCCESS" if failed == 0 else "FAILED"
            self.source_repository.update_ingestion_run(
                run_id,
                status,
                objects_processed=processed,
                objects_failed=failed,
                error_message="; ".join(errors) if errors else None,
            )
        except Exception as exc:
            self.source_repository.update_ingestion_run(
                run_id,
                "FAILED",
                objects_processed=processed,
                objects_failed=failed + 1,
                error_message="%s\n%s" % (exc, traceback.format_exc(limit=3)),
            )
        finally:
            try:
                connector.close()
            except Exception:
                pass

    def _run_unstructured(self, source: dict, connector, obj: dict, trace_id: str):
        event = _event_for_object(source, obj, trace_id)
        return run_ingestion(
            event,
            {"connection_id": "source-service"},
            source_id=str(source["source_id"]),
            trace_id=trace_id,
            fetch_unstructured_fn=lambda adapter, handle, object_id: connector.fetch_object(object_id),
            sdk_emit_fn=self.index_client.index,
            checkpoint_store=self.checkpoint_store,
            metadata_repository=self.metadata_repository,
        )

    def _run_structured(self, source: dict, connector, trace_id: str):
        config = source.get("config") or {}
        schema = config.get("schema")
        schema_scope = [schema] if schema else []
        event = _event_for_schema(source, trace_id)
        return run_ingestion(
            event,
            {"connection_id": "source-service"},
            source_id=str(source["source_id"]),
            trace_id=trace_id,
            schema_scope=schema_scope,
            schema_database=config.get("database"),
            fetch_structured_fn=lambda adapter, handle, scope: connector.get_schema_card(
                scope[0] if scope else schema or "PUBLIC",
                max_tables=config.get("max_tables"),
            ),
            sdk_emit_fn=self.index_client.index,
            checkpoint_store=self.checkpoint_store,
            metadata_repository=self.metadata_repository,
        )

    def _build_connector(self, source: dict):
        config = source.get("config") or {}
        if source["kind"] == "structured":
            return ConnectorFactory.create(
                ConnectionConfig(
                    adapter=source["adapter"],
                    account_id=config.get("account_id") or source["account_id"],
                    user=config.get("user", ""),
                    credential_ref=source.get("credential_ref") or "",
                    database=config.get("database", ""),
                    schema=config.get("schema", ""),
                    role=config.get("role"),
                    warehouse=config.get("warehouse"),
                    max_rows=int(config.get("max_rows", 1000)),
                    login_timeout_s=int(config.get("login_timeout_s", 20)),
                    network_timeout_s=int(config.get("network_timeout_s", 30)),
                )
            )
        if source["adapter"] == "local-fs":
            return ConnectorFactory.create_unstructured(
                "local-fs",
                root_path=config["root_path"],
                source_id=str(source["source_id"]),
            )
        if source["adapter"] == "azure-blob":
            container_name = config.get("container") or config.get("container_name")
            if not container_name:
                raise ValueError("azure-blob source config requires container or container_name")
            return ConnectorFactory.create_unstructured(
                "azure-blob",
                connection_string=load_credential(source["credential_ref"]),
                container_name=container_name,
                source_id=str(source["source_id"]),
            )
        raise ValueError("unsupported source adapter %r" % source["adapter"])

    def _require_source(self, source_id: str) -> dict:
        source = self.source_repository.get_source(source_id)
        if source is None:
            raise KeyError("source %r is not registered" % source_id)
        if not source.get("enabled", True):
            raise ValueError("source %r is disabled" % source_id)
        return source


def _kind_for_adapter(adapter: str) -> str:
    return "structured" if adapter == "snowflake" else "unstructured"


def _public_source(source: dict) -> dict:
    return {
        "source_id": str(source["source_id"]),
        "adapter": source["adapter"],
        "account_id": source["account_id"],
        "kind": source.get("kind"),
        "credential_ref": source.get("credential_ref"),
        "config": _redact_secrets(source.get("config") or {}),
        "enabled": source.get("enabled", True),
        "created_at": source.get("created_at"),
        "updated_at": source.get("updated_at"),
    }


def _redact_secrets(value):
    sensitive_keys = {
        "api_key",
        "connection_string",
        "credential",
        "password",
        "private_key",
        "secret",
        "token",
    }
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in sensitive_keys else _redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def _event_for_object(source: dict, obj: dict, trace_id: str) -> dict:
    return {
        "event_id": "evt_%s" % uuid.uuid4().hex,
        "trace_id": trace_id,
        "tenant_id": None,
        "source": {"adapter": source["adapter"], "kind": source["kind"]},
        "object": obj,
        "change_type": "created",
        "checkpoint": {"previous_cursor": None, "current_cursor": None},
        "entitlement_state": "unknown",
    }


def _event_for_schema(source: dict, trace_id: str) -> dict:
    config = source.get("config") or {}
    object_id = "%s.%s" % (config.get("database", ""), config.get("schema", "schema"))
    return _event_for_object(
        source,
        {
            "object_id": object_id,
            "object_type": "schema",
            "source_ref": "%s:%s" % (source["adapter"], object_id),
            "version": "latest",
            "content_hash": None,
            "modified_at": None,
        },
        trace_id,
    )
