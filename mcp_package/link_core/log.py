"""Shared Link log helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .files import append_text_with_rotation, atomic_write_text

DEFAULT_LOG_TEXT = "# Link Wiki Log\n\n*Append-only record of wiki operations.*\n"
DEFAULT_LOG_MAX_BYTES = 2 * 1024 * 1024
DEFAULT_LOG_BACKUPS = 5


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_default_log(path: Path) -> None:
    atomic_write_text(path, DEFAULT_LOG_TEXT)


def append_log(
    wiki_dir: Path,
    timestamp: str,
    operation: str,
    description: str,
    lines: list[str],
    *,
    max_bytes: int = DEFAULT_LOG_MAX_BYTES,
    backups: int = DEFAULT_LOG_BACKUPS,
) -> None:
    log_path = wiki_dir / "log.md"
    entry = [f"## [{timestamp}] {operation} | {description}", ""]
    entry.extend(f"- {line}" for line in lines)
    entry.extend(["", "---", ""])
    append_text_with_rotation(
        log_path,
        "\n".join(entry),
        initial_text=DEFAULT_LOG_TEXT,
        max_bytes=max_bytes,
        backups=backups,
    )
