#!/usr/bin/env python3
"""Database-agnostic connection parameters. No vendor name may gate on a
field here beyond what every adapter needs -- an adapter-only parameter
(e.g. Snowflake's `warehouse`) still lives on this shared dataclass (the
design docs' own call), but stays Optional and unused by any adapter that
doesn't need it, rather than spawning a second per-adapter config class the
factory would have to special-case.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ConnectionConfig:
    adapter: str                        # "snowflake", "postgres", ... -- registry key, not a display name
    account_id: str                     # account/project identifier
    user: str
    credential_ref: str                 # "env://VAR_NAME" -- see common/tools/credential_loader.py
    database: str
    schema: str
    role: Optional[str] = None
    warehouse: Optional[str] = None     # Snowflake-specific; None for adapters that don't have one
    max_rows: int = 1000
    login_timeout_s: int = 20
    network_timeout_s: int = 30
    write_probe_enabled: bool = True
