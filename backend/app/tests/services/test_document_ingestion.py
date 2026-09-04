from __future__ import annotations

import asyncio
import json

from agenticplane.types import MemoryType

from services.document_ingestion import (
    document_ingestion_service,
)


METADATA = {
    "document_id": "noaa_data/national-202607.pdf",
    "source_system": "azure_blob",
    "source_uri": "azure://noaa-data/national-202607.pdf",
    "original_filename": "national-202607.pdf",
    "mime_type": "application/pdf",
}


CONTENT = {
    "document_title": "National Climate Report — July 2026",
    "sections": [
        {
            "title": "National Overview",
            "content": [
                {
                    "type": "heading",
                    "level": 3,
                    "text": "Highlights",
                },
                {
                    "type": "paragraph",
                    "text": (
                        "July 2026 was characterized "
                        "by above-average temperatures "
                        "across much of the contiguous "
                        "United States."
                    ),
                },
                {
                    "type": "heading",
                    "level": 3,
                    "text": "July Temperature",
                },
                {
                    "type": "paragraph",
                    "text": (
                        "The national average "
                        "temperature for July was "
                        "above the long-term average."
                    ),
                },
                {
                    "type": "heading",
                    "level": 3,
                    "text": (
                        "Statewide Average Temperature "
                        "Percentiles and Ranks"
                    ),
                },
                {
                    "type": "table",
                    "headers": [
                        "State",
                        "Average Temperature",
                        "Departure from Average",
                        "Rank",
                    ],
                    "rows": [
                        [
                            "Alabama",
                            "84.2°F",
                            "+2.1°F",
                            8,
                        ],
                        [
                            "Arizona",
                            "92.7°F",
                            "+3.4°F",
                            5,
                        ],
                        [
                            "California",
                            "75.6°F",
                            "+1.8°F",
                            10,
                        ],
                        [
                            "Texas",
                            "88.9°F",
                            "+2.7°F",
                            6,
                        ],
                    ],
                },
                {
                    "type": "heading",
                    "level": 3,
                    "text": "July Precipitation",
                },
                {
                    "type": "paragraph",
                    "text": (
                        "July precipitation varied "
                        "substantially across the country."
                    ),
                },
                {
                    "type": "list",
                    "items": [
                        (
                            "Above-average precipitation "
                            "occurred across portions of "
                            "the northern United States."
                        ),
                        (
                            "Below-average precipitation "
                            "affected several areas of "
                            "the Southwest."
                        ),
                        (
                            "Localized heavy rainfall "
                            "resulted in flooding in "
                            "some regions."
                        ),
                        (
                            "Drought conditions improved "
                            "in some areas but intensified "
                            "in others."
                        ),
                    ],
                },
                {
                    "type": "heading",
                    "level": 3,
                    "text": (
                        "July 2026 Temperature "
                        "Departures from Average"
                    ),
                },
                {
                    "type": "image",
                    "caption": (
                        "July 2026 temperature "
                        "departures from average"
                    ),
                    "image_reference": (
                        "images/page_6_image_1.png"
                    ),
                },
            ],
        },
        {
            "title": "Regional Summary",
            "content": [
                {
                    "type": "heading",
                    "level": 3,
                    "text": "Southeast",
                },
                {
                    "type": "paragraph",
                    "text": (
                        "The Southeast experienced "
                        "generally above-average "
                        "temperatures during July."
                    ),
                },
                {
                    "type": "heading",
                    "level": 3,
                    "text": "West",
                },
                {
                    "type": "paragraph",
                    "text": (
                        "Much of the West experienced "
                        "warmer-than-average conditions."
                    ),
                },
            ],
        },
    ],
}


AGENT_ID = "cce-document-ingestion-test"

# Replace this with the MemoryType value you already use
# successfully in your existing AgenticPlane test.
MEMORY_TYPE = MemoryType.SEMANTIC


async def main() -> None:

    print("=" * 80)
    print("CCE DOCUMENT INGESTION TEST")
    print("=" * 80)

    print()
    print("Document ID:")
    print(METADATA["document_id"])

    print()
    print("Starting ingestion...")

    result = (
        await document_ingestion_service
        .ingest_document(
            metadata=METADATA,
            content=CONTENT,
            agent_id=AGENT_ID,
            memory_type=MEMORY_TYPE,
            tags=[
                "noaa",
                "climate",
                "2026",
            ],
        )
    )

    print()
    print("=" * 80)
    print("INGESTION RESULT")
    print("=" * 80)

    print(
        f"Document ID       : {result.document_id}"
    )

    print(
        f"Markdown size     : "
        f"{result.markdown_size_bytes:,} bytes "
        f"({result.markdown_size_bytes / 1024:.2f} KB)"
    )

    print(
        f"Total chunks      : "
        f"{result.total_chunks}"
    )

    print()
    print("-" * 80)
    print("CHUNKS")
    print("-" * 80)

    for chunk in result.chunks:

        print()
        print(
            f"Chunk {chunk.chunk_index + 1}"
            f"/{chunk.total_chunks}"
        )

        print(
            f"  Chunk ID        : "
            f"{chunk.chunk_id}"
        )

        print(
            f"  Content size    : "
            f"{chunk.content_size_bytes:,} bytes "
            f"({chunk.content_size_bytes / 1024:.2f} KB)"
        )

        print(
            f"  Metadata size   : "
            f"{chunk.metadata_size_bytes:,} bytes "
            f"({chunk.metadata_size_bytes / 1024:.2f} KB)"
        )

        print(
            f"  Payload size    : "
            f"{chunk.payload_size_bytes:,} bytes "
            f"({chunk.payload_size_bytes / 1024:.2f} KB)"
        )

        print(
            f"  Under 256 KB    : "
            f"{chunk.payload_size_bytes <= 256 * 1024}"
        )

        print()
        print("  Metadata:")
        print(
            json.dumps(
                chunk.metadata,
                indent=2,
                ensure_ascii=False,
            )
        )

        print()
        print("  Markdown:")
        print("-" * 40)
        print(chunk.content)
        print("-" * 40)

    print()
    print("=" * 80)
    print("AGENTICPLANE RESULTS")
    print("=" * 80)

    for index, stored_result in enumerate(
        result.stored_results
    ):
        print()
        print(
            f"Chunk {index + 1}: SUCCESS"
        )
        print(
            json.dumps(
                stored_result,
                indent=2,
                default=str,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())