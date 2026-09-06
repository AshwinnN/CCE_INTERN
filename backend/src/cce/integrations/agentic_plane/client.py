"""AgenticPlane SDK integration boundary.

CCE must not depend on AgenticPlane infrastructure internals from this
package; callers use this adapter only.
"""


class AgenticPlaneClient:
    def index(self, payload: dict) -> dict:
        return {"status": "not_configured", "indexed": 0}

    def search(self, query: str, *, limit: int = 5):
        return self.retrieve(query)[:limit]

    def delete(self, document_id: str) -> dict:
        return {"status": "not_configured", "deleted": 0}

    def graph(self, *args, **kwargs):
        raise NotImplementedError("AgenticPlane graph operations are not implemented")

    def retrieve(self, question: str):
        return []
