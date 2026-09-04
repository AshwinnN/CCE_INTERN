"""Thin MCP query adapter."""

from cce.runtime.service import QueryRequest


def query(query_service, question: str, **metadata):
    return query_service.query(QueryRequest(question=question, metadata=metadata))
