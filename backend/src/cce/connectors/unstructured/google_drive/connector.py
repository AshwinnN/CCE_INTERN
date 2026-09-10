"""Explicitly scoped, read-only Drive ingestion with transient native exports."""
import json
from uuid import uuid4

from cce.connectors.base.source import SourceConnection, SourceConnector
from cce.security.credentials import load_credential


EXPORTS = {
    "application/vnd.google-apps.document": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.spreadsheet": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
}
FOLDER = "application/vnd.google-apps.folder"


class GoogleDriveConnector(SourceConnector):
    def __init__(self, config, credential_ref, source_id, *, session_factory=None, credential_loader=load_credential):
        self.config = config
        self.credential_ref = credential_ref
        self.source_id = str(source_id)
        self._session_factory = session_factory
        self._credential_loader = credential_loader
        self._session = None

    def connect(self):
        info = json.loads(self._credential_loader(self.credential_ref))
        if self._session_factory:
            self._session = self._session_factory(info)
        else:
            from google.oauth2.service_account import Credentials
            from google.auth.transport.requests import AuthorizedSession
            credentials = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/drive.readonly"])
            self._session = AuthorizedSession(credentials)
        root = self.config.folder_id if self.config.scope == "folder" else self.config.shared_drive_id
        try:
            if self.config.scope == "folder":
                if self._metadata(root).get("mimeType") != FOLDER:
                    raise ValueError("Configured Drive folder is not a folder")
            else:
                self._get(f"drives/{root}").json()
        except Exception:
            self.close()
            raise
        return SourceConnection(self, str(uuid4()), self.source_id, "google_drive")

    def _get(self, path, params=None):
        if self._session is None:
            raise RuntimeError("Drive connector is not connected")
        from urllib.parse import quote
        # IDs occupy a single URL path component, never a caller-supplied URL.
        path = "/".join(quote(part, safe="") for part in path.split("/"))
        response = self._session.get("https://www.googleapis.com/drive/v3/" + path, params=params, timeout=30)
        response.raise_for_status()
        return response

    def _metadata(self, file_id):
        return self._get(f"files/{file_id}", {"fields": "id,name,mimeType,parents,driveId,trashed,modifiedTime,version,webViewLink", "supportsAllDrives": "true"}).json()

    def list_objects(self, cursor=None):
        root = self.config.folder_id if self.config.scope == "folder" else self.config.shared_drive_id
        pending, seen, objects = [root], set(), []
        while pending:
            parent = pending.pop()
            if parent in seen:
                continue
            seen.add(parent)
            page_token = None
            while True:
                escaped = parent.replace("\\", "\\\\").replace("'", "\\'")
                params = {"q": f"'{escaped}' in parents and trashed = false", "pageSize": 1000,
                          "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,version,webViewLink)",
                          "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
                if self.config.scope == "shared_drive":
                    params.update(corpora="drive", driveId=root)
                if page_token:
                    params["pageToken"] = page_token
                result = self._get("files", params).json()
                for file in result.get("files", []):
                    if file["mimeType"] == FOLDER:
                        if self.config.recursive:
                            pending.append(file["id"])
                        continue
                    export = EXPORTS.get(file["mimeType"])
                    name = file["name"] + (export[1] if export else "")
                    objects.append({"object_id": file["id"], "source_ref": file.get("webViewLink") or f"https://drive.google.com/file/d/{file['id']}/view",
                                    "filename": name, "mime_type": export[0] if export else file["mimeType"],
                                    "version": file.get("version"), "modified_at": file.get("modifiedTime")})
                page_token = result.get("nextPageToken")
                if not page_token:
                    break
        return {"objects": objects}

    def _assert_scope(self, metadata):
        root = self.config.folder_id if self.config.scope == "folder" else self.config.shared_drive_id
        if metadata.get("trashed"):
            raise ValueError("Drive file is trashed")
        pending = list(metadata.get("parents", []))
        seen = set()
        while pending:
            parent = pending.pop()
            if parent == root:
                return
            if parent not in seen and self.config.recursive:
                seen.add(parent)
                pending.extend(self._metadata(parent).get("parents", []))
        raise PermissionError("Drive file is outside the configured scope")

    def fetch_object(self, object_id):
        metadata = self._metadata(object_id)
        self._assert_scope(metadata)
        export = EXPORTS.get(metadata["mimeType"])
        if export:
            return self._get(f"files/{object_id}/export", {"mimeType": export[0]}).content
        return self._get(f"files/{object_id}", {"alt": "media", "supportsAllDrives": "true"}).content

    def close(self):
        if self._session is not None:
            session, self._session = self._session, None
            session.close()
