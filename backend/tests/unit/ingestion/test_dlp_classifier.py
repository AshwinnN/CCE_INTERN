"""Baseline pattern redaction is explicit; malformed configuration fails closed."""

import pytest
from cce.security.dlp import classify_text, get_dlp_confidence_threshold, redact_text


def test_known_pii_is_classified_and_redacted():
    text = "Email analyst@example.com, SSN 123-45-6789, phone 513-555-0123"
    verdict = classify_text(text)
    assert verdict["sensitivity"] == "PII"
    assert set(verdict["patterns_found"]) == {"EMAIL", "SSN", "PHONE"}
    redacted = redact_text(text)
    assert (
        "analyst@example.com" not in redacted
        and "123-45-6789" not in redacted
        and "513-555-0123" not in redacted
    )
    assert redact_text("Approved metric definition") == "Approved metric definition"


def test_dlp_configuration_validation(monkeypatch):
    monkeypatch.delenv("CCE_DLP_CONFIDENCE_THRESHOLD", raising=False)
    assert get_dlp_confidence_threshold() == 0.7
    monkeypatch.setenv("CCE_DLP_CONFIDENCE_THRESHOLD", ".42")
    assert get_dlp_confidence_threshold() == 0.42
    for value in ("invalid", "1.5", "-1"):
        monkeypatch.setenv("CCE_DLP_CONFIDENCE_THRESHOLD", value)
        with pytest.raises(ValueError):
            get_dlp_confidence_threshold()
