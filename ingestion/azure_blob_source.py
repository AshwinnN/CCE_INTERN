import os
import tempfile
from typing import Iterator, Tuple
from azure.storage.blob import BlobServiceClient
from ingestion.models import DocumentMetadata
from ingestion.parsers.factory import ParserFactory
from ingestion.models import ProcessingResult, ProcessingStatus
from ingestion.file_detection import detect_mime_type

class AzureBlobSource:
    def __init__(self, connection_string: str, container_name: str):
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self.container_client = self.blob_service_client.get_container_client(container_name)
        
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
