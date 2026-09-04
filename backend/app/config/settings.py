"""CCE application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    agenticplane_base_url: str
    agenticplane_api_key: str
    agenticplane_timeout: float
    agenticplane_max_retries: int


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings

    if _settings is None:
        _settings = Settings(
            agenticplane_base_url=os.getenv(
                "CCE_AGENTICPLANE_BASE_URL",
                "http://localhost:8080",
            ),
            agenticplane_api_key=os.getenv(
                "CCE_AGENTICPLANE_API_KEY",
                "",
            ),
            agenticplane_timeout=float(
                os.getenv("CCE_AGENTICPLANE_TIMEOUT", "30")
            ),
            agenticplane_max_retries=int(
                os.getenv("CCE_AGENTICPLANE_MAX_RETRIES", "3")
            ),
        )

    return _settings