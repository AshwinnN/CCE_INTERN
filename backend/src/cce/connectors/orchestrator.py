#!/usr/bin/env python3
"""Deterministic connector-stage orchestration.

Runtime connector work is code, not skill invocation: registry validation,
credential prerequisites, connect handles, and source observation all use
plain Python services with explicit fail-closed error codes. Skills may
remain in this repository as contracts or reference material, but this agent
does not require skill scripts to connect to sources or extract metadata.
"""
from typing import Callable, Optional

from cce.connectors import errors
from cce.connectors.contracts import ConnectorRequest, SkillTraceEntry
from cce.connectors.registry_to_document_connect import validate_document_connect_registry
from cce.connectors.registry_to_structured_connect import to_structured_connect_registry
from cce.connectors.base.connector import StructuredConnector
from cce.connectors.base.exceptions import StructuredConnectorException
from cce.connectors.base.models import ConnectionConfig
from cce.connectors.factory import ConnectorFactory


class Blocked(Exception):
    def __init__(self, error_code, retryable=False):
        self.error = errors.make_error(error_code, retryable)
        super().__init__(error_code)


class Failed(Exception):
    def __init__(self, error_code, retryable=False):
        self.error = errors.make_error(error_code, retryable)
        super().__init__(error_code)


_SUPPORTED_REGISTRY_SCHEMA_VERSIONS = ("1.0",)
_ACTIVE_REGISTRY_STATUS = "READY"
_STRUCTURED_CAPABILITIES = ("write_probe", "statement_timeout", "row_cap", "schema_scope")
_UNSTRUCTURED_CAPABILITIES = (
    "write_probe", "change_detection", "entitlement_capture", "content_fetch", "incremental_sync",
)


def _registry_entry_is_ready(descriptor: dict) -> bool:
    kind = descriptor.get("kind")
    required = _STRUCTURED_CAPABILITIES if kind == "structured" else _UNSTRUCTURED_CAPABILITIES
    capabilities = descriptor.get("capabilities")
    return (
        descriptor.get("schema_version") in _SUPPORTED_REGISTRY_SCHEMA_VERSIONS
        and descriptor.get("status") == _ACTIVE_REGISTRY_STATUS
        and descriptor.get("deprecated") is False
        and descriptor.get("violated_rule") is None
        and bool(descriptor.get("adapter"))
        and kind in ("structured", "unstructured")
        and (kind != "structured" or bool(descriptor.get("dialect")))
        and isinstance(capabilities, dict)
        and all(isinstance(capabilities.get(k), bool) for k in required)
    )


def validate_registry_entry(entry: dict, trace_id: str, skill_trace: list) -> dict:
    """Validate one source-registry entry without loading skill scripts."""
    descriptor = dict(entry or {})
    skill_trace.append(SkillTraceEntry(
        skill="code.source-registry",
        status="success" if _registry_entry_is_ready(descriptor) else "rejected",
        trace_id=trace_id,
    ))

    if descriptor.get("schema_version") not in _SUPPORTED_REGISTRY_SCHEMA_VERSIONS:
        raise Blocked(errors.REGISTRY_SCHEMA_UNSUPPORTED)
    if descriptor.get("status") != _ACTIVE_REGISTRY_STATUS:
        raise Blocked(errors.REGISTRY_INACTIVE)
    if descriptor.get("deprecated") is not False:
        raise Blocked(errors.REGISTRY_DEPRECATED)
    if descriptor.get("violated_rule") is not None:
        raise Blocked(errors.REGISTRY_RULE_VIOLATION)
    if not descriptor.get("adapter"):
        raise Blocked(errors.REGISTRY_ADAPTER_MISSING)

    kind = descriptor.get("kind")
    if kind not in ("structured", "unstructured"):
        raise Blocked(errors.REGISTRY_KIND_MISMATCH)
    if kind == "structured" and not descriptor.get("dialect"):
        raise Blocked(errors.REGISTRY_DIALECT_MISSING)

    required = _STRUCTURED_CAPABILITIES if kind == "structured" else _UNSTRUCTURED_CAPABILITIES
    capabilities = descriptor.get("capabilities")
    if not isinstance(capabilities, dict) or any(not isinstance(capabilities.get(k), bool) for k in required):
        raise Blocked(errors.REGISTRY_CAPABILITIES_INVALID)

    return descriptor


def check_requested_capabilities(descriptor: dict, requested: list) -> None:
    """Fail closed when a requested source capability is unavailable."""
    caps = descriptor.get("capabilities") or {}
    for cap in requested:
        if cap not in caps or caps[cap] is not True:
            raise Failed(errors.REGISTRY_CAPABILITY_UNAVAILABLE)


def resolve_credential(credential_ref: str, role: str, grants: list, ttl_seconds: int,
                        trace_id: str, skill_trace: list) -> dict:
    """Validate the credential prerequisite without fetching or exposing secrets."""
    if not credential_ref:
        raise Blocked(errors.CREDENTIAL_REF_MISSING)
    if not isinstance(grants, list) or ttl_seconds <= 0:
        raise Blocked(errors.CREDENTIAL_RESOLUTION_FAILED)

    lease = {
        "status": "READY",
        "credential_ref_present": True,
        "role": role,
        "grants": list(grants),
        "ttl_seconds": ttl_seconds,
    }
    skill_trace.append(SkillTraceEntry(
        skill="code.credential-resolution",
        status="success",
        trace_id=trace_id,
    ))
    return lease


def connect_structured(descriptor: dict, request: ConnectorRequest, lease: dict,
                        trace_id: str, skill_trace: list,
                        structured_connector_factory: Optional[Callable[[ConnectionConfig], StructuredConnector]] = None
                        ) -> dict:
    """Open a governed, read-only structured-source connection."""
    reshaped = to_structured_connect_registry(descriptor)
    if reshaped["status"] != "OK":
        raise Failed(reshaped["error_code"])

    source_id = request.source_scope.get("source_id", request.source_adapter)
    statement_timeout_ms = request.source_scope.get("statement_timeout_ms", 30000)
    max_rows = request.source_scope.get("max_rows", 200)
    schema_scope = request.source_scope.get("schema_scope", [])

    config = ConnectionConfig(
        adapter=descriptor["adapter"],
        account_id=request.source_scope.get("account_id", ""),
        user=request.source_scope.get("user", ""),
        credential_ref=request.credential_ref,
        database=request.source_scope.get("database", ""),
        schema=schema_scope[0] if schema_scope else "",
        role=request.source_scope.get("role"),
        warehouse=request.source_scope.get("warehouse"),
        max_rows=max_rows,
        network_timeout_s=max(1, statement_timeout_ms // 1000),
    )

    create = structured_connector_factory or ConnectorFactory.create
    connector = create(config)
    trace_label = "cce.connectors.structured.%s.%s" % (
        descriptor["adapter"],
        type(connector).__name__,
    )

    try:
        connection = connector.connect()
        read_only_verified = connection.read_only_verified
    except StructuredConnectorException as e:
        skill_trace.append(SkillTraceEntry(skill=trace_label, status="rejected", trace_id=trace_id))
        raise Failed(errors.CONNECTOR_SKILL_REJECTED) from e
    finally:
        connector.close()

    skill_trace.append(SkillTraceEntry(skill=trace_label, status="success", trace_id=trace_id))
    return {
        "handle_id": "hnd_%s" % source_id,
        "source_id": source_id,
        "adapter": descriptor["adapter"],
        "dialect": descriptor.get("dialect"),
        "read_only_verified": read_only_verified,
        "statement_timeout_ms": statement_timeout_ms,
        "max_rows": max_rows,
        "schema_scope": schema_scope,
        "status": "READY",
        "violated_rule": None,
    }


def connect_unstructured(descriptor: dict, request: ConnectorRequest,
                          trace_id: str, skill_trace: list) -> dict:
    """Create a deterministic unstructured-source connection handle."""
    validated = validate_document_connect_registry(descriptor)
    if validated["status"] != "OK":
        raise Failed(validated["error_code"])

    source_id = request.source_scope.get("source_id", request.source_adapter)
    fetch_timeout_ms = request.source_scope.get("fetch_timeout_ms", 30000)
    max_objects = request.source_scope.get("max_objects", 500)
    object_scope = request.source_scope.get("object_scope", [])
    if fetch_timeout_ms <= 0 or max_objects <= 0:
        raise Failed(errors.CONNECTOR_SKILL_REJECTED)

    handle = {
        "handle_id": "hnd_%s" % source_id,
        "source_id": source_id,
        "adapter": descriptor["adapter"],
        "read_only_verified": validated["capabilities"]["write_probe"],
        "entitlement_capture_verified": validated["capabilities"]["entitlement_capture"],
        "fetch_timeout_ms": fetch_timeout_ms,
        "max_objects": max_objects,
        "object_scope": object_scope,
        "status": "READY",
        "violated_rule": None,
    }
    skill_trace.append(SkillTraceEntry(skill="code.source-connect", status="success", trace_id=trace_id))
    return handle
