"""Context package use cases."""

from cce.core.errors import NotImplementedCCEError


class ContextPackageService:
    def get_package(self, package_id: str):
        raise NotImplementedCCEError("context package service is not implemented yet")
