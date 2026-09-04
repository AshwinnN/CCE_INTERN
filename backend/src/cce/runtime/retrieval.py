"""AgenticPlane retrieval adapter boundary."""

from cce.integrations.agentic_plane.client import AgenticPlaneClient


def retrieve_evidence(client: AgenticPlaneClient, question: str):
    return client.retrieve(question)
