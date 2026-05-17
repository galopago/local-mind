"""Lightweight operation journal for Link's local multi-file writes."""
from __future__ import annotations

import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .files import atomic_write_json

OPERATION_DIR_NAME = ".link-operations"
DEFAULT_STALE_AFTER_SECONDS = 10 * 60


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str, fallback: str = "operation") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or fallback


def operation_dir(wiki_dir: Path) -> Path:
    return wiki_dir / OPERATION_DIR_NAME


def begin_operation(
    wiki_dir: Path,
    operation: str,
    description: str,
    *,
    timestamp: str = "",
    paths: Iterable[str] | None = None,
) -> Path:
    """Write a pending operation marker before a multi-file mutation begins."""
    marker_dir = operation_dir(wiki_dir)
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker = marker_dir / f"{_slug(operation)}-{uuid.uuid4().hex}.json"
    now = timestamp or _utc_timestamp()
    atomic_write_json(marker, {
        "status": "pending",
        "operation": operation,
        "description": description,
        "started_at": now,
        "monotonic_started_at": time.monotonic(),
        "paths": list(paths or []),
    })
    return marker


def finish_operation(marker: Path) -> None:
    """Clear a pending marker after a mutation fully completes."""
    try:
        marker.unlink()
    except FileNotFoundError:
        pass


def fail_operation(marker: Path, exc: BaseException) -> None:
    """Leave a failed marker with a small error summary for doctor/status."""
    try:
        payload = _read_marker(marker)
        payload["status"] = "failed"
        payload["failed_at"] = _utc_timestamp()
        payload["error"] = str(exc)[:300] or exc.__class__.__name__
        atomic_write_json(marker, payload)
    except OSError:
        pass


@contextmanager
def operation_journal(
    wiki_dir: Path,
    operation: str,
    description: str,
    *,
    timestamp: str = "",
    paths: Iterable[str] | None = None,
):
    marker = begin_operation(wiki_dir, operation, description, timestamp=timestamp, paths=paths)
    try:
        yield marker
    except BaseException as exc:
        fail_operation(marker, exc)
        raise
    else:
        finish_operation(marker)


def _parse_timestamp(value: object) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _read_marker(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def pending_operations(
    wiki_dir: Path,
    *,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    now: float | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return pending or failed operation markers, newest first."""
    marker_dir = operation_dir(wiki_dir)
    if not marker_dir.exists():
        return []
    current = time.time() if now is None else now
    operations: list[dict[str, Any]] = []
    for marker in sorted(marker_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        try:
            payload = _read_marker(marker)
        except (OSError, ValueError):
            payload = {"status": "invalid", "operation": "unknown", "description": "Unreadable operation marker"}
        started_epoch = _parse_timestamp(payload.get("started_at"))
        age_seconds = max(0, current - started_epoch) if started_epoch is not None else None
        payload["marker"] = marker.name
        payload["path"] = str(marker)
        payload["age_seconds"] = age_seconds
        payload["stale"] = age_seconds is None or age_seconds >= stale_after_seconds or payload.get("status") == "failed"
        operations.append(payload)
    return operations
