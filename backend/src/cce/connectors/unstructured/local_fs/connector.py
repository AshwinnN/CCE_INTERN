"""Read-only local filesystem connector for synthetic/demo ingestion."""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Dict, Optional

from cce.connectors.base.source import SourceConnection, SourceConnector


class LocalFileSystemConnector(SourceConnector):
    def __init__(self, root_path: str, *, source_id: str = "local-fs"):
        self.root_path = Path(root_path).resolve()
        self.source_id = source_id
        self._connected = False

    def connect(self) -> SourceConnection:
        if not self.root_path.exists() or not self.root_path.is_dir():
            raise FileNotFoundError("local-fs root_path does not exist: %s" % self.root_path)
        self._connected = True
        return SourceConnection(
            connector=self,
            connection_id="local-fs:%s" % self.root_path,
            source_id=self.source_id,
            adapter="local-fs",
        )

    def list_objects(self, cursor: Optional[str] = None) -> Dict:
        self._require_connected()
        objects = []
        for path in sorted(self.root_path.rglob("*")):
            if not path.is_file():
                continue
            object_id = path.relative_to(self.root_path).as_posix()
            stat = path.stat()
            objects.append(
                {
                    "object_id": object_id,
                    "object_type": mimetypes.guess_type(path.name)[0] or "text/plain",
                    "source_ref": str(path),
                    "version": _file_version(path),
                    "content_hash": _file_version(path),
                    "modified_at": stat.st_mtime,
                }
            )
        return {"objects": objects, "next_cursor": None}

    def fetch_object(self, object_id: str) -> bytes:
        self._require_connected()
        path = (self.root_path / object_id).resolve()
        if self.root_path not in path.parents and path != self.root_path:
            raise ValueError("object_id escapes local-fs root_path")
        if not path.is_file():
            raise FileNotFoundError("local-fs object not found: %s" % object_id)
        return path.read_bytes()

    def close(self) -> None:
        self._connected = False

    def _require_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("local-fs connector is not connected")


def _file_version(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
