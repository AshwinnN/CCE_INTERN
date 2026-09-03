#!/usr/bin/env python3
"""Sanity check only — lists the first 5 blobs under the configured prefix.
This is NOT the Discover-stage skill call; it's a quick manual peek using
the same credential the Connect stage already validated as read-only.
"""
import os
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(REPO, ".env"))

conn_str = os.environ["CCE_AZURE_BLOB_CONNECTION_STRING"]
container_name = os.environ["CCE_AZURE_BLOB_CONTAINER"]
prefix = os.environ.get("CCE_AZURE_BLOB_PREFIX", "")

service = BlobServiceClient.from_connection_string(conn_str)
container = service.get_container_client(container_name)

blobs = container.list_blobs(name_starts_with=prefix)
top5 = []
for b in blobs:
    top5.append(b)
    if len(top5) == 5:
        break

print(f"First 5 blobs under prefix '{prefix}':\n")
for b in top5:
    size_kb = b.size / 1024
    print(f"  {b.name:<50} {size_kb:>8.1f} KB   last modified: {b.last_modified}")