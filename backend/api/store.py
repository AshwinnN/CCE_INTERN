from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy
import uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class MockStore:
    def __init__(self) -> None:
        self.proposals = [
            {
                "proposal_id": "prop-001",
                "type": "GLOSSARY",
                "title": "Delivery SLA",
                "term": "Delivery SLA",
                "candidate": "The contractual delivery performance target for Customer ABC.",
                "evidence": [
                    {"source": "Customer Contract - ABC.pdf", "location": "Section 4.2", "snippet": "Delivery SLA target is 90% unless an approved customer-specific override applies."},
                    {"source": "Snowflake", "location": "delivery_performance", "snippet": "Current performance: 82%."},
                ],
                "status": "PROPOSED",
                "confidence": 0.94,
                "entity": "Customer ABC",
                "created_at": _now(),
            },
            {
                "proposal_id": "prop-002",
                "type": "SEMANTIC_MAPPING",
                "title": "Delivery SLA -> Snowflake.delivery_performance",
                "term": "Delivery SLA",
                "candidate": "Map Delivery SLA to the governed Snowflake delivery_performance field.",
                "evidence": [
                    {"source": "Snowflake", "location": "ENTERPRISE.delivery_performance", "snippet": "Read-only current performance measure."},
                    {"source": "Customer Contract - ABC.pdf", "location": "Section 4.2", "snippet": "Delivery performance is the contractual measure used for SLA compliance."},
                ],
                "status": "PROPOSED",
                "confidence": 0.91,
                "entity": "Customer ABC",
                "created_at": _now(),
            },
            {
                "proposal_id": "prop-003",
                "type": "POLICY_RULE",
                "title": "Customer ABC override = 80%",
                "term": "Customer ABC SLA override",
                "candidate": "Customer ABC override = 80%, valid until September 30.",
                "evidence": [
                    {"source": "Customer Contract - ABC.pdf", "location": "Section 4.3", "snippet": "Customer ABC approved exception: SLA threshold is 80% through September 30."},
                ],
                "status": "PROPOSED",
                "confidence": 0.97,
                "entity": "Customer ABC",
                "created_at": _now(),
            },
            {
                "proposal_id": "prop-004",
                "type": "ENTITY_RESOLUTION",
                "title": "Customer ABC",
                "term": "Customer ABC",
                "candidate": "Contract entity Customer ABC resolves to the governed Snowflake customer record.",
                "evidence": [
                    {"source": "Customer Contract - ABC.pdf", "location": "Customer section", "snippet": "Customer ABC"},
                    {"source": "Snowflake", "location": "customer_master", "snippet": "CUSTOMER_ID=ABC-001; NAME=Customer ABC"},
                ],
                "status": "PROPOSED",
                "confidence": 0.99,
                "entity": "Customer ABC",
                "created_at": _now(),
            },
        ]
        self.packages = [
            {
                "package_id": "pkg-delivery-001",
                "name": "Delivery Performance",
                "description": "Governed context for delivery SLA questions.",
                "active_version": "v1.0",
                "status": "ACTIVE",
                "created_at": _now(),
                "assets": ["Delivery SLA", "Customer ABC", "Customer ABC SLA override", "delivery_performance"],
                "glossary": [{"term": "Delivery SLA", "definition": "Contractual delivery performance threshold."}],
                "semantic_model": [{"concept": "Delivery SLA", "physical_ref": "Snowflake.delivery_performance"}],
                "policy_rules": [{"rule_id": "RULE-ABC-80", "expression": "Customer ABC override = 80%, valid until Sept 30"}],
                "verified_sql": [{"sql_id": "SQL-SLA-001", "sql": "SELECT delivery_performance FROM ENTERPRISE.delivery_performance WHERE customer_id = 'ABC-001'"}],
                "entity_graph": [{"from": "Customer ABC", "to": "ABC-001", "relation": "RESOLVES_TO"}],
                "ambiguity_register": [],
                "approved_by": "Domain Steward",
                "valid_until": "2026-09-30",
            }
        ]
        self.ingestion_runs: list[dict] = [
            {
                "run_id": "ing-1001",
                "document_name": "Customer Contract - ABC.pdf",
                "source": "Customer Contract (Google Docs)",
                "status": "COMPLETED",
                "stage": "ENTITY_RESOLUTION",
                "created_at": _now(),
                "objects_processed": 1,
                "chunks": 18,
                "grounded_facts": 7,
                "resolved_entities": 3,
                "trace_id": "trc_ing_1001",
            }
        ]

    def ingest(self, document_name: str, source: str) -> dict:
        run_id = f"ing-{uuid.uuid4().hex[:8]}"
        trace_id = f"trc_ing_{uuid.uuid4().hex[:10]}"
        run = {
            "run_id": run_id,
            "document_name": document_name,
            "source": "Customer Contract (Google Docs)" if source == "customer-contract" else source,
            "status": "COMPLETED",
            "stage": "ENTITY_RESOLUTION",
            "created_at": _now(),
            "objects_processed": 1,
            "chunks": 18,
            "grounded_facts": 7,
            "resolved_entities": 3,
            "trace_id": trace_id,
            "agentic_plane": {
                "ingest": "COMPLETED",
                "ground": "COMPLETED",
                "entity_resolution": "COMPLETED",
            },
        }
        self.ingestion_runs.insert(0, run)
        # Re-use deterministic proposals for UI iteration; the real backend will create these from the pipeline.
        for proposal in self.proposals:
            proposal["status"] = "PROPOSED"
        return deepcopy(run)

    def review(self, proposal_id: str, decision: str, comment: str) -> dict:
        for proposal in self.proposals:
            if proposal["proposal_id"] == proposal_id:
                proposal["status"] = decision
                proposal["review"] = {"decision": decision, "comment": comment, "approved_by": "Domain Steward", "reviewed_at": _now()}
                return deepcopy(proposal)
        raise KeyError(proposal_id)

    def create_package(self, body: dict) -> dict:
        selected = body.get("proposal_ids") or [p["proposal_id"] for p in self.proposals if p["status"] == "APPROVED"]
        approved = [p for p in self.proposals if p["proposal_id"] in selected and p["status"] == "APPROVED"]
        if not approved:
            raise ValueError("At least one approved proposal is required to create a domain package")
        pkg_id = f"pkg-{uuid.uuid4().hex[:8]}"
        package = {
            "package_id": pkg_id,
            "name": body["name"],
            "description": body.get("description", ""),
            "active_version": "v1.0",
            "status": "ACTIVE",
            "created_at": _now(),
            "assets": [p["title"] for p in approved],
            "glossary": [{"term": p["term"], "definition": p["candidate"]} for p in approved if p["type"] == "GLOSSARY"],
            "semantic_model": [{"concept": p["term"], "physical_ref": "Snowflake.delivery_performance"} for p in approved if p["type"] == "SEMANTIC_MAPPING"],
            "policy_rules": [{"rule_id": p["proposal_id"], "expression": p["candidate"]} for p in approved if p["type"] == "POLICY_RULE"],
            "verified_sql": [{"sql_id": "SQL-GENERATED-001", "sql": "SELECT delivery_performance FROM ENTERPRISE.delivery_performance WHERE customer_id = 'ABC-001'"}],
            "entity_graph": [{"from": p["entity"], "to": "ABC-001", "relation": "RESOLVES_TO"} for p in approved if p["type"] == "ENTITY_RESOLUTION"],
            "ambiguity_register": [],
            "approved_by": "Domain Steward",
            "valid_until": "2026-09-30",
        }
        self.packages.insert(0, package)
        return deepcopy(package)

    def answer(self, question: str, package_id: str, context_enabled: bool) -> dict:
        package = next((p for p in self.packages if p["package_id"] == package_id), None)
        if not package:
            raise KeyError(package_id)
        base = {
            "82% vs. the standard 90%.": "NO",
            "82% vs. 80%.": "YES",
        }
        if context_enabled:
            answer = "YES"
            rationale = "Current performance is 82%. The active Domain Package resolves the applicable Customer ABC exception to an approved 80% threshold."
            comparison = "82% vs 80%"
            rule = "Customer ABC override = 80%, valid until Sept 30"
            sql = package["verified_sql"][0]["sql"]
        else:
            answer = "NO"
            rationale = "Without context, the baseline 90% SLA is applied. The approved customer-specific exception is not available."
            comparison = "82% vs standard 90%"
            rule = "Baseline SLA 90% (context disabled)"
            sql = "SELECT delivery_performance FROM ENTERPRISE.delivery_performance WHERE customer_id = 'ABC-001'"
        return {
            "question": question,
            "answer": answer,
            "rationale": rationale,
            "comparison": comparison,
            "context_enabled": context_enabled,
            "context_used": context_enabled,
            "package_id": package["package_id"] if context_enabled else "",
            "package_version": package["active_version"] if context_enabled else "",
            "applied_rule": rule,
            "executed_sql": sql,
            "trace_id": f"trc_q_{uuid.uuid4().hex[:10]}",
            "approver": package["approved_by"] if context_enabled else "",
            "valid_until": package["valid_until"] if context_enabled else "",
            "confidence": 0.96 if context_enabled else 0.83,
            "citations": [
                {"source": "Customer Contract (Google Docs)", "location": "Section 4.3", "detail": "Approved 80% Customer ABC exception"},
                {"source": "Snowflake", "location": "ENTERPRISE.delivery_performance", "detail": "Current performance 82%"},
            ],
        }

    def snapshot(self) -> dict:
        return {"proposals": deepcopy(self.proposals), "packages": deepcopy(self.packages), "ingestion_runs": deepcopy(self.ingestion_runs)}


store = MockStore()
