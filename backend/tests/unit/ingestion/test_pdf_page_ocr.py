from types import SimpleNamespace
import sys

from cce.ingestion.models import BoundingBox, DocumentMetadata, TextElement
from cce.ingestion.parsers.pdf_text import PdfTextParser


def test_mixed_pdf_ocr_only_insufficient_pages(monkeypatch):
    closed = []
    class Page:
        def __init__(self, index): self.index = index
        def get_textpage(self):
            return SimpleNamespace(get_text_range=lambda: ["Native policy text with sufficient characters.", ""][self.index], close=lambda: None)
        def close(self): closed.append(self.index)
    class PDF:
        def __len__(self): return 2
        def __getitem__(self, index): return Page(index)
        def close(self): closed.append("document")
    monkeypatch.setitem(sys.modules, "pypdfium2", SimpleNamespace(PdfDocument=lambda _: PDF()))
    calls = []
    def ocr(pdf, metadata, page_indices):
        calls.extend(page_indices)
        return [TextElement(id="ocr-2", type="text", text="Scanned return policy", page_number=2,
                            confidence=.97, bbox=BoundingBox(x0=1, y0=2, x1=20, y1=30))]
    result = PdfTextParser(ocr_pages=ocr).parse("mixed.pdf", DocumentMetadata(document_id="d", source_system="test", source_uri="mixed.pdf"))
    assert result.status == "SUCCESS"
    assert calls == [1]
    assert len(result.document.elements) == 2
    native, scanned = result.document.elements
    assert native.page_number == 1 and native.text.startswith("Native")
    assert scanned.page_number == 2 and scanned.confidence == .97
    assert scanned.bbox.x1 == 20
    assert closed == [0, 1, "document"]


def test_native_pdf_never_invokes_ocr(monkeypatch):
    page = SimpleNamespace(get_textpage=lambda: SimpleNamespace(get_text_range=lambda: "Native text " * 20, close=lambda: None), close=lambda: None)
    class PDF:
        def __len__(self): return 1
        def __getitem__(self, index): return page
        def close(self): pass
    monkeypatch.setitem(sys.modules, "pypdfium2", SimpleNamespace(PdfDocument=lambda _: PDF()))
    def unexpected(*args, **kwargs): raise AssertionError("Native page must not use OCR")
    result = PdfTextParser(ocr_pages=unexpected).parse("native.pdf", DocumentMetadata(document_id="d", source_system="test", source_uri="native.pdf"))
    assert result.status == "SUCCESS"
