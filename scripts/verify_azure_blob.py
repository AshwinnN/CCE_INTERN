#!/usr/bin/env python3
"""Manual Azure Blob connector connectivity diagnostic."""

import os
import sys
from pathlib import Path

from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend" / "src"))
load_dotenv(REPO / ".env", override=True)
load_dotenv(REPO / "backend" / ".env", override=True)


def main() -> int:
    if os.environ.get("CCE_AZURE_BLOB_ENABLED", "false").lower() != "true":
        print("CCE_AZURE_BLOB_ENABLED is not 'true' -- stopping before any connection.")
        return 1

    service = BlobServiceClient.from_connection_string(os.environ["CCE_AZURE_BLOB_CONNECTION_STRING"])
    container = service.get_container_client(os.environ["CCE_AZURE_BLOB_CONTAINER"])
    prefix = os.environ.get("CCE_AZURE_BLOB_PREFIX", "")
    pages = container.list_blobs(name_starts_with=prefix).by_page(results_per_page=5)
    first_page = next(pages, [])
    names = [blob.name for blob in first_page]
    print("Container:", container.container_name)
    print("Prefix:", prefix)
    print("Blobs visible:", len(names))
    for name in names:
        print(" ", name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
