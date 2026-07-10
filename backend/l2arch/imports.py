"""Parse pasted OpenAPI specs and Kubernetes manifests into L2 artifacts.

Real, offline parsers (no external calls) — the "live import" surface for tools
like SwaggerHub / an API gateway (OpenAPI) and Kubernetes/OpenShift (manifests).
Accepts JSON or YAML content.
"""

from __future__ import annotations

import json
from typing import Any


class ImportError_(ValueError):
    pass


def _load(content: str) -> Any:
    content = (content or "").strip()
    if not content:
        raise ImportError_("Paste some content to import.")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise ImportError_("YAML parsing is unavailable; paste JSON instead.") from exc
    try:
        return yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ImportError_(f"Could not parse content as JSON or YAML: {exc}") from exc


def _load_all(content: str) -> list[Any]:
    """Kubernetes manifests are often multi-document YAML."""
    try:
        return [json.loads(content)]
    except json.JSONDecodeError:
        pass
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise ImportError_("YAML parsing is unavailable; paste JSON instead.") from exc
    try:
        return [doc for doc in yaml.safe_load_all(content) if doc]
    except yaml.YAMLError as exc:
        raise ImportError_(f"Could not parse Kubernetes manifest: {exc}") from exc


_SEC_TO_AUTH = {"oauth2": "OAuth2", "openidconnect": "OIDC", "apikey": "API key", "http": "HTTP auth"}


def parse_openapi(content: str) -> list[dict[str, Any]]:
    """OpenAPI paths → API-contract records (one per path+method)."""
    spec = _load(content)
    if not isinstance(spec, dict) or "paths" not in spec:
        raise ImportError_("Not a recognisable OpenAPI document (no 'paths').")
    title = (spec.get("info") or {}).get("title") or "API"
    version = str((spec.get("info") or {}).get("version") or "v1")
    schemes = spec.get("securitySchemes") or (spec.get("components") or {}).get("securitySchemes") or {}
    default_auth = ""
    for scheme in schemes.values():
        if isinstance(scheme, dict):
            default_auth = _SEC_TO_AUTH.get((scheme.get("type") or "").lower(), scheme.get("type", ""))
            break

    apis: list[dict[str, Any]] = []
    for path, methods in (spec.get("paths") or {}).items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            op = op if isinstance(op, dict) else {}
            apis.append({
                "name": f"{method.upper()} {path}"[:200],
                "provider": title[:200],
                "consumer": "",
                "endpoint": path[:400],
                "api_type": "REST",
                "data_classification": "internal",
                "authentication": (default_auth if op.get("security", spec.get("security")) else "")[:160],
                "version": version[:40],
                "owner": "",
                "status": "active",
            })
    if not apis:
        raise ImportError_("No API operations found in the OpenAPI document.")
    return apis


_WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Service", "CronJob", "Job"}


def parse_kubernetes(content: str) -> list[dict[str, Any]]:
    """Kubernetes workloads/services → container records."""
    docs = _load_all(content)
    containers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        kind = doc.get("kind")
        if kind not in _WORKLOAD_KINDS:
            continue
        meta = doc.get("metadata") or {}
        name = meta.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        labels = meta.get("labels") or {}
        containers.append({
            "name": str(name)[:200],
            "capability": str(labels.get("app.kubernetes.io/part-of") or labels.get("app") or "")[:200],
            "responsibilities": f"Imported from Kubernetes {kind}." + (f" Namespace: {meta.get('namespace')}." if meta.get("namespace") else ""),
            "owns_data": "",
            "owner_team": str(labels.get("team") or labels.get("owner") or "")[:160],
            "security_classification": "internal",
            "nfr_criticality": "medium",
            "status": "active",
        })
    if not containers:
        raise ImportError_("No Deployments, StatefulSets or Services found in the manifest.")
    return containers


def run_import(project_id: str, l2_element_id: str, kind: str, content: str) -> dict[str, Any]:
    from backend.l2arch import store
    from backend.l2arch.models import ApiCreate, ContainerCreate

    if kind == "openapi":
        created = 0
        for api in parse_openapi(content):
            store.create_api(project_id, l2_element_id, ApiCreate(**api))
            created += 1
        return {"kind": kind, "created_apis": created}
    if kind == "kubernetes":
        created = 0
        for container in parse_kubernetes(content):
            store.create_container(project_id, l2_element_id, ContainerCreate(**container))
            created += 1
        return {"kind": kind, "created_containers": created}
    raise ImportError_(f"Unknown import kind '{kind}'. Use 'openapi' or 'kubernetes'.")
