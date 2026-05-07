#!/usr/bin/env python3
"""Guard against large copied helper bodies across Link runtimes."""
from __future__ import annotations

import argparse
import ast
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
    findings: list[str] = []
    for name, group in duplicate_private_name_groups(functions):
        if max(info.line_count for info in group) < LARGE_DUPLICATE_LINE_THRESHOLD:
            continue
        if name in ALLOWED_LARGE_DUPLICATE_NAMES:
            continue
        locations = ", ".join(info.location for info in sorted(group, key=lambda item: item.location))
        findings.append(f"large duplicate private helper '{name}': {locations}")
    return findings


def duplicate_private_name_groups(functions: list[FunctionInfo]) -> list[tuple[str, list[FunctionInfo]]]:
    by_name: dict[str, list[FunctionInfo]] = {}
    for info in functions:
        if info.name.startswith("_"):
            by_name.setdefault(info.name, []).append(info)

    groups: list[tuple[str, list[FunctionInfo]]] = []
    for name, group in sorted(by_name.items()):
        paths = {info.path for info in group}
        if len(paths) >= 2:
            groups.append((name, group))
    return groups


def format_private_name_report(functions: list[FunctionInfo]) -> str:
    groups = duplicate_private_name_groups(functions)
    if not groups:
        return "Duplicate private runtime helper names: 0"

    report_rows = []
    for name, group in groups:
        max_lines = max(info.line_count for info in group)
        total_lines = sum(info.line_count for info in group)
        guarded = max_lines >= LARGE_DUPLICATE_LINE_THRESHOLD
        locations = ", ".join(info.location for info in sorted(group, key=lambda item: item.location))
        report_rows.append((guarded, max_lines, total_lines, name, locations))

    report_rows.sort(key=lambda row: (not row[0], -row[1], row[3]))
    guarded_count = sum(1 for guarded, *_ in report_rows if guarded)
    lines = [
        "Duplicate private runtime helper names: "
        f"{len(report_rows)} ({guarded_count} at or above {LARGE_DUPLICATE_LINE_THRESHOLD} lines)"
    ]
    for guarded, max_lines, total_lines, name, locations in report_rows:
        status = "guarded" if guarded else "thin"
        lines.append(f"- {name}: {status}; max {max_lines} lines, total {total_lines}; {locations}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        action="store_true",
        help="print a non-failing audit of duplicate private helper names before running the guard",
    )
    args = parser.parse_args(argv)

    functions = runtime_functions()
    if args.report:
        print(format_private_name_report(functions))

    findings = [
        *check_exact_duplicate_bodies(functions),
        *check_large_duplicate_private_names(functions),
    ]
    if findings:
        if args.report:
            print("")
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
