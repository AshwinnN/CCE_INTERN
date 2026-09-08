from cce.rpc.services.errors import rpc_errors
from google.protobuf.json_format import ParseDict


def encode(snapshot):
    from cce.gen.cce.v1 import packages_pb2

    if snapshot is None:
        return packages_pb2.PackageVersion(status="NO_ACTIVE_PACKAGE")
    return ParseDict(
        {
            "package_id": str(snapshot.package_id),
            "version": str(snapshot.version),
            "status": snapshot.status,
            "assets": [str(a.asset_revision_id) for a in snapshot.assets],
            "snapshot": snapshot.model_dump(mode="json"),
        },
        packages_pb2.PackageVersion(),
    )


class PackageRPCService:
    def __init__(self, app):
        self.app = app

    @rpc_errors
    def GetPackage(self, request, context):
        from cce.gen.cce.v1 import packages_pb2

        return ParseDict(
            self.app.package_service.get_package(request.package_id),
            packages_pb2.Package(),
        )

    @rpc_errors
    def ListPackages(self, request, context):
        from cce.gen.cce.v1 import packages_pb2

        return ParseDict(
            {"packages": self.app.package_service.list_packages()},
            packages_pb2.ListPackagesResponse(),
        )

    @rpc_errors
    def GetPackageVersion(self, request, context):
        return encode(
            self.app.package_service.get_package_version(
                request.package_id, request.version
            )
        )

    @rpc_errors
    def GetActivePackage(self, request, context):
        return encode(self.app.package_service.active(request.domain_id))
