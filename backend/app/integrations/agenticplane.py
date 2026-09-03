"""Small boundary around the project's AgenticPlane SDK.

CCE owns the orchestration; AgenticPlane owns long-term memory. This module
only resolves a configured plane object and delegates to the SDK methods.
No memory implementation is duplicated here.
"""
import importlib
import os
from typing import Any, Callable


class AgenticPlaneUnavailable(RuntimeError):
    pass


def _load_object(path: str) -> Any:
    module_name, separator, attribute = path.rpartition(":")
    if not separator:
        raise ValueError("CCE_AGENTICPLANE_FACTORY must use module:attribute format")
    module = importlib.import_module(module_name)
    return getattr(module, attribute)


def get_plane() -> Any:
    """Resolve the host application's already-created AgenticPlane object.

    Preferred configuration is CCE_AGENTICPLANE_FACTORY=module:callable. The
    callable may return the plane instance. For SDK packages that expose a
    module-level `plane` or `get_plane`, those are accepted as well.
    """
    factory_path = os.getenv("CCE_AGENTICPLANE_FACTORY")
    if factory_path:
        factory: Callable[[], Any] = _load_object(factory_path)
        plane = factory()
        if plane is None:
            raise AgenticPlaneUnavailable("AgenticPlane factory returned None")
        return plane

    try:
        sdk = importlib.import_module("agenticplane")
    except ImportError as exc:
        raise AgenticPlaneUnavailable(
            "AgenticPlane SDK is not installed/configured. Set CCE_AGENTICPLANE_FACTORY."
        ) from exc

    plane = getattr(sdk, "plane", None)
    if plane is not None:
        return plane
    sdk_get_plane = getattr(sdk, "get_plane", None)
    if callable(sdk_get_plane):
        plane = sdk_get_plane()
        if plane is not None:
            return plane

    raise AgenticPlaneUnavailable(
        "No AgenticPlane instance found. Set CCE_AGENTICPLANE_FACTORY=module:factory."
    )


class AgenticPlaneMemory:
    """Direct delegation to the three project-approved SDK memory methods."""

    def __init__(self, plane: Any = None):
        self.plane = plane

    def _resolve(self) -> Any:
        return self.plane if self.plane is not None else get_plane()

    def store(self, **kwargs):
        return self._resolve().memory.store(**kwargs)

    def store_batch(self, **kwargs):
        return self._resolve().memory.store_batch(**kwargs)

    def search(self, **kwargs):
        return self._resolve().memory.search(**kwargs)
