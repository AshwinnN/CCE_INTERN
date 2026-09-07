"""Raw retrieval RPC mapping."""

from google.protobuf.struct_pb2 import Struct


class RetrievalRPCService:
    def __init__(self, app):
        self.app = app

    def Retrieve(self, request, context):
        from cce.gen.cce.v1 import retrieval_pb2

        result = self.app.retrieval_service.retrieve(
            request.question,
            limit=request.limit or 10,
            graph_depth=request.graph_depth or 2,
        )
        return retrieval_pb2.RetrieveResponse(
            trace_id=result["trace_id"],
            question=result["question"],
            backend=result["backend"],
            memories=[_memory(item, retrieval_pb2) for item in result["memories"]],
            graph=_graph(result["graph"], retrieval_pb2),
        )


def _struct(value: dict | None) -> Struct:
    message = Struct()
    message.update(value or {})
    return message


def _memory(item: dict, retrieval_pb2):
    provenance = item["provenance"]
    return retrieval_pb2.RetrievedMemory(
        memory_id=item["memory_id"],
        content=item["content"],
        score=item["score"],
        provenance=retrieval_pb2.RetrievalProvenance(
            document_id=provenance.get("document_id") or "",
            source_id=provenance.get("source_id") or "",
            object_id=provenance.get("object_id") or "",
            trace_id=provenance.get("trace_id") or "",
            source_ref=provenance.get("source_ref") or "",
            version=provenance.get("version") or "",
        ),
        metadata=_struct(item.get("metadata")),
    )


def _graph(item: dict, retrieval_pb2):
    if item.get("unsupported"):
        return retrieval_pb2.GraphPayload(
            unsupported=True,
            backend=item.get("backend", ""),
            reason=item.get("reason", ""),
        )
    return retrieval_pb2.GraphPayload(
        entities=[
            retrieval_pb2.GraphEntity(
                entity_id=value.get("entity_id", ""),
                name=value.get("name", ""),
                entity_type=value.get("entity_type", ""),
                description=value.get("description", ""),
                source_memories=value.get("source_memories", []),
                properties=_struct(value.get("properties")),
                project_id=value.get("project_id", ""),
                created_at=value.get("created_at") or "",
                updated_at=value.get("updated_at") or "",
            )
            for value in item.get("entities", [])
        ],
        relationships=[
            retrieval_pb2.GraphRelationship(
                relationship_id=value.get("relationship_id", ""),
                source_entity_id=value.get("source_entity_id", ""),
                target_entity_id=value.get("target_entity_id", ""),
                relation_type=value.get("relation_type", ""),
                description=value.get("description", ""),
                weight=value.get("weight", 0.0),
                created_at=value.get("created_at") or "",
            )
            for value in item.get("relationships", [])
        ],
        memories=[
            retrieval_pb2.GraphMemory(
                memory_id=value.get("memory_id", ""),
                content=value.get("content", ""),
                score=value.get("score", 0.0),
            )
            for value in item.get("memories", [])
        ],
    )
