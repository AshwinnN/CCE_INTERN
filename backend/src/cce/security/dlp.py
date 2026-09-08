"""Deterministic baseline PII pattern detection, not a comprehensive enterprise DLP engine."""

import os
import re
from typing import Optional

DEFAULT_DLP_CONFIDENCE_THRESHOLD = 0.7
_PATTERNS = {
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "PHONE": re.compile(
        r"(?<!\w)(?:\+\d{1,3}[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\w)"
    ),
}


def get_dlp_confidence_threshold() -> float:
    value = float(
        os.environ.get("CCE_DLP_CONFIDENCE_THRESHOLD", DEFAULT_DLP_CONFIDENCE_THRESHOLD)
    )
    if not 0 <= value <= 1:
        raise ValueError("DLP threshold must be between 0 and 1")
    return value


def classify_text(text: str, column_name: Optional[str] = None) -> dict:
    found = [name for name, pattern in _PATTERNS.items() if pattern.search(text)]
    return {
        "sensitivity": "PII" if found else "PUBLIC",
        "patterns_found": found,
        "confidence": 1.0,
    }


def redact_text(text: str) -> str:
    for name, pattern in _PATTERNS.items():
        text = pattern.sub("[REDACTED_" + name + "]", text)
    return text
