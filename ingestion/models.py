from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum

class ElementType(str, Enum):
    TEXT = "text"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    IMAGE = "image"
    LIST = "list"
    LIST_ITEM = "list_item"
    SECTION = "section"
    SPREADSHEET = "spreadsheet"

class ProcessingStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"

class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float

class ContentElement(BaseModel):
    id: str
    type: ElementType
    page_number: Optional[int] = None
    order: Optional[int] = None
    bbox: Optional[BoundingBox] = None
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    parent_id: Optional[str] = None

class TextElement(ContentElement):
    text: str

class TableCell(BaseModel):
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    text: str = ""
    is_header: bool = False
    bbox: Optional[BoundingBox] = None

class TableElement(ContentElement):
    type: ElementType = ElementType.TABLE
    rows: int
    cols: int
    cells: List[TableCell]
    caption: Optional[str] = None

class ImageElement(ContentElement):
    type: ElementType = ElementType.IMAGE
    image_reference: Optional[str] = None
    caption: Optional[str] = None

class SpreadsheetElement(ContentElement):
    type: ElementType = ElementType.SPREADSHEET
    sheet_name: str
    visible: bool = True
    tables: List[TableElement] = Field(default_factory=list)

class DocumentMetadata(BaseModel):
    document_id: str
    source_system: str
    source_uri: str
    original_filename: Optional[str] = None
    file_extension: Optional[str] = None
    mime_type: Optional[str] = None
    document_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    creation_time: Optional[datetime] = None
    modified_time: Optional[datetime] = None
    ingestion_time: datetime = Field(default_factory=datetime.utcnow)
    parser_used: Optional[str] = None
    parser_version: Optional[str] = None
    hash_checksum: Optional[str] = None
    source_specific: Dict[str, Any] = Field(default_factory=dict)

class CanonicalDocument(BaseModel):
    metadata: DocumentMetadata
    elements: List[Union[TextElement, TableElement, ImageElement, SpreadsheetElement, ContentElement]] = Field(default_factory=list)

class ProcessingResult(BaseModel):
    status: ProcessingStatus
    document: Optional[CanonicalDocument] = None
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    processing_duration_ms: Optional[float] = None

