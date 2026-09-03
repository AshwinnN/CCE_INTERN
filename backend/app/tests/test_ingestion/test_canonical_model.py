import sys
import os
import pytest
from dotenv import load_dotenv

sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
)

from ingestion.azure_blob_source import AzureBlobSource


def test_azure_blob_small_pdf():
    load_dotenv()

    conn_str = os.getenv("CCE_AZURE_BLOB_CONNECTION_STRING")
    container = os.getenv("CCE_AZURE_BLOB_CONTAINER")

    if not conn_str or not container:
        print("Skipping Azure Blob test: missing credentials in .env")
        return

    target_blob = "noaa_data/national-202607.pdf"

    print(f"Connecting to Azure Blob Storage (Container: {container})...")

    source = AzureBlobSource(
        connection_string=conn_str,
        container_name=container
    )

    print(f"Processing target blob: {target_blob}...")

    results = list(source.process_blobs(prefix=target_blob))

    print(f"\nNumber of results: {len(results)}")

    for i, res in enumerate(results):
        print("\n" + "=" * 80)
        print(f"RESULT #{i + 1}")
        print("=" * 80)

        print("\n--- Processing Result ---")
        print(f"Type:   {type(res)}")
        print(f"Status: {res.status}")
        print(f"Errors: {res.errors}")

        print("\n--- Result Attributes ---")
        print(vars(res))

        if res.document:
            doc = res.document

            print("\n" + "-" * 80)
            print("doc")
            print("-" * 80)

            print(f"Type: {type(doc)}")

            print("\n--- doc Attributes ---")
            print(vars(doc))

            print("\n--- doc Metadata ---")

            if doc.metadata:
                print(f"Metadata Type: {type(doc.metadata)}")
                print(vars(doc.metadata))

            else:
                print("Metadata: None")

            print("\n--- Elements ---")
            print(f"Element count: {len(doc.elements)}")

            if doc.elements:
                print("\n--- Extracted Elements ---")

                for i, elem in enumerate(doc.elements[:1]):
                    text = getattr(elem, "text", "") or ""

                    print(f"\nElement #{i + 1}")
                    print(f"Type: {type(elem)}")
                    print(f"Attributes: {vars(elem)}")
                    print(f"Text: {text[:500]}")
            else:
                print("\nNO ELEMENTS EXTRACTED")

        else:
            print("\ndoc: None")
        text = getattr(elem, "text", "") or ""

        print(
            f"[{elem.type.value.upper()}] "
            f"(Page {elem.page_number}): "
            f"{text[:80]}..."
        )


if __name__ == "__main__":
    test_azure_blob_small_pdf()