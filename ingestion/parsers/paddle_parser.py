
from typing import Union, BinaryIO
from ingestion.parsers.base import DocumentParser
from ingestion.models import (ProcessingResult, DocumentMetadata, ProcessingStatus, 
                              CanonicalDocument, TextElement, ElementType, BoundingBox)

class PaddleOCRParser(DocumentParser):
    def parse(self, file_stream_or_path: Union[str, BinaryIO], metadata: DocumentMetadata) -> ProcessingResult:
        try:
            from paddleocr import PaddleOCR
            
            if not isinstance(file_stream_or_path, str):
                return ProcessingResult(
                    status=ProcessingStatus.FAILED, 
                    errors=["PaddleOCR parser currently requires a file path."]
                )
                
            ocr = PaddleOCR(use_angle_cls=True, lang='en')
            result = ocr.ocr(file_stream_or_path, cls=True)
            
            elements = []
            order = 0
            
            # PaddleOCR returns [[[x1, y1], [x2, y2], [x3, y3], [x4, y4]], (text, confidence)]
            if result and result[0]:
                for line in result[0]:
                    box, (text, conf) = line
                    bbox = BoundingBox(
                        x0=min(pt[0] for pt in box),
                        y0=min(pt[1] for pt in box),
                        x1=max(pt[0] for pt in box),
                        y1=max(pt[1] for pt in box)
                    )
                    elements.append(TextElement(
                        id=f"{metadata.document_id}_ocr_{order}",
                        type=ElementType.TEXT,
                        text=text,
                        order=order,
                        bbox=bbox,
                        confidence=conf
                    ))
                    order += 1
                    
            doc = CanonicalDocument(metadata=metadata, elements=elements)
            return ProcessingResult(status=ProcessingStatus.SUCCESS, document=doc)
        except Exception as e:
            return ProcessingResult(status=ProcessingStatus.FAILED, errors=[str(e)])
