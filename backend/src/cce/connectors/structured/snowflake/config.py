#!/usr/bin/env python3
"""Snowflake-specific config assembly: env vars -> ConnectionConfig.

Only place in this package that names a CCE_SNOWFLAKE_* variable -- the
generic layers (connectors/base/, connectors/factory.py) never read the
environment directly.
"""
import os
from typing import Optional

from cce.connectors.base.models import ConnectionConfig


def build_config_from_env(schema: Optional[str] = None, database: Optional[str] = None) -> ConnectionConfig:
    """Assemble a ConnectionConfig from CCE_SNOWFLAKE_* env vars, the same
    variables tools/verify_snowflake_connection.py already reads for a real
    connection. `schema`/`database` override the env default when the
    caller needs a different one than the account-level default (e.g. per
    change-event schema_scope)."""
    return ConnectionConfig(
        adapter="snowflake",
        account_id=os.environ["CCE_SNOWFLAKE_ACCOUNT"],
        user=os.environ["CCE_SNOWFLAKE_USER"],
        credential_ref="env://CCE_SNOWFLAKE_PRIVATE_KEY",
        database=database or os.environ["CCE_SNOWFLAKE_DATABASE"],
        schema=schema or os.environ["CCE_SNOWFLAKE_SCHEMA"],
        role=os.environ.get("CCE_SNOWFLAKE_ROLE") or None,
        warehouse=os.environ.get("CCE_SNOWFLAKE_WAREHOUSE") or None,
        login_timeout_s=int(os.environ.get("CCE_SNOWFLAKE_LOGIN_TIMEOUT", 20)),
        network_timeout_s=int(os.environ.get("CCE_SNOWFLAKE_NETWORK_TIMEOUT", 30)),
    )
