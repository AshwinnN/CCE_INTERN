#!/usr/bin/env python3
"""PII/sensitivity classification and redaction -- STUB.

Not yet required: real regex/heuristic DLP logic (see ingestion_summary.md's
DLP responsibility matrix and ingestion_implementation_checklist.md #3 for
the intended patterns/thresholds) is deliberately deferred. This stub exists
so agents/ingestion_workflow.py's classify_for_dlp / redact_if_needed nodes
have a stable interface to call today; every classification comes back
PUBLIC and redact_text() is a no-op until the real implementation lands.
"""
import os
from typing import Dict, Optional

DEFAULT_DLP_CONFIDENCE_THRESHOLD = 0.7


def get_dlp_confidence_threshold() -> float:
    """CCE_DLP_CONFIDENCE_THRESHOLD -- read now so callers don't have to
    change once real thresholding logic lands here."""
    raw = os.environ.get("CCE_DLP_CONFIDENCE_THRESHOLD")
    if not raw:
        return DEFAULT_DLP_CONFIDENCE_THRESHOLD
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_DLP_CONFIDENCE_THRESHOLD


def classify_text(text: str, column_name: Optional[str] = None) -> Dict:
    """STUB: always reports PUBLIC / no patterns found. Real signature and
    output shape match the intended implementation so callers don't need to
    change when it's filled in:
        {"sensitivity": "PUBLIC" | "INTERNAL" | "PII",
         "patterns_found": [...], "confidence": 0.0-1.0}
    """
    return {"sensitivity": "PUBLIC", "patterns_found": [], "confidence": 1.0}


def redact_text(text: str) -> str:
    """STUB: no-op passthrough until real redaction logic lands here."""
    return text
