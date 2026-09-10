from cce.runtime.models import QueryRequest

def query(query_service, question: str, *, workspace_id: str, actor_id=None):
    return query_service.query(QueryRequest(question=question,workspace_id=workspace_id,actor_id=actor_id))
