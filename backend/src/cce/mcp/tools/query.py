"""Thin MCP helper using the same governed runtime contract."""

from cce.runtime.models import QueryRequest


def query(query_service, question: str, *, domain_id=None, actor_id=None, **metadata):
    return query_service.query(
        QueryRequest(
            question=question, domain_id=domain_id, actor_id=actor_id, metadata=metadata
        )
    )
