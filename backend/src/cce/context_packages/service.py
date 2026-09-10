class ContextPackageService:
    def __init__(self, repository): self.repository=repository
    def get_package(self, workspace_uuid): return self.repository.get_package(workspace_uuid)
    def versions(self, workspace_uuid): return self.repository.versions(workspace_uuid)
    def get_package_version(self, workspace_uuid, version): return self.repository.version(workspace_uuid,version)
    def active(self, workspace_uuid): return self.repository.active(workspace_uuid)
    def rename(self, workspace_uuid, name): return self.repository.rename(workspace_uuid,name)
