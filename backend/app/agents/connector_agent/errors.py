#!/usr/bin/env python3
"""Explicit, safe error codes for the Connector Agent. Every code here maps
to a specific fail-closed condition named in the design -- no generic
"something went wrong" code, because a generic code gives a caller nothing
to act on and a reviewer nothing to audit against.
"""
from dataclasses import dataclass
from typing import Optional

# Registry / adapter validation.
REGISTRY_SCHEMA_UNSUPPORTED = "REGISTRY_SCHEMA_UNSUPPORTED"
REGISTRY_INACTIVE = "REGISTRY_INACTIVE"
REGISTRY_DEPRECATED = "REGISTRY_DEPRECATED"
REGISTRY_RULE_VIOLATION = "REGISTRY_RULE_VIOLATION"
REGISTRY_KIND_MISMATCH = "REGISTRY_KIND_MISMATCH"
REGISTRY_ADAPTER_MISSING = "REGISTRY_ADAPTER_MISSING"
REGISTRY_DIALECT_MISSING = "REGISTRY_DIALECT_MISSING"
REGISTRY_CAPABILITIES_INVALID = "REGISTRY_CAPABILITIES_INVALID"
REGISTRY_CAPABILITY_UNAVAILABLE = "REGISTRY_CAPABILITY_UNAVAILABLE"
REGISTRY_ADAPTER_UNKNOWN = "REGISTRY_ADAPTER_UNKNOWN"  # not in known_adapters at all

# Credential prerequisite.
CREDENTIAL_REF_MISSING = "CREDENTIAL_REF_MISSING"
CREDENTIAL_RESOLUTION_FAILED = "CREDENTIAL_RESOLUTION_FAILED"

# Connector Skill invocation.
CONNECTOR_SKILL_REJECTED = "CONNECTOR_SKILL_REJECTED"

# Observation / change capture.
OBSERVATION_MODE_INVALID = "OBSERVATION_MODE_INVALID"
OBSERVATION_SKILL_REJECTED = "OBSERVATION_SKILL_REJECTED"
CHECKPOINT_MISSING_FOR_RESUME = "CHECKPOINT_MISSING_FOR_RESUME"


@dataclass
class ConnectorError:
    code: str
    message: str
    retryable: bool = False

    def to_dict(self):
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


# Human-safe messages, deliberately generic -- never include the raw skill
# rejection payload, a registry internal, or anything provider-specific here.
_MESSAGES = {
    REGISTRY_SCHEMA_UNSUPPORTED: "The registry record's schema version is not supported.",
    REGISTRY_INACTIVE: "The requested source adapter is inactive.",
    REGISTRY_DEPRECATED: "The requested source adapter is deprecated.",
    REGISTRY_RULE_VIOLATION: "The registry record failed its own validation rule.",
    REGISTRY_KIND_MISMATCH: "The registry record's kind does not match the requested route.",
    REGISTRY_ADAPTER_MISSING: "The registry record is missing its adapter key.",
    REGISTRY_DIALECT_MISSING: "The registry record is missing a required dialect.",
    REGISTRY_CAPABILITIES_INVALID: "The registry record's capability set is invalid.",
    REGISTRY_CAPABILITY_UNAVAILABLE: "A requested capability is not available for this adapter.",
    REGISTRY_ADAPTER_UNKNOWN: "The requested source adapter is not known to this deployment.",
    CREDENTIAL_REF_MISSING: "No credential reference was supplied.",
    CREDENTIAL_RESOLUTION_FAILED: "The credential reference could not be resolved.",
    CONNECTOR_SKILL_REJECTED: "The connector could not validate this source.",
    OBSERVATION_MODE_INVALID: "The requested observation mode is not valid.",
    OBSERVATION_SKILL_REJECTED: "Change observation could not be completed for this source.",
    CHECKPOINT_MISSING_FOR_RESUME: "No checkpoint exists to resume observation from.",
}


def make_error(code: str, retryable: bool = False) -> ConnectorError:
    return ConnectorError(code=code, message=_MESSAGES.get(code, "Request failed."), retryable=retryable)
