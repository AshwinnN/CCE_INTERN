from unittest.mock import Mock

import pytest

from cce.connectors.base.exceptions import ConnectionFailedError
from cce.connectors.unstructured.azure_blob.connector import AzureBlobSource


def test_azure_blob_rejects_invalid_connection_configuration(monkeypatch):
    from_connection_string = Mock(side_effect=ValueError("malformed connection string"))
    monkeypatch.setattr(
        "cce.connectors.unstructured.azure_blob.connector."
        "BlobServiceClient.from_connection_string",
        from_connection_string,
    )

    with pytest.raises(ConnectionFailedError, match="client initialization failed"):
        AzureBlobSource("not-a-connection-string", "documents")


def test_azure_blob_surfaces_container_connection_failure(monkeypatch):
    container_client = Mock()
    container_client.get_container_properties.side_effect = RuntimeError("access denied")
    blob_service_client = Mock()
    blob_service_client.get_container_client.return_value = container_client
    monkeypatch.setattr(
        "cce.connectors.unstructured.azure_blob.connector."
        "BlobServiceClient.from_connection_string",
        Mock(return_value=blob_service_client),
    )
    source = AzureBlobSource("valid-looking", "documents")

    with pytest.raises(ConnectionFailedError, match="documents.*access denied"):
        source.connect()
