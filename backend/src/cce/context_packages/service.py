"""Context package use cases."""


class ContextPackageService:
    def get_package(self, package_id: str):
        return {"package_id": package_id, "name": "", "active_version": ""}

    def list_packages(self):
        return []

    def get_package_version(self, package_id: str, version: str):
        return {
            "package_id": package_id,
            "version": version,
            "status": "NOT_FOUND",
            "assets": [],
            "scope": "",
            "created_at": "",
            "parent_version": "",
        }
