"""Shared raw capture helpers for Link CLI and MCP runtimes."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from .frontmatter import parse_frontmatter
from .memory import normalize_project, slugify
from .security import redact_secret_values, secret_value_warnings


CaptureCommands = Callable[[str], dict[str, str]]


def capture_title(
    text: str,
    source: str = "",
    title: str | None = None,
    *,
    default_source: str = "inline",
    path_source: bool = False,
    max_source_len: int = 120,
) -> str:
    """Build a stable human-readable title for saved raw memory captures."""
    if title and title.strip():
        return " ".join(title.split())

    source_value = " ".join(str(source or "").split())
    if source_value and source_value != default_source:
        if path_source:
            stem = Path(source_value).stem.replace("-", " ").replace("_", " ").strip()
            if stem:
                return f"Memory capture: {stem.title()}"
        else:
            return f"Memory capture: {source_value[:max_source_len]}"

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "Session notes")
    short = " ".join(first_line.split()[:10]).strip(" .")
    return f"Memory capture: {short or 'Session notes'}"


def capture_filename(timestamp: str, title: str, raw_dir: Path) -> Path:
    """Return a unique capture path under raw_dir for the given timestamp/title."""
    safe_stamp = str(timestamp).replace("-", "").replace(":", "")
    title_slug = slugify(title.replace("Memory capture:", ""), fallback="session-notes")
    base = f"{safe_stamp}-{title_slug}"
    candidate = raw_dir / f"{base}.md"
    counter = 2
    while candidate.exists():
        candidate = raw_dir / f"{base}-{counter}.md"
        counter += 1
    return candidate


def resolve_capture_file(root: Path, capture: str, *, max_len: int | None = None) -> Path | None:
    """Resolve a user-provided raw capture path without escaping the Link root."""
    raw = str(capture or "").strip()
    if max_len is not None:
        raw = raw[:max_len]
    if not raw:
        return None

    root = root.expanduser().resolve()
    raw_path = Path(raw).expanduser()
    candidates = [raw_path]
    if not raw_path.is_absolute():
        candidates.extend([
            root / raw,
            root / "raw" / "memory-captures" / raw,
            root / "raw" / "memory-captures" / f"{raw}.md",
        ])

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.is_file():
            continue
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        return resolved
    return None


def capture_notes_from_markdown(text: str) -> tuple[dict[str, object], str]:
    """Return capture frontmatter and the `## Notes` body when present."""
    meta, body = parse_frontmatter(text)
    match = re.search(r"^## Notes\s*(.*?)(?=^## |\Z)", body, flags=re.MULTILINE | re.DOTALL)
    notes = match.group(1).strip() if match else body.strip()
    return meta, notes


def cli_capture_commands(rel_path: str) -> dict[str, str]:
    return {
        "accept": f'python3 link.py accept-capture "{rel_path}" . --index 1',
        "redact": f'python3 link.py redact-capture "{rel_path}" .',
        "delete": f'python3 link.py delete-capture "{rel_path}" . --confirm',
    }


def mcp_capture_commands(rel_path: str) -> dict[str, str]:
    return {
        "accept": f'accept_capture(capture="{rel_path}", index=1)',
        "redact": f'redact_capture(capture="{rel_path}")',
        "delete": f'delete_capture(capture="{rel_path}", confirm=true)',
    }


def capture_records(
    root: Path,
    limit: int = 20,
    project: str | None = None,
    commands_for: CaptureCommands | None = None,
) -> list[dict[str, object]]:
    root = root.expanduser().resolve()
    capture_dir = root / "raw" / "memory-captures"
    if not capture_dir.exists():
        return []
    project_name = normalize_project(project)
    command_builder = commands_for or cli_capture_commands
    records: list[dict[str, object]] = []
    for path in sorted(capture_dir.rglob("*.md")):
        if path.name.startswith("."):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            stat = path.stat()
        except OSError:
            continue
        meta, notes = capture_notes_from_markdown(text)
        capture_project = normalize_project(str(meta.get("project") or ""))
        if project_name and capture_project and capture_project != project_name:
            continue
        rel = path.relative_to(root).as_posix()
        warnings = secret_value_warnings(text)
        safe_notes, _, _ = redact_secret_values(notes)
        records.append({
            "path": rel,
            "title": str(meta.get("title") or path.stem),
            "project": capture_project,
            "date_captured": str(meta.get("date_captured") or ""),
            "size_bytes": stat.st_size,
            "secret_warnings": warnings,
            "warning_count": len(warnings),
            "snippet": re.sub(r"\s+", " ", safe_notes).strip()[:180],
            "commands": command_builder(rel),
        })
    records.sort(key=lambda item: (str(item["date_captured"]), str(item["path"])), reverse=True)
    return records[:max(1, min(limit, 50))]


def capture_inbox(
    root: Path,
    limit: int = 20,
    project: str | None = None,
    commands_for: CaptureCommands | None = None,
) -> dict[str, object]:
    project_name = normalize_project(project)
    captures = capture_records(root, limit=limit, project=project_name, commands_for=commands_for)
    return {
        "count": len(captures),
        "warning_count": sum(1 for capture in captures if capture["warning_count"]),
        "project": project_name,
        "captures": captures,
    }
