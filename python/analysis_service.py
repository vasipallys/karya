"""Bundled JSON-lines static-analysis worker used by RepoParserAgent.

Input:  {"action":"analyze","root":"..."}
Output: {"files":[...],"symbols":[...],"dependencies":[...]}
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".cs", ".go"}
DECLARATION = re.compile(r"\b(class|interface|type|function|func)\s+([A-Za-z_]\w*)")
IMPORT = re.compile(r"(?:from|import|require\()\s*['\"]?([^'\"\s;)]+)")


def analyze(root: str) -> dict:
    files, symbols, dependencies = [], [], []
    for file in Path(root).rglob("*"):
        if not file.is_file() or file.suffix.lower() not in EXTENSIONS:
            continue
        if any(part in {"node_modules", ".git", "dist", "build", ".venv"} for part in file.parts):
            continue
        relative = str(file.relative_to(root)).replace("\\", "/")
        try:
            source = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        files.append({"path": relative, "language": file.suffix.lstrip("."), "lines": source.count("\n") + 1})
        if file.suffix == ".py":
            try:
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.append({"name": node.name, "kind": node.__class__.__name__, "path": relative, "line": node.lineno})
            except SyntaxError:
                pass
        else:
            for match in DECLARATION.finditer(source):
                symbols.append({"name": match.group(2), "kind": match.group(1), "path": relative, "line": source[:match.start()].count("\n") + 1})
        for match in IMPORT.finditer(source):
            dependencies.append({"source": relative, "target": match.group(1)})
    return {"files": files, "symbols": symbols, "dependencies": dependencies}


for line in sys.stdin:
    try:
        message = json.loads(line)
        result = analyze(message["root"]) if message.get("action") == "analyze" else {"error": "unknown action"}
    except Exception as exc:  # worker protocol must always respond
        result = {"error": str(exc)}
    print(json.dumps(result), flush=True)
