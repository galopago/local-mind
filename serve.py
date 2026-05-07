#!/usr/bin/env python3
"""Link — local wiki viewer. python serve.py → http://localhost:3000"""
from __future__ import annotations
import html, http.server, json, re, socketserver, sys, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_BUNDLED_CORE = ROOT / "mcp_package"
if (_BUNDLED_CORE / "link_core").exists():
    sys.path.insert(0, str(_BUNDLED_CORE))

from link_core.memory import (
    add_capture_review_to_brief as _core_add_capture_review_to_brief,
    count_values as _core_count_values,
    is_active_memory as _core_is_active_memory,
    memory_action_hints as _core_memory_action_hints,
    memory_brief as _core_memory_brief,
    memory_explanation as _core_memory_explanation,
    memory_inbox as _core_memory_inbox,
    memory_profile as _core_memory_profile,
    memory_audit_report as _core_memory_audit_report,
    memory_records as _core_memory_records,
    memory_review_issues as _core_memory_review_issues,
    memory_duplicate_candidates as _core_memory_duplicate_candidates,
    memory_visible_for_project as _core_memory_visible_for_project,
    mark_memory_reviewed as _core_mark_memory_reviewed,
    normalize_project as _core_normalize_project,
    propose_memories_from_text as _core_propose_memories_from_text,
    set_memory_status as _core_set_memory_status,
    update_memory_page as _core_update_memory_page,
    write_memory_page as _core_write_memory_page,
)
from link_core.frontmatter import (
    parse_frontmatter as _parse_frontmatter,
)
from link_core.ingest import (
    collect_ingest_status as _core_collect_ingest_status,
)
from link_core.log import (
    append_log as _core_append_log,
    utc_timestamp as _core_utc_timestamp,
)
from link_core.security import (
    clean_text_input as _clean_text_input,
    redact_secret_values as _redact_secret_values,
    secret_value_warnings as _secret_value_warnings,
)
from link_core.query import (
    query_link as _core_query_link,
)
from link_core.prompts import (
    starter_prompt_payload as _core_starter_prompt_payload,
)
from link_core.validation import (
    validate_wiki as _core_validate_wiki,
)
from link_core.status import (
    link_status as _core_link_status,
)
from link_core.capture import (
    capture_inbox as _core_capture_inbox,
    capture_records as _core_capture_records,
    cli_capture_commands as _core_cli_capture_commands,
)
from link_core.wiki import (
    build_backlinks as _core_build_backlinks,
    build_wiki_cache as _core_build_wiki_cache,
    close_wiki_cache as _core_close_wiki_cache,
    context_for_topic as _core_context_for_topic,
    graph_data as _core_graph_data,
    load_backlinks_index as _core_load_backlinks_index,
    rebuild_index as _core_rebuild_index,
    search_pages as _core_search_pages,
    wiki_mtime as _core_wiki_mtime,
)
del _BUNDLED_CORE

WIKI_DIR = ROOT / "wiki"
RAW_DIR = ROOT / "raw"
PORT = 3000
API_VERSION = "1"
MAX_POST_BYTES = 64 * 1024
MAX_PROPOSAL_SOURCE_BYTES = 64 * 1024
LOCAL_ACTION_HEADER = "X-Link-Local-Action"
LOCAL_ACTION_VALUES = {"1", "true", "yes"}
PROPOSAL_SOURCE_SUFFIXES = {
    ".md",
    ".markdown",
    ".txt",
    ".text",
    ".rst",
    ".adoc",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
}
RAW_STATIC_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
}

# ---------------------------------------------------------------------------
# In-memory caches — invalidated on each request by mtime check
# ---------------------------------------------------------------------------
_pages_cache: list | None = None
_pages_cache_mtime: float = 0.0
_page_index: dict[str, Path] = {}  # stem.lower() → path
_fulltext_index: dict[str, str] = {}  # stem.lower() → full text (for search)
_normalized_fulltext_index: dict[str, str] = {}  # punctuation-normalized full text
_text_words_index: dict[str, set[str]] = {}  # stem.lower() → normalized fulltext words
_meta_words_index: dict[str, set[str]] = {}  # stem.lower() → normalized metadata words
_snippet_index: dict[str, str] = {}  # stem.lower() → pre-extracted first snippet
_token_index: dict[str, set[str]] = {}  # token → set of page stems that contain it
_page_map: dict[str, dict] = {}  # stem.lower() → page dict (for O(1) lookup in search)
_meta_token_index: dict[str, set[str]] = {}  # token → stems with that token in title/alias/tag/tldr
_fts_index = None
_search_backend = "token-index"

def _invalidate_pages_cache() -> None:
    global _pages_cache, _pages_cache_mtime, _fts_index, _search_backend
    _core_close_wiki_cache({"fts_index": _fts_index})
    _pages_cache = None
    _pages_cache_mtime = 0.0
    _fts_index = None
    _search_backend = "token-index"


def _wiki_mtime() -> float:
    return _core_wiki_mtime(WIKI_DIR)


def _get_all_pages() -> list:
    global _pages_cache, _pages_cache_mtime, _page_index, _fulltext_index, _normalized_fulltext_index, _text_words_index, _meta_words_index, _snippet_index, _token_index, _page_map, _meta_token_index, _fts_index, _search_backend
    mtime = _wiki_mtime()
    if _pages_cache is not None and mtime == _pages_cache_mtime:
        return _pages_cache
    _core_close_wiki_cache({"fts_index": _fts_index})
    cache = _core_build_wiki_cache(WIKI_DIR)
    _pages_cache = cache["pages"]
    _pages_cache_mtime = mtime
    _page_index = cache["page_index"]
    _fulltext_index = cache["fulltext"]
    _normalized_fulltext_index = cache["normalized_fulltext"]
    _text_words_index = cache["text_words_index"]
    _meta_words_index = cache["meta_words_index"]
    _snippet_index = cache["snippet_index"]
    _token_index = cache["token_index"]
    _meta_token_index = cache["meta_token_index"]
    _page_map = cache["page_map"]
    _fts_index = cache.get("fts_index")
    _search_backend = str(cache.get("search_backend") or "token-index")
    return _pages_cache


def _current_wiki_cache() -> dict[str, object]:
    _get_all_pages()
    return {
        "pages": _pages_cache or [],
        "page_index": _page_index,
        "fulltext": _fulltext_index,
        "normalized_fulltext": _normalized_fulltext_index,
        "text_words_index": _text_words_index,
        "meta_words_index": _meta_words_index,
        "snippet_index": _snippet_index,
        "token_index": _token_index,
        "meta_token_index": _meta_token_index,
        "page_map": _page_map,
        "fts_index": _fts_index,
        "search_backend": _search_backend,
    }


def _find_page(name: str) -> Path | None:
    # Ensure cache is warm — _get_all_pages populates _page_index as a side effect
    _get_all_pages()
    return _page_index.get(name.strip().lower())


# Keep _all_pages as alias for API compatibility
def _all_pages() -> list:
    return _get_all_pages()


def _load_backlinks_index() -> tuple[dict, str | None]:
    return _core_load_backlinks_index(WIKI_DIR / "_backlinks.json")


def _parse_search_limit(raw: str) -> tuple[int | None, str | None]:
    try:
        limit = int(raw)
    except ValueError:
        return None, "limit must be an integer"
    if limit < 1:
        return None, "limit must be at least 1"
    return min(limit, 50), None


def _utc_timestamp() -> str:
    return _core_utc_timestamp()


def _append_log(timestamp: str, operation: str, description: str, lines: list[str]) -> None:
    _core_append_log(WIKI_DIR, timestamp, operation, description, lines)


def _page_href(name: str) -> str:
    return "/page/" + urllib.parse.quote(name.strip(), safe="")


def _plural_type_label(page_type: str) -> str:
    irregular = {"entity": "entities", "memory": "memories"}
    if page_type in irregular:
        return irregular[page_type]
    return page_type if page_type.endswith("s") else page_type + "s"


def _memory_records() -> list[dict[str, object]]:
    return _core_memory_records(WIKI_DIR, include_body=False)


def _count_values(records: list[dict[str, object]], field: str) -> dict[str, int]:
    return _core_count_values(records, field)


def _is_active_memory(record: dict[str, object]) -> bool:
    return _core_is_active_memory(record)


def _memory_review_issues(record: dict[str, object]) -> list[dict[str, str]]:
    return _core_memory_review_issues(record, review_command="review-memory")


def _project_visible_records(project: str | None = None) -> list[dict[str, object]]:
    project_name = _core_normalize_project(project)
    return [
        record
        for record in _memory_records()
        if _core_memory_visible_for_project(record, project_name)
    ]


def _ingest_status() -> dict[str, object]:
    return _core_collect_ingest_status(WIKI_DIR.parent)


def _memory_inbox(limit: int = 20, include_archived: bool = False, project: str | None = None) -> dict[str, object]:
    return _core_memory_inbox(
        _project_visible_records(project),
        limit=limit,
        include_archived=include_archived,
        review_command="review-memory",
        project=project,
    )


def _slugify(value: str, fallback: str = "memory") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def _memory_title(text: str, explicit_title: str | None = None) -> str:
    if explicit_title and explicit_title.strip():
        return explicit_title.strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "Memory")
    first_sentence = re.split(r"(?<=[.!?])\s+", first_line, maxsplit=1)[0].strip()
    if len(first_sentence) <= 70:
        return first_sentence.rstrip(".")
    return first_sentence[:67].rstrip() + "..."


def _memory_duplicate_candidates(
    text: str,
    title: str | None,
    memory_type: str,
    scope: str,
    limit: int = 3,
) -> list[dict[str, object]]:
    return _core_memory_duplicate_candidates(
        _memory_records(),
        text,
        title,
        memory_type,
        scope,
        limit=limit,
    )


def _propose_memories_from_text(
    text: str,
    source: str = "http",
    limit: int = 10,
    project: str | None = None,
) -> dict[str, object]:
    return _core_propose_memories_from_text(
        text,
        _memory_records(),
        source=source,
        limit=limit,
        writes_memory=False,
        project=project,
    )


def _memory_explanation(identifier: str) -> dict[str, object]:
    return _core_memory_explanation(
        WIKI_DIR,
        identifier,
        records=_memory_records(),
        review_command="review-memory",
    )


def _memory_profile(limit: int = 10, project: str | None = None) -> dict[str, object]:
    return _core_memory_profile(_memory_records(), limit=limit, review_command="review-memory", project=project)


def _mark_memory_reviewed(identifier: str, note: str = "") -> dict[str, object]:
    result = _core_mark_memory_reviewed(
        WIKI_DIR,
        _clean_text_input(identifier, max_len=300),
        note=_clean_text_input(note, max_len=500),
        timestamp=_utc_timestamp(),
        records=_memory_records(),
        review_command="review-memory",
        log_writer=_append_log,
    )
    if result["updated"]:
        _invalidate_pages_cache()
    return result


def _set_memory_status(identifier: str, status: str, reason: str = "") -> dict[str, object]:
    result = _core_set_memory_status(
        WIKI_DIR,
        _clean_text_input(identifier, max_len=300),
        status,
        reason=_clean_text_input(reason, max_len=500),
        timestamp=_utc_timestamp(),
        records=_memory_records(),
        log_writer=_append_log,
    )
    if result["updated"]:
        _invalidate_pages_cache()
    return result


def _remember_memory_from_web(payload: dict[str, object]) -> dict[str, object]:
    result = _core_write_memory_page(
        WIKI_DIR,
        _clean_text_input(payload.get("memory") or payload.get("text"), max_len=MAX_POST_BYTES),
        _clean_text_input(payload.get("title"), max_len=160) or None,
        _clean_text_input(payload.get("memory_type") or payload.get("type") or "note", max_len=30),
        _clean_text_input(payload.get("scope") or "user", max_len=30),
        _clean_text_input(payload.get("tags"), max_len=500) or None,
        _clean_text_input(payload.get("source") or "web approval", max_len=500),
        _utc_timestamp(),
        project=_clean_text_input(payload.get("project"), max_len=80) or None,
        records=_memory_records(),
        allow_duplicate=bool(payload.get("allow_duplicate")),
        allow_conflict=bool(payload.get("allow_conflict")),
        log_writer=_append_log,
        rebuild_backlinks=lambda: bool(_rebuild_backlinks_payload().get("rebuilt")),
    )
    if result.get("created"):
        _invalidate_pages_cache()
    return result


def _update_memory_from_web(payload: dict[str, object]) -> dict[str, object]:
    result = _core_update_memory_page(
        WIKI_DIR,
        _clean_text_input(payload.get("memory") or payload.get("identifier"), max_len=300),
        _clean_text_input(payload.get("text"), max_len=MAX_POST_BYTES),
        _clean_text_input(payload.get("source") or "web approval", max_len=500),
        _utc_timestamp(),
        records=_memory_records(),
        review_command="review-memory",
        allow_conflict=bool(payload.get("allow_conflict")),
        project=_clean_text_input(payload.get("project"), max_len=80) or None,
        log_writer=_append_log,
        rebuild_backlinks=lambda: bool(_rebuild_backlinks_payload().get("rebuilt")),
    )
    if result.get("updated"):
        _invalidate_pages_cache()
    return result


def _memory_activity_key(record: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(record.get("updated_at") or record.get("date_captured") or ""),
        str(record.get("date_captured") or ""),
        str(record.get("title") or "").lower(),
    )


def _memory_action_hints(record: dict[str, object]) -> list[dict[str, object]]:
    hints: list[dict[str, object]] = []
    for action in _core_memory_action_hints(record, review_command="review-memory"):
        item = {
            "kind": str(action.get("kind") or ""),
            "label": str(action.get("label") or ""),
            "href": "",
            "command": str(action.get("command") or ""),
            "description": str(action.get("description") or ""),
            "priority": str(action.get("priority") or ""),
            "arguments": action.get("arguments") if isinstance(action.get("arguments"), dict) else {},
        }
        if action.get("kind") == "explain":
            name = str(record.get("name") or "")
            item["href"] = f"/explain-memory?memory={urllib.parse.quote(name, safe='')}"
        hints.append(item)
    return hints


def _memory_with_actions(record: dict[str, object]) -> dict[str, object]:
    item = dict(record)
    item["actions"] = _memory_action_hints(record)
    return item


def _memory_dashboard_next_actions(
    memory_count: int,
    review_count: int,
    updated_count: int,
    archived_count: int,
    capture_count: int = 0,
    capture_warning_count: int = 0,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if capture_warning_count:
        actions.append({
            "label": "Redact capture warnings",
            "detail": f"{capture_warning_count} raw capture{'s' if capture_warning_count != 1 else ''} contain secret-looking values.",
            "href": "/captures",
            "command": "python3 link.py redact-capture raw/memory-captures/<capture>.md .",
            "priority": "high",
        })
    if review_count:
        memory_label = "memory" if review_count == 1 else "memories"
        verb = "needs" if review_count == 1 else "need"
        actions.append({
            "label": "Review pending memories",
            "detail": f"{review_count} {memory_label} {verb} confirmation or metadata cleanup.",
            "href": "/inbox",
            "command": "python3 link.py memory-inbox .",
            "priority": "high",
        })
    if updated_count:
        actions.append({
            "label": "Audit recent memory updates",
            "detail": f"{updated_count} memory update{'s' if updated_count != 1 else ''} should be checked for accuracy.",
            "href": "/memory",
            "command": "python3 link.py profile .",
            "priority": "medium",
        })
    if archived_count:
        actions.append({
            "label": "Inspect archived memory",
            "detail": f"{archived_count} archived memory page{'s' if archived_count != 1 else ''} remain inspectable but hidden from default recall.",
            "href": "/profile",
            "command": "python3 link.py profile .",
            "priority": "low",
        })
    if capture_count and not capture_warning_count:
        actions.append({
            "label": "Review raw captures",
            "detail": f"{capture_count} saved raw capture{'s' if capture_count != 1 else ''} can be accepted, redacted, or deleted.",
            "href": "/captures",
            "command": "python3 link.py accept-capture raw/memory-captures/<capture>.md . --index 1",
            "priority": "medium",
        })
    if not memory_count:
        actions.append({
            "label": "Create the first memory",
            "detail": "Save an explicit preference, decision, project fact, or note for local agents.",
            "href": "",
            "command": 'python3 link.py remember "User prefers ..." . --type preference --scope user',
            "priority": "high",
        })
    if not actions:
        actions.append({
            "label": "Memory is recall-ready",
            "detail": "No pending review items or recent updates need attention.",
            "href": "/profile",
            "command": "python3 link.py profile .",
            "priority": "info",
        })
    return actions[:3]


def _capture_records(limit: int = 12, project: str | None = None) -> list[dict[str, object]]:
    root = WIKI_DIR.parent
    return _core_capture_records(
        root,
        limit=limit,
        project=project,
        commands_for=_core_cli_capture_commands,
    )


def _capture_inbox(limit: int = 20, project: str | None = None) -> dict[str, object]:
    return _core_capture_inbox(
        WIKI_DIR.parent,
        limit=limit,
        project=project,
        commands_for=_core_cli_capture_commands,
    )


def _capture_review_summary(project: str | None = None, limit: int = 3) -> dict[str, object]:
    project_name = _core_normalize_project(project)
    captures = _capture_records(limit=50, project=project_name)
    project_query = f"?project={urllib.parse.quote(project_name, safe='')}" if project_name else ""
    project_arg = f' --project "{project_name}"' if project_name else ""
    return {
        "count": len(captures),
        "warning_count": sum(1 for capture in captures if capture["warning_count"]),
        "project": project_name,
        "href": f"/captures{project_query}",
        "command": f"python3 link.py capture-inbox .{project_arg}",
        "items": captures[:max(1, min(limit, 10))],
    }


def _memory_brief(query: str = "", limit: int = 6, project: str | None = None) -> dict[str, object]:
    limit = max(1, min(limit, 20))
    project_name = _core_normalize_project(project)
    payload = _core_memory_brief(
        _memory_records(), query=query, limit=limit,
        review_command="review-memory", project=project_name,
    )
    return _core_add_capture_review_to_brief(
        payload,
        _capture_review_summary(project=project_name, limit=min(limit, 10)),
    )


def _memory_dashboard(limit: int = 12, project: str | None = None) -> dict[str, object]:
    limit = max(1, min(limit, 50))
    project_name = _core_normalize_project(project)
    records = _project_visible_records(project_name)
    active_records = [record for record in records if _is_active_memory(record)]
    archived_records = [
        record for record in records
        if str(record.get("status") or "").lower() == "archived"
    ]
    recent_active = sorted(active_records, key=_memory_activity_key, reverse=True)
    recent_updates = sorted(
        [record for record in records if str(record.get("updated_at") or "").strip()],
        key=lambda record: (
            str(record.get("updated_at") or ""),
            str(record.get("title") or "").lower(),
        ),
        reverse=True,
    )
    archived = sorted(archived_records, key=_memory_activity_key, reverse=True)
    inbox = _memory_inbox(limit=limit, project=project_name)
    review_count = inbox["review_count"]
    updated_count = len(recent_updates)
    archived_count = len(archived_records)
    captures = _capture_records(limit=limit, project=project_name)
    capture_warning_count = sum(1 for capture in captures if capture["warning_count"])
    return {
        "memory_count": len(records),
        "active_count": len(active_records),
        "review_count": review_count,
        "archived_count": archived_count,
        "updated_count": updated_count,
        "capture_count": len(captures),
        "capture_warning_count": capture_warning_count,
        "project": project_name,
        "by_type": _count_values(records, "memory_type"),
        "by_scope": _count_values(records, "scope"),
        "counts_by_severity": inbox["counts_by_severity"],
        "next_actions": _memory_dashboard_next_actions(
            memory_count=len(records),
            review_count=review_count,
            updated_count=updated_count,
            archived_count=archived_count,
            capture_count=len(captures),
            capture_warning_count=capture_warning_count,
        ),
        "active": [_memory_with_actions(record) for record in recent_active[:limit]],
        "review": [_memory_with_actions(record) for record in inbox["items"][:limit]],
        "recent_updates": [_memory_with_actions(record) for record in recent_updates[:limit]],
        "archived": [_memory_with_actions(record) for record in archived[:limit]],
        "captures": captures,
    }


def _web_memory_audit_actions(
    inbox: dict[str, object],
    captures: dict[str, object],
    risk_factors: list[dict[str, object]],
    project_name: str,
) -> list[dict[str, object]]:
    project_query = f"?project={urllib.parse.quote(project_name, safe='')}" if project_name else ""
    project_arg = f' --project "{project_name}"' if project_name else ""
    return [
        {
            "label": "Review memory inbox",
            "detail": "Review pending, stale, invalid, or underspecified memories.",
            "href": f"/inbox{project_query}",
            "command": f"python3 link.py memory-inbox .{project_arg}",
            "recommended": bool(inbox["review_count"]),
        },
        {
            "label": "Review raw captures",
            "detail": "Accept, redact, or delete saved proposal-only raw captures.",
            "href": f"/captures{project_query}",
            "command": f"python3 link.py capture-inbox .{project_arg}",
            "recommended": bool(captures["count"]),
        },
        {
            "label": "Run doctor",
            "detail": "Check graph, source, memory, raw capture, and secret hygiene.",
            "href": "",
            "command": "python3 link.py doctor .",
            "recommended": not risk_factors,
        },
    ]


def _memory_audit(limit: int = 10, project: str | None = None) -> dict[str, object]:
    limit = max(1, min(limit, 50))
    project_name = _core_normalize_project(project)
    profile = _memory_profile(limit=limit, project=project_name)
    inbox = _memory_inbox(limit=limit, include_archived=True, project=project_name)
    capture_items = _capture_records(limit=min(limit, 10), project=project_name)
    captures = {
        "count": len(capture_items),
        "warning_count": sum(1 for capture in capture_items if capture["warning_count"]),
        "items": capture_items,
    }
    payload = _core_memory_audit_report(profile, inbox, captures, [], project=project_name)
    payload["next_actions"] = _web_memory_audit_actions(
        inbox,
        captures,
        payload["risk_factors"],
        str(payload["project"]),
    )
    return payload


def _json_for_script(data) -> str:
    """Serialize JSON for direct embedding inside a <script> tag."""
    return (
        json.dumps(data, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _safe_resolve(path: Path) -> Path | None:
    try:
        return path.resolve()
    except (OSError, ValueError):
        return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_allowed_static_file(path: Path) -> bool:
    root = Path(__file__).parent.resolve()
    raw_root = RAW_DIR.resolve()
    allowed_root_files = {
        (root / "logo.svg").resolve(),
        (root / "logo.png").resolve(),
    }
    return path in allowed_root_files or (
        _is_relative_to(path, raw_root)
        and path.suffix.lower() in RAW_STATIC_TYPES
    )


def _resolve_raw_static_path(url_fragment: str) -> tuple[Path | None, str | None]:
    decoded = urllib.parse.unquote(url_fragment).lstrip("/")
    resolved = _safe_resolve(RAW_DIR / decoded)
    if not resolved or not _is_relative_to(resolved, RAW_DIR.resolve()):
        return None, None
    content_type = RAW_STATIC_TYPES.get(resolved.suffix.lower())
    if not content_type:
        return None, None
    return resolved, content_type


def _proposal_source_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()[:100] or fallback
        if stripped:
            return stripped[:100]
    return fallback


def _proposal_source_snippet(text: str) -> str:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("---")
    ]
    return " ".join(lines[:3])[:260]


def _resolve_proposal_source_path(source_path: str) -> Path | None:
    decoded = urllib.parse.unquote(str(source_path or "")).strip().lstrip("/")
    if decoded.startswith("raw/"):
        decoded = decoded[4:]
    if not decoded:
        return None
    resolved = _safe_resolve(RAW_DIR / decoded)
    raw_root = RAW_DIR.resolve()
    if not resolved or not _is_relative_to(resolved, raw_root):
        return None
    if not resolved.is_file() or resolved.suffix.lower() not in PROPOSAL_SOURCE_SUFFIXES:
        return None
    return resolved


def _proposal_source_record(path: Path, include_text: bool = False) -> dict[str, object]:
    raw_root = RAW_DIR.resolve()
    rel = path.relative_to(raw_root).as_posix()
    try:
        size = path.stat().st_size
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "path": f"raw/{rel}",
            "source": f"raw/{rel}",
            "title": rel,
            "size": 0,
            "snippet": "",
            "secret_warnings": [],
            "warning_count": 0,
            "loadable": False,
            "error": str(exc),
        }
    labels = _secret_value_warnings(text)
    redacted, _, _ = _redact_secret_values(text) if labels else (text, [], 0)
    record: dict[str, object] = {
        "path": f"raw/{rel}",
        "source": f"raw/{rel}",
        "title": _proposal_source_title(redacted, rel),
        "size": size,
        "snippet": _proposal_source_snippet(redacted),
        "secret_warnings": labels,
        "warning_count": len(labels),
        "loadable": not labels and size <= MAX_PROPOSAL_SOURCE_BYTES,
        "truncated": size > MAX_PROPOSAL_SOURCE_BYTES,
    }
    if include_text and record["loadable"]:
        record["text"] = text[:MAX_PROPOSAL_SOURCE_BYTES]
    return record


def _proposal_sources(limit: int = 50) -> dict[str, object]:
    if not RAW_DIR.exists():
        return {"count": 0, "sources": [], "raw_dir": str(RAW_DIR), "warning_count": 0}
    raw_root = RAW_DIR.resolve()
    sources: list[dict[str, object]] = []
    for path in sorted(RAW_DIR.rglob("*")):
        resolved = _safe_resolve(path)
        if not resolved or not _is_relative_to(resolved, raw_root):
            continue
        if not resolved.is_file() or resolved.suffix.lower() not in PROPOSAL_SOURCE_SUFFIXES:
            continue
        if any(part.startswith(".") for part in resolved.relative_to(raw_root).parts):
            continue
        sources.append(_proposal_source_record(resolved))
        if len(sources) >= limit:
            break
    warning_count = sum(int(source.get("warning_count") or 0) for source in sources)
    return {
        "count": len(sources),
        "sources": sources,
        "raw_dir": str(RAW_DIR),
        "warning_count": warning_count,
    }


def _proposal_source_payload(source_path: str) -> tuple[dict[str, object], int]:
    path = _resolve_proposal_source_path(source_path)
    if not path:
        return {"found": False, "error": "source path not found or unsupported"}, 404
    record = _proposal_source_record(path, include_text=True)
    if record.get("warning_count"):
        record["found"] = True
        record["error"] = "source contains secret-looking values; redact before loading"
        return record, 409
    if not record.get("loadable"):
        record["found"] = True
        record["error"] = "source is too large to load into the proposal form"
        return record, 413
    record["found"] = True
    return record, 200


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _inline(text):
    def _stash(rendered: str) -> str:
        html_spans.append(rendered)
        return f"\x00HTML{len(html_spans)-1}\x00"

    def _safe_href(href: str) -> str:
        href = html.unescape(href).strip()
        parsed = urllib.parse.urlparse(href)
        if href.startswith("//") or (parsed.scheme and parsed.scheme.lower() not in {"http", "https", "mailto"}):
            return "#"
        return html.escape(href, quote=True)

    def _wl(m):
        inner = html.unescape(m.group(1))
        t, d = (inner.split("|", 1) if "|" in inner else (inner, inner))
        href = _page_href(t)
        return _stash(f'<a href="{href}">{html.escape(d.strip())}</a>')

    def _md_link(m):
        label = html.unescape(m.group(1))
        href = _safe_href(m.group(2))
        return _stash(f'<a href="{href}">{html.escape(label)}</a>')

    html_spans: list[str] = []
    text = html.escape(text, quote=False)

    def _save_code(m):
        return _stash(f"<code>{m.group(1)}</code>")

    text = re.sub(r"`([^`]+)`", _save_code, text)
    text = re.sub(r"\[\[([^\]]+)\]\]", _wl, text)
    text = re.sub(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", _md_link, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Guard: only match single * that are not part of **
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    for i, span in enumerate(html_spans):
        text = text.replace(f"\x00HTML{i}\x00", span)
    return text


def _md_to_html(md):
    out, in_code, in_table, in_list, lt, code_lang, in_blockquote, bq_lines = [], False, False, False, None, "", False, []

    def _flush_blockquote():
        if bq_lines:
            out.append(f"<blockquote>{'<br>'.join(bq_lines)}</blockquote>")
            bq_lines.clear()

    for line in md.split("\n"):
        s = line.strip()
        if s.startswith("```"):
            _flush_blockquote(); in_blockquote = False
            if in_code:
                out.append("</code></pre>"); in_code = False; code_lang = ""
            else:
                code_lang = s[3:].strip()
                lang_attr = f' class="language-{html.escape(code_lang)}"' if code_lang else ""
                out.append(f'<pre><code{lang_attr}>'); in_code = True
            continue
        if in_code: out.append(html.escape(line)); continue
        if in_table and not s.startswith("|"):
            out.append("</tbody></table>"); in_table = False
        if in_list and not re.match(r"^\s*[-*]\s|^\s*\d+\.\s", line) and s:
            out.append(f'</{"ul" if lt == "ul" else "ol"}>'); in_list = False
        # Blockquote: collect consecutive > lines, flush on non-> line
        if s.startswith(">"):
            if in_list: out.append(f'</{"ul" if lt == "ul" else "ol"}>'); in_list = False
            if in_table: out.append("</tbody></table>"); in_table = False
            bq_lines.append(_inline(s[1:].strip()))
            in_blockquote = True
            continue
        if in_blockquote:
            _flush_blockquote(); in_blockquote = False
        if s in ("---", "***", "___") and not in_table: out.append("<hr>"); continue
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m: out.append(f'<h{len(m.group(1))}>{_inline(m.group(2))}</h{len(m.group(1))}>'); continue
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.match(r"^[-:]+$", c) for c in cells): continue
            if not in_table:
                out.append("<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in cells) + "</tr></thead><tbody>"); in_table = True
            else:
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
            continue
        m = re.match(r"^\s*[-*]\s+(.*)", line)
        if m:
            if not in_list or lt != "ul":
                if in_list: out.append(f'</{"ul" if lt == "ul" else "ol"}>')
                out.append("<ul>"); in_list, lt = True, "ul"
            out.append(f"<li>{_inline(m.group(1))}</li>"); continue
        m = re.match(r"^\s*\d+\.\s+(.*)", line)
        if m:
            if not in_list or lt != "ol":
                if in_list: out.append(f'</{"ul" if lt == "ul" else "ol"}>')
                out.append("<ol>"); in_list, lt = True, "ol"
            out.append(f"<li>{_inline(m.group(1))}</li>"); continue
        if not s: out.append(""); continue
        out.append(f"<p>{_inline(s)}</p>")
    if in_code: out.append("</code></pre>")
    if in_table: out.append("</tbody></table>")
    if in_list: out.append(f'</{"ul" if lt == "ul" else "ol"}>')
    _flush_blockquote()
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CSS + layout
# ---------------------------------------------------------------------------

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  color-scheme: light;
  --bg: #ffffff;
  --text: #222222;
  --text-strong: #222222;
  --muted: #666666;
  --subtle: #888888;
  --faint: #aaaaaa;
  --link: #0645ad;
  --border: #d0d7de;
  --border-soft: #eeeeee;
  --surface: #ffffff;
  --surface-muted: #f6f8fa;
  --surface-code: #f6f6f6;
  --surface-code-inline: #f0f0f0;
  --surface-table: #f8f8f8;
  --surface-graph: #101418;
  --surface-empty: #fafafa;
  --mark-bg: #fff3cd;
  --button-bg: #ffffff;
  --button-hover: #f6f8fa;
  --button-text: #24292f;
  --button-disabled: #8c959f;
  --accent: #0969da;
  --accent-soft: #6ea8fe;
  --quote-border: #cccccc;
  --quote-text: #555555;
  --shadow: rgba(0,0,0,0.15);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #000000;
    --text: #e7e7e7;
    --text-strong: #f2f2f2;
    --muted: #b7b7b7;
    --subtle: #8e8e8e;
    --faint: #777777;
    --link: #7db7ff;
    --border: #2a2a2a;
    --border-soft: #1f1f1f;
    --surface: #080808;
    --surface-muted: #101010;
    --surface-code: #0d0d0d;
    --surface-code-inline: #151515;
    --surface-table: #0d0d0d;
    --surface-graph: #05090d;
    --surface-empty: #080808;
    --mark-bg: #3b2f00;
    --button-bg: #0f0f0f;
    --button-hover: #171717;
    --button-text: #e7e7e7;
    --button-disabled: #777777;
    --accent: #4ea1ff;
    --accent-soft: #7db7ff;
    --quote-border: #333333;
    --quote-text: #c7c7c7;
    --shadow: rgba(0,0,0,0.55);
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #000000;
  --text: #e7e7e7;
  --text-strong: #f2f2f2;
  --muted: #b7b7b7;
  --subtle: #8e8e8e;
  --faint: #777777;
  --link: #7db7ff;
  --border: #2a2a2a;
  --border-soft: #1f1f1f;
  --surface: #080808;
  --surface-muted: #101010;
  --surface-code: #0d0d0d;
  --surface-code-inline: #151515;
  --surface-table: #0d0d0d;
  --surface-graph: #05090d;
  --surface-empty: #080808;
  --mark-bg: #3b2f00;
  --button-bg: #0f0f0f;
  --button-hover: #171717;
  --button-text: #e7e7e7;
  --button-disabled: #777777;
  --accent: #4ea1ff;
  --accent-soft: #7db7ff;
  --quote-border: #333333;
  --quote-text: #c7c7c7;
  --shadow: rgba(0,0,0,0.55);
}
:root[data-theme="light"] { color-scheme: light; }
html { overflow-x: hidden; background: var(--bg); }
body { font-family: Georgia, "Times New Roman", serif; background: var(--bg); color: var(--text);
       width: 100%; max-width: 760px; margin: 0 auto; padding: 20px;
       overflow-x: hidden; overflow-wrap: anywhere; }
body.graph-page { max-width: min(1440px, 100%); }
a { color: var(--link); }
a, p, li, code { overflow-wrap: anywhere; }
a:hover { text-decoration: underline; }

header { border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-bottom: 24px; }
header .header-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
header .logo { font-size: 24px; font-weight: bold; letter-spacing: 0; white-space: nowrap; flex: 0 0 auto; }
header .logo a { color: var(--text-strong); text-decoration: none; display: inline-flex; align-items: center; gap: 8px; }
header .logo img { width: 28px; height: 28px; border-radius: 7px; flex: none; }
header .logo small { font-weight: normal; font-size: 13px; color: var(--subtle); margin-left: 8px; }
header nav { display: flex; gap: 10px 16px; font-size: 14px; font-family: sans-serif; flex-wrap: wrap; min-width: 0; align-items: center; }
header .header-tools { display: grid; justify-items: end; gap: 7px; flex: 0 0 220px; min-width: 170px; max-width: 42vw; }
header form { display: block; width: 100%; }
header input { padding: 4px 8px; border: 1px solid var(--border); border-radius: 4px; font-size: 13px; width: 100%; background: var(--surface); color: var(--text); }
header .theme-toggle { border: 1px solid var(--border); background: var(--button-bg); color: var(--button-text);
                       border-radius: 999px; padding: 3px 8px; font: 12px -apple-system, BlinkMacSystemFont, sans-serif;
                       cursor: pointer; display: inline-flex; align-items: center; gap: 6px; max-width: 100%; }
header .theme-toggle:hover { background: var(--button-hover); }
header .theme-icon { width: 14px; height: 14px; border-radius: 50%; border: 1px solid currentColor;
                     background: linear-gradient(90deg, currentColor 0 50%, transparent 50% 100%); flex: none; }
header .theme-text { white-space: nowrap; }

.breadcrumb { font-size: 13px; color: var(--subtle); margin-bottom: 12px; font-family: sans-serif; }
.breadcrumb a { color: var(--link); }

.meta { font-size: 13px; color: var(--muted); margin-bottom: 16px; font-family: sans-serif; }
.meta .badge { background: var(--surface-muted); padding: 1px 8px; border-radius: 3px; font-size: 12px; }

h1 { font-size: 26px; margin-bottom: 4px; line-height: 1.3; }
h2 { font-size: 20px; margin-top: 28px; margin-bottom: 10px; border-bottom: 1px solid var(--border-soft); padding-bottom: 4px; }
h3 { font-size: 17px; margin-top: 20px; margin-bottom: 8px; }
p { line-height: 1.7; margin-bottom: 12px; }
ul, ol { margin: 8px 0 12px 28px; line-height: 1.7; }
li { margin-bottom: 3px; }
blockquote { border-left: 3px solid var(--quote-border); padding: 6px 16px; margin: 12px 0; color: var(--quote-text); }
pre { background: var(--surface-code); padding: 14px; border-radius: 4px; overflow-x: auto; margin: 12px 0;
      font-size: 13px; font-family: Menlo, monospace; }
code { font-family: Menlo, monospace; font-size: 0.9em; }
p code { background: var(--surface-code-inline); padding: 1px 5px; border-radius: 3px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 15px; }
th, td { border: 1px solid var(--border); padding: 7px 12px; text-align: left; }
th { background: var(--surface-table); }
hr { border: none; border-top: 1px solid var(--border); margin: 24px 0; }

.home-stats { display: flex; gap: 24px; margin: 20px 0; font-family: sans-serif; font-size: 14px; }
.home-stats .stat { text-align: center; }
.home-stats .stat .num { font-size: 28px; font-weight: bold; color: var(--accent-soft); display: block; }
.home-stats .stat .label { color: var(--subtle); font-size: 12px; }
.product-lanes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 18px 0 22px; }
.product-lane { border: 1px solid var(--border-soft); border-radius: 6px; background: var(--surface); padding: 12px; font-family: sans-serif; }
.product-lane h2 { border: 0; margin: 0 0 8px; padding: 0; font-size: 15px; font-family: sans-serif; }
.product-lane p { margin: 0; color: var(--muted); line-height: 1.45; font-size: 13px; }
.product-lane code { white-space: normal; overflow-wrap: anywhere; }

.page-list { list-style: none; padding: 0; margin: 12px 0; }
.page-list li { padding: 6px 0; border-bottom: 1px solid var(--border-soft); }
.page-list li:last-child { border-bottom: none; }
.page-list .type { font-size: 11px; color: var(--subtle); font-family: sans-serif; margin-left: 6px; }
.memory-profile { margin: 18px 0; }
.memory-profile .summary { color: var(--muted); font-family: sans-serif; margin-bottom: 16px; }
.memory-profile .memory-meta { color: var(--subtle); font-size: 12px; font-family: sans-serif; }
.brief-form { display: flex; gap: 8px; flex-wrap: wrap; margin: 14px 0; font-family: sans-serif; }
.brief-form input { flex: 1 1 220px; min-width: 0; padding: 6px 8px; border: 1px solid var(--border);
                    border-radius: 4px; background: var(--surface); color: var(--text); }
.brief-form button { border: 1px solid var(--border); background: var(--button-bg); color: var(--button-text);
                     border-radius: 4px; padding: 6px 10px; cursor: pointer; }
.brief-form button:hover { background: var(--button-hover); }
.proposal-form { display: grid; gap: 10px; margin: 16px 0; font-family: sans-serif; }
.proposal-form textarea,
.proposal-form input { width: 100%; min-width: 0; padding: 8px 9px; border: 1px solid var(--border);
                       border-radius: 4px; background: var(--surface); color: var(--text); font: inherit; }
.proposal-form textarea { min-height: 190px; resize: vertical; line-height: 1.45; }
.proposal-controls { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr) 92px auto; gap: 8px; align-items: end; }
.proposal-form label { display: grid; gap: 4px; color: var(--muted); font-size: 12px; }
.proposal-form button { border: 1px solid var(--border); background: var(--button-bg); color: var(--button-text);
                        border-radius: 4px; padding: 8px 10px; cursor: pointer; font: inherit; }
.proposal-form button:hover { background: var(--button-hover); }
.proposal-source-list { display: grid; gap: 10px; margin: 16px 0; }
.proposal-source-card { border: 1px solid var(--border-soft); border-radius: 6px; padding: 10px;
                        background: var(--surface); min-width: 0; display: grid; gap: 6px; }
.proposal-source-card strong { overflow-wrap: anywhere; }
.proposal-source-card button { justify-self: start; border: 1px solid var(--border); background: var(--button-bg);
                               color: var(--button-text); border-radius: 4px; padding: 6px 9px; cursor: pointer; }
.proposal-source-card button:disabled { color: var(--button-disabled); cursor: default; }
.proposal-status { min-height: 1.4em; color: var(--muted); font-family: sans-serif; }
.proposal-results { display: grid; gap: 12px; margin-top: 14px; }
.proposal-card { border: 1px solid var(--border-soft); border-radius: 6px; padding: 12px; background: var(--surface); min-width: 0; }
.proposal-card h3 { margin-top: 0; font-size: 16px; }
.proposal-checklist { display: grid; gap: 5px; margin: 10px 0; padding: 9px 10px;
                      border: 1px solid var(--border-soft); border-radius: 6px; background: var(--surface-soft);
                      color: var(--muted); font-family: sans-serif; font-size: 13px; line-height: 1.4; }
.proposal-checklist strong { color: var(--text); }
.proposal-warning { color: #8a6d3b; font-family: sans-serif; font-size: 13px; line-height: 1.45; }
.proposal-command { display: block; margin-top: 10px; padding: 8px; background: var(--surface-code);
                    border-radius: 4px; white-space: normal; overflow-wrap: anywhere; }
.proposal-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; font-family: sans-serif; }
.proposal-actions button { border: 1px solid var(--border); background: var(--button-bg); color: var(--button-text);
                           border-radius: 4px; padding: 5px 8px; cursor: pointer; font: inherit; }
.proposal-actions button:hover { background: var(--button-hover); }
.proposal-actions button:disabled { color: var(--button-disabled); cursor: default; }
.memory-issues { margin-top: 6px; }
.memory-issues li { border: none; padding: 0; color: var(--muted); font-size: 13px; }
.memory-issues .severity { font-family: sans-serif; font-size: 11px; text-transform: uppercase; color: #8a6d3b; }
.memory-dashboard { margin: 18px 0; }
.memory-dashboard .section-heading { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
.memory-dashboard .section-heading a { font-size: 13px; font-family: sans-serif; font-weight: normal; }
.memory-next { border-left: 3px solid var(--accent); padding: 10px 12px; margin: 12px 0 16px; background: var(--surface-muted); font-family: sans-serif; min-width: 0; }
.memory-next ul { margin: 8px 0 0; padding-left: 18px; }
.memory-next li { margin: 4px 0; }
.memory-next code { white-space: normal; overflow-wrap: anywhere; }
.memory-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin: 12px 0; }
.memory-card { border: 1px solid var(--border-soft); border-radius: 6px; padding: 12px; min-width: 0; background: var(--surface); }
.memory-card h3 { margin-top: 0; font-size: 16px; }
.memory-card .summary { color: var(--muted); font-family: sans-serif; font-size: 13px; line-height: 1.5; margin: 8px 0; }
.memory-card .memory-meta { color: var(--subtle); font-size: 12px; font-family: sans-serif; }
.memory-actions { margin-top: 10px; display: grid; gap: 6px; }
.memory-actions div { font-size: 12px; font-family: sans-serif; }
.memory-actions code { display: block; margin-top: 2px; white-space: normal; overflow-wrap: anywhere; }
.memory-action-row { display: grid; gap: 4px; }
.memory-action-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.memory-actions button { border: 1px solid var(--border); background: var(--button-bg); color: var(--button-text);
                         border-radius: 4px; padding: 4px 8px; cursor: pointer; font: inherit; }
.memory-actions button:hover { background: var(--button-hover); }
.memory-actions button:disabled { color: var(--button-disabled); cursor: default; }
.memory-action-result { color: var(--muted); min-height: 1em; }
.ingest-path { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin: 14px 0 18px; }
.ingest-step { border: 1px solid var(--border-soft); border-radius: 4px; background: var(--surface); padding: 12px; font-family: sans-serif; min-width: 0; }
.ingest-step .step-num { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; background: var(--accent); color: #fff; font-size: 12px; font-weight: 700; }
.ingest-step h3 { margin: 8px 0 5px; font-size: 15px; }
.ingest-step p { margin: 0 0 8px; color: var(--muted); line-height: 1.4; }
.ingest-step code { white-space: normal; overflow-wrap: anywhere; }
.trust-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 16px 0; }
.trust-grid div { border: 1px solid var(--border-soft); border-radius: 4px; padding: 10px; font-family: sans-serif; background: var(--surface); }
.trust-grid strong { display: block; font-size: 12px; color: var(--subtle); margin-bottom: 4px; }
.prompt-strip { margin: 16px 0; padding: 12px; border: 1px solid var(--border-soft); border-radius: 4px; background: var(--surface-muted); }
.prompt-strip h2 { margin-top: 0; font-size: 17px; }
.prompt-strip p { color: var(--muted); margin-bottom: 10px; }
.prompt-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px; }
.prompt-grid code { display: block; padding: 8px; background: var(--surface-code); border-radius: 4px; white-space: normal; }
.log-entry { white-space: pre-wrap; font-size: 12px; }

mark { background: var(--mark-bg); color: inherit; border-radius: 2px; padding: 0 1px; }

#graph-canvas { width: 100%; height: min(74vh, 860px); min-height: 560px;
                border: 1px solid var(--border); border-radius: 4px; background: var(--surface-graph);
                cursor: grab; display: block; margin: 0; }
#graph-canvas:active { cursor: grabbing; }
#graph-canvas:focus { outline: 2px solid var(--accent-soft); outline-offset: 2px; }
.graph-frame { margin: 12px 0; }
.graph-frame.is-fullscreen { position: fixed; inset: 0; z-index: 200; background: var(--bg); padding: 18px;
                              display: flex; flex-direction: column; overflow: hidden; }
.graph-frame.is-fullscreen .graph-shell { flex: 1; min-height: 0; }
.graph-frame.is-fullscreen #graph-canvas { height: 100%; min-height: 0; }
.graph-frame.is-fullscreen .graph-inspector { max-height: 100%; overflow: auto; }
.graph-shell { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 12px; align-items: stretch; margin: 12px 0; }
.graph-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
                 margin: 12px 0 8px; font: 13px -apple-system, BlinkMacSystemFont, sans-serif; }
.graph-toolbar button { border: 1px solid var(--border); background: var(--button-bg); color: var(--button-text);
                        border-radius: 4px; padding: 5px 9px; cursor: pointer; }
.graph-toolbar button:hover { background: var(--button-hover); }
.graph-toolbar button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }
.graph-control { display: grid; gap: 3px; color: var(--muted); font-size: 11px; }
.graph-control input,
.graph-control select { border: 1px solid var(--border); background: var(--surface); color: var(--text);
                        border-radius: 4px; padding: 5px 8px; font: 13px -apple-system, BlinkMacSystemFont, sans-serif; }
.graph-control input { width: 180px; }
.graph-control select:disabled { color: var(--button-disabled); cursor: not-allowed; opacity: 0.65; }
.graph-status { color: var(--muted); margin-left: auto; }
.graph-inspector { border: 1px solid var(--border-soft); border-radius: 4px; padding: 12px; font: 13px -apple-system, BlinkMacSystemFont, sans-serif; color: var(--muted); background: var(--surface); }
.graph-inspector strong { display: block; color: var(--text-strong); font-size: 15px; margin-bottom: 6px; overflow-wrap: anywhere; }
.graph-inspector p { margin: 0 0 10px; line-height: 1.4; }
.graph-inspector-links { display: grid; gap: 5px; margin: 10px 0; max-height: 180px; overflow: auto; }
.graph-inspector-links a { overflow-wrap: anywhere; }
.graph-inspector button { border: 1px solid var(--border); background: var(--button-bg); color: var(--button-text); border-radius: 4px; padding: 6px 9px; cursor: pointer; }
.graph-inspector button:disabled { color: var(--button-disabled); cursor: default; }
.graph-tooltip { position: fixed; background: var(--surface); border: 1px solid var(--border); border-radius: 4px;
                 padding: 6px 10px; font-size: 13px; pointer-events: none; display: none;
                 box-shadow: 0 2px 8px var(--shadow); z-index: 100; }
.graph-legend { font-size: 12px; color: var(--subtle); font-family: sans-serif; margin-top: 8px; }
.graph-legend span { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
                     margin-right: 4px; vertical-align: middle; }
.graph-empty { border: 1px solid var(--border-soft); border-radius: 4px; padding: 28px; background: var(--surface-empty);
               color: var(--muted); font-family: sans-serif; margin: 12px 0; }

footer { margin-top: 40px; padding-top: 12px; border-top: 1px solid var(--border-soft);
         font-size: 12px; color: var(--faint); font-family: sans-serif; }
@media (max-width: 760px) {
  body { padding: 20px; }
  header .header-top { align-items: flex-start; }
  header nav { gap: 10px 14px; }
  header .header-tools { justify-items: end; }
  header .theme-toggle { justify-self: end; }
  .home-stats { flex-wrap: wrap; gap: 14px 22px; }
  .product-lanes { grid-template-columns: minmax(0, 1fr); }
  .memory-grid { grid-template-columns: minmax(0, 1fr); }
  .proposal-controls { grid-template-columns: minmax(0, 1fr); }
  .memory-dashboard .section-heading { flex-wrap: wrap; }
  .memory-actions code, .memory-next code { word-break: break-word; }
  .graph-shell { grid-template-columns: 1fr; }
  #graph-canvas { min-height: 460px; }
  .graph-frame.is-fullscreen { padding: 12px; }
}
@media (max-width: 560px) {
  header .header-top { flex-wrap: wrap; }
  header .header-tools { flex-basis: 100%; max-width: none; justify-items: stretch; }
  header .theme-toggle { justify-self: end; }
}
"""


THEME_INIT_JS = """
(function() {
  try {
    var theme = localStorage.getItem('link-theme') || 'system';
    if (theme === 'dark' || theme === 'light') {
      document.documentElement.dataset.theme = theme;
    }
  } catch (err) {}
})();
"""


THEME_CONTROL_JS = """
(function() {
  var modes = ['system', 'dark', 'light'];
  var button = document.querySelector('[data-theme-toggle]');
  var media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function systemTheme() {
    return media && media.matches ? 'dark' : 'light';
  }

  function storedTheme() {
    try {
      return localStorage.getItem('link-theme') || 'system';
    } catch (err) {
      return 'system';
    }
  }

  function saveTheme(theme) {
    try {
      localStorage.setItem('link-theme', theme);
    } catch (err) {}
  }

  function applyTheme(theme) {
    if (theme === 'dark' || theme === 'light') {
      document.documentElement.dataset.theme = theme;
    } else {
      delete document.documentElement.dataset.theme;
    }
    if (!button) return;
    var active = theme === 'system' ? systemTheme() : theme;
    var text = button.querySelector('[data-theme-text]');
    if (text) {
      text.textContent = theme;
    } else {
      button.textContent = theme;
    }
    button.title = 'Theme: ' + theme + ' (' + active + ')';
    button.setAttribute('aria-label', 'Theme: ' + theme + ' (' + active + '). Click to switch.');
  }

  applyTheme(storedTheme());

  if (button) {
    button.addEventListener('click', function() {
      var current = storedTheme();
      var next = modes[(modes.indexOf(current) + 1) % modes.length] || 'system';
      saveTheme(next);
      applyTheme(next);
    });
  }

  if (media && media.addEventListener) {
    media.addEventListener('change', function() {
      if (storedTheme() === 'system') applyTheme('system');
    });
  }
})();
"""


MEMORY_ACTION_JS = """
(function() {
  var endpoints = {
    review: '/api/review-memory',
    archive: '/api/archive-memory',
    restore: '/api/restore-memory'
  };
  var buttons = Array.from(document.querySelectorAll('[data-memory-action]'));
  if (!buttons.length) return;

  function resultFor(button) {
    var row = button.closest('.memory-action-row') || button.parentElement;
    var result = row ? row.querySelector('.memory-action-result') : null;
    if (!result && row) {
      result = document.createElement('span');
      result.className = 'memory-action-result';
      row.appendChild(result);
    }
    return result;
  }

  buttons.forEach(function(button) {
    button.addEventListener('click', async function() {
      var action = button.getAttribute('data-memory-action') || '';
      var endpoint = endpoints[action];
      var memory = button.getAttribute('data-memory') || '';
      var result = resultFor(button);
      if (!endpoint || !memory) return;

      var payload = {memory: memory};
      if (action === 'review' && !window.confirm('Mark this memory as reviewed?')) return;
      if (action === 'archive') {
        var reason = window.prompt('Archive reason', 'stale');
        if (reason === null) return;
        payload.reason = reason;
      }
      if (action === 'restore' && !window.confirm('Restore this memory to active recall?')) return;

      button.disabled = true;
      if (result) result.textContent = 'Updating...';
      try {
        var response = await fetch(endpoint, {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-Link-Local-Action': 'true'},
          body: JSON.stringify(payload)
        });
        var data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || 'memory action failed');
        }
        if (result) result.textContent = 'Updated. Refreshing...';
        window.setTimeout(function() { window.location.reload(); }, 450);
      } catch (err) {
        if (result) result.textContent = err.message || 'memory action failed';
        button.disabled = false;
      }
    });
  });
})();
"""


PROPOSAL_UI_JS = """
(function() {
  var form = document.querySelector('[data-proposal-form]');
  if (!form) return;
  var statusEl = document.querySelector('[data-proposal-status]');
  var resultsEl = document.querySelector('[data-proposal-results]');
  var sourceListEl = document.querySelector('[data-proposal-sources]');

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text || '';
  }

  function addText(parent, tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = text || '';
    parent.appendChild(node);
    return node;
  }

  function candidateNames(items) {
    return (items || []).map(function(item) {
      return item.name || item.title || '';
    }).filter(Boolean).join(', ');
  }

  function renderSources(data) {
    if (!sourceListEl) return;
    sourceListEl.textContent = '';
    if (!data || !data.sources || !data.sources.length) {
      addText(sourceListEl, 'p', 'summary', 'No local raw text sources found yet.');
      return;
    }
    data.sources.forEach(function(source) {
      var card = document.createElement('article');
      card.className = 'proposal-source-card';
      addText(card, 'strong', '', source.title || source.path || 'raw source');
      addText(card, 'div', 'memory-meta', [
        source.path || '',
        source.size ? source.size + ' bytes' : '',
        source.warning_count ? source.warning_count + ' warning' + (source.warning_count === 1 ? '' : 's') : ''
      ].filter(Boolean).join(' · '));
      if (source.snippet) addText(card, 'p', 'summary', source.snippet);
      if (source.secret_warnings && source.secret_warnings.length) {
        addText(card, 'p', 'proposal-warning', 'Secret-looking values: ' + source.secret_warnings.join(', '));
      }
      var button = document.createElement('button');
      button.type = 'button';
      button.textContent = source.loadable ? 'Use in form' : (source.warning_count ? 'Redact first' : 'Too large');
      button.disabled = !source.loadable;
      button.setAttribute('data-proposal-source', source.path || '');
      card.appendChild(button);
      sourceListEl.appendChild(card);
    });
  }

  async function loadSource(path) {
    setStatus('Loading ' + path + '...');
    try {
      var response = await fetch('/api/proposal-source?path=' + encodeURIComponent(path));
      var data = await response.json();
      if (!response.ok) throw new Error(data.error || 'source load failed');
      form.elements.text.value = data.text || '';
      form.elements.source.value = data.source || path;
      setStatus('Loaded ' + (data.path || path) + '. Nothing was written.');
    } catch (error) {
      setStatus(error.message || 'source load failed');
    }
  }

  function approvalPrompt(proposal) {
    if (proposal.primary_action && proposal.primary_action.prompt) {
      return proposal.primary_action.prompt;
    }
    var memory = proposal.memory || '';
    if (proposal.suggested_action === 'update-memory' && proposal.duplicate_candidates && proposal.duplicate_candidates.length) {
      var target = proposal.duplicate_candidates[0].name || proposal.duplicate_candidates[0].title || '<memory>';
      return 'Approve by asking: update memory ' + target + ' with "' + memory + '"';
    }
    return 'Approve by asking: remember that ' + memory;
  }

  function addCopyButton(parent, label, text) {
    if (!text) return;
    var button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.addEventListener('click', async function() {
      try {
        await navigator.clipboard.writeText(text);
        button.textContent = 'Copied';
        window.setTimeout(function() { button.textContent = label; }, 1200);
      } catch (error) {
        button.textContent = 'Select text above';
        window.setTimeout(function() { button.textContent = label; }, 1600);
      }
    });
    parent.appendChild(button);
  }

  function firstCandidateName(items) {
    if (!items || !items.length) return '';
    return items[0].name || items[0].title || '';
  }

  function approvalEndpoint(proposal) {
    var action = proposal.primary_action || {};
    if (action.kind === 'remember' && !(proposal.conflict_candidates && proposal.conflict_candidates.length)) {
      return '/api/remember-memory';
    }
    if (action.kind === 'update' && firstCandidateName(proposal.duplicate_candidates)) {
      return '/api/update-memory';
    }
    return '';
  }

  function approvalPayload(proposal) {
    var endpoint = approvalEndpoint(proposal);
    if (endpoint === '/api/update-memory') {
      return {
        memory: firstCandidateName(proposal.duplicate_candidates),
        text: proposal.memory || '',
        source: proposal.source || 'web approval',
        project: proposal.project || ''
      };
    }
    return {
      memory: proposal.memory || '',
      title: proposal.title || '',
      memory_type: proposal.memory_type || 'note',
      scope: proposal.scope || 'user',
      source: proposal.source || 'web approval',
      project: proposal.project || ''
    };
  }

  function addApproveButton(parent, proposal) {
    var endpoint = approvalEndpoint(proposal);
    if (!endpoint) {
      var blocked = document.createElement('button');
      blocked.type = 'button';
      blocked.disabled = true;
      blocked.textContent = 'Manual review required';
      blocked.title = 'Copy the approval prompt and resolve duplicates or conflicts with your agent.';
      parent.appendChild(blocked);
      return;
    }
    var button = document.createElement('button');
    button.type = 'button';
    button.textContent = endpoint === '/api/update-memory' ? 'Approve update' : 'Approve and save';
    button.title = 'Writes durable local memory only after this explicit approval.';
    button.addEventListener('click', async function() {
      var message = endpoint === '/api/update-memory'
        ? 'Update the existing memory with this proposal?'
        : 'Save this proposal as durable local memory?';
      if (!window.confirm(message)) return;
      button.disabled = true;
      button.textContent = 'Saving...';
      try {
        var response = await fetch(endpoint, {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-Link-Local-Action': 'true'},
          body: JSON.stringify(approvalPayload(proposal))
        });
        var data = await response.json();
        if (!response.ok) throw new Error(data.error || data.message || 'memory save failed');
        button.textContent = 'Saved';
        setStatus('Saved ' + (data.title || data.name || 'memory') + '. Review it in the memory inbox.');
      } catch (error) {
        button.disabled = false;
        button.textContent = endpoint === '/api/update-memory' ? 'Approve update' : 'Approve and save';
        setStatus(error.message || 'memory save failed');
      }
    });
    parent.appendChild(button);
  }

  function renderProposals(data) {
    if (!resultsEl) return;
    resultsEl.textContent = '';
    if (!data || data.error) {
      addText(resultsEl, 'p', 'summary', data && data.error ? data.error : 'No response.');
      return;
    }
    if (!data.proposals || !data.proposals.length) {
      addText(resultsEl, 'p', 'summary', 'No durable memory candidates found. Keep this as source-backed wiki knowledge unless there is a clear preference, decision, or project fact.');
      return;
    }
    data.proposals.forEach(function(proposal) {
      var card = document.createElement('article');
      card.className = 'proposal-card';
      addText(card, 'h3', '', proposal.title || 'Memory proposal');
      addText(card, 'div', 'memory-meta', [
        proposal.memory_type || 'note',
        proposal.scope || 'user',
        proposal.confidence || 'unknown confidence',
        proposal.suggested_action || 'remember'
      ].filter(Boolean).join(' · '));
      addText(card, 'p', 'summary', proposal.memory || '');
      if (proposal.reason) addText(card, 'p', 'summary', proposal.reason);
      var duplicates = candidateNames(proposal.duplicate_candidates);
      if (duplicates) addText(card, 'p', 'proposal-warning', 'Possible duplicate: ' + duplicates);
      var conflicts = candidateNames(proposal.conflict_candidates);
      if (conflicts) addText(card, 'p', 'proposal-warning', 'Possible conflict: ' + conflicts);
      var action = proposal.primary_action || {};
      if (action.label) addText(card, 'p', 'summary', action.label + ': ' + (action.description || ''));
      addText(card, 'p', 'proposal-warning', 'Proposal-only: no durable memory has been written yet.');
      var checklist = document.createElement('div');
      checklist.className = 'proposal-checklist';
      addText(checklist, 'strong', '', 'Review gate');
      addText(checklist, 'span', '', 'Save only if this is a durable preference, decision, fact, or project context.');
      addText(checklist, 'span', '', 'Check scope, project, source label, duplicates, and conflicts before approval.');
      addText(checklist, 'span', '', conflicts ? 'Conflict found: use the approval prompt instead of direct save.' : 'Direct save still requires explicit approval.');
      card.appendChild(checklist);
      var promptText = approvalPrompt(proposal);
      var prompt = addText(card, 'code', 'proposal-command', promptText);
      prompt.setAttribute('title', 'Copy this into your agent chat if you approve the memory.');
      if (action.command) {
        var command = addText(card, 'code', 'proposal-command', action.command);
        command.setAttribute('title', 'Equivalent local command.');
      }
      var actions = document.createElement('div');
      actions.className = 'proposal-actions';
      addApproveButton(actions, proposal);
      addCopyButton(actions, 'Copy approval prompt', promptText);
      addCopyButton(actions, 'Copy CLI command', action.command || '');
      card.appendChild(actions);
      resultsEl.appendChild(card);
    });
  }

  form.addEventListener('submit', async function(event) {
    event.preventDefault();
    var text = form.elements.text.value || '';
    if (!text.trim()) {
      setStatus('Paste source or session notes first.');
      return;
    }
    setStatus('Proposing memories...');
    if (resultsEl) resultsEl.textContent = '';
    try {
      var response = await fetch('/api/propose-memories', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          text: text,
          source: form.elements.source.value || 'web proposal',
          project: form.elements.project.value || '',
          limit: form.elements.limit.value || '10'
        })
      });
      var data = await response.json();
      if (!response.ok) throw new Error(data.error || 'proposal failed');
      setStatus(data.count + ' proposal' + (data.count === 1 ? '' : 's') + ' found. Nothing was written.');
      renderProposals(data);
    } catch (error) {
      setStatus(error.message || 'proposal failed');
    }
  });

  if (sourceListEl) {
    sourceListEl.addEventListener('click', function(event) {
      var button = event.target.closest('[data-proposal-source]');
      if (!button || button.disabled) return;
      loadSource(button.getAttribute('data-proposal-source') || '');
    });
    fetch('/api/proposal-sources')
      .then(function(response) { return response.json(); })
      .then(renderSources)
      .catch(function() {
        renderSources({sources: []});
      });
  }
  var initialSource = form.getAttribute('data-initial-source') || '';
  if (initialSource) {
    loadSource(initialSource);
  }
})();
"""


def _header_html():
    return f"""<header>
  <div class="header-top">
    <div class="logo"><a href="/"><img src="/logo.svg" alt="">Link</a><small>agent memory</small></div>
    <div class="header-tools">
      <button type="button" class="theme-toggle" data-theme-toggle>
        <span class="theme-icon" aria-hidden="true"></span><span class="theme-text" data-theme-text>system</span>
      </button>
      <form action="/search" method="get">
        <input type="text" name="q" placeholder="search... (/)" autocomplete="off" id="search-input">
      </form>
    </div>
  </div>
  <nav>
    <a href="/">home</a>
    <a href="/prompts">prompts</a>
    <a href="/ingest">ingest</a>
    <a href="/brief">brief</a>
    <a href="/propose">propose</a>
    <a href="/memory">memory</a>
    <a href="/audit">audit</a>
    <a href="/inbox">inbox</a>
    <a href="/captures">captures</a>
    <a href="/profile">profile</a>
    <a href="/page/log">log</a>
    <a href="/all">all pages</a>
    <a href="/graph">graph</a>
  </nav>
</header>"""


def _footer_html():
    return '<footer>Link — local agent memory · <a href="https://github.com/gowtham0992/link">github</a></footer>'


def _layout(title, body, page_class: str = ""):
    body_class = f' class="{html.escape(page_class, quote=True)}"' if page_class else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)} — Link</title>
<link rel="icon" href="/logo.svg" type="image/svg+xml">
<script>{THEME_INIT_JS}</script>
<style>{CSS}</style>
</head>
<body{body_class}>
{_header_html()}
<div class="graph-tooltip" id="graph-tooltip"></div>
{body}
{_footer_html()}
<script>
// Keyboard navigation
document.addEventListener('keydown', function(e) {{
  var tag = document.activeElement.tagName;
  var inInput = tag === 'INPUT' || tag === 'TEXTAREA';
  // / → focus search
  if (e.key === '/' && !inInput) {{
    e.preventDefault();
    var inp = document.getElementById('search-input');
    if (inp) {{ inp.focus(); inp.select(); }}
  }}
  // Escape → blur search
  if (e.key === 'Escape' && inInput) {{
    document.activeElement.blur();
  }}
  if (e.key === 'Enter' && document.activeElement.id === 'search-input') {{
    var q = document.activeElement.value.trim();
    if (q) {{
      e.preventDefault();
      window.location.href = '/search?q=' + encodeURIComponent(q);
    }}
  }}
  // j/k → navigate focusable links in page-list
  if ((e.key === 'j' || e.key === 'k') && !inInput) {{
    var links = Array.from(document.querySelectorAll('.page-list a, .search-results a'));
    if (!links.length) return;
    var cur = document.activeElement;
    var idx = links.indexOf(cur);
    if (e.key === 'j') idx = idx < links.length - 1 ? idx + 1 : 0;
    else idx = idx > 0 ? idx - 1 : links.length - 1;
    links[idx].focus();
    e.preventDefault();
  }}
}});
</script>
<script>{THEME_CONTROL_JS}</script>
<script>{MEMORY_ACTION_JS}</script>
<script>{PROPOSAL_UI_JS}</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def _render_home():
    pages = _get_all_pages()
    counts = {}
    for p in pages:
        t = p["type"] or "other"
        counts[t] = counts.get(t, 0) + 1

    stats_items = f'<div class="stat"><span class="num">{len(pages)}</span><span class="label">pages</span></div>'
    for t in ["memory", "source", "concept", "entity", "comparison", "exploration"]:
        if counts.get(t, 0) > 0:
            label = _plural_type_label(t)
            stats_items += f'<div class="stat"><span class="num">{counts[t]}</span><span class="label">{label}</span></div>'
    stats = f'<div class="home-stats">{stats_items}</div>'

    cats = {}
    for p in pages:
        if p["category"] == "root": continue
        cats.setdefault(p["category"], []).append(p)

    sections = ""
    for cat in sorted(cats.keys()):
        items = "".join(
            f'<li><a href="{_page_href(p["name"])}">{html.escape(p["title"])}</a>'
            f'<span class="type">{p["type"]}</span></li>'
            for p in sorted(cats[cat], key=lambda x: x["title"])
        )
        sections += f'<h2>{html.escape(cat)}</h2><ul class="page-list">{items}</ul>'

    if not cats:
        sections = "<p>Wiki is empty. Drop sources into <code>raw/</code> and tell your agent to ingest them.</p>"

    lanes = (
        '<div class="product-lanes" aria-label="How Link stores context">'
        '<section class="product-lane"><h2>1. Sources become wiki knowledge</h2>'
        '<p>Drop files into <code>raw/</code> and say <code>ingest raw/file.md into Link</code>. '
        'Link creates source-backed pages, concepts, backlinks, index entries, and logs.</p></section>'
        '<section class="product-lane"><h2>2. Remember saves agent memory</h2>'
        '<p>Say <code>remember that ...</code> when a preference, decision, or project fact should affect future agents. '
        'Ingest alone does not silently personalize recall.</p></section>'
        '<section class="product-lane"><h2>3. Query uses both safely</h2>'
        '<p>Ask <code>query Link for ...</code> or open a memory brief. Link combines reviewed memory, wiki pages, and graph context.</p></section>'
        '</div>'
    )
    prompt_codes = ""
    for item in _starter_prompts_payload().get("prompts", []):
        if isinstance(item, dict):
            prompt_codes += f'<code>{html.escape(str(item.get("prompt") or ""))}</code>'
    prompts = (
        '<section class="prompt-strip" aria-label="First Link prompts">'
        '<h2>Try These Prompts</h2>'
        '<p>Ask from Codex, Claude, Cursor, Kiro, or any agent with Link installed. <a href="/prompts">Open starter prompts</a>.</p>'
        '<div class="prompt-grid">'
        f'{prompt_codes}</div></section>'
    )

    return _layout("Link", f"<h1>Link</h1><p>Local agent memory. Knowledge compounds here.</p>{lanes}{prompts}{stats}{sections}")


def _starter_prompts_payload(project: str | None = None) -> dict[str, object]:
    return _core_starter_prompt_payload(WIKI_DIR, project=project)


def _render_prompts(project: str | None = None):
    payload = _starter_prompts_payload(project=project)
    prompt_rows = ""
    for item in payload.get("prompts", []):
        if not isinstance(item, dict):
            continue
        prompt_rows += (
            f'<article class="proposal-card">'
            f'<h3>{html.escape(str(item.get("label") or "Prompt"))}</h3>'
            f'<code class="proposal-command">{html.escape(str(item.get("prompt") or ""))}</code>'
            f'<p class="summary">{html.escape(str(item.get("when") or ""))}</p>'
            f'</article>'
        )
    command_rows = "".join(
        f'<li><code>{html.escape(str(command))}</code></li>'
        for command in payload.get("commands", [])
    )
    project_line = (
        f'<p class="summary">Project examples are scoped to <code>{html.escape(str(payload["project"]))}</code>.</p>'
        if payload.get("project")
        else '<p class="summary">These prompts work for a personal Link wiki. Add <code>?project=slug</code> for project wording.</p>'
    )
    body = (
        f'<div class="breadcrumb"><a href="/">Link</a> / prompts</div>'
        f'<h1>Starter Prompts</h1>'
        f'{project_line}'
        f'<section><h2>Ask Your Agent</h2><div class="proposal-results">{prompt_rows}</div></section>'
        f'<section><h2>Local Checks</h2><ul class="page-list">{command_rows}</ul></section>'
    )
    return _layout("Starter Prompts", body)


def _render_page(page_path):
    text = page_path.read_text(encoding="utf-8", errors="replace")
    meta, body = _parse_frontmatter(text)
    body_html = _md_to_html(body)

    title = meta.get("title", "")
    if not title:
        m = re.search(r"^#\s+(.+)", body, re.MULTILINE)
        title = m.group(1) if m else page_path.stem

    rel = page_path.relative_to(WIKI_DIR)
    cat = rel.parts[0] if len(rel.parts) > 1 else ""
    crumb = f'<div class="breadcrumb"><a href="/">Link</a>'
    if cat:
        crumb += f' / {html.escape(cat)}'
    crumb += f' / {html.escape(title)}</div>'

    parts = []
    if meta.get("type"): parts.append(f'<span class="badge">{html.escape(str(meta["type"]))}</span>')
    if meta.get("maturity"): parts.append(html.escape(str(meta["maturity"])))
    if meta.get("source_count"): parts.append(f'{meta["source_count"]} sources')
    if meta.get("date_updated"): parts.append(f'updated {meta["date_updated"]}')
    aliases = meta.get("aliases", [])
    if isinstance(aliases, list) and aliases:
        parts.append("also: " + ", ".join(html.escape(a) for a in aliases))
    elif isinstance(aliases, str) and aliases:
        parts.append(f"also: {html.escape(aliases)}")
    meta_line = f'<div class="meta">{" · ".join(parts)}</div>' if parts else ""

    return _layout(title, crumb + meta_line + body_html)


def _render_all():
    pages = _get_all_pages()
    items = "".join(
        f'<li><a href="{_page_href(p["name"])}">{html.escape(p["title"])}</a>'
        f'<span class="type">{p["type"] or p["category"]}</span></li>'
        for p in sorted(pages, key=lambda x: x["title"])
    )
    return _layout("All Pages", f'<div class="breadcrumb"><a href="/">Link</a> / all pages</div>'
                   f"<h1>All Pages ({len(pages)})</h1><ul class='page-list'>{items}</ul>")


def _render_memory_card(record: dict[str, object], include_issues: bool = False) -> str:
    name = str(record.get("name") or "")
    title = str(record.get("title") or name)
    summary = str(record.get("tldr") or record.get("snippet") or "")
    meta_parts = [
        str(record.get("memory_type") or "note"),
        str(record.get("scope") or "user"),
        str(record.get("status") or "active"),
    ]
    if record.get("updated_at"):
        meta_parts.append(f'updated {record["updated_at"]}')
    elif record.get("date_captured"):
        meta_parts.append(f'captured {record["date_captured"]}')
    meta = " · ".join(part for part in meta_parts if part)
    issues_html = ""
    if include_issues and record.get("issues"):
        issues_html = "<ul class='memory-issues'>" + "".join(
            f'<li><span class="severity">{html.escape(str(issue["severity"]))}</span> '
            f'{html.escape(str(issue["code"]))}: {html.escape(str(issue["message"]))}</li>'
            for issue in record["issues"]
        ) + "</ul>"
    actions = _render_memory_action_commands(record.get("actions") or _memory_action_hints(record))
    summary_html = f'<p class="summary">{html.escape(summary)}</p>' if summary else ""
    return (
        '<article class="memory-card">'
        f'<h3><a href="{_page_href(name)}">{html.escape(title)}</a></h3>'
        f'<div class="memory-meta">{html.escape(meta)}</div>'
        f'{summary_html}'
        f'{issues_html}'
        f'{actions}'
        '</article>'
    )


def _render_memory_action_commands(actions: list[dict[str, object]] | tuple[dict[str, object], ...]) -> str:
    if not actions:
        return ""
    rows = ""
    for action in actions:
        label = html.escape(str(action.get("label") or ""))
        if action.get("href"):
            label_html = f'<a href="{html.escape(str(action["href"]))}">{label}</a>'
        else:
            label_html = label
        priority = str(action.get("priority") or "")
        priority_html = f'<span class="memory-meta">{html.escape(priority)}</span>' if priority else ""
        button_html = _render_memory_action_button(action)
        rows += (
            f'<div class="memory-action-row"><span class="memory-action-head"><strong>{label_html}</strong>'
            f'{priority_html}{button_html}</span>'
            f'<code>{html.escape(str(action.get("command") or ""))}</code></div>'
        )
    return f'<div class="memory-actions">{rows}</div>'


def _render_memory_action_button(action: dict[str, object]) -> str:
    kind = str(action.get("kind") or "")
    if kind not in {"review", "archive", "restore"}:
        return ""
    arguments = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
    identifier = str(arguments.get("identifier") or "")
    if not identifier:
        return ""
    labels = {
        "review": "Mark reviewed",
        "archive": "Archive",
        "restore": "Restore",
    }
    return (
        f'<button type="button" data-memory-action="{html.escape(kind, quote=True)}" '
        f'data-memory="{html.escape(identifier, quote=True)}">'
        f'{html.escape(labels[kind])}</button>'
    )


def _render_memory_section(title: str, records: list[dict[str, object]], empty: str, href: str = "", include_issues: bool = False) -> str:
    heading_link = f'<a href="{html.escape(href)}">view all</a>' if href else ""
    heading = f'<div class="section-heading"><h2>{html.escape(title)}</h2>{heading_link}</div>'
    if not records:
        return heading + f"<p>{html.escape(empty)}</p>"
    cards = "".join(_render_memory_card(record, include_issues=include_issues) for record in records)
    return heading + f'<div class="memory-grid">{cards}</div>'


def _render_capture_card(capture: dict[str, object]) -> str:
    title = html.escape(str(capture.get("title") or capture.get("path") or "Raw capture"))
    path = html.escape(str(capture.get("path") or ""))
    meta_parts = ["raw capture"]
    if capture.get("project"):
        meta_parts.append(f'project {capture["project"]}')
    if capture.get("date_captured"):
        meta_parts.append(f'captured {capture["date_captured"]}')
    warnings = [str(label) for label in capture.get("secret_warnings") or []]
    if warnings:
        meta_parts.append("secret warnings")
    meta = " · ".join(meta_parts)
    warning_html = ""
    if warnings:
        warning_html = (
            '<p class="summary"><strong>Secret-looking values:</strong> '
            + html.escape(", ".join(warnings))
            + "</p>"
        )
    commands = capture.get("commands") or {}
    actions = "".join(
        f'<div><strong>{html.escape(label)}</strong><code>{html.escape(str(command))}</code></div>'
        for label, command in (
            ("Accept proposal", commands.get("accept", "")),
            ("Redact", commands.get("redact", "")),
            ("Delete", commands.get("delete", "")),
        )
        if command
    )
    return (
        '<article class="memory-card">'
        f'<h3>{title}</h3>'
        f'<div class="memory-meta">{html.escape(meta)}</div>'
        f'<p class="summary"><code>{path}</code></p>'
        f'{warning_html}'
        f'<div class="memory-actions">{actions}</div>'
        '</article>'
    )


def _render_capture_section(captures: list[dict[str, object]]) -> str:
    heading = '<div class="section-heading"><h2>Raw captures</h2></div>'
    if not captures:
        return heading + "<p>No saved raw captures.</p>"
    cards = "".join(_render_capture_card(capture) for capture in captures)
    return heading + f'<div class="memory-grid">{cards}</div>'


def _render_memory_next_actions(actions: list[dict[str, str]]) -> str:
    items = ""
    for action in actions:
        label = html.escape(action["label"])
        if action.get("href"):
            label_html = f'<a href="{html.escape(action["href"])}">{label}</a>'
        else:
            label_html = label
        items += (
            f'<li><strong>{label_html}</strong>: {html.escape(action["detail"])}'
            f'<br><code>{html.escape(action["command"])}</code></li>'
        )
    return f'<div class="memory-next"><strong>Next actions</strong><ul>{items}</ul></div>'


def _render_brief(query: str = "", project: str | None = None):
    brief = _memory_brief(query=query, limit=8, project=project)
    profile = brief["profile"]
    captures = brief["captures"]
    stats = (
        f'<div class="home-stats">'
        f'<div class="stat"><span class="num">{profile["active_count"]}</span><span class="label">active</span></div>'
        f'<div class="stat"><span class="num">{brief["relevant_count"]}</span><span class="label">relevant</span></div>'
        f'<div class="stat"><span class="num">{brief["review"]["count"]}</span><span class="label">review</span></div>'
        f'<div class="stat"><span class="num">{captures["count"]}</span><span class="label">captures</span></div>'
        f'</div>'
    )
    guidance = "".join(
        f"<li>{html.escape(str(item))}</li>"
        for item in brief["agent_guidance"]
    )
    query_value = html.escape(str(query), quote=True)
    project_field = (
        f'<input type="hidden" name="project" value="{html.escape(str(brief["project"]), quote=True)}">'
        if brief["project"] else ""
    )
    body = (
        f'<div class="breadcrumb"><a href="/">Link</a> / brief</div>'
        f'<h1>Memory Brief</h1>'
        f'<div class="memory-profile">'
        f'<p class="summary">Startup context for local agents before answering, coding, or planning.</p>'
        f'<form class="brief-form" action="/brief" method="get">'
        f'<input type="text" name="q" value="{query_value}" placeholder="task or question">'
        f'{project_field}<button type="submit">Brief</button></form>'
        f'{"<p><strong>Project:</strong> " + html.escape(str(brief["project"])) + "</p>" if brief["project"] else ""}'
        f'{stats}'
        f'<h2>Agent Guidance</h2><ul>{guidance}</ul>'
        f'{_render_memory_section("Relevant memories", brief["relevant_memories"], "No relevant memories yet.")}'
        f'{_render_memory_section("Review queue", brief["review"]["items"], "No memory review items.", href="/inbox", include_issues=True)}'
        f'{_render_capture_section(captures["items"])}'
        f'</div>'
    )
    return _layout("Memory Brief", body)


def _render_memory_dashboard(project: str | None = None):
    dashboard = _memory_dashboard(limit=8, project=project)
    stats = (
        f'<div class="home-stats">'
        f'<div class="stat"><span class="num">{dashboard["memory_count"]}</span><span class="label">memories</span></div>'
        f'<div class="stat"><span class="num">{dashboard["active_count"]}</span><span class="label">active</span></div>'
        f'<div class="stat"><span class="num">{dashboard["review_count"]}</span><span class="label">review</span></div>'
        f'<div class="stat"><span class="num">{dashboard["updated_count"]}</span><span class="label">updated</span></div>'
        f'<div class="stat"><span class="num">{dashboard["capture_count"]}</span><span class="label">captures</span></div>'
        f'<div class="stat"><span class="num">{dashboard["archived_count"]}</span><span class="label">archived</span></div>'
        f'</div>'
    )
    counts = ""
    if dashboard["by_type"]:
        counts += "<p><strong>Types:</strong> " + ", ".join(
            f"{html.escape(name)}: {count}" for name, count in dashboard["by_type"].items()
        ) + "</p>"
    if dashboard["by_scope"]:
        counts += "<p><strong>Scopes:</strong> " + ", ".join(
            f"{html.escape(name)}: {count}" for name, count in dashboard["by_scope"].items()
        ) + "</p>"
    body = (
        f'<div class="breadcrumb"><a href="/">Link</a> / memory</div>'
        f'<h1>Memory Dashboard</h1>'
        f'<div class="memory-dashboard">'
        f'<p class="summary">Read-only command center for what local agents can remember, what needs review, and what changed recently.</p>'
        f'{"<p><strong>Project:</strong> " + html.escape(str(dashboard["project"])) + "</p>" if dashboard["project"] else ""}'
        f'{stats}'
        f'{_render_memory_next_actions(dashboard["next_actions"])}'
        f'{counts}'
        f'{_render_memory_section("Review needed", dashboard["review"], "No memories need review.", href="/inbox", include_issues=True)}'
        f'{_render_capture_section(dashboard["captures"])}'
        f'{_render_memory_section("Recent updates", dashboard["recent_updates"], "No memory updates yet.")}'
        f'{_render_memory_section("Active memories", dashboard["active"], "No active memories yet.", href="/profile")}'
        f'{_render_memory_section("Archived memories", dashboard["archived"], "No archived memories.")}'
        f'</div>'
    )
    return _layout("Memory Dashboard", body)


def _render_profile(project: str | None = None):
    profile = _memory_profile(limit=12, project=project)
    memory_count = profile["memory_count"]
    active_count = profile["active_count"]
    stats = (
        f'<div class="home-stats">'
        f'<div class="stat"><span class="num">{memory_count}</span><span class="label">memories</span></div>'
        f'<div class="stat"><span class="num">{active_count}</span><span class="label">active</span></div>'
        f'<div class="stat"><span class="num">{profile["review_count"]}</span><span class="label">review</span></div>'
        f'</div>'
    )

    def counts_line(title: str, counts: dict[str, int]) -> str:
        if not counts:
            return ""
        parts = ", ".join(f"{html.escape(name)}: {count}" for name, count in counts.items())
        return f"<p><strong>{html.escape(title)}:</strong> {parts}</p>"

    def section(title: str, records: list[dict[str, object]], empty: str = "none") -> str:
        if not records:
            return f"<h2>{html.escape(title)}</h2><p>{html.escape(empty)}</p>"
        items = ""
        for record in records:
            summary = record.get("tldr") or record.get("snippet") or ""
            meta = f'{record.get("memory_type", "")} · {record.get("scope", "")}'
            items += (
                f'<li><a href="{_page_href(str(record["name"]))}">{html.escape(str(record["title"]))}</a>'
                f'<div class="memory-meta">{html.escape(meta)}</div>'
                f'<div class="memory-meta"><a href="/explain-memory?memory={urllib.parse.quote(str(record["name"]), safe="")}">explain</a></div>'
                f'{f"<small>{html.escape(str(summary))}</small>" if summary else ""}</li>'
            )
        return f"<h2>{html.escape(title)}</h2><ul class='page-list'>{items}</ul>"

    body = (
        f'<div class="breadcrumb"><a href="/">Link</a> / profile</div>'
        f'<h1>Memory Profile</h1>'
        f'<div class="memory-profile">'
        f'<p class="summary">What Link currently remembers about the user, projects, decisions, and preferences.</p>'
        f'{"<p><strong>Project:</strong> " + html.escape(str(profile["project"])) + "</p>" if profile["project"] else ""}'
        f'{stats}'
        f'{counts_line("Types", profile["by_type"])}'
        f'{counts_line("Scopes", profile["by_scope"])}'
        f'{counts_line("Status", profile["by_status"])}'
        f'{section("Recent memories", profile["recent"])}'
        f'{section("Preferences", profile["preferences"])}'
        f'{section("Decisions", profile["decisions"])}'
        f'{section("Project context", profile["projects"])}'
        f'{section("Archived memories", profile["archived"]) if profile["archived"] else ""}'
        f'</div>'
    )
    return _layout("Memory Profile", body)


def _render_memory_audit(project: str | None = None):
    audit = _memory_audit(limit=10, project=project)
    profile = audit["profile"]
    captures = audit["captures"]
    stats = (
        f'<div class="home-stats">'
        f'<div class="stat"><span class="num">{profile["memory_count"]}</span><span class="label">memories</span></div>'
        f'<div class="stat"><span class="num">{profile["active_count"]}</span><span class="label">active</span></div>'
        f'<div class="stat"><span class="num">{profile["review_count"]}</span><span class="label">review</span></div>'
        f'<div class="stat"><span class="num">{captures["count"]}</span><span class="label">captures</span></div>'
        f'<div class="stat"><span class="num">{captures["warning_count"]}</span><span class="label">warnings</span></div>'
        f'</div>'
    )
    risk_html = ""
    if audit["risk_factors"]:
        risk_html = "<h2>Needs attention</h2><ul class='memory-issues'>" + "".join(
            f'<li><span class="severity">review</span> {html.escape(str(item["code"]))}: '
            f'{html.escape(str(item["message"]))}</li>'
            for item in audit["risk_factors"]
        ) + "</ul>"
    else:
        risk_html = "<h2>Needs attention</h2><p>No memory audit risks detected.</p>"
    body = (
        f'<div class="breadcrumb"><a href="/">Link</a> / audit</div>'
        f'<h1>Memory Audit</h1>'
        f'<div class="memory-profile">'
        f'<p class="summary">Read-only health report for local agent memory, review backlog, raw captures, and safe next actions.</p>'
        f'{"<p><strong>Project:</strong> " + html.escape(str(audit["project"])) + "</p>" if audit["project"] else ""}'
        f'<p><strong>Status:</strong> {html.escape(str(audit["status"]))}</p>'
        f'{stats}'
        f'{risk_html}'
        f'{_render_memory_next_actions(audit["next_actions"])}'
        f'{_render_memory_section("Memory inbox sample", audit["inbox"]["items"], "No memory review items.", href="/inbox", include_issues=True)}'
        f'{_render_capture_section(captures["items"])}'
        f'</div>'
    )
    return _layout("Memory Audit", body)


def _render_captures(project: str | None = None):
    inbox = _capture_inbox(limit=50, project=project)
    stats = (
        f'<div class="home-stats">'
        f'<div class="stat"><span class="num">{inbox["count"]}</span><span class="label">captures</span></div>'
        f'<div class="stat"><span class="num">{inbox["warning_count"]}</span><span class="label">warnings</span></div>'
        f'</div>'
    )
    warning_html = ""
    if inbox["warning_count"]:
        warning_html = (
            f'<div class="memory-next"><strong>Needs redaction</strong>'
            f'<p>{inbox["warning_count"]} raw capture'
            f'{"s contain" if inbox["warning_count"] != 1 else " contains"} secret-looking values.</p>'
            f'<code>python3 link.py redact-capture raw/memory-captures/&lt;capture&gt;.md .</code></div>'
        )
    body = (
        f'<div class="breadcrumb"><a href="/">Link</a> / captures</div>'
        f'<h1>Raw Capture Inbox</h1>'
        f'<div class="memory-profile">'
        f'<p class="summary">Saved proposal-only session notes waiting for human review before they become durable memory.</p>'
        f'{"<p><strong>Project:</strong> " + html.escape(str(inbox["project"])) + "</p>" if inbox["project"] else ""}'
        f'{stats}'
        f'{warning_html}'
        f'{_render_capture_section(inbox["captures"])}'
        f'</div>'
    )
    return _layout("Raw Capture Inbox", body)


def _render_propose(project: str | None = None, source: str | None = None):
    project_value = html.escape(str(project or ""), quote=True)
    source_value = html.escape(str(source or ""), quote=True)
    proposal_path = (
        f'<section class="ingest-path" aria-label="Memory proposal path">'
        f'<article class="ingest-step"><span class="step-num">1</span>'
        f'<h3>Load source</h3><p>Paste notes or load a safe local raw file. The source stays local.</p>'
        f'<code>raw/file.md</code></article>'
        f'<article class="ingest-step"><span class="step-num">2</span>'
        f'<h3>Propose</h3><p>Link returns candidates only. This step never writes durable memory.</p>'
        f'<code>Propose</code></article>'
        f'<article class="ingest-step"><span class="step-num">3</span>'
        f'<h3>Approve explicitly</h3><p>Copy the approval prompt into your agent chat only for memories you want kept.</p>'
        f'<code>remember that ...</code></article>'
        f'<article class="ingest-step"><span class="step-num">4</span>'
        f'<h3>Review later</h3><p>Use the inbox and explain views to review, archive, update, or forget memories.</p>'
        f'<code>link memory-inbox</code></article>'
        f'</section>'
    )
    body = (
        f'<div class="breadcrumb"><a href="/">Link</a> / propose</div>'
        f'<h1>Propose Memories</h1>'
        f'<p class="summary">Paste source notes, session notes, or a raw excerpt. Link returns memory candidates without writing anything.</p>'
        f'<div class="memory-next"><strong>Trust rule</strong>'
        f'<p>Source-backed wiki knowledge and durable agent memory are separate. Save only preferences, decisions, or project facts you approve.</p></div>'
        f'<section><h2>Review Gate</h2><div class="proposal-checklist">'
        f'<strong>Before saving memory</strong>'
        f'<span>Keep ordinary facts in wiki pages; save only durable preferences, decisions, project context, or user facts.</span>'
        f'<span>Check source label, scope, project, duplicate candidates, and conflict warnings.</span>'
        f'<span>Use direct approval only when the proposal is clean; otherwise copy the approval prompt into your agent chat.</span>'
        f'</div></section>'
        f'{proposal_path}'
        f'<section><div class="section-heading"><h2>Local Raw Sources</h2><a href="/captures">captures</a></div>'
        f'<div class="proposal-source-list" data-proposal-sources aria-live="polite"></div></section>'
        f'<form class="proposal-form" data-proposal-form data-initial-source="{source_value}">'
        f'<label>Source or session notes'
        f'<textarea name="text" placeholder="Paste notes here. Example: I prefer short release notes. We decided to keep Link local-first."></textarea>'
        f'</label>'
        f'<div class="proposal-controls">'
        f'<label>Source label<input name="source" value="web proposal" autocomplete="off"></label>'
        f'<label>Project<input name="project" value="{project_value}" placeholder="optional" autocomplete="off"></label>'
        f'<label>Limit<input name="limit" type="number" min="1" max="20" value="10"></label>'
        f'<button type="submit">Propose</button>'
        f'</div>'
        f'<div class="proposal-status" data-proposal-status aria-live="polite"></div>'
        f'</form>'
        f'<section class="proposal-results" data-proposal-results aria-live="polite"></section>'
    )
    return _layout("Propose Memories", body)


def _render_ingest():
    status = _ingest_status()
    guidance = status.get("guidance") if isinstance(status.get("guidance"), dict) else {}
    agent_prompt = str(guidance.get("agent_prompt") or "")
    commands = guidance.get("commands") if isinstance(guidance.get("commands"), list) else []
    notes = guidance.get("notes") if isinstance(guidance.get("notes"), list) else []
    plan = status.get("plan") if isinstance(status.get("plan"), dict) else {}
    pending = status.get("pending_raw") if isinstance(status.get("pending_raw"), list) else []
    represented = status.get("represented_raw") if isinstance(status.get("represented_raw"), list) else []
    first_raw = str(pending[0].get("raw") or "raw/<file>") if pending else "raw/<file>"
    ingest_prompt = agent_prompt or f"ingest {first_raw} into Link"
    memory_prompt = str(plan.get("memory_prompt") or f"propose memories from {first_raw}")
    propose_href = "/propose?source=" + urllib.parse.quote(first_raw) if pending else "/propose"
    state = str(guidance.get("state") or plan.get("state") or "unknown")

    stats = (
        f'<div class="home-stats">'
        f'<div class="stat"><span class="num">{int(status.get("raw_count") or 0)}</span><span class="label">raw</span></div>'
        f'<div class="stat"><span class="num">{int(status.get("represented_count") or 0)}</span><span class="label">represented</span></div>'
        f'<div class="stat"><span class="num">{int(status.get("pending_count") or 0)}</span><span class="label">pending</span></div>'
        f'<div class="stat"><span class="num">{html.escape(str(status.get("backlinks_status") or "unknown"))}</span><span class="label">graph</span></div>'
        f'</div>'
    )
    action_rows = ""
    if agent_prompt:
        action_rows += (
            f'<div class="memory-action-row"><span class="memory-action-head"><strong>Ask your agent</strong></span>'
            f'<code>{html.escape(agent_prompt)}</code></div>'
        )
    for command in commands:
        action_rows += (
            f'<div class="memory-action-row"><span class="memory-action-head"><strong>Run</strong></span>'
            f'<code>{html.escape(str(command))}</code></div>'
        )
    actions = f'<div class="memory-actions">{action_rows}</div>' if action_rows else ""
    if agent_prompt:
        next_detail = "Copy this into your agent chat. The agent should ingest the raw source, rebuild indexes, and validate before reporting done."
        next_code = agent_prompt
        next_extra = (
            f'<p>If the source contains preferences, decisions, or project facts, '
            f'<a href="{html.escape(propose_href, quote=True)}">open memory proposals first</a>.</p>'
        )
    elif state == "blocked_secrets":
        next_detail = "Redact secret-looking values in the flagged raw source before asking any agent to ingest it."
        next_code = f"edit {first_raw}"
        next_extra = ""
    elif state == "stale_graph":
        next_detail = "Repair the graph index before relying on search, context, or the graph view."
        next_code = "link rebuild-backlinks && link validate"
        next_extra = ""
    elif state == "empty":
        next_detail = "Add a note, article, transcript, or project file to raw/, then refresh this page."
        next_code = "cp notes.md raw/ && link ingest-status"
        next_extra = ""
    elif state == "ready":
        next_detail = "No ingest is pending. Ask Link for context, or add another source when there is new material."
        next_code = 'link brief "current task"'
        next_extra = ""
    else:
        next_detail = "Initialize or repair the Link folder before ingesting sources."
        next_code = "link init && link status --validate"
        next_extra = ""
    if state == "blocked_secrets":
        ingest_prompt = f"redact secret-looking values in {first_raw} before ingest"
        optional_memory_html = '<code>redact before memory proposals</code>'
    else:
        optional_memory_html = (
            f'<a href="{html.escape(propose_href, quote=True)}"><code>{html.escape(memory_prompt)}</code></a>'
        )
    next_html = (
        f'<div class="memory-next"><strong>Next step</strong>'
        f'<p>{html.escape(next_detail)}</p>'
        f'<code>{html.escape(next_code)}</code>'
        f'{next_extra}</div>'
    )
    guide_html = (
        f'<section class="ingest-path" aria-label="Ingest path">'
        f'<article class="ingest-step"><span class="step-num">1</span>'
        f'<h3>Add source</h3><p>Put notes, articles, transcripts, or project files in <code>raw/</code>.</p>'
        f'<code>{html.escape(first_raw)}</code></article>'
        f'<article class="ingest-step"><span class="step-num">2</span>'
        f'<h3>Ask agent</h3><p>Have your agent convert the source into source-backed wiki pages.</p>'
        f'<code>{html.escape(ingest_prompt)}</code></article>'
        f'<article class="ingest-step"><span class="step-num">3</span>'
        f'<h3>Validate</h3><p>Check page shape, links, and graph freshness before relying on the result.</p>'
        f'<code>link validate</code></article>'
        f'<article class="ingest-step"><span class="step-num">4</span>'
        f'<h3>Optional memory</h3><p>Only save preferences, decisions, or project facts after approval.</p>'
        f'{optional_memory_html}</article>'
        f'</section>'
    )

    pending_html = ""
    if pending:
        rows = ""
        for item in pending[:50]:
            raw_path = str(item.get("raw") or "")
            propose_href = "/propose?source=" + urllib.parse.quote(raw_path)
            secret_warnings = item.get("secret_warnings") if isinstance(item.get("secret_warnings"), list) else []
            if secret_warnings:
                meta = (
                    f'{int(item.get("size_bytes") or 0)} bytes · secret warning: '
                    f'{", ".join(html.escape(str(label)) for label in secret_warnings)} · redact before ingest'
                )
            else:
                meta = (
                    f'{int(item.get("size_bytes") or 0)} bytes · '
                    f'<a href="{html.escape(propose_href, quote=True)}">propose memories</a>'
                )
            rows += f'<li><code>{html.escape(raw_path)}</code><span class="type">{meta}</span></li>'
        if len(pending) > 50:
            rows += f'<li>... {len(pending) - 50} more</li>'
        pending_html = f'<div class="section-heading"><h2>Pending Raw Files</h2><a href="/propose">propose memories</a></div><ul class="page-list">{rows}</ul>'
    elif represented:
        rows = "".join(
            f'<li><code>{html.escape(str(item.get("raw") or ""))}</code>'
            f'<span class="type">{", ".join(html.escape(str(page)) for page in item.get("source_pages", []) or [])}</span></li>'
            for item in represented[:20]
        )
        pending_html = f'<div class="section-heading"><h2>Represented Raw Files</h2><a href="/all">all pages</a></div><ul class="page-list">{rows}</ul>'
    else:
        pending_html = '<p>No raw source files found yet.</p>'

    notes_html = ""
    if notes:
        notes_html = "<ul>" + "".join(f"<li>{html.escape(str(note))}</li>" for note in notes) + "</ul>"

    plan_html = ""
    if plan:
        steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
        batch = plan.get("batch") if isinstance(plan.get("batch"), list) else []
        post_checks = plan.get("post_checks") if isinstance(plan.get("post_checks"), list) else []
        step_html = "".join(f"<li>{html.escape(str(step))}</li>" for step in steps[:6])
        batch_html = ""
        if batch:
            rows = ""
            for item in batch[:5]:
                rows += (
                    f'<li><code>{html.escape(str(item.get("raw") or ""))}</code>'
                    f'<span class="type">{html.escape(str(item.get("suggested_source_page") or ""))}</span></li>'
                )
            batch_html = f'<h3>Batch</h3><ul class="page-list">{rows}</ul>'
        checks_html = ""
        if post_checks:
            rows = "".join(
                f'<li><code>{html.escape(str(check))}</code>'
                f'<span class="type">run before reporting done</span></li>'
                for check in post_checks[:6]
            )
            checks_html = f'<h3>Post-ingest checks</h3><ul class="page-list">{rows}</ul>'
        plan_html = (
            f'<section><h2>{html.escape(str(plan.get("title") or "Suggested Workflow"))}</h2>'
            f'<p class="summary">{html.escape(str(plan.get("summary") or ""))}</p>'
            f'<ol>{step_html}</ol>{batch_html}{checks_html}</section>'
        )

    body = (
        f'<div class="breadcrumb"><a href="/">Link</a> / ingest</div>'
        f'<h1>Ingest</h1>'
        f'<p class="summary">{html.escape(str(guidance.get("summary") or "Check raw source ingest state."))}</p>'
        f'{stats}'
        f'{next_html}'
        f'{guide_html}'
        f'{actions}'
        f'{plan_html}'
        f'{pending_html}'
        f'{notes_html}'
    )
    return _layout("Ingest", body)


def _render_inbox(project: str | None = None):
    inbox = _memory_inbox(limit=50, project=project)
    review_count = inbox["review_count"]
    stats = (
        f'<div class="home-stats">'
        f'<div class="stat"><span class="num">{review_count}</span><span class="label">review</span></div>'
        f'</div>'
    )
    if inbox["counts_by_severity"]:
        severity = ", ".join(
            f"{html.escape(name)}: {count}"
            for name, count in inbox["counts_by_severity"].items()
        )
        severity_html = f"<p><strong>Severity:</strong> {severity}</p>"
    else:
        severity_html = ""

    if not inbox["items"]:
        content = "<p>Inbox is clear.</p>"
    else:
        items = ""
        for item in inbox["items"]:
            summary = item.get("tldr") or item.get("snippet") or ""
            meta = f'{item.get("memory_type", "")} · {item.get("scope", "")} · {item.get("status", "")}'
            issues = "".join(
                f'<li><span class="severity">{html.escape(str(issue["severity"]))}</span> '
                f'{html.escape(str(issue["code"]))}: {html.escape(str(issue["message"]))}</li>'
                for issue in item["issues"]
            )
            primary = item.get("primary_action") or {}
            primary_html = ""
            if primary:
                primary_html = (
                    f'<p class="summary"><strong>Next:</strong> {html.escape(str(primary.get("label") or ""))} '
                    f'- {html.escape(str(primary.get("description") or ""))}</p>'
                )
            actions_html = _render_memory_action_commands(item.get("actions") or [])
            items += (
                f'<li><a href="{_page_href(str(item["name"]))}">{html.escape(str(item["title"]))}</a>'
                f'<div class="memory-meta">{html.escape(meta)}</div>'
                f'<div class="memory-meta"><a href="/explain-memory?memory={urllib.parse.quote(str(item["name"]), safe="")}">explain</a></div>'
                f'{f"<small>{html.escape(str(summary))}</small>" if summary else ""}'
                f'<ul class="memory-issues">{issues}</ul>'
                f'{primary_html}'
                f'{actions_html}</li>'
            )
        content = f"<ul class='page-list'>{items}</ul>"

    body = (
        f'<div class="breadcrumb"><a href="/">Link</a> / inbox</div>'
        f'<h1>Memory Review Inbox</h1>'
        f'<div class="memory-profile">'
        f'<p class="summary">Memories that need confirmation, stronger metadata, or cleanup.</p>'
        f'{"<p><strong>Project:</strong> " + html.escape(str(inbox["project"])) + "</p>" if inbox["project"] else ""}'
        f'{stats}'
        f'{severity_html}'
        f'{content}'
        f'</div>'
    )
    return _layout("Memory Review Inbox", body)


def _render_explain_memory(identifier: str):
    try:
        explanation = _memory_explanation(identifier)
    except ValueError as exc:
        return _layout("Memory Explanation", f'<h1>Memory not found</h1><p>{html.escape(str(exc))}</p>')

    memory = explanation["memory"]
    recall_info = explanation["recall"]
    review = explanation["review"]
    provenance = explanation["provenance"]
    lifecycle = explanation["lifecycle"]
    graph = explanation["graph"]
    summary = memory.get("tldr") or memory.get("snippet") or ""
    issues = "".join(
        f'<li><span class="severity">{html.escape(str(issue["severity"]))}</span> '
        f'{html.escape(str(issue["code"]))}: {html.escape(str(issue["message"]))}</li>'
        for issue in review["issues"]
    )
    issue_html = (
        f'<h2>Review Issues</h2><ul class="memory-issues">{issues}</ul>'
        if issues else "<h2>Review Issues</h2><p>No detected issues.</p>"
    )
    primary = review.get("primary_action") or {}
    primary_html = ""
    if primary:
        primary_html = (
            f'<p class="summary"><strong>Next:</strong> {html.escape(str(primary.get("label") or ""))} '
            f'- {html.escape(str(primary.get("description") or ""))}</p>'
        )
    action_html = f'<h2>Actions</h2>{primary_html}{_render_memory_action_commands(review.get("actions") or [])}'
    graph_html = (
        f'<h2>Graph</h2>'
        f'<p><strong>Forward:</strong> {html.escape(", ".join(graph["forward"]) or "none")}</p>'
        f'<p><strong>Inbound:</strong> {html.escape(", ".join(graph["inbound"]) or "none")}</p>'
        f'<p><strong>Wikilinks:</strong> {html.escape(", ".join(graph["wikilinks"]) or "none")}</p>'
    )
    logs = "".join(
        f'<pre class="log-entry">{html.escape(entry)}</pre>'
        for entry in explanation["log_entries"][-5:]
    )
    log_html = f"<h2>Log Entries</h2>{logs}" if logs else "<h2>Log Entries</h2><p>No matching log entries.</p>"
    body_html = _md_to_html(str(explanation.get("body") or ""))
    body = (
        f'<div class="breadcrumb"><a href="/">Link</a> / explain memory</div>'
        f'<h1>{html.escape(str(memory["title"]))}</h1>'
        f'<p class="summary">{html.escape(str(summary))}</p>'
        f'<div class="trust-grid">'
        f'<div><strong>Recall</strong>{html.escape(str(recall_info["state"]))}<br><small>{html.escape(str(recall_info["reason"]))}</small></div>'
        f'<div><strong>Review</strong>{html.escape(str(review["status"]))} · {review["issue_count"]} issues</div>'
        f'<div><strong>Status</strong>{html.escape(str(lifecycle["status"]))}</div>'
        f'<div><strong>Source</strong>{html.escape(str(provenance["source"] or "missing"))}</div>'
        f'<div><strong>Captured</strong>{html.escape(str(provenance["date_captured"] or "missing"))}</div>'
        f'<div><strong>Path</strong>{html.escape(str(provenance["path"]))}</div>'
        f'</div>'
        f'{issue_html}'
        f'{action_html}'
        f'{graph_html}'
        f'{log_html}'
        f'<h2>Memory Body</h2>{body_html}'
    )
    return _layout(f"Explain: {memory['title']}", body)


def _render_graph():
    graph = _get_graph_data()
    visible_nodes = [n for n in graph["nodes"] if n["category"] != "root"]
    visible_ids = {n["id"] for n in visible_nodes}
    visible_edges = [
        e for e in graph["edges"]
        if e["source"] in visible_ids and e["target"] in visible_ids
    ]
    nodes_json = _json_for_script(visible_nodes)
    edges_json = _json_for_script(visible_edges)
    node_count = len(visible_nodes)
    edge_count = len(visible_edges)

    if node_count == 0:
        body = (
            f'<div class="breadcrumb"><a href="/">Link</a> / graph</div>'
            f'<h1>Knowledge Graph</h1>'
            f'<div class="graph-empty">'
            f'<strong>No graph pages yet.</strong><br>'
            f'Add sources to <code>raw/</code>, ingest them, then rebuild backlinks.'
            f'</div>'
        )
        return _layout("Knowledge Graph", body)

    # Category → color mapping
    cat_colors = {"concepts": "#4e79a7", "entities": "#f28e2b", "memories": "#edc948",
                  "sources": "#59a14f", "comparisons": "#e15759",
                  "explorations": "#76b7b2", "root": "#bab0ac"}
    categories = sorted({str(n["category"]) for n in visible_nodes if n["category"] != "root"})
    category_options = '<option value="all">all types</option>' + "".join(
        f'<option value="{html.escape(category, quote=True)}">{html.escape(category)}</option>'
        for category in categories
    )

    graph_js = f"""
<script>
(function() {{
  var nodes = {nodes_json};
  var edges = {edges_json};
  var catColors = {_json_for_script(cat_colors)};

  var canvas = document.getElementById('graph-canvas');
  var ctx = canvas.getContext('2d');
  var tooltip = document.getElementById('graph-tooltip');
  var resetButton = document.getElementById('graph-reset');
  var labelsButton = document.getElementById('graph-labels');
  var motionButton = document.getElementById('graph-motion');
  var fullscreenButton = document.getElementById('graph-fullscreen');
  var searchInput = document.getElementById('graph-search');
  var categoryFilter = document.getElementById('graph-category');
  var depthFilter = document.getElementById('graph-depth');
  var frameEl = document.getElementById('graph-frame');
  var status = document.getElementById('graph-status');
  var inspector = document.getElementById('graph-inspector');
  var inspectorTitle = document.getElementById('graph-inspector-title');
  var inspectorMeta = document.getElementById('graph-inspector-meta');
  var inspectorLinks = document.getElementById('graph-inspector-links');
  var inspectorOpen = document.getElementById('graph-open');
  var inspectorFocus = document.getElementById('graph-focus');
  var W, H;

  // Compact neural-map sizing: concepts lead, sources recede.
  var NODE_R = 6;
  var LABEL_FONT = '11px -apple-system, sans-serif';
  var LARGE_GRAPH_LIMIT = 350;
  var nodeById = {{}};
  nodes.forEach(function(n) {{ nodeById[n.id] = n; }});

  function stableNoise(id, salt) {{
    var h = salt * 2166136261;
    for (var i = 0; i < id.length; i++) {{
      h ^= id.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }}
    return ((h >>> 0) % 1000) / 1000;
  }}

  // Start in a loose two-lobe silhouette. Physics keeps it organic after load.
  var pos = {{}}, vel = {{}}, pinned = {{}};
  nodes.forEach(function(n, i) {{
    var lobe = i % 2 === 0 ? -1 : 1;
    var a = i * 2.399963 + stableNoise(n.id, 7) * 0.7;
    var r = 50 + Math.sqrt((i + 1) / Math.max(nodes.length, 1)) * 155;
    var categoryDrop = n.category === 'sources' ? 58 : (n.category === 'memories' ? -34 : (n.category === 'entities' ? 24 : -6));
    pos[n.id] = {{
      x: lobe * 78 + Math.cos(a) * r * 0.78,
      y: Math.sin(a) * r * 0.58 + categoryDrop
    }};
    vel[n.id] = {{ x: 0, y: 0 }};
  }});

  // Adjacency
  var adj = {{}}, degree = {{}};
  nodes.forEach(function(n) {{ adj[n.id] = []; degree[n.id] = 0; }});
  edges.forEach(function(e) {{
    if (adj[e.source]) {{ adj[e.source].push(e.target); degree[e.source]++; }}
    if (adj[e.target]) {{ adj[e.target].push(e.source); degree[e.target]++; }}
  }});

  var dragging = null, dragOffX = 0, dragOffY = 0, hoverNode = null, selectedNode = null;
  var panX = 0, panY = 0, panStartX = 0, panStartY = 0, panning = false, didPan = false;
  var downX = 0, downY = 0, didDrag = false, suppressClick = false;
  var zoom = 1;
  var frame = 0;
  var showAllLabels = false;
  var motionPaused = (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) || nodes.length > LARGE_GRAPH_LIMIT;
  var SETTLE = 200; // frames of physics
  var searchTerm = '';
  var categoryValue = 'all';
  var depthValue = 'all';
  var visibleCache = null;
  var renderQueued = false;
  var animationRunning = false;

  function resize() {{
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = W * devicePixelRatio; canvas.height = H * devicePixelRatio;
    ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  }}

  function nodeColor(n) {{ return catColors[n.category] || '#8b949e'; }}
  function pageHref(id) {{ return '/page/' + encodeURIComponent(id); }}
  function invalidateFilters() {{ visibleCache = null; }}
  function nodeSearchText(n) {{
    return (n.title + ' ' + n.id + ' ' + n.category).toLowerCase();
  }}
  function searchMatches(n) {{
    return searchTerm && nodeSearchText(n).indexOf(searchTerm) !== -1;
  }}
  function depthMap() {{
    if (!selectedNode || depthValue === 'all') return null;
    var maxDepth = parseInt(depthValue, 10);
    if (!Number.isFinite(maxDepth)) return null;
    var seen = {{}};
    var queue = [selectedNode.id];
    seen[selectedNode.id] = 0;
    while (queue.length) {{
      var current = queue.shift();
      var nextDepth = seen[current] + 1;
      if (nextDepth > maxDepth) continue;
      (adj[current] || []).forEach(function(next) {{
        if (seen[next] === undefined) {{
          seen[next] = nextDepth;
          queue.push(next);
        }}
      }});
    }}
    return seen;
  }}
  function visibleIds() {{
    if (visibleCache) return visibleCache;
    var byDepth = depthMap();
    var ids = {{}};
    nodes.forEach(function(n) {{
      var categoryOk = categoryValue === 'all' || n.category === categoryValue;
      var depthOk = !byDepth || byDepth[n.id] !== undefined;
      var keepSelected = selectedNode && selectedNode.id === n.id;
      ids[n.id] = (categoryOk || keepSelected) && depthOk;
    }});
    visibleCache = ids;
    return ids;
  }}
  function visibleNodes() {{
    var ids = visibleIds();
    return nodes.filter(function(n) {{ return ids[n.id]; }});
  }}
  function visibleEdges() {{
    var ids = visibleIds();
    return edges.filter(function(e) {{ return ids[e.source] && ids[e.target]; }});
  }}
  function graphTooLargeForMotion() {{
    return visibleNodes().length > LARGE_GRAPH_LIMIT;
  }}
  function nodeRadius(n) {{
    if (n.category === 'sources') return 4.5;
    if (n.category === 'memories') return 6.4;
    if (n.category === 'entities') return 6.8;
    return NODE_R;
  }}
  function isNeighbor(a, b) {{
    return (adj[a] || []).indexOf(b) !== -1;
  }}
  function isActiveNode(n) {{
    return !hoverNode || n.id === hoverNode.id || isNeighbor(hoverNode.id, n.id);
  }}
  function pinnedCount() {{
    var count = 0;
    Object.keys(pinned).forEach(function(id) {{ if (pinned[id]) count++; }});
    return count;
  }}
  function updateStatus() {{
    if (!status) return;
    syncDepthControl();
    var currentNodes = visibleNodes();
    var currentEdges = visibleEdges();
    var parts = [
      currentNodes.length + '/' + nodes.length + ' nodes',
      currentEdges.length + '/' + edges.length + ' edges',
      Math.round(zoom * 100) + '%'
    ];
    if (categoryValue !== 'all') parts.push(categoryValue);
    if (depthValue !== 'all') parts.push('depth ' + depthValue);
    if (graphTooLargeForMotion()) parts.push('motion capped');
    if (searchTerm) {{
      var matches = currentNodes.filter(searchMatches).length;
      parts.push(matches + ' match' + (matches === 1 ? '' : 'es'));
    }}
    var locked = pinnedCount();
    if (locked) parts.push(locked + ' placed');
    if (selectedNode) parts.push('selected ' + selectedNode.id);
    status.textContent = parts.join(' · ');
  }}

  function syncDepthControl() {{
    if (!depthFilter) return;
    if (!selectedNode && depthValue !== 'all') {{
      depthValue = 'all';
      depthFilter.value = 'all';
      invalidateFilters();
    }}
    depthFilter.disabled = !selectedNode;
    depthFilter.title = selectedNode ? 'Limit graph to the selected node neighborhood.' : 'Select a node before filtering by neighborhood.';
  }}

  function updateInspector() {{
    if (!inspector || !inspectorTitle || !inspectorMeta || !inspectorLinks || !inspectorOpen || !inspectorFocus) return;
    inspectorLinks.textContent = '';
    if (!selectedNode) {{
      inspectorTitle.textContent = 'Select a node';
      inspectorMeta.textContent = 'Click a node to inspect it. Drag a node to place it. Double-click a node, or use Open page, to navigate.';
      inspectorOpen.disabled = true;
      inspectorFocus.disabled = true;
      return;
    }}
    var neighbors = (adj[selectedNode.id] || []).slice().sort(function(a, b) {{
      return (nodeById[a] ? nodeById[a].title : a).localeCompare(nodeById[b] ? nodeById[b].title : b);
    }});
    inspectorTitle.textContent = selectedNode.title;
    inspectorMeta.textContent = selectedNode.category + ' · ' + neighbors.length + ' linked page' + (neighbors.length === 1 ? '' : 's');
    inspectorOpen.disabled = false;
    inspectorFocus.disabled = false;
    neighbors.slice(0, 10).forEach(function(id) {{
      var target = nodeById[id];
      var link = document.createElement('a');
      link.href = pageHref(id);
      link.textContent = target ? target.title : id;
      inspectorLinks.appendChild(link);
    }});
    if (neighbors.length > 10) {{
      var more = document.createElement('span');
      more.textContent = '+' + (neighbors.length - 10) + ' more';
      inspectorLinks.appendChild(more);
    }}
  }}

  function selectNode(node) {{
    selectedNode = node;
    hoverNode = node;
    invalidateFilters();
    syncDepthControl();
    updateInspector();
    updateStatus();
    drawSoon();
  }}

  function openNode(node) {{
    if (node) window.location.href = pageHref(node.id);
  }}

  function toScreen(x, y) {{
    return {{ x: (x + panX) * zoom + W/2, y: (y + panY) * zoom + H/2 }};
  }}
  function toWorld(sx, sy) {{
    return {{ x: (sx - W/2) / zoom - panX, y: (sy - H/2) / zoom - panY }};
  }}

  function simulate() {{
    var simNodes = visibleNodes();
    if (simNodes.length > LARGE_GRAPH_LIMIT) return;
    var simIds = visibleIds();
    // Tuned for a brain-like neural map: broad lobes, readable spacing, gentle drift.
    var springLen = 135, springK = 0.032, repel = 13500, gravity = 0.005, damp = 0.84;
    simNodes.forEach(function(n) {{
      if (pinned[n.id]) return;
      var fx = 0, fy = 0;
      var p = pos[n.id];
      // Repulsion between all pairs
      simNodes.forEach(function(m) {{
        if (m.id === n.id) return;
        var q = pos[m.id];
        var dx = p.x - q.x, dy = p.y - q.y;
        var d2 = Math.max(dx*dx + dy*dy, 100);
        var f = repel / d2;
        fx += f * dx / Math.sqrt(d2);
        fy += f * dy / Math.sqrt(d2);
      }});
      // Spring attraction along edges (toward natural length)
      (adj[n.id] || []).forEach(function(mid) {{
        if (!simIds[mid]) return;
        var q = pos[mid];
        var dx = q.x - p.x, dy = q.y - p.y;
        var d = Math.sqrt(dx*dx + dy*dy) + 0.01;
        var f = springK * (d - springLen);
        fx += f * dx / d; fy += f * dy / d;
      }});
      // Weak center gravity plus a two-lobe bias so the map feels organic.
      fx -= p.x * gravity; fy -= p.y * gravity;
      var lobeX = p.x < 0 ? -95 : 95;
      fx += (lobeX - p.x) * 0.0018;
      fy += ((n.category === 'sources' ? 40 : -8) - p.y) * 0.0012;
      vel[n.id].x = (vel[n.id].x + fx * 0.016) * damp;
      vel[n.id].y = (vel[n.id].y + fy * 0.016) * damp;
      pos[n.id].x += vel[n.id].x;
      pos[n.id].y += vel[n.id].y;
    }});
  }}

  // Auto-fit: after physics settles, zoom/pan so all nodes are visible and centered
  function autoFit() {{
    var currentNodes = visibleNodes();
    if (currentNodes.length === 0) return;
    var minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    currentNodes.forEach(function(n) {{
      minX = Math.min(minX, pos[n.id].x); maxX = Math.max(maxX, pos[n.id].x);
      minY = Math.min(minY, pos[n.id].y); maxY = Math.max(maxY, pos[n.id].y);
    }});
    var pad = 60;
    var gw = maxX - minX + pad*2, gh = maxY - minY + pad*2;
    zoom = Math.min(W / gw, H / gh, 2);
    panX = -(minX + maxX) / 2;
    panY = -(minY + maxY) / 2;
    updateStatus();
  }}

  var fitted = false;

  function draw() {{
    ctx.clearRect(0, 0, W, H);
    var time = frame * 0.018;
    var currentNodes = visibleNodes();
    var currentEdges = visibleEdges();
    var animateFlow = !motionPaused && !graphTooLargeForMotion();

    // Edges — double draw: blurred glow + sharp line + flow particle
    currentEdges.forEach(function(e) {{
      var a = toScreen(pos[e.source].x, pos[e.source].y);
      var b = toScreen(pos[e.target].x, pos[e.target].y);
      var activeEdge = !hoverNode || e.source === hoverNode.id || e.target === hoverNode.id;
      var alpha = hoverNode ? (activeEdge ? 0.42 : 0.035) : 0.14;

      // Glow layer
      ctx.save();
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = 'rgba(88,166,255,' + (alpha * 0.55) + ')';
      ctx.lineWidth = 3;
      ctx.filter = 'blur(2px)';
      ctx.stroke();
      ctx.restore();

      // Sharp line
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = 'rgba(139,148,158,' + alpha + ')';
      ctx.lineWidth = 0.8;
      ctx.stroke();

      // Flow particle
      if (activeEdge && animateFlow) {{
        var flowT = ((time * 0.5 + (a.x + b.y) * 0.001) % 2) / 2;
        var px = a.x + (b.x - a.x) * flowT;
        var py = a.y + (b.y - a.y) * flowT;
        var pa = Math.sin(flowT * Math.PI) * (hoverNode ? 0.6 : 0.32);
        ctx.beginPath(); ctx.arc(px, py, 1.5, 0, Math.PI*2);
        ctx.fillStyle = 'rgba(45,212,191,' + pa + ')';
        ctx.fill();
      }}
    }});

    // Nodes
    currentNodes.forEach(function(n) {{
      var s = toScreen(pos[n.id].x, pos[n.id].y);
      var r = nodeRadius(n) * Math.max(0.65, Math.min(1.2, zoom));
      var color = nodeColor(n);
      var pulse = Math.sin(time * 1.2 + (pos[n.id].x + pos[n.id].y) * 0.01) * 0.12 + 0.88;
      var activeNode = isActiveNode(n);
      var selected = selectedNode && selectedNode.id === n.id;
      var matched = searchMatches(n);
      ctx.save();
      ctx.globalAlpha = (hoverNode && !activeNode) || (searchTerm && !matched) ? 0.28 : 1;

      // Radial glow
      var glowR = r * 3.5 * pulse;
      var grad = ctx.createRadialGradient(s.x, s.y, r * 0.3, s.x, s.y, glowR);
      grad.addColorStop(0, color + '30');
      grad.addColorStop(1, color + '00');
      ctx.beginPath(); ctx.arc(s.x, s.y, glowR, 0, Math.PI*2);
      ctx.fillStyle = grad; ctx.fill();

      // Node body
      ctx.beginPath(); ctx.arc(s.x, s.y, r, 0, Math.PI*2);
      ctx.fillStyle = color + '40'; ctx.fill();

      // Node border
      ctx.beginPath(); ctx.arc(s.x, s.y, r, 0, Math.PI*2);
      ctx.strokeStyle = selected || matched ? '#ffffff' : color; ctx.lineWidth = selected || matched ? 2.4 : 1.5;
      ctx.globalAlpha = 0.85; ctx.stroke(); ctx.globalAlpha = 1;

      // Inner bright core
      ctx.beginPath(); ctx.arc(s.x, s.y, r * 0.35, 0, Math.PI*2);
      ctx.fillStyle = color + 'cc'; ctx.fill();

      // Labels stay sparse until a node is hovered.
      var label = n.title.length > 22 ? n.title.slice(0, 20) + '…' : n.title;
      var showLabel = showAllLabels || matched || (hoverNode ? activeNode : (n.category !== 'sources' && degree[n.id] >= 2));
      if (showLabel) {{
        ctx.font = LABEL_FONT;
        ctx.textAlign = 'center'; ctx.textBaseline = 'top';
        ctx.shadowColor = 'rgba(0,0,0,0.9)'; ctx.shadowBlur = 4;
        ctx.fillStyle = '#dce7f2';
        var labelWidth = ctx.measureText(label).width;
        var labelX = Math.max(labelWidth / 2 + 4, Math.min(W - labelWidth / 2 - 4, s.x));
        ctx.fillText(label, labelX, s.y + r + 5);
        ctx.shadowBlur = 0;
      }}
      ctx.restore();
    }});
  }}

  function shouldRunContinuously() {{
    return !motionPaused && !graphTooLargeForMotion();
  }}

  function drawSoon() {{
    if (renderQueued) return;
    renderQueued = true;
    requestAnimationFrame(function() {{
      renderQueued = false;
      draw();
    }});
  }}

  function startLoop() {{
    if (animationRunning) return;
    animationRunning = true;
    requestAnimationFrame(loop);
  }}

  function loop() {{
    if (!shouldRunContinuously()) {{
      animationRunning = false;
      drawSoon();
      return;
    }}
    if (frame < SETTLE) {{
      simulate();
      // Auto-fit once physics has mostly settled
      if (frame === SETTLE - 1) {{ autoFit(); fitted = true; }}
    }}
    frame++;
    draw();
    requestAnimationFrame(loop);
  }}

  function hitTest(sx, sy) {{
    var w = toWorld(sx, sy);
    var currentNodes = visibleNodes();
    for (var i = currentNodes.length - 1; i >= 0; i--) {{
      var n = currentNodes[i];
      var p = pos[n.id];
      var r = nodeRadius(n) + 6; // slightly larger hit area
      var dx = w.x - p.x, dy = w.y - p.y;
      if (dx*dx + dy*dy <= r*r) return n;
    }}
    return null;
  }}

  function movedPastThreshold(sx, sy) {{
    var dx = sx - downX, dy = sy - downY;
    return dx * dx + dy * dy > 9;
  }}

  function resetView() {{
    pinned = {{}};
    selectedNode = null;
    hoverNode = null;
    searchTerm = '';
    categoryValue = 'all';
    depthValue = 'all';
    if (searchInput) searchInput.value = '';
    if (categoryFilter) categoryFilter.value = 'all';
    if (depthFilter) depthFilter.value = 'all';
    invalidateFilters();
    frame = SETTLE;
    autoFit();
    updateInspector();
    updateStatus();
    drawSoon();
  }}

  function setMotionPaused(next) {{
    motionPaused = next || graphTooLargeForMotion();
    if (motionButton) {{
      motionButton.setAttribute('aria-pressed', motionPaused ? 'true' : 'false');
      motionButton.textContent = graphTooLargeForMotion() ? 'Motion capped' : (motionPaused ? 'Motion paused' : 'Motion on');
    }}
    updateStatus();
    if (shouldRunContinuously()) startLoop();
    else drawSoon();
  }}

  function setFullscreen(next) {{
    if (!frameEl || !fullscreenButton) return;
    frameEl.classList.toggle('is-fullscreen', next);
    fullscreenButton.setAttribute('aria-pressed', next ? 'true' : 'false');
    fullscreenButton.textContent = next ? 'Exit fullscreen' : 'Fullscreen';
    window.setTimeout(function() {{
      resize();
      autoFit();
      updateStatus();
      drawSoon();
    }}, 0);
  }}

  canvas.addEventListener('mousedown', function(e) {{
    var rect = canvas.getBoundingClientRect();
    var sx = e.clientX - rect.left, sy = e.clientY - rect.top;
    downX = sx; downY = sy; didDrag = false; didPan = false; suppressClick = false;
    var hit = hitTest(sx, sy);
    if (hit) {{
      dragging = hit; pinned[hit.id] = true;
      canvas.style.cursor = 'grabbing';
      var w = toWorld(sx, sy);
      dragOffX = pos[hit.id].x - w.x; dragOffY = pos[hit.id].y - w.y;
    }} else {{
      panning = true; didPan = false;
      canvas.style.cursor = 'grabbing';
      panStartX = sx - panX * zoom; panStartY = sy - panY * zoom;
    }}
  }});

  canvas.addEventListener('mousemove', function(e) {{
    var rect = canvas.getBoundingClientRect();
    var sx = e.clientX - rect.left, sy = e.clientY - rect.top;
    if (dragging) {{
      if (movedPastThreshold(sx, sy)) didDrag = true;
      var w = toWorld(sx, sy);
      pos[dragging.id].x = w.x + dragOffX; pos[dragging.id].y = w.y + dragOffY;
      updateStatus();
      drawSoon();
    }} else if (panning) {{
      panX = (sx - panStartX) / zoom; panY = (sy - panStartY) / zoom;
      if (movedPastThreshold(sx, sy)) didPan = true;
      updateStatus();
      drawSoon();
    }} else {{
      var hit = hitTest(sx, sy);
      hoverNode = hit;
      if (hit) {{
        tooltip.style.display = 'block';
        tooltip.style.left = (e.clientX + 14) + 'px';
        tooltip.style.top = (e.clientY - 10) + 'px';
        tooltip.textContent = hit.title + ' · ' + hit.category;
        canvas.style.cursor = 'pointer';
      }} else {{
        tooltip.style.display = 'none';
        canvas.style.cursor = 'grab';
      }}
      drawSoon();
    }}
  }});

  canvas.addEventListener('mouseup', function() {{
    if (dragging) {{
      pinned[dragging.id] = didDrag;
      dragging = null;
      suppressClick = didDrag;
      updateStatus();
      drawSoon();
    }}
    if (panning) {{ suppressClick = didPan; }}
    panning = false;
    canvas.style.cursor = hoverNode ? 'pointer' : 'grab';
  }});

  canvas.addEventListener('mouseleave', function() {{
    hoverNode = null;
    if (tooltip) tooltip.style.display = 'none';
    drawSoon();
  }});

  canvas.addEventListener('click', function(e) {{
    if (suppressClick) {{ suppressClick = false; return; }}
    var rect = canvas.getBoundingClientRect();
    var hit = hitTest(e.clientX - rect.left, e.clientY - rect.top);
    if (hit) selectNode(hit);
  }});

  canvas.addEventListener('dblclick', function(e) {{
    e.preventDefault();
    var rect = canvas.getBoundingClientRect();
    var hit = hitTest(e.clientX - rect.left, e.clientY - rect.top);
    if (hit) openNode(hit);
  }});

  canvas.addEventListener('wheel', function(e) {{
    e.preventDefault();
    var rect = canvas.getBoundingClientRect();
    var sx = e.clientX - rect.left, sy = e.clientY - rect.top;
    var before = toWorld(sx, sy);
    var factor = e.deltaY < 0 ? 1.12 : 0.9;
    zoom = Math.max(0.15, Math.min(6, zoom * factor));
    var after = toWorld(sx, sy);
    panX += after.x - before.x;
    panY += after.y - before.y;
    updateStatus();
    drawSoon();
  }}, {{ passive: false }});

  canvas.addEventListener('keydown', function(e) {{
    if (e.key === '+' || e.key === '=') {{ zoom = Math.min(6, zoom * 1.12); updateStatus(); drawSoon(); e.preventDefault(); }}
    if (e.key === '-' || e.key === '_') {{ zoom = Math.max(0.15, zoom * 0.9); updateStatus(); drawSoon(); e.preventDefault(); }}
    if (e.key === '0') {{ resetView(); e.preventDefault(); }}
    if (e.key === 'Enter' && hoverNode) {{ openNode(hoverNode); e.preventDefault(); }}
    if (e.key === 'Escape') {{
      if (frameEl && frameEl.classList.contains('is-fullscreen')) {{
        setFullscreen(false);
      }} else {{
        selectedNode = null; invalidateFilters(); updateInspector(); updateStatus(); drawSoon();
      }}
      e.preventDefault();
    }}
    if (e.key === 'l' || e.key === 'L') {{
      showAllLabels = !showAllLabels;
      if (labelsButton) labelsButton.setAttribute('aria-pressed', showAllLabels ? 'true' : 'false');
      drawSoon();
      e.preventDefault();
    }}
  }});

  if (resetButton) resetButton.addEventListener('click', resetView);
  if (labelsButton) labelsButton.addEventListener('click', function() {{
    showAllLabels = !showAllLabels;
    labelsButton.setAttribute('aria-pressed', showAllLabels ? 'true' : 'false');
    drawSoon();
  }});
  if (motionButton) motionButton.addEventListener('click', function() {{
    setMotionPaused(!motionPaused);
  }});
  if (fullscreenButton) fullscreenButton.addEventListener('click', function() {{
    setFullscreen(!frameEl.classList.contains('is-fullscreen'));
  }});
  if (inspectorOpen) inspectorOpen.addEventListener('click', function() {{ openNode(selectedNode); }});
  if (inspectorFocus) inspectorFocus.addEventListener('click', function() {{
    if (!selectedNode) return;
    depthValue = '1';
    if (depthFilter) depthFilter.value = '1';
    invalidateFilters();
    setMotionPaused(motionPaused);
    autoFit();
    updateStatus();
    drawSoon();
  }});
  if (searchInput) {{
    searchInput.addEventListener('input', function() {{
      searchTerm = searchInput.value.trim().toLowerCase();
      updateStatus();
      drawSoon();
    }});
    searchInput.addEventListener('keydown', function(e) {{
      if (e.key !== 'Enter') return;
      var match = visibleNodes().find(searchMatches);
      if (match) selectNode(match);
      e.preventDefault();
    }});
  }}
  if (categoryFilter) categoryFilter.addEventListener('change', function() {{
    categoryValue = categoryFilter.value || 'all';
    invalidateFilters();
    setMotionPaused(motionPaused);
    autoFit();
    updateStatus();
    drawSoon();
  }});
  if (depthFilter) depthFilter.addEventListener('change', function() {{
    depthValue = depthFilter.value || 'all';
    invalidateFilters();
    setMotionPaused(motionPaused);
    autoFit();
    updateStatus();
    drawSoon();
  }});

  window.addEventListener('resize', function() {{ resize(); if (fitted) autoFit(); updateStatus(); drawSoon(); }});
  resize();
  if (motionPaused) {{ autoFit(); fitted = true; frame = SETTLE; }}
  setMotionPaused(motionPaused);
  updateInspector();
  updateStatus();
  if (shouldRunContinuously()) startLoop();
  else drawSoon();
}})();
</script>"""

    legend_items = "".join(
        f'<span style="background:{c}"></span>{cat} '
        for cat, c in cat_colors.items() if cat != "root"
    )

    body = (
        f'<div class="breadcrumb"><a href="/">Link</a> / graph</div>'
        f'<h1>Knowledge Graph</h1>'
        f'<p class="meta">For large wikis, use fullscreen, zoom, pan, and sparse labels. '
        f'The graph is for exploring neighborhoods, not reading every label at once.</p>'
        f'<section id="graph-frame" class="graph-frame">'
        f'<div class="graph-toolbar" aria-label="Graph controls">'
        f'<button id="graph-reset" type="button">Reset</button>'
        f'<button id="graph-labels" type="button" aria-pressed="false">Labels</button>'
        f'<button id="graph-motion" type="button" aria-pressed="false">Motion on</button>'
        f'<button id="graph-fullscreen" type="button" aria-pressed="false">Fullscreen</button>'
        f'<label class="graph-control">Find'
        f'<input id="graph-search" type="search" placeholder="node title"></label>'
        f'<label class="graph-control">Type'
        f'<select id="graph-category">{category_options}</select></label>'
        f'<label class="graph-control">Neighborhood'
        f'<select id="graph-depth"><option value="all">all</option><option value="1">1 hop</option>'
        f'<option value="2">2 hops</option><option value="3">3 hops</option></select></label>'
        f'<span id="graph-status" class="graph-status" aria-live="polite">'
        f'{node_count} nodes · {edge_count} edges</span>'
        f'</div>'
        f'<div class="graph-shell">'
        f'<canvas id="graph-canvas" tabindex="0" role="img" '
        f'aria-label="Knowledge graph with {node_count} nodes and {edge_count} edges"></canvas>'
        f'<aside id="graph-inspector" class="graph-inspector" aria-live="polite">'
        f'<strong id="graph-inspector-title">Select a node</strong>'
        f'<p id="graph-inspector-meta">Click a node to inspect it. Drag a node to place it. '
        f'Double-click a node, or use Open page, to navigate.</p>'
        f'<div id="graph-inspector-links" class="graph-inspector-links"></div>'
        f'<button id="graph-focus" type="button" disabled>Focus neighborhood</button>'
        f'<button id="graph-open" type="button" disabled>Open page</button>'
        f'</aside>'
        f'</div>'
        f'<div class="graph-legend">{legend_items}</div>'
        f'</section>'
        f'{graph_js}'
    )
    return _layout("Knowledge Graph", body, page_class="graph-page")


def _render_search(query):
    q = query.lower().strip()
    if not q:
        return _layout("Search",
            f'<div class="breadcrumb"><a href="/">Link</a> / search</div>'
            f'<h1>Search</h1><p>Enter a search term above.</p>')
    results = _search_pages(q, limit=30)
    total = len(results)
    cap_note = f" (showing 30 of {total})" if total > 30 else ""

    def _highlight(text: str, term: str) -> str:
        """Wrap all occurrences of term in <mark> tags (case-insensitive)."""
        if not term or not text: return html.escape(text)
        parts = re.split(f"({re.escape(term)})", text, flags=re.IGNORECASE)
        return "".join(
            f"<mark>{html.escape(p)}</mark>" if p.lower() == term.lower() else html.escape(p)
            for p in parts
        )

    items = "".join(
        f'<li><a href="{_page_href(r["name"])}">{_highlight(r["title"], query)}</a>'
        f'<br><small style="color:#888">...{_highlight(r.get("snippet",""), query)}...</small></li>'
        for r in results[:30]
    )
    return _layout(f"Search: {query}",
        f'<div class="breadcrumb"><a href="/">Link</a> / search</div>'
        f'<h1>Search: {html.escape(query)}</h1>'
        f'<p>{total} result{"s" if total != 1 else ""}{cap_note}</p>'
        f'<ul class="page-list search-results">{items}</ul>')


# ---------------------------------------------------------------------------
# Agent search helpers
# ---------------------------------------------------------------------------

def _search_pages(q: str, limit: int = 20) -> list:
    """Search pages by title, alias, tag, and full-text body.
    Uses token index to pre-filter candidates, snippet index for zero file I/O.
    """
    return _core_search_pages(q, _current_wiki_cache(), limit=limit)


def _query_link(query: str, budget: str = "medium", project: str | None = None) -> dict[str, object]:
    return _core_query_link(
        WIKI_DIR,
        query,
        _current_wiki_cache(),
        _memory_records(),
        budget=budget,
        project=project,
        review_command="review-memory",
    )


def _get_context(topic: str) -> dict:
    """Return everything an agent needs to answer a question about a topic.
    Finds the best matching page, then returns:
    - The page's full content
    - Its backlinks (pages that reference it)
    - Its forward links (pages it references)
    - Related pages (shared tags or backlink overlap)
    """
    return _core_context_for_topic(WIKI_DIR, topic, _current_wiki_cache())


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------

def _build_backlinks() -> dict[str, dict[str, list[str]]]:
    """Scan all wiki pages for [[wikilinks]] and build graph indexes.
    Returns {"backlinks": {target: [sources]}, "forward": {source: [targets]}}.
    """
    return _core_build_backlinks(WIKI_DIR)


def _get_graph_data() -> dict:
    """Return graph nodes and edges for visualization.
    Uses in-memory fulltext index — no separate rglob scan.
    """
    return _core_graph_data(_current_wiki_cache())


def _rebuild_backlinks_payload() -> dict[str, object]:
    result = _build_backlinks()
    bl_path = WIKI_DIR / "_backlinks.json"
    bl_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    # Invalidate pages cache so next request picks up the new backlinks mtime.
    _invalidate_pages_cache()
    return {"rebuilt": True, "pages": len(result.get("backlinks", {}))}


def _rebuild_index_payload() -> dict[str, object]:
    result = _core_rebuild_index(WIKI_DIR, cache=_current_wiki_cache())
    _invalidate_pages_cache()
    return result


def _validate_wiki_payload(strict: bool = False) -> dict[str, object]:
    return _core_validate_wiki(WIKI_DIR, strict=strict)


def _link_status_payload(include_validation: bool = False) -> dict[str, object]:
    payload = _core_link_status(
        WIKI_DIR,
        cache=_current_wiki_cache(),
        records=_memory_records(),
        include_validation=include_validation,
    )
    payload["api_version"] = API_VERSION
    return payload


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        """HEAD requests: send headers only, no body."""
        self._head_only = True
        self.do_GET()
        self._head_only = False

    def do_POST(self):
        self._head_only = False
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/api/rebuild-index":
            if not self._require_local_action_header({"rebuilt": False}):
                return
            payload, error, status = self._read_json_body()
            if error:
                self._json({"rebuilt": False, "error": error}, status=status)
                return
            assert payload is not None
            self._json(_rebuild_index_payload())
            return
        if path == "/api/rebuild-backlinks":
            if not self._require_local_action_header({"rebuilt": False}):
                return
            payload, error, status = self._read_json_body()
            if error:
                self._json({"rebuilt": False, "error": error}, status=status)
                return
            assert payload is not None
            self._json(_rebuild_backlinks_payload())
            return
        if path == "/api/propose-memories":
            payload, error, status = self._read_json_body()
            if error:
                self._json({"proposed": False, "error": error, "count": 0, "proposals": []}, status=status)
                return
            assert payload is not None
            text = str(payload.get("text") or "")
            if not text.strip():
                self._json({"proposed": False, "error": "text required", "count": 0, "proposals": []}, status=400)
                return
            source = str(payload.get("source") or "http")[:500]
            limit, limit_error = _parse_search_limit(str(payload.get("limit", "10")))
            if limit_error:
                self._json({"proposed": False, "error": limit_error, "count": 0, "proposals": []}, status=400)
                return
            result = _propose_memories_from_text(
                text[:MAX_POST_BYTES],
                source=source,
                limit=min(limit, 20),
                project=str(payload.get("project") or ""),
            )
            self._json(result)
            return
        if path in {"/api/remember-memory", "/api/update-memory"}:
            if not self._require_local_action_header({"saved": False}):
                return
            payload, error, status = self._read_json_body()
            if error:
                self._json({"saved": False, "error": error}, status=status)
                return
            assert payload is not None
            try:
                if path == "/api/remember-memory":
                    result = _remember_memory_from_web(payload)
                    http_status = 200 if result.get("created") else 409
                    self._json({"saved": bool(result.get("created")), **result}, status=http_status)
                else:
                    result = _update_memory_from_web(payload)
                    http_status = 200 if result.get("updated") else 409
                    self._json({"saved": bool(result.get("updated")), **result}, status=http_status)
            except ValueError as exc:
                self._json({"saved": False, "error": str(exc)}, status=400)
            return
        if path in {"/api/review-memory", "/api/archive-memory", "/api/restore-memory"}:
            if not self._require_local_action_header():
                return
            payload, error, status = self._read_json_body()
            if error:
                self._json({"updated": False, "error": error}, status=status)
                return
            assert payload is not None
            identifier = _clean_text_input(payload.get("memory") or payload.get("identifier"), max_len=300)
            if not identifier:
                self._json({"updated": False, "error": "memory required"}, status=400)
                return
            try:
                if path == "/api/review-memory":
                    result = _mark_memory_reviewed(
                        identifier,
                        note=_clean_text_input(payload.get("note"), max_len=500),
                    )
                elif path == "/api/archive-memory":
                    result = _set_memory_status(
                        identifier,
                        "archived",
                        reason=_clean_text_input(payload.get("reason"), max_len=500),
                    )
                else:
                    result = _set_memory_status(identifier, "active")
            except ValueError as exc:
                self._json({"updated": False, "error": str(exc)}, status=404)
                return
            self._json(result)
            return
        self._json({"error": "POST endpoint not found"}, status=404)

    def do_GET(self):
        self._head_only = getattr(self, '_head_only', False)
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        if path == "/logo.svg":
            self._file(Path(__file__).parent / "logo.svg", "image/svg+xml")
        elif path == "/logo.png":
            self._file(Path(__file__).parent / "logo.png", "image/png")
        elif path.startswith("/raw/"):
            raw_path, content_type = _resolve_raw_static_path(path[5:])
            if raw_path and content_type:
                self._file(raw_path, content_type)
            else:
                self._err("file")
        elif path in ("/", ""):
            self._ok(_render_home())
        elif path == "/ingest":
            self._ok(_render_ingest())
        elif path == "/brief":
            brief_query = query.get("q", [""])[0] or query.get("query", [""])[0]
            self._ok(_render_brief(query=brief_query, project=query.get("project", [""])[0]))
        elif path == "/propose":
            self._ok(_render_propose(
                project=query.get("project", [""])[0],
                source=query.get("source", [""])[0],
            ))
        elif path == "/prompts":
            self._ok(_render_prompts(project=query.get("project", [""])[0]))
        elif path == "/memory":
            self._ok(_render_memory_dashboard(project=query.get("project", [""])[0]))
        elif path == "/audit":
            self._ok(_render_memory_audit(project=query.get("project", [""])[0]))
        elif path == "/inbox":
            self._ok(_render_inbox(project=query.get("project", [""])[0]))
        elif path == "/captures":
            self._ok(_render_captures(project=query.get("project", [""])[0]))
        elif path == "/explain-memory":
            identifier = query.get("memory", [""])[0].strip() or query.get("name", [""])[0].strip()
            self._ok(_render_explain_memory(identifier))
        elif path == "/profile":
            self._ok(_render_profile(project=query.get("project", [""])[0]))
        elif path == "/all":
            self._ok(_render_all())
        elif path == "/graph":
            self._ok(_render_graph())
        elif path == "/search":
            self._ok(_render_search(query.get("q", [""])[0]))
        elif path.startswith("/page/"):
            page = _find_page(urllib.parse.unquote(path[6:]))
            if page: self._ok(_render_page(page))
            else: self._err(urllib.parse.unquote(path[6:]))
        elif path == "/api/pages":
            self._json(_all_pages())
        elif path == "/api/status":
            include_validation = query.get("validate", ["false"])[0].lower() in {"1", "true", "yes"}
            self._json(_link_status_payload(include_validation=include_validation))
        elif path == "/api/prompts":
            self._json(_starter_prompts_payload(project=query.get("project", [""])[0]))
        elif path == "/api/ingest-status":
            self._json(_ingest_status())
        elif path == "/api/backlinks":
            data, error = _load_backlinks_index()
            if error:
                self._json({"error": error}, status=500)
            else:
                self._json(data)
        elif path == "/api/rebuild-backlinks":
            self._json({"error": "use POST with JSON body: {}"}, status=405)
        elif path == "/api/rebuild-index":
            self._json({"error": "use POST with JSON body: {}"}, status=405)
        elif path == "/api/validate":
            strict = query.get("strict", ["false"])[0].lower() in {"1", "true", "yes"}
            payload = _validate_wiki_payload(strict=strict)
            self._json(payload, status=200 if payload.get("passed") else 422)
        elif path == "/api/graph":
            self._json(_get_graph_data())
        elif path == "/api/memory-profile":
            limit, error = _parse_search_limit(query.get("limit", ["10"])[0])
            if error:
                self._json({"error": error}, status=400)
            else:
                self._json(_memory_profile(limit=limit, project=query.get("project", [""])[0]))
        elif path == "/api/memory-dashboard":
            limit, error = _parse_search_limit(query.get("limit", ["12"])[0])
            if error:
                self._json({"error": error}, status=400)
            else:
                self._json(_memory_dashboard(limit=limit, project=query.get("project", [""])[0]))
        elif path == "/api/memory-brief":
            limit, error = _parse_search_limit(query.get("limit", ["6"])[0])
            if error:
                self._json({"error": error}, status=400)
            else:
                brief_query = query.get("q", [""])[0] or query.get("query", [""])[0]
                self._json(_memory_brief(
                    query=brief_query,
                    limit=limit,
                    project=query.get("project", [""])[0],
                ))
        elif path == "/api/query-link":
            query_text = query.get("q", [""])[0] or query.get("query", [""])[0]
            if not query_text.strip():
                self._json({"found": False, "error": "query parameter required", "context_packet": []}, status=400)
            else:
                self._json(_query_link(
                    query=query_text,
                    budget=query.get("budget", ["medium"])[0],
                    project=query.get("project", [""])[0],
                ))
        elif path == "/api/memory-audit":
            limit, error = _parse_search_limit(query.get("limit", ["10"])[0])
            if error:
                self._json({"error": error}, status=400)
            else:
                self._json(_memory_audit(limit=limit, project=query.get("project", [""])[0]))
        elif path == "/api/memory-inbox":
            limit, error = _parse_search_limit(query.get("limit", ["20"])[0])
            if error:
                self._json({"error": error}, status=400)
            else:
                include_archived = query.get("include_archived", ["false"])[0].lower() in {"1", "true", "yes"}
                self._json(_memory_inbox(
                    limit=limit,
                    include_archived=include_archived,
                    project=query.get("project", [""])[0],
                ))
        elif path == "/api/capture-inbox":
            limit, error = _parse_search_limit(query.get("limit", ["20"])[0])
            if error:
                self._json({"error": error}, status=400)
            else:
                self._json(_capture_inbox(
                    limit=limit,
                    project=query.get("project", [""])[0],
                ))
        elif path == "/api/proposal-sources":
            limit, error = _parse_search_limit(query.get("limit", ["50"])[0])
            if error:
                self._json({"error": error, "sources": []}, status=400)
            else:
                self._json(_proposal_sources(limit=min(limit, 100)))
        elif path == "/api/proposal-source":
            source_path = query.get("path", [""])[0]
            payload, status = _proposal_source_payload(source_path)
            self._json(payload, status=status)
        elif path == "/api/propose-memories":
            self._json({"error": "use POST with JSON body: {\"text\": \"...\"}"}, status=405)
        elif path in {"/api/review-memory", "/api/archive-memory", "/api/restore-memory"}:
            self._json({"error": "use POST with JSON body: {\"memory\": \"...\"}"}, status=405)
        elif path == "/api/explain-memory":
            identifier = query.get("memory", [""])[0].strip() or query.get("name", [""])[0].strip()
            if not identifier:
                self._json({"found": False, "error": "memory parameter required"}, status=400)
            else:
                try:
                    self._json(_memory_explanation(identifier))
                except ValueError as exc:
                    self._json({"found": False, "error": str(exc)}, status=404)
        elif path == "/api/search":
            q = query.get("q", [""])[0].strip()
            limit, error = _parse_search_limit(query.get("limit", ["20"])[0])
            if error:
                self._json({"error": error, "results": []}, status=400)
                return
            if not q:
                self._json({"error": "q parameter required", "results": []}, status=400)
            else:
                results = _search_pages(q, limit=limit)
                self._json({"query": q, "count": len(results), "results": results})
        elif path == "/api/context":
            topic = query.get("topic", [""])[0].strip() or query.get("q", [""])[0].strip()
            if not topic:
                self._json({"error": "topic parameter required"}, status=400)
            else:
                self._json(_get_context(topic))
        else:
            self._err("page")

    def _ok(self, body: str):
        encoded = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._security_headers()
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(encoded)

    def _err(self, name: str):
        encoded = _layout("Not Found", f"<h1>Not found</h1><p>No page: {html.escape(name)}</p>").encode()
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._security_headers()
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(encoded)

    def _json(self, data, status: int = 200):
        encoded = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._security_headers()
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(encoded)

    def _require_local_action_header(self, error_payload: dict[str, object] | None = None) -> bool:
        value = self.headers.get(LOCAL_ACTION_HEADER, "").strip().lower()
        if value in LOCAL_ACTION_VALUES:
            return True
        payload = dict(error_payload or {"updated": False})
        payload["error"] = f"{LOCAL_ACTION_HEADER} header required for local mutations"
        self._json({
            **payload,
        }, status=403)
        return False

    def _read_json_body(self) -> tuple[dict | None, str | None, int]:
        content_type = self.headers.get("Content-Type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            return None, "Content-Type must be application/json", 415
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return None, "Content-Length required", 411
        try:
            length = int(raw_length)
        except ValueError:
            return None, "invalid Content-Length", 400
        if length < 0:
            return None, "invalid Content-Length", 400
        if length > MAX_POST_BYTES:
            return None, f"request body too large; max {MAX_POST_BYTES} bytes", 413
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, "invalid JSON body", 400
        if not isinstance(payload, dict):
            return None, "JSON body must be an object", 400
        return payload, None, 200

    def _security_headers(self):
        self.send_header("X-Link-API-Version", API_VERSION)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")

    def _file(self, fpath, content_type):
        fpath = _safe_resolve(fpath)
        if not fpath or not _is_allowed_static_file(fpath):
            self._err("file")
            return
        if fpath.exists() and fpath.is_file():
            data = fpath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self._security_headers()
            if content_type == "image/svg+xml":
                self.send_header("Content-Security-Policy", "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; script-src 'none'; object-src 'none'; sandbox")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if not getattr(self, '_head_only', False):
                self.wfile.write(data)
        else:
            self._err("file")

    def log_message(self, *a): pass


def _parse_serve_port(argv: list[str], default: int = PORT) -> int:
    port = default
    for index, arg in enumerate(argv):
        if arg in {"--host", "--bind"} or arg.startswith("--host=") or arg.startswith("--bind="):
            raise SystemExit("Link serve is local-only; host/bind options are not supported.")
        if arg == "--port":
            if index + 1 >= len(argv):
                raise SystemExit("--port requires a value")
            try:
                port = int(argv[index + 1])
            except ValueError as exc:
                raise SystemExit("--port must be an integer") from exc
        elif arg.startswith("--port="):
            try:
                port = int(arg.split("=", 1)[1])
            except ValueError as exc:
                raise SystemExit("--port must be an integer") from exc
    return port


def main():
    global PORT
    PORT = _parse_serve_port(sys.argv[1:], default=PORT)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as s:
        print(f"  Link → http://localhost:{PORT}")
        print("  Local-only: bound to 127.0.0.1; no public host mode.")
        try: s.serve_forever()
        except KeyboardInterrupt: print("\n  stopped.")


if __name__ == "__main__":
    main()
