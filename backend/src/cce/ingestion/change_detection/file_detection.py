
import os
import mimetypes
import zipfile

_EXTENSION_MIME_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def detect_mime_type(file_path: str) -> str:
    extension = os.path.splitext(file_path)[1].lower()
    try:
        import magic
        mime_type = magic.from_file(file_path, mime=True)
        if mime_type in {"application/zip", "application/x-zip-compressed"}:
            # OOXML documents are ZIP containers; some libmagic versions report
            # only that outer format. Check the document parts before routing.
            try:
                with zipfile.ZipFile(file_path) as archive:
                    names = set(archive.namelist())
                if "[Content_Types].xml" in names:
                    for part, suffix in (
                        ("word/document.xml", ".docx"),
                        ("ppt/presentation.xml", ".pptx"),
                        ("xl/workbook.xml", ".xlsx"),
                    ):
                        if part in names:
                            return _EXTENSION_MIME_TYPES[suffix]
            except (OSError, zipfile.BadZipFile):
                pass
        if mime_type and mime_type != "application/octet-stream":
            return mime_type
    except ImportError:
        pass
        
    mime_type = _EXTENSION_MIME_TYPES.get(extension)
    if mime_type:
        return mime_type
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or 'application/octet-stream'
