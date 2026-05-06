#!/usr/bin/env python3
"""Guard against large copied helper bodies across Link runtimes."""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = (
    ROOT / "link.py",
    ROOT / "serve.py",
    ROOT / "mcp_package/link_mcp/server.py",
)
EXACT_DUPLICATE_LINE_THRESHOLD = 12
LARGE_DUPLICATE_LINE_THRESHOLD = 20

# New large duplicate runtime helpers should be extracted instead of added here.
ALLOWED_LARGE_DUPLICATE_NAMES: set[str] = set()


@dataclass(frozen=True)
class FunctionInfo:
    path: Path
    name: str
    lineno: int
    end_lineno: int
    body_dump: str

    @property
    def line_count(self) -> int:
        return self.end_lineno - self.lineno + 1

    @property
    def location(self) -> str:
        try:
            display_path = self.path.relative_to(ROOT)
        except ValueError:
            display_path = self.path
        return f"{display_path}:{self.lineno}"


def runtime_functions(paths: tuple[Path, ...] = RUNTIME_FILES) -> list[FunctionInfo]:
    functions: list[FunctionInfo] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            functions.append(
                FunctionInfo(
                    path=path,
                    name=node.name,
                    lineno=node.lineno,
                    end_lineno=node.end_lineno or node.lineno,
                    body_dump=ast.dump(
                        ast.Module(body=node.body, type_ignores=[]),
                        include_attributes=False,
                    ),
                )
            )
    return functions


def check_exact_duplicate_bodies(functions: list[FunctionInfo]) -> list[str]:
    by_body: dict[str, list[FunctionInfo]] = {}
    for info in functions:
        if info.line_count >= EXACT_DUPLICATE_LINE_THRESHOLD:
            by_body.setdefault(info.body_dump, []).append(info)

    findings: list[str] = []
    for group in by_body.values():
        paths = {info.path for info in group}
        if len(paths) < 2:
            continue
        locations = ", ".join(info.location for info in sorted(group, key=lambda item: item.location))
        findings.append(f"exact duplicate runtime function body: {locations}")
    return findings


def check_large_duplicate_private_names(functions: list[FunctionInfo]) -> list[str]:
    by_name: dict[str, list[FunctionInfo]] = {}
    for info in functions:
        if info.name.startswith("_"):
            by_name.setdefault(info.name, []).append(info)

    findings: list[str] = []
    for name, group in sorted(by_name.items()):
        paths = {info.path for info in group}
        if len(paths) < 2:
            continue
        if max(info.line_count for info in group) < LARGE_DUPLICATE_LINE_THRESHOLD:
            continue
        if name in ALLOWED_LARGE_DUPLICATE_NAMES:
            continue
        locations = ", ".join(info.location for info in sorted(group, key=lambda item: item.location))
        findings.append(f"large duplicate private helper '{name}': {locations}")
    return findings


def main() -> int:
    functions = runtime_functions()
    findings = [
        *check_exact_duplicate_bodies(functions),
        *check_large_duplicate_private_names(functions),
    ]
    if findings:
        print("Runtime duplication guard failed:")
        for finding in findings:
            print(f"- {finding}")
        print("")
        print("Move shared logic into mcp_package/link_core/ and keep runtimes as thin adapters.")
        return 1
    print("Runtime duplication guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
