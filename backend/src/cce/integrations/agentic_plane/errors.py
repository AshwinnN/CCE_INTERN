"""CCE-owned errors exposed by the AgenticPlane integration boundary."""


class GraphNotSupportedError(RuntimeError):
    """Raised when the selected index backend has no graph store."""


class GraphExtractionError(RuntimeError):
    """Raised when synchronous graph extraction fails after memory storage."""
