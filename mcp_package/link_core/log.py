"""Shared Link log helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .files import append_text, atomic_write_text

DEFAULT_LOG_TEXT = "# Link Wiki Log\n\n*Append-only record of wiki operations.*\n"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_default_log(path: Path) -> None:
    atomic_write_text(path, DEFAULT_LOG_TEXT)


def append_log(wiki_dir: Path, timestamp: str, operation: str, description: str, lines: list[str]) -> None:
    log_path = wiki_dir / "log.md"
    if not log_path.exists():
        write_default_log(log_path)
    entry = [f"## [{timestamp}] {operation} | {description}", ""]
    entry.extend(f"- {line}" for line in lines)
    entry.extend(["", "---", ""])
    append_text(log_path, "\n".join(entry))
