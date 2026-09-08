from fastapi import APIRouter, HTTPException
from api.models import PackageCreate
from api.store import store

router = APIRouter(prefix="/packages", tags=["packages"])


@router.get("")
def list_packages():
    return {"packages": store.packages}


@router.get("/{package_id}")
def get_package(package_id: str):
    package = next((p for p in store.packages if p["package_id"] == package_id), None)
    if not package:
        raise HTTPException(404, "Package not found")
    return package


@router.post("")
def create_package(body: PackageCreate):
    try:
        return store.create_package(body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
