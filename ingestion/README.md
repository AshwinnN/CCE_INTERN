# Document Ingestion and Normalization Layer

This module provides an extensible document ingestion and normalization layer for the CoStrategix Context Engine (CCE). It converts various unstructured and semi-structured documents into a CanonicalDocument format that downstream systems can consume uniformly.

## Supported File Types & Parsers
- **Text & Markdown** (	text/plain, 	text/markdown): Handled by TextParser.
- **CSV** (	text/csv): Handled by CSVParser.
- **Excel** (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet): Handled by ExcelParser (uses openpyxl).
- **PDF, DOCX, PPTX**: Handled by DoclingParser (uses docling).
- **Images (PNG, JPEG, TIFF)**: Handled by PaddleOCRParser (uses PaddleOCR).

## Adding a New Parser
1. Create a new class inheriting from ingestion.parsers.base.DocumentParser.
2. Implement the parse method, returning a ProcessingResult.
3. Register it in ingestion.parsers.factory.ParserFactory.

## Azure Blob Source
The AzureBlobSource can list and download blobs from Azure using the CCE_AZURE_BLOB_CONNECTION_STRING provided in the environment. It manages temp file downloading required by advanced parsers (e.g. docling and paddleocr).

## Output Format
Parsers return a ProcessingResult containing a CanonicalDocument. 
CanonicalDocument retains document hierarchy via elements (TextElement, TableElement, ImageElement, SpreadsheetElement), capturing location, bounding boxes, parent-child relationships, and comprehensive source provenance.
