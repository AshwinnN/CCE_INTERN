
import os
import mimetypes

def detect_mime_type(file_path: str) -> str:
    try:
        import magic
        mime_type = magic.from_file(file_path, mime=True)
        if mime_type:
            return mime_type
    except ImportError:
        pass
        
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or 'application/octet-stream'
