
import logging
from typing import Type
from cce.ingestion.parsers.base import DocumentParser

logger = logging.getLogger(__name__)

class ParserFactory:
    _registry = {}

    @classmethod
    def register_parser(cls, mime_type: str, parser_cls: Type[DocumentParser]):
        cls._registry[mime_type] = parser_cls

    @classmethod
    def get_parser(cls, mime_type: str) -> DocumentParser:
        parser_cls = cls._registry.get(mime_type)
        if not parser_cls:
            logger.warning(f"No specific parser found for {mime_type}")
            return None
        return parser_cls()
        
    @classmethod
    def _try_register(cls, mime_types, module_path, class_name):
        """Register a parser for one or more mime types, skipping it (with a
        warning, not a crash) when its optional third-party dependency isn't
        installed. A missing OCR/Docling install must not take down every
        other parser -- get_parser() already returns None for an unmapped
        mime type, which is the intended degrade path for this case too."""
        import importlib
        try:
            module = importlib.import_module(module_path)
            parser_cls = getattr(module, class_name)
        except ImportError as e:
            logger.warning(
                "Parser %s unavailable (missing dependency: %s); mime types %s "
                "will report UNSUPPORTED until it's installed.", class_name, e, mime_types)
            return
        for mime_type in mime_types:
            cls.register_parser(mime_type, parser_cls)

    @classmethod
    def initialize_registry(cls):
        cls._try_register(
            ["text/plain", "text/markdown"], "cce.ingestion.parsers.text", "TextParser")
        cls._try_register(
            ["text/csv"], "cce.ingestion.parsers.csv", "CSVParser")
        cls._try_register(
            ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel"],
            "cce.ingestion.parsers.excel", "ExcelParser")
        cls._try_register(
            ["application/pdf",
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             "application/vnd.openxmlformats-officedocument.presentationml.presentation"],
            "cce.ingestion.parsers.docling", "DoclingParser")
        cls._try_register(
            ["image/jpeg", "image/png", "image/tiff"],
            "cce.ingestion.parsers.image", "PaddleOCRParser")

# Initialize on load
ParserFactory.initialize_registry()
