
from abc import ABC, abstractmethod
from typing import Union, BinaryIO
from cce.ingestion.models import ProcessingResult, DocumentMetadata

class DocumentParser(ABC):
    @abstractmethod
    def parse(self, file_stream_or_path: Union[str, BinaryIO], metadata: DocumentMetadata) -> ProcessingResult:
        pass
