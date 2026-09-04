import os
import re
from typing import BinaryIO, Union

from cce.ingestion.models import (
    CanonicalDocument,
    BoundingBox,
    DocumentMetadata,
    ElementType,
    ProcessingResult,
    ProcessingStatus,
    TextElement,
)
from cce.ingestion.parsers.base import DocumentParser


class PdfTextParser(DocumentParser):
    """Extract deterministic semantic text blocks from PDFs."""

    def parse(self, file_stream_or_path: Union[str, BinaryIO], metadata: DocumentMetadata) -> ProcessingResult:
        if not isinstance(file_stream_or_path, str):
            return ProcessingResult(
                status=ProcessingStatus.FAILED,
                errors=["PdfTextParser requires a file path."],
            )

        try:
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(file_stream_or_path)
            try:
                elements = []
                order = 0
                for page_index in range(len(pdf)):
                    page = pdf[page_index]
                    textpage = page.get_textpage()
                    try:
                        text = (textpage.get_text_range() or "").strip()
                    finally:
                        textpage.close()
                        page.close()

                    for block in _split_text_blocks(text):
                        element_type = _classify_text_block(block)
                        elements.append(TextElement(
                            id="%s_elem_%d" % (metadata.document_id, order),
                            type=element_type,
                            text=block,
                            order=order,
                            page_number=page_index + 1,
                        ))
                        order += 1

                if not elements:
                    elements = _ocr_pdf_pages(pdf, metadata)
            finally:
                pdf.close()
            metadata.parser_used = "pypdfium2"
            metadata.parser_version = getattr(pdfium, "__version__", None)
            document = CanonicalDocument(metadata=metadata, elements=elements)
            status = ProcessingStatus.SUCCESS if elements else ProcessingStatus.UNSUPPORTED
            errors = [] if elements else ["No extractable PDF text found."]
            return ProcessingResult(status=status, document=document if elements else None, errors=errors)
        except Exception as exc:
            return ProcessingResult(status=ProcessingStatus.FAILED, errors=[str(exc)])


def _split_text_blocks(text: str):
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n")]
    blocks = []
    paragraph = []

    for line in lines:
        if not line:
            if paragraph:
                blocks.append(" ".join(paragraph).strip())
                paragraph = []
            continue
        if _is_list_line(line) or _looks_like_heading(line):
            if paragraph:
                blocks.append(" ".join(paragraph).strip())
                paragraph = []
            blocks.append(line)
            continue
        paragraph.append(line)

    if paragraph:
        blocks.append(" ".join(paragraph).strip())

    return [block for block in blocks if block]


def _is_list_line(text: str) -> bool:
    return bool(re.match(r"^(\u2022|-|\*|\d+[\.)])\s+", text))


def _looks_like_heading(text: str) -> bool:
    if len(text) > 120:
        return False
    if text.endswith((".", ",", ";", ":")):
        return False
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words or len(words) > 12:
        return False
    uppercase_ratio = sum(1 for ch in text if ch.isalpha() and ch.isupper()) / max(
        1, sum(1 for ch in text if ch.isalpha()))
    titlecase_words = sum(1 for word in words if word[:1].isupper())
    return uppercase_ratio > 0.65 or titlecase_words >= max(1, len(words) - 1)


def _classify_text_block(text: str) -> ElementType:
    if _is_list_line(text):
        return ElementType.LIST_ITEM
    if _looks_like_heading(text):
        return ElementType.HEADING
    return ElementType.PARAGRAPH


def _ocr_pdf_pages(pdf, metadata: DocumentMetadata):
    import numpy as np
    from rapidocr import RapidOCR
    from rapidocr.utils.typings import EngineType

    max_pages = int(os.environ.get("CCE_PDF_OCR_MAX_PAGES", "10"))
    max_elements = int(os.environ.get("CCE_PDF_OCR_MAX_ELEMENTS", "200"))
    ocr = RapidOCR(params={
        "Det.engine_type": EngineType.TORCH,
        "Cls.engine_type": EngineType.TORCH,
        "Rec.engine_type": EngineType.TORCH,
    })
    elements = []
    order = 0
    for page_index in range(min(len(pdf), max_pages)):
        page = pdf[page_index]
        try:
            image = page.render(scale=2).to_pil()
            result = ocr(np.array(image))
        finally:
            page.close()

        txts = getattr(result, "txts", None)
        boxes = getattr(result, "boxes", None)
        scores = getattr(result, "scores", None)
        txts = txts if txts is not None else ()
        boxes = boxes if boxes is not None else ()
        scores = scores if scores is not None else ()
        for idx, text in enumerate(txts):
            box = boxes[idx] if idx < len(boxes) else None
            bbox = None
            if box is not None:
                bbox = BoundingBox(
                    x0=float(min(pt[0] for pt in box)),
                    y0=float(min(pt[1] for pt in box)),
                    x1=float(max(pt[0] for pt in box)),
                    y1=float(max(pt[1] for pt in box)),
                )
            elements.append(TextElement(
                id="%s_ocr_%d" % (metadata.document_id, order),
                type=ElementType.TEXT,
                text=str(text),
                order=order,
                page_number=page_index + 1,
                bbox=bbox,
                confidence=float(scores[idx]) if idx < len(scores) else None,
            ))
            order += 1
            if order >= max_elements:
                return elements
    return elements
