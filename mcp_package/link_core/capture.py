"""Shared raw capture helpers for Link CLI and MCP runtimes."""
from __future__ import annotations

import re
from pathlib import Path

from .frontmatter import parse_frontmatter


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
