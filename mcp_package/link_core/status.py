"""Shared Link runtime status helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from .memory import memory_records
from .schema import schema_status
from .validation import validate_wiki
from .wiki import build_wiki_cache, close_wiki_cache


def _action(label: str, tool: str, arguments: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "label": label,
        "tool": tool,
        "arguments": arguments or {},
    }


def link_status(
    wiki_dir: Path,
    *,
    version: str = "",
    cache: Mapping[str, Any] | None = None,
    records: Iterable[Mapping[str, object]] | None = None,
    include_validation: bool = False,
) -> dict[str, object]:
    """Return a compact readiness summary for agents and local clients."""
    wiki_dir = wiki_dir.expanduser().resolve()
    required_paths = {
        "wiki": wiki_dir,
        "index": wiki_dir / "index.md",
        "log": wiki_dir / "log.md",
        "backlinks": wiki_dir / "_backlinks.json",
        "memories": wiki_dir / "memories",
    }
    missing = [name for name, path in required_paths.items() if not path.exists()]
    pages: list[Mapping[str, object]] = []
    record_list: list[Mapping[str, object]] = []
    search_backend = "unavailable"
    if wiki_dir.exists():
        wiki_cache: Mapping[str, Any] | None = None
        owns_cache = False
        try:
            if cache is None:
                wiki_cache = build_wiki_cache(wiki_dir)
                owns_cache = True
            else:
                wiki_cache = cache
            pages = list(wiki_cache.get("pages", []))
            search_backend = str(wiki_cache.get("search_backend") or "token-index")
        except Exception:
            pages = []
        finally:
            if owns_cache and isinstance(wiki_cache, dict):
                close_wiki_cache(wiki_cache)
        try:
            record_list = list(records if records is not None else memory_records(wiki_dir))
        except Exception:
            record_list = []

    validation_summary: dict[str, object] = {"checked": False}
    if include_validation and wiki_dir.exists():
        validation = validate_wiki(wiki_dir)
        validation_summary = {
            "checked": True,
            "passed": validation["passed"],
            "error_count": validation["error_count"],
            "warning_count": validation["warning_count"],
            "finding_count": validation["finding_count"],
        }

    active_memory_count = sum(1 for record in record_list if str(record.get("status") or "active").lower() == "active")
    needs_review_count = sum(
        1
        for record in record_list
        if str(record.get("review_status") or "pending").lower() != "reviewed"
        and str(record.get("status") or "active").lower() == "active"
    )
    content_page_count = sum(
        1
        for page in pages
        if str(page.get("path") or "") not in {"wiki/index.md", "wiki/log.md"}
    )
    ready = not missing and bool(pages) and (
        not include_validation or bool(validation_summary.get("passed"))
    )
    schema = schema_status(wiki_dir)

    next_actions: list[dict[str, object]] = []
    if missing:
        next_actions.append(_action("repair or scaffold Link structure", "doctor", {"fix": True}))
    if schema.get("status") in {"missing", "old"}:
        next_actions.append(_action("write current Link wiki schema marker", "migrate_wiki"))
    elif schema.get("status") == "invalid":
        next_actions.append(_action("inspect invalid Link wiki schema marker", "doctor"))
    elif schema.get("status") == "newer":
        next_actions.append(_action("upgrade Link before writing this wiki", "upgrade_link"))
    if include_validation and validation_summary.get("checked") and not validation_summary.get("passed"):
        next_actions.append(_action("rebuild graph index", "rebuild_backlinks"))
        next_actions.append(_action("rerun validation gate", "validate_wiki"))
    if ready and content_page_count:
        next_actions.append(_action("answer with compact local context", "query_link", {"query": "<user task>"}))
        next_actions.append(_action("prime agent memory before work", "memory_brief", {"query": "<user task>"}))
    elif ready:
        next_actions.append(_action("add raw sources or inspect ingest readiness", "ingest_status"))
        next_actions.append(_action("show first-run prompts", "starter_prompts"))
    elif not missing:
        next_actions.append(_action("inspect wiki health", "validate_wiki"))

    return {
        "ready": ready,
        "version": version,
        "wiki": str(wiki_dir),
        "missing": missing,
        "page_count": len(pages),
        "content_page_count": content_page_count,
        "memory_count": len(record_list),
        "active_memory_count": active_memory_count,
        "needs_review_count": needs_review_count,
        "search_backend": search_backend,
        "schema": schema,
        "validation": validation_summary,
        "next_actions": next_actions,
    }
