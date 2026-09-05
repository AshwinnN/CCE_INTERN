"""Package RPC mapping."""


class PackageRPCService:
    def __init__(self, app):
        self.app = app

    def GetPackage(self, request, context):
        from cce.gen.cce.v1 import packages_pb2

        package = self.app.package_service.get_package(request.package_id)
        return packages_pb2.Package(
            package_id=package["package_id"],
            name=package["name"],
            active_version=package["active_version"],
        )

    def ListPackages(self, request, context):
        from cce.gen.cce.v1 import packages_pb2

        packages = [
            packages_pb2.Package(
                package_id=item.get("package_id", ""),
                name=item.get("name", ""),
                active_version=item.get("active_version", ""),
            )
            for item in self.app.package_service.list_packages()
        ]
        return packages_pb2.ListPackagesResponse(packages=packages)

    def GetPackageVersion(self, request, context):
        from cce.gen.cce.v1 import packages_pb2

        version = self.app.package_service.get_package_version(
            request.package_id, request.version
        )
        return packages_pb2.PackageVersion(
            package_id=version["package_id"],
            version=version["version"],
            status=version["status"],
            assets=version.get("assets", []),
            scope=version.get("scope", ""),
            created_at=version.get("created_at", ""),
            parent_version=version.get("parent_version", ""),
        )
