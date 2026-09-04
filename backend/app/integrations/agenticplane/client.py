"""AgenticPlane client configuration and lifecycle."""

from __future__ import annotations

from agenticplane import AsyncAgenticPlane

from config.settings import get_settings


_client: AsyncAgenticPlane | None = None


async def get_client() -> AsyncAgenticPlane:
    """Return the shared AgenticPlane client."""
    global _client

    if _client is None:
        settings = get_settings()

        _client = AsyncAgenticPlane(
            base_url=settings.agenticplane_base_url,
            api_key=settings.agenticplane_api_key,
            timeout=settings.agenticplane_timeout,
            max_retries=settings.agenticplane_max_retries,
        )

    return _client


async def close_client() -> None:
    """Close the shared AgenticPlane client."""
    global _client

    if _client is None:
        return

    close = getattr(_client, "close", None)

    if close is not None:
        result = close()

        if hasattr(result, "__await__"):
            await result

    _client = None