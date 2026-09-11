import logging
import os
import tempfile
from typing import Iterator, Tuple
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import HttpResponseError
from cce.connectors.base.source import SourceConnection, SourceConnector
from cce.connectors.base.exceptions import ConnectionFailedError
from cce.ingestion.models import DocumentMetadata
from cce.ingestion.parsers.factory import ParserFactory
from cce.ingestion.models import ProcessingResult, ProcessingStatus
from cce.ingestion.change_detection.file_detection import detect_mime_type

logger = logging.getLogger(__name__)

# Azure SDK default page size for list_blobs(); pages are logged individually
# so a large container's listing is visible without dumping every blob name.
_LIST_PAGE_SIZE = 5000


class AzureBlobSource(SourceConnector):
    def __init__(self, connection_string: str, container_name: str, source_id: str = "azure-blob"):
        if not connection_string or not connection_string.strip():
            raise ConnectionFailedError("Azure Blob connection string is empty")
        if not container_name or not container_name.strip():
            raise ConnectionFailedError("Azure Blob container name is empty")
        self.source_id = source_id
        self.connection_string = connection_string
        self.container_name = container_name
        try:
            self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        except Exception as exc:
            raise ConnectionFailedError(
                "Azure Blob client initialization failed; verify the configured credential reference"
            ) from exc
        self.container_client = self.blob_service_client.get_container_client(container_name)

    def connect(self) -> SourceConnection:
        logger.info("Connecting to Azure Blob container=%s", self.container_name)
        try:
            try:
                self.container_client.get_container_properties()
            except HttpResponseError as exc:
                if exc.status_code != 403:
                    raise
                # A container SAS may allow blob read/list without permission
                # to inspect container properties. Probe the operation ingestion
                # actually needs, consuming at most one listing page.
                next(iter(self.container_client.list_blobs(results_per_page=1)), None)
        except Exception as exc:
            logger.error("Azure Blob connection failed for container=%s: %s", self.container_name, exc)
            raise ConnectionFailedError(
                "Azure Blob connection failed for container %r: %s"
                % (self.container_name, exc)
            ) from exc
        logger.info("Connected to Azure Blob container=%s source_id=%s", self.container_name, self.source_id)
        return SourceConnection(
            connector=self,
            connection_id=f"azure-blob:{self.container_name}",
            source_id=self.source_id,
            adapter="azure-blob",
        )

    def list_objects(self, cursor=None):
        logger.info(
            "Listing blobs: container=%s prefix=%r (page_size=%d)",
            self.container_name, cursor, _LIST_PAGE_SIZE,
        )
        objects = []
        pages = self.container_client.list_blobs(name_starts_with=cursor).by_page()
        for page_number, page in enumerate(pages, start=1):
            page_objects = [
                {
                    "object_id": blob.name,
                    "object_type": getattr(getattr(blob, "content_settings", None), "content_type", None) or "application/octet-stream",
                    "source_ref": f"azure://{self.container_name}/{blob.name}",
                    "version": getattr(blob, "etag", None) or "",
                    "content_hash": getattr(blob, "etag", None) or "",
                    "modified_at": getattr(blob, "last_modified", None),
                }
                for blob in page
            ]
            objects.extend(page_objects)
            logger.info(
                "Listed page %d: %d blobs (running total=%d) container=%s",
                page_number, len(page_objects), len(objects), self.container_name,
            )
        logger.info("Listing complete: %d blobs total from container=%s prefix=%r",
                    len(objects), self.container_name, cursor)
        return {"objects": objects, "next_cursor": None}

    def fetch_object(self, object_id: str) -> bytes:
        logger.info("Fetching blob object_id=%s from container=%s", object_id, self.container_name)
        data = self.container_client.get_blob_client(object_id).download_blob().readall()
        logger.info("Fetched blob object_id=%s: %d bytes", object_id, len(data))
        return data

    def close(self) -> None:
        return None

    def process_blobs(self, prefix: str = None) -> Iterator[ProcessingResult]:
        blobs = self.container_client.list_blobs(name_starts_with=prefix)
        for blob in blobs:
            blob_client = self.container_client.get_blob_client(blob)
            properties = blob_client.get_blob_properties()
            
            # Initial guess by blob name to see if we can skip early
            mime_type = properties.content_settings.content_type
            if not mime_type or mime_type == 'application/octet-stream':
                import mimetypes
                guessed, _ = mimetypes.guess_type(blob.name)
                mime_type = guessed or 'application/octet-stream'
                
            metadata = DocumentMetadata(
                document_id=blob.name,
                source_system="azure_blob",
                source_uri=f"azure://{self.container_client.container_name}/{blob.name}",
                original_filename=blob.name,
                mime_type=mime_type,
                file_size_bytes=properties.size,
                file_extension=os.path.splitext(blob.name)[1].lower(),
                creation_time=properties.creation_time
            )
            
            # Download to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{os.path.basename(blob.name)}") as tmp:
                blob_data = blob_client.download_blob()
                blob_data.readinto(tmp)
                tmp_path = tmp.name
                
            try:
                # Better mime type detection using magic
                if metadata.mime_type == 'application/octet-stream':
                    detected = detect_mime_type(tmp_path)
                    if detected:
                        metadata.mime_type = detected
                        
                parser = ParserFactory.get_parser(metadata.mime_type)
                if not parser:
                    yield ProcessingResult(
                        status=ProcessingStatus.UNSUPPORTED,
                        errors=[f"Unsupported mime type {metadata.mime_type} for blob {blob.name}"],
                    )
                    continue
                    
                result = parser.parse(tmp_path, metadata)
                yield result
            except Exception as e:
                yield ProcessingResult(
                    status=ProcessingStatus.FAILED,
                    errors=[str(e)],
                    document=None
                )
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except:
                        pass
