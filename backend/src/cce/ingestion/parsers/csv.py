
import csv
from typing import Union, BinaryIO
from cce.ingestion.parsers.base import DocumentParser
from cce.ingestion.models import ProcessingResult, DocumentMetadata, ProcessingStatus, CanonicalDocument, TableElement, TableCell

class CSVParser(DocumentParser):
    def parse(self, file_stream_or_path: Union[str, BinaryIO], metadata: DocumentMetadata) -> ProcessingResult:
        if isinstance(file_stream_or_path, str):
            with open(file_stream_or_path, "r", encoding="utf-8") as f:
                return self._parse_file(f, metadata)
        else:
            import io
            text_stream = io.TextIOWrapper(file_stream_or_path, encoding='utf-8')
            return self._parse_file(text_stream, metadata)

    def _parse_file(self, f, metadata: DocumentMetadata) -> ProcessingResult:
        reader = csv.reader(f)
        cells = []
        rows = 0
        cols = 0
        
        for row_idx, row in enumerate(reader):
            rows += 1
            cols = max(cols, len(row))
            for col_idx, cell_value in enumerate(row):
                cells.append(TableCell(
                    row=row_idx,
                    col=col_idx,
                    text=cell_value,
                    is_header=(row_idx == 0)
                ))
                
        table = TableElement(
            id=f"{metadata.document_id}_csv_table",
            rows=rows,
            cols=cols,
            cells=cells,
            order=0
        )
        
        doc = CanonicalDocument(metadata=metadata, elements=[table])
        return ProcessingResult(status=ProcessingStatus.SUCCESS, document=doc)
