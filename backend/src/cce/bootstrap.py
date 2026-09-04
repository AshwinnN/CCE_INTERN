"""Composition root for wiring CCE services and infrastructure."""

from dataclasses import dataclass

from cce.config.settings import Settings
from cce.runtime.service import QueryService


@dataclass(frozen=True)
class Application:
    settings: Settings
    query_service: QueryService


def build_application(settings: Settings) -> Application:
    return Application(settings=settings, query_service=QueryService())
