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


@pytest.mark.parametrize('list_allowed', [True, False])
def test_container_sas_properties_denied_probes_listing(monkeypatch, list_allowed):
    from azure.core.exceptions import HttpResponseError

    denied = HttpResponseError(message='properties forbidden')
    denied.status_code = 403
    container = Mock()
    container.get_container_properties.side_effect = denied
    if list_allowed:
        container.list_blobs.return_value = iter([])
    else:
        container.list_blobs.side_effect = HttpResponseError(message='listing forbidden')
    service = Mock()
    service.get_container_client.return_value = container
    monkeypatch.setattr(
        'cce.connectors.unstructured.azure_blob.connector.BlobServiceClient.from_connection_string',
        Mock(return_value=service),
    )
    source = AzureBlobSource('test', 'documents')
    if list_allowed:
        assert source.connect().source_id == 'azure-blob'
    else:
        with pytest.raises(ConnectionFailedError, match='listing forbidden'):
            source.connect()
    container.list_blobs.assert_called_once_with(results_per_page=1)
