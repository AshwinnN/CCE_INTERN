from typing import Union, BinaryIO
from ingestion.parsers.base import DocumentParser
from ingestion.models import (ProcessingResult, DocumentMetadata, ProcessingStatus, 
                              CanonicalDocument, TextElement, TableElement, TableCell, ElementType, BoundingBox)

class DoclingParser(DocumentParser):
    def parse(self, file_stream_or_path: Union[str, BinaryIO], metadata: DocumentMetadata) -> ProcessingResult:
        try:
            from docling.document_converter import DocumentConverter
            
            if not isinstance(file_stream_or_path, str):
                return ProcessingResult(
                    status=ProcessingStatus.FAILED, 
                    errors=["Docling parser currently requires a file path."]
                )
                
            converter = DocumentConverter()
            result = converter.convert(file_stream_or_path)
            doc_model = result.document
            
            elements = []
            order = 0
            
            for docling_elem, level in doc_model.iterate_items():
                label_str = str(getattr(docling_elem, 'label', '')).lower()
                
                # Check for text / heading / paragraph labels
                if any(k in label_str for k in ["text", "paragraph", "title", "heading", "section_header", "code", "list"]):
                    text_val = getattr(docling_elem, 'text', '')
                    if text_val:
                        elements.append(TextElement(
                            id=f"{metadata.document_id}_elem_{order}",
                            type=ElementType.HEADING if "title" in label_str or "heading" in label_str else ElementType.PARAGRAPH,
                            text=text_val,
                            order=order,
                            page_number=docling_elem.prov[0].page_no if hasattr(docling_elem, 'prov') and docling_elem.prov else None
                        ))
                elif "table" in label_str and hasattr(docling_elem, 'data'):
                    cells = []
                    if hasattr(docling_elem.data, 'grid'):
                        for docling_cell in docling_elem.data.grid:
                            cells.append(TableCell(
                                row=docling_cell.start_row,
                                col=docling_cell.start_col,
                                row_span=getattr(docling_cell, 'end_row', docling_cell.start_row) - docling_cell.start_row + 1,
                                col_span=getattr(docling_cell, 'end_col', docling_cell.start_col) - docling_cell.start_col + 1,
                                text=getattr(docling_cell, 'text', ''),
                                is_header=getattr(docling_cell, 'column_header', False) or getattr(docling_cell, 'row_header', False)
                            ))
                    elements.append(TableElement(
                        id=f"{metadata.document_id}_elem_{order}",
                        rows=getattr(docling_elem.data, 'num_rows', 0),
                        cols=getattr(docling_elem.data, 'num_cols', 0),
                        cells=cells,
                        order=order,
                        page_number=docling_elem.prov[0].page_no if hasattr(docling_elem, 'prov') and docling_elem.prov else None
                    ))
                order += 1
                
            doc = CanonicalDocument(metadata=metadata, elements=elements)
            return ProcessingResult(status=ProcessingStatus.SUCCESS, document=doc)
        except Exception as e:
            return ProcessingResult(status=ProcessingStatus.FAILED, errors=[str(e)])
