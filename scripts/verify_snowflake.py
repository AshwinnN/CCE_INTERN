#!/usr/bin/env python3
"""Manual Snowflake connector connectivity diagnostic."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend" / "src"))
load_dotenv(REPO / ".env", override=True)
load_dotenv(REPO / "backend" / ".env", override=True)

from cce.connectors.factory import ConnectorFactory  # noqa: E402
from cce.connectors.structured.snowflake.config import build_config_from_env  # noqa: E402


def main() -> int:
    if os.environ.get("CCE_SNOWFLAKE_ENABLED", "false").lower() != "true":
        print("CCE_SNOWFLAKE_ENABLED is not 'true' -- stopping before any connection.")
        return 1

    config = build_config_from_env()
    connector = ConnectorFactory.create(config)
    try:
        connection = connector.connect()
        print("Snowflake connection status:", connection.status)
        print("Read-only verified:", connection.read_only_verified)
        card = connector.get_schema_card(config.schema, max_tables=5)
        print("Schema:", card.get("schema"))
        print("Tables discovered:", len(card.get("tables", [])))
        return 0
    finally:
        connector.close()


if __name__ == "__main__":
    sys.exit(main())
