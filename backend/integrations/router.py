"""Integration-catalog + per-connector configuration endpoints."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.integrations import catalog, connectors, store

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _run(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except store.NotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)}) from exc
    except store.IntegrationValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": "integration_invalid", "message": str(exc)}) from exc


def _require_configurable(key: str) -> None:
    if key not in connectors.CONNECTOR_ARCHETYPE and key not in connectors.NON_CONFIGURABLE:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"Unknown connector '{key}'"})


class ConfigPayload(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)
    enabled: bool = False


@router.get("/catalog")
async def list_catalog() -> dict[str, Any]:
    return catalog.list_catalog()


@router.get("/{connector_key}/config")
async def get_config(connector_key: str) -> dict[str, Any]:
    _require_configurable(connector_key)
    return store.get_config(connector_key)


@router.patch("/{connector_key}/config")
async def save_config(connector_key: str, payload: ConfigPayload, request: Request) -> dict[str, Any]:
    _require_configurable(connector_key)
    user = request.headers.get("X-User-Id", "") or request.headers.get("X-User-Role", "")
    return _run(lambda: store.save_config(connector_key, payload.values, payload.enabled, user))


@router.post("/{connector_key}/test")
async def test_config(connector_key: str) -> dict[str, Any]:
    _require_configurable(connector_key)
    return _run(lambda: store.test_config(connector_key))


@router.delete("/{connector_key}/config")
async def clear_config(connector_key: str) -> dict[str, str]:
    _require_configurable(connector_key)
    _run(lambda: store.clear_config(connector_key))
    return {"status": "cleared"}
