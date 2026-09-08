
import os
import mimetypes

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
        if mime_type and mime_type != "application/octet-stream":
            return mime_type
    except ImportError:
        pass
        
    mime_type = _EXTENSION_MIME_TYPES.get(extension)
    if mime_type:
        return mime_type
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or 'application/octet-stream'
