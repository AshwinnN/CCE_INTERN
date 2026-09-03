#!/usr/bin/env python3
"""Sequences calls to existing connector-stage Skills and interprets their
results. Contains no validation logic that re-implements a Skill's own Core
Rule -- every fail-closed decision below is either (a) inspecting a status
field a Skill already returned, or (b) a check this stage's design review
explicitly assigned to the Agent (requested-capability matching, credential
presence, routing) because no existing Skill owns it.

One exception: the structured lane's connect step (connect_structured()
below) is NOT a Skill call. skill-strucutred_source_connect's write-probe
was a caller-supplied boolean nothing in production ever set, so its STR03
"prove read-only with a live write probe" guarantee was simulated, never
enforced. Opening a database connection is a deterministic process with a
real, checkable outcome -- it belongs in connectors/ as a tool, not behind
a Skill's validate-a-JSON-profile contract. See
structured_connector_architecture.md and connectors/README (if present)
for the design; skill-strucutred_source_connect itself is no longer
invoked anywhere in this Agent.
"""
from typing import Callable, Optional

from agents.connector_agent import errors, router
from agents.connector_agent.contracts import ConnectorRequest, ConnectorResponse, SkillTraceEntry
from common.skill_loader import load_skill_function
from common.registry_to_structured_connect import to_structured_connect_registry
from common.registry_to_document_connect import validate_document_connect_registry
from connectors.base.connector import StructuredConnector
from connectors.base.exceptions import StructuredConnectorException
from connectors.base.models import ConnectionConfig
from connectors.factory import ConnectorFactory


class Blocked(Exception):
    def __init__(self, error_code, retryable=False):
        self.error = errors.make_error(error_code, retryable)
        super().__init__(error_code)


class Failed(Exception):
    def __init__(self, error_code, retryable=False):
        self.error = errors.make_error(error_code, retryable)
        super().__init__(error_code)


def _load_registry_validate():
    return load_skill_function("skill-source-registry", "validate_registry_entry.py", "validate")


def _load_credential_resolve():
    return load_skill_function("skill-credential-resolution", "resolve_credential.py", "resolve")


def _load_document_connect():
    return load_skill_function("skill-document-source-connect", "validate_document_profile.py", "validate")


def validate_registry_entry(entry: dict, trace_id: str, skill_trace: list) -> dict:
    """Runs the real skill-source-registry validator and fails closed on
    every non-READY outcome, mapping its own status to this Agent's codes."""
    validate = _load_registry_validate()
    descriptor = validate(entry)
    skill_trace.append(SkillTraceEntry(
        skill="skill-source-registry",
        status="success" if descriptor["status"] == "READY" else "rejected",
        trace_id=trace_id,
    ))
    if descriptor["status"] != "READY":
        # skill-source-registry's own rule IDs (REG02..REG08) map directly
        # onto this Agent's REGISTRY_* codes for the conditions this design
        # calls out explicitly; anything else surfaces as the closest match.
        rule_to_code = {
            "REG02": errors.REGISTRY_KIND_MISMATCH,
            "REG03": errors.REGISTRY_CAPABILITIES_INVALID,
            "REG04": errors.REGISTRY_CAPABILITIES_INVALID,
            "REG06": errors.REGISTRY_DIALECT_MISSING,
            "REG08": errors.REGISTRY_SCHEMA_UNSUPPORTED,
        }
        code = rule_to_code.get(descriptor["violated_rule"], errors.REGISTRY_RULE_VIOLATION)
        raise Blocked(code)
    if descriptor.get("deprecated"):
        raise Blocked(errors.REGISTRY_DEPRECATED)
    return descriptor


def check_requested_capabilities(descriptor: dict, requested: list) -> None:
    """Requested capability strings are checked against the REAL capability
    keys the registry descriptor carries -- not the illustrative "connect"/
    "read_only" names in early design notes, per direct inspection of
    skill-source-registry's actual CAPABILITY_SETS."""
    caps = descriptor.get("capabilities") or {}
    for cap in requested:
        if cap not in caps or caps[cap] is not True:
            raise Failed(errors.REGISTRY_CAPABILITY_UNAVAILABLE)


def resolve_credential(credential_ref: str, role: str, grants: list, ttl_seconds: int,
                        trace_id: str, skill_trace: list) -> dict:
    if not credential_ref:
        raise Blocked(errors.CREDENTIAL_REF_MISSING)
    resolve = _load_credential_resolve()
    lease = resolve({
        "credential_ref": credential_ref, "role": role,
        "grants": grants, "ttl_seconds": ttl_seconds,
    })
    skill_trace.append(SkillTraceEntry(
        skill="skill-credential-resolution",
        status="success" if lease["status"] == "READY" else "rejected",
        trace_id=trace_id,
    ))
    if lease["status"] != "READY":
        raise Blocked(errors.CREDENTIAL_RESOLUTION_FAILED)
    return lease


def connect_structured(descriptor: dict, request: ConnectorRequest, lease: dict,
                        trace_id: str, skill_trace: list,
                        structured_connector_factory: Optional[Callable[[ConnectionConfig], StructuredConnector]] = None
                        ) -> dict:
    """Opens a governed, read-only connection to a structured source via
    connectors.factory.ConnectorFactory -- a real, live write-probe, not a
    simulated one (see this module's docstring). `structured_connector_factory`
    defaults to ConnectorFactory.create; tests inject a fake StructuredConnector
    the same way change_capture.py's observers take an injected
    object_lister/catalog_lister, so no test in this Agent's suite needs
    live database credentials.

    to_structured_connect_registry() still runs first -- it's deterministic,
    zero-I/O plumbing that validates the registry descriptor is well-formed
    before any connection is attempted, independent of which connector
    handles the connection itself.
    """
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
    trace_label = "connectors.%s.%s" % (descriptor["adapter"], type(connector).__name__)

    # This Agent's job ends at proving connectivity -- it hands back an
    # opaque handle_id, never a live session (the handle must stay a plain,
    # JSON-serializable dict; see contracts.ConnectorResponse.to_dict()).
    # Whatever later needs a live connection (e.g. agents/ingestion_workflow.py's
    # fetch_structured node) opens its own, fresh, separately write-probed.
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
    validated = validate_document_connect_registry(descriptor)
    if validated["status"] != "OK":
        raise Failed(validated["error_code"])

    connect = _load_document_connect()
    profile = {
        "source_id": request.source_scope.get("source_id", request.source_adapter),
        "adapter": descriptor["adapter"],
        "credential_ref": request.credential_ref,
        "fetch_timeout_ms": request.source_scope.get("fetch_timeout_ms", 30000),
        "max_objects": request.source_scope.get("max_objects", 500),
        "object_scope": request.source_scope.get("object_scope", []),
    }
    handle = connect(profile)
    skill_trace.append(SkillTraceEntry(
        skill="skill-document-source-connect",
        status="success" if handle["status"] == "READY" else "rejected",
        trace_id=trace_id,
    ))
    if handle["status"] != "READY":
        raise Failed(errors.CONNECTOR_SKILL_REJECTED)
    return handle
