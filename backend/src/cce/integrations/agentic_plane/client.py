"""AgenticPlane SDK integration boundary.

CCE must not depend on AgenticPlane infrastructure internals from this
package; callers use this adapter only.
"""


class AgenticPlaneClient:
    def retrieve(self, question: str):
        return []
