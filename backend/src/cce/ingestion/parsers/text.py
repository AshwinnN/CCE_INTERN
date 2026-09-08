
import os
from typing import Union, BinaryIO
from cce.ingestion.parsers.base import DocumentParser
from cce.ingestion.models import ProcessingResult, DocumentMetadata, ProcessingStatus, CanonicalDocument, TextElement, ElementType

class TextParser(DocumentParser):
    def parse(self, file_stream_or_path: Union[str, BinaryIO], metadata: DocumentMetadata) -> ProcessingResult:
        if isinstance(file_stream_or_path, str):
            with open(file_stream_or_path, "r", encoding="utf-8") as f:
                text = f.read()
        else:
            import io
            text = io.TextIOWrapper(file_stream_or_path, encoding='utf-8').read()
            
        paragraphs = text.split("\n\n")
        elements = []
        
        for idx, para in enumerate(paragraphs):
            para = para.strip()
            if not para:
                continue
            elements.append(TextElement(
                id=f"{metadata.document_id}_p_{idx}",
                type=ElementType.PARAGRAPH,
                text=para,
                order=idx
            ))
            
        doc = CanonicalDocument(metadata=metadata, elements=elements)
        return ProcessingResult(status=ProcessingStatus.SUCCESS, document=doc)
