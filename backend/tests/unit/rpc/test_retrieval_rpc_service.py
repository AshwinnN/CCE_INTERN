from types import SimpleNamespace

from cce.gen.cce.v1 import retrieval_pb2
from cce.rpc.services.retrieval_service import RetrievalRPCService


def test_retrieval_rpc_maps_the_shared_service_response():
    service = SimpleNamespace(
        retrieve=lambda question, limit, graph_depth: {
            "trace_id": "trace-1",
            "question": question,
            "backend": "local",
            "memories": [],
            "graph": {
                "unsupported": True,
                "backend": "local",
                "reason": "no graph store",
            },
        }
    )
    rpc = RetrievalRPCService(SimpleNamespace(retrieval_service=service))

    response = rpc.Retrieve(
        retrieval_pb2.RetrieveRequest(
            question="What is CCE?", limit=4, graph_depth=3
        ),
        None,
    )

    assert response.trace_id == "trace-1"
    assert response.question == "What is CCE?"
    assert response.backend == "local"
    assert response.graph.unsupported is True
    assert response.graph.reason == "no graph store"
