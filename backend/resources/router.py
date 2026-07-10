"""HTTP endpoints for the global resource directory."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.resources import store
from backend.resources.models import (
    CustomFieldCreate,
    CustomFieldUpdate,
    LookupCreate,
    LookupUpdate,
    StaffCreate,
    StaffUpdate,
)

router = APIRouter(prefix="/resources", tags=["resources"])


def _guard(operation: Any) -> Any:
    try:
        return operation()
    except store.NotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc
    except store.ValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_resource", "message": str(exc)}) from exc


# ------------------------------------------------------------------ staff


@router.get("/staff")
async def list_staff(
    staff_status: str | None = None,
    sub_status: str | None = None,
    staff_type: str | None = None,
    tech_unit: str | None = None,
    rank: str | None = None,
    hr_role: str | None = None,
    search: str | None = Query(default=None, max_length=160),
) -> list[dict[str, Any]]:
    return store.list_staff({
        "staff_status": staff_status,
        "sub_status": sub_status,
        "staff_type": staff_type,
        "tech_unit": tech_unit,
        "rank": rank,
        "hr_role": hr_role,
        "search": search,
    })


@router.post("/staff")
async def create_staff(payload: StaffCreate) -> dict[str, Any]:
    return _guard(lambda: store.create_staff(payload))


@router.get("/staff/{staff_id}")
async def get_staff(staff_id: str) -> dict[str, Any]:
    return _guard(lambda: store.get_staff(staff_id))


@router.patch("/staff/{staff_id}")
async def update_staff(staff_id: str, payload: StaffUpdate) -> dict[str, Any]:
    return _guard(lambda: store.update_staff(staff_id, payload))


@router.delete("/staff/{staff_id}")
async def delete_staff(staff_id: str) -> dict[str, str]:
    _guard(lambda: store.delete_staff(staff_id))
    return {"status": "deleted"}


# ------------------------------------------------------------------ lookups


@router.get("/lookups")
async def list_all_lookups() -> dict[str, list[dict[str, Any]]]:
    return store.list_all_lookups()


@router.get("/lookups/{category}")
async def list_lookups(category: str) -> list[dict[str, Any]]:
    return _guard(lambda: store.list_lookups(category))


@router.post("/lookups/{category}")
async def create_lookup(category: str, payload: LookupCreate) -> dict[str, Any]:
    return _guard(lambda: store.create_lookup(category, payload))


@router.patch("/lookups/{lookup_id}")
async def update_lookup(lookup_id: str, payload: LookupUpdate) -> dict[str, Any]:
    return _guard(lambda: store.update_lookup(lookup_id, payload))


@router.delete("/lookups/{lookup_id}")
async def delete_lookup(lookup_id: str) -> dict[str, str]:
    _guard(lambda: store.delete_lookup(lookup_id))
    return {"status": "deleted"}


# ------------------------------------------------------------------ custom fields


@router.get("/custom-fields")
async def list_custom_fields() -> list[dict[str, Any]]:
    return store.list_custom_fields()


@router.post("/custom-fields")
async def create_custom_field(payload: CustomFieldCreate) -> dict[str, Any]:
    return _guard(lambda: store.create_custom_field(payload))


@router.patch("/custom-fields/{field_id}")
async def update_custom_field(field_id: str, payload: CustomFieldUpdate) -> dict[str, Any]:
    return _guard(lambda: store.update_custom_field(field_id, payload))


@router.delete("/custom-fields/{field_id}")
async def delete_custom_field(field_id: str) -> dict[str, str]:
    _guard(lambda: store.delete_custom_field(field_id))
    return {"status": "deleted"}
