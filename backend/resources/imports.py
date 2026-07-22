"""Excel and LDAP ingestion for the global resource directory."""

from __future__ import annotations

import io
import re
from copy import copy
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from backend.integrations import store as integration_store
from backend.resources import store
from backend.resources.models import StaffCreate, StaffUpdate


class ResourceImportError(ValueError):
    pass


_ALIASES = {
    "staff_first_name": ("first name", "firstname", "given name", "givenname"),
    "staff_last_name": ("last name", "lastname", "surname", "family name", "sn"),
    "staff_name": ("display name", "staff name", "full name", "name"),
    "staff_type": ("staff type", "employment type", "employee type", "type"),
    "staff_status": ("staff status", "employee status", "status"),
    "sub_status": ("allocation", "allocation status", "sub status", "substatus"),
    "tech_unit": ("tech unit", "technology unit", "department"),
    "citizenship": ("citizenship", "country", "country code"),
    "rank": ("rank", "grade", "level"),
    "hr_role": ("hr role", "job title", "title", "role"),
    "staff_start_date": ("start date", "joining date", "staff start date"),
    "staff_end_date": ("end date", "leaving date", "staff end date"),
}


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:10]
    return str(value).strip()


def _column_map(columns: list[str]) -> dict[str, str]:
    normalized = {_norm(column): column for column in columns}
    result: dict[str, str] = {}
    for field, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                result[field] = normalized[alias]
                break
    return result


def _enum(value: str, allowed: tuple[str, ...], default: str) -> str:
    squashed = _norm(value).replace(" ", "")
    aliases = {item.lower().replace(" ", ""): item for item in allowed}
    aliases.update({"permanent": "Perm", "employee": "Perm", "contractor": "Contract",
                    "unallocated": "UnAllocated", "partiallyallocated": "PartiallyAllocated"})
    return aliases.get(squashed, default)


def _payload_from_row(row: dict[str, Any], mapping: dict[str, str]) -> tuple[dict[str, Any], set[str]]:
    values = {field: _text(row.get(column)) for field, column in mapping.items()}
    first = values.get("staff_first_name", "")
    last = values.get("staff_last_name", "")
    display = values.get("staff_name", "")
    if (not first or not last) and display:
        parts = display.split(None, 1)
        first = first or parts[0]
        last = last or (parts[1] if len(parts) > 1 else parts[0])
    if not first or not last:
        raise ResourceImportError("First Name and Last Name are required (or provide Display Name)")

    payload: dict[str, Any] = {
        "staff_first_name": first,
        "staff_last_name": last,
        "staff_name": display or f"{first} {last}",
        "staff_type": _enum(values.get("staff_type", ""), ("Perm", "Contract"), "Perm"),
        "staff_status": _enum(values.get("staff_status", ""), ("Active", "Inactive"), "Active"),
        "sub_status": _enum(values.get("sub_status", ""),
                            ("Allocated", "UnAllocated", "PartiallyAllocated"), "UnAllocated"),
        "tech_unit": values.get("tech_unit", ""),
        "citizenship": values.get("citizenship", ""),
        "rank": values.get("rank", ""),
        "hr_role": values.get("hr_role", ""),
        "staff_start_date": values.get("staff_start_date") or None,
        "staff_end_date": values.get("staff_end_date") or None,
        "custom_values": {},
    }
    for column, raw in row.items():
        normalized = _norm(column)
        if normalized.startswith("custom "):
            label = re.sub(r"^custom\s*[:_]\s*", "", str(column), flags=re.IGNORECASE).strip()
            key = re.sub(r"[^a-zA-Z0-9_]", "_", label)
            if value := _text(raw):
                payload["custom_values"][key] = value
    present = {field for field, column in mapping.items() if _text(row.get(column))}
    present.update({"staff_first_name", "staff_last_name", "staff_name"})
    if payload["custom_values"]:
        present.add("custom_values")
    return payload, present


def _apply(rows: list[dict[str, Any]], *, update_existing: bool, source: str) -> dict[str, Any]:
    existing = {person["staff_name"].casefold(): person for person in store.list_staff()}
    created: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(rows, start=2):
        row = item.get("values", item)
        mapping = item.get("mapping") or {key: key for key in row}
        row_number = int(item.get("row", index))
        try:
            payload, present = _payload_from_row(row, mapping)
            match = existing.get(payload["staff_name"].casefold())
            if match and not update_existing:
                skipped.append({"row": row_number, "name": payload["staff_name"], "reason": "already exists"})
                continue
            if match:
                changes = {key: value for key, value in payload.items() if key in present}
                person = store.update_staff(match["id"], StaffUpdate(**changes))
                updated.append({"id": person["id"], "staff_code": person["staff_code"], "staff_name": person["staff_name"]})
            else:
                person = store.create_staff(StaffCreate(**payload))
                existing[person["staff_name"].casefold()] = person
                created.append({"id": person["id"], "staff_code": person["staff_code"], "staff_name": person["staff_name"]})
        except Exception as exc:
            errors.append({"row": row_number, "name": _text(row.get(mapping.get("staff_name", ""))),
                           "message": str(exc)[:400]})
    return {"source": source, "created": created, "updated": updated, "skipped": skipped, "errors": errors,
            "counts": {"created": len(created), "updated": len(updated), "skipped": len(skipped), "errors": len(errors)}}


def import_excel(content: bytes, filename: str, *, update_existing: bool = False) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".csv":
            frame = pd.read_csv(io.BytesIO(content), dtype=object).fillna("")
        elif suffix in {".xlsx", ".xls"}:
            frame = pd.read_excel(io.BytesIO(content), dtype=object,
                                  engine="openpyxl" if suffix == ".xlsx" else "xlrd").fillna("")
        else:
            raise ResourceImportError("Use a .csv, .xlsx, or .xls resource file")
    except ResourceImportError:
        raise
    except Exception as exc:
        raise ResourceImportError(f"Could not parse {filename}: {exc}") from exc
    if len(frame.index) > 5000:
        raise ResourceImportError("Resource imports are limited to 5,000 rows")
    mapping = _column_map([str(column) for column in frame.columns])
    if "staff_name" not in mapping and not {"staff_first_name", "staff_last_name"} <= set(mapping):
        raise ResourceImportError("The file needs First Name + Last Name, or a Display Name column")
    rows = [{"row": index + 2, "values": row, "mapping": mapping}
            for index, row in enumerate(frame.to_dict(orient="records"))]
    return _apply(rows, update_existing=update_existing, source="excel")


def template_workbook() -> bytes:
    frame = pd.DataFrame([{
        "First Name": "Ada", "Last Name": "Lovelace", "Display Name": "Ada Lovelace",
        "Staff Type": "Perm", "Staff Status": "Active", "Allocation Status": "UnAllocated",
        "Tech Unit": "", "Citizenship": "GB", "Rank": "", "HR Role": "",
        "Start Date": "", "End Date": "",
    }])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Resources")
        sheet = writer.book["Resources"]
        sheet.freeze_panes = "A2"
        for cell in sheet[1]:
            font = copy(cell.font)
            font.bold = True
            cell.font = font
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = max(15, min(28, len(str(column[0].value)) + 4))
    return output.getvalue()


def _first(attributes: dict[str, Any], *keys: str) -> str:
    lower = {str(key).lower(): value for key, value in attributes.items()}
    for key in keys:
        value = lower.get(key.lower())
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        if _text(value):
            return _text(value)
    return ""


def _escape_filter_value(value: str) -> str:
    """Escape an LDAP assertion value according to RFC 4515."""
    return (value.replace("\\", r"\5c").replace("*", r"\2a")
            .replace("(", r"\28").replace(")", r"\29").replace("\x00", r"\00"))


def _single_user_filter(base_filter: str, identifier: str) -> str:
    escaped = _escape_filter_value(identifier.strip())
    identity = (f"(|(uid={escaped})(sAMAccountName={escaped})(userPrincipalName={escaped})"
                f"(mail={escaped})(employeeNumber={escaped})(displayName={escaped}))")
    return f"(&{base_filter}{identity})"


def _fetch_ldap_entries(settings: dict[str, str], search_filter: str, max_results: int) -> list[dict[str, Any]]:
    try:
        from ldap3 import ALL, SUBTREE, Connection, Server
    except ImportError as exc:
        raise ResourceImportError("LDAP import requires the ldap3 package; reinstall backend dependencies") from exc
    parsed = urlparse(settings["server_url"])
    server = Server(parsed.hostname or settings["server_url"], port=parsed.port,
                    use_ssl=parsed.scheme.lower() == "ldaps", get_info=ALL, connect_timeout=15)
    connection = None
    try:
        connection = Connection(server, user=settings["bind_dn"], password=settings["bind_password"],
                                auto_bind=True, receive_timeout=30, raise_exceptions=True)
        attributes = ["givenName", "sn", "displayName", "cn", "employeeType", "department", "title",
                      "c", "userAccountControl", "uid", "sAMAccountName", "userPrincipalName", "mail",
                      "employeeNumber", "telephoneNumber", "mobile"]
        connection.search(settings["base_dn"], search_filter, SUBTREE, attributes=attributes,
                          size_limit=max_results, time_limit=30)
        return [dict(entry.entry_attributes_as_dict) for entry in connection.entries]
    except Exception as exc:
        raise ResourceImportError(f"LDAP query failed: {exc}") from exc
    finally:
        if connection is not None:
            try:
                connection.unbind()
            except Exception:
                pass


def import_ldap(connector_key: str, search_filter: str, max_results: int,
                *, update_existing: bool = False, identifier: str | None = None) -> dict[str, Any]:
    if connector_key not in {"ldap", "active_directory"}:
        raise ResourceImportError("Choose the LDAP or Active Directory connector")
    try:
        settings = integration_store.runtime_config(connector_key)
    except integration_store.IntegrationValidationError as exc:
        raise ResourceImportError(str(exc)) from exc
    effective_filter = _single_user_filter(search_filter, identifier) if identifier else search_filter
    entries = _fetch_ldap_entries(settings, effective_filter, 1 if identifier else max_results)
    lookup_codes = {category: {row["code"] for row in store.list_lookups(category)}
                    for category in ("tech_unit", "rank", "hr_role")}
    custom_keys = {field["key"] for field in store.list_custom_fields()}
    rows = []
    for index, attrs in enumerate(entries, start=1):
        first = _first(attrs, "givenName")
        last = _first(attrs, "sn")
        display = _first(attrs, "displayName", "cn")
        department = _first(attrs, "department")
        title = _first(attrs, "title")
        employee_type = _first(attrs, "employeeType")
        uac = _first(attrs, "userAccountControl")
        disabled = False
        try:
            disabled = bool(int(uac) & 2) if uac else False
        except ValueError:
            pass
        values = {
            "staff_first_name": first, "staff_last_name": last, "staff_name": display,
            "staff_type": "Contract" if "contract" in employee_type.lower() else "Perm",
            "staff_status": "Inactive" if disabled else "Active", "sub_status": "UnAllocated",
            "tech_unit": next((code for code in lookup_codes["tech_unit"] if code.casefold() == department.casefold()), ""),
            "rank": "", "hr_role": next((code for code in lookup_codes["hr_role"] if code.casefold() == title.casefold()), ""),
            "citizenship": _first(attrs, "c"),
        }
        custom_candidates = {
            "email": _first(attrs, "mail", "userPrincipalName"),
            "username": _first(attrs, "sAMAccountName", "uid", "userPrincipalName"),
            "employee_number": _first(attrs, "employeeNumber"),
            "phone": _first(attrs, "telephoneNumber", "mobile"),
        }
        for key, value in custom_candidates.items():
            if key in custom_keys and value:
                values[f"custom:{key}"] = value
        rows.append({"row": index, "values": values, "mapping": {key: key for key in values}})
    return _apply(rows, update_existing=update_existing, source=connector_key)
