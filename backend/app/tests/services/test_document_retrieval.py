from __future__ import annotations

import asyncio
import json

from agenticplane.types import SearchOptions

from services.document_retrieval import (
    document_retrieval_service,
)


AGENT_ID = "cce-document-ingestion-test"

QUERY = (
    "What were the temperature conditions "
    "during July 2026?"
)


async def main() -> None:

    print("=" * 80)
    print("CCE DOCUMENT RETRIEVAL TEST")
    print("=" * 80)

    print()
    print(f"Agent ID : {AGENT_ID}")
    print(f"Query    : {QUERY}")

    options = SearchOptions(
        limit=10,
    )

    print()
    print("Calling DocumentRetrievalService...")

    results = await (
        document_retrieval_service.retrieve(
            agent_id=AGENT_ID,
            query=QUERY,
            options=options,
        )
    )

    print()
    print("=" * 80)
    print("RETRIEVAL RESULT")
    print("=" * 80)

    print(
        json.dumps(
            results,
            indent=2,
            default=str,
            ensure_ascii=False,
        )
    )

    print()
    print("=" * 80)
    print("RETRIEVAL TEST COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())