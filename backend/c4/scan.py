"""Deterministic repo scan that proposes C4 elements from directory structure."""

from __future__ import annotations

from pathlib import Path
from typing import Any

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "venv", ".venv", "__pycache__",
    "dist", "build", "target", ".idea", ".vscode", "coverage", ".pytest_cache",
    "data", "docs",
}

TECH_BY_EXTENSION = {
    ".py": "Python",
    ".java": "Java",
    ".kt": "Kotlin",
    ".js": "JavaScript",
    ".jsx": "React",
    ".ts": "TypeScript",
    ".tsx": "React",
    ".go": "Go",
    ".cs": "C#",
    ".sql": "SQL",
}


def _code_extensions(directory: Path, depth: int = 3) -> set[str]:
    found: set[str] = set()
    if depth < 0:
        return found
    try:
        entries = list(directory.iterdir())
    except OSError:
        return found
    for entry in entries:
        if entry.is_file() and entry.suffix in TECH_BY_EXTENSION:
            found.add(entry.suffix)
        elif entry.is_dir() and entry.name not in SKIP_DIRS and not entry.name.startswith("."):
            found |= _code_extensions(entry, depth - 1)
    return found


def _tech_label(extensions: set[str]) -> str:
    return ", ".join(sorted({TECH_BY_EXTENSION[ext] for ext in extensions}))


def scan_repo(local_path: str, project_name: str) -> dict[str, Any]:
    """Propose an L1 system, L2 containers (top-level code dirs), and L3 components (their code subdirs)."""
    root = Path(local_path)
    if not root.is_dir():
        raise FileNotFoundError(f"Local path '{local_path}' is not a directory")

    containers: list[dict[str, Any]] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name in SKIP_DIRS or entry.name.startswith("."):
            continue
        extensions = _code_extensions(entry)
        if not extensions:
            continue
        components = []
        for child in sorted(entry.iterdir()):
            if not child.is_dir() or child.name in SKIP_DIRS or child.name.startswith("."):
                continue
            child_extensions = _code_extensions(child)
            if not child_extensions:
                continue
            components.append({
                "name": child.name,
                "level": "L3",
                "kind": "component",
                "tech": _tech_label(child_extensions),
                "code_path": str(child.relative_to(root)).replace("\\", "/"),
            })
        containers.append({
            "name": entry.name,
            "level": "L2",
            "kind": "container",
            "tech": _tech_label(extensions),
            "code_path": str(entry.relative_to(root)).replace("\\", "/"),
            "components": components,
        })

    return {
        "system": {"name": project_name, "level": "L1", "kind": "system", "code_path": ""},
        "containers": containers,
    }
