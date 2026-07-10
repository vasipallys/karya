"""Excel/CSV detection, mapping, validation, and template generation."""

from __future__ import annotations

import io
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, BinaryIO

import pandas as pd

from backend.models import Story

TARGET_ALIASES = {
    "title": ["title", "summary", "story title", "issue", "name"],
    "user_story": ["user story", "description", "story", "details", "requirement"],
    "acceptance_criteria": ["acceptance criteria", "acs", "ac", "criteria", "conditions of satisfaction"],
    "technical_breakdown": ["technical breakdown", "technical notes", "implementation", "dev notes"],
    "existing_points": ["existing points", "story points", "points", "sp", "estimate"],
}


class UploadError(ValueError):
    pass


def _score(header: str, alias: str) -> float:
    clean_header = re.sub(r"[^a-z0-9]+", " ", header.lower()).strip()
    if clean_header == alias:
        return 1.0
    if alias in clean_header or clean_header in alias:
        return 0.9
    return SequenceMatcher(None, clean_header, alias).ratio()


def suggest_mapping(columns: list[str]) -> dict[str, str | None]:
    suggestions: dict[str, str | None] = {}
    used: set[str] = set()
    for target, aliases in TARGET_ALIASES.items():
        candidates = [(max(_score(column, alias) for alias in aliases), column) for column in columns if column not in used]
        score, column = max(candidates, default=(0.0, ""))
        suggestions[target] = column if score >= 0.55 else None
        if suggestions[target]:
            used.add(column)
    return suggestions


def read_upload(content: bytes, filename: str) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".csv":
            return pd.read_csv(io.BytesIO(content), dtype=object).fillna("")
        if suffix in {".xlsx", ".xls"}:
            engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
            return pd.read_excel(io.BytesIO(content), dtype=object, engine=engine).fillna("")
    except Exception as exc:
        raise UploadError(f"Could not parse {filename}: {exc}") from exc
    raise UploadError("Use a .csv, .xlsx, or .xls file")


def dataframe_payload(frame: pd.DataFrame, preview_rows: int = 20) -> dict[str, Any]:
    columns = [str(column) for column in frame.columns]
    rows = json.loads(frame.to_json(orient="records", date_format="iso"))
    rows = [{key: "" if value is None else value for key, value in row.items()} for row in rows]
    return {
        "columns": columns,
        "suggested_mapping": suggest_mapping(columns),
        "preview": rows[:preview_rows],
        "rows": rows,
        "row_count": len(rows),
    }


def rows_to_stories(
    rows: list[dict[str, Any]], mapping: dict[str, str | None]
) -> tuple[list[Story], list[dict[str, Any]]]:
    title_column = mapping.get("title")
    if not title_column:
        raise UploadError("Map a source column to Title before estimating")
    stories: list[Story] = []
    skipped: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):
        title = str(row.get(title_column, "")).strip()
        if not title:
            skipped.append({"row": index, "reason": "Title is blank"})
            continue
        points_raw = row.get(mapping.get("existing_points") or "", "")
        try:
            points = float(points_raw) if str(points_raw).strip() else None
        except (TypeError, ValueError):
            points = None
        stories.append(
            Story(
                title=title,
                user_story=str(row.get(mapping.get("user_story") or "", "")).strip(),
                acceptance_criteria=row.get(mapping.get("acceptance_criteria") or "", ""),
                technical_breakdown=str(row.get(mapping.get("technical_breakdown") or "", "")).strip() or None,
                existing_points=points,
                source="upload",
            )
        )
    return stories, skipped


def template_workbook() -> bytes:
    frame = pd.DataFrame(
        [
            {
                "Title": "Add beneficiary confirmation",
                "User Story": "As a customer, I want to confirm beneficiary details before payment.",
                "Acceptance Criteria": "Show beneficiary name\nRecord confirmation in audit trail",
                "Technical Breakdown": "React confirmation panel; Spring audit event",
                "Existing Points": "",
            }
        ]
    )
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Stories")
        sheet = writer.book["Stories"]
        sheet.freeze_panes = "A2"
        for cell in sheet[1]:
            cell.font = cell.font.copy(bold=True)
        for column, width in {"A": 34, "B": 60, "C": 60, "D": 50, "E": 18}.items():
            sheet.column_dimensions[column].width = width
    return output.getvalue()
