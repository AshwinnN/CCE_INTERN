from typing import Union, BinaryIO
from ingestion.parsers.base import DocumentParser
from ingestion.models import (ProcessingResult, DocumentMetadata, ProcessingStatus, 
                              CanonicalDocument, TextElement, TableElement, TableCell, ElementType)

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
            metadata.parser_used = "docling"
            metadata.parser_version = "2.x"
            
            elements = []
            order = 0
            
            for docling_elem, level in doc_model.iterate_items():
                label_str = str(getattr(docling_elem, 'label', '')).lower()
                page_number = _page_number(docling_elem)
                
                if any(k in label_str for k in ["text", "paragraph", "title", "heading", "section_header", "code", "list"]):
                    text_val = getattr(docling_elem, 'text', '')
                    if text_val:
                        element_type = _text_element_type(label_str)
                        elements.append(TextElement(
                            id=f"{metadata.document_id}_elem_{order}",
                            type=element_type,
                            text=text_val,
                            order=order,
                            page_number=page_number,
                            metadata={"docling_label": label_str, "docling_level": level},
                        ))
                        order += 1
                elif "table" in label_str and hasattr(docling_elem, 'data'):
                    cells = []
                    if hasattr(docling_elem.data, 'grid'):
                        for docling_cell in _iter_docling_cells(docling_elem.data.grid):
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
                        page_number=page_number,
                        metadata={"docling_label": label_str, "docling_level": level},
                    ))
                    order += 1
                
            doc = CanonicalDocument(metadata=metadata, elements=elements)
            if not elements:
                return ProcessingResult(
                    status=ProcessingStatus.UNSUPPORTED,
                    errors=["Docling did not return extractable text, tables, or images."],
                )
            return ProcessingResult(status=ProcessingStatus.SUCCESS, document=doc)
        except Exception as e:
            return ProcessingResult(status=ProcessingStatus.FAILED, errors=[str(e)])


def _page_number(docling_elem):
    prov = getattr(docling_elem, 'prov', None)
    if prov:
        return getattr(prov[0], 'page_no', None)
    return None


def _text_element_type(label_str: str) -> ElementType:
    if "list" in label_str:
        return ElementType.LIST_ITEM
    if "title" in label_str or "heading" in label_str or "section_header" in label_str:
        return ElementType.HEADING
    return ElementType.PARAGRAPH


def _iter_docling_cells(grid):
    for item in grid:
        if isinstance(item, (list, tuple)):
            for nested in item:
                yield nested
        else:
            yield item
