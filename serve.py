#!/usr/bin/env python3
"""Link — local wiki viewer. python serve.py → http://127.0.0.1:3000"""
from __future__ import annotations

import errno
import html
import http.server
import json
import re
import socketserver
import sys
import time
import urllib.parse
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
from link_core.markdown import (
    markdown_to_html as _core_markdown_to_html,
)
from link_core.security import (
    clean_text_input as _clean_text_input,
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
from link_core.version import (
    LINK_VERSION,
)
from link_core.web_assets import CSS  # noqa: F401 - kept as serve.CSS for tests and compatibility
from link_core.web_memory import (
    render_memory_action_commands as _render_memory_action_commands,
    render_memory_card as _core_render_memory_card,
    render_memory_section as _core_render_memory_section,
)
from link_core.web_memory_pages import (
    render_brief_page as _core_render_brief_page,
    render_captures_page as _core_render_captures_page,
    render_inbox_page as _core_render_inbox_page,
    render_memory_audit_page as _core_render_memory_audit_page,
    render_memory_dashboard_page as _core_render_memory_dashboard_page,
    render_profile_page as _core_render_profile_page,
)
from link_core.web_layout import (
    render_footer_html as _core_render_footer_html,
    render_header_html as _core_render_header_html,
    render_layout as _core_render_layout,
)
from link_core.web_graph import (
    GRAPH_CATEGORY_COLORS as _core_graph_category_colors,
    GRAPH_INITIAL_SUMMARY_EDGE_LIMIT as _core_graph_initial_summary_edge_limit,
    GRAPH_INITIAL_SUMMARY_NODE_LIMIT as _core_graph_initial_summary_node_limit,
    graph_category_options as _core_graph_category_options,
    graph_initial_payload as _core_graph_initial_payload,
    graph_legend_items as _core_graph_legend_items,
    graph_needs_bounded_overview as _core_graph_needs_bounded_overview,
)
from link_core.web_home import (
    plural_type_label as _core_plural_type_label,
    render_home_page as _core_render_home_page,
)
from link_core.web_ingest import (
    render_ingest_page as _core_render_ingest_page,
)
from link_core.web_http import (
    CONTENT_SECURITY_POLICY as _core_content_security_policy,
    is_allowed_static_file as _core_is_allowed_static_file,
    is_relative_to as _core_is_relative_to,
    LocalRateLimiter as _CoreLocalRateLimiter,
    local_no_store_headers as _core_local_no_store_headers,
    local_security_headers as _core_local_security_headers,
    parse_bounded_int as _core_parse_bounded_int,
    PERMISSIONS_POLICY as _core_permissions_policy,
    resolve_raw_static_path as _core_resolve_raw_static_path,
    safe_resolve as _core_safe_resolve,
    SVG_CONTENT_SECURITY_POLICY as _core_svg_content_security_policy,
    validate_local_browser_source_headers as _core_validate_local_browser_source_headers,
    validate_local_host_header as _core_validate_local_host_header,
)
from link_core.web_proposals import (
    create_raw_source_payload as _core_create_raw_source_payload,
    proposal_source_payload as _core_proposal_source_payload,
    proposal_sources as _core_proposal_sources,
)
from link_core.web_prompts import (
    render_prompts_page as _core_render_prompts_page,
)
from link_core.web_pages import (
    render_all_pages as _core_render_all_pages,
    render_wiki_page as _core_render_wiki_page,
)
from link_core.web_search import (
    render_search_page as _core_render_search_page,
)
from link_core.status import (
    link_status as _core_link_status,
)
from link_core.capture import (
    capture_inbox as _core_capture_inbox,
    capture_records as _core_capture_records,
    capture_review_summary as _core_capture_review_summary,
    cli_capture_commands as _core_cli_capture_commands,
)
from link_core.files import (
    atomic_write_json as _core_atomic_write_json,
)
from link_core.wiki import (
    build_backlinks as _core_build_backlinks,
    build_wiki_cache as _core_build_wiki_cache,
    close_wiki_cache as _core_close_wiki_cache,
    context_for_topic as _core_context_for_topic,
    graph_data as _core_graph_data,
    graph_summary as _core_graph_summary,
    list_pages as _core_list_pages,
    load_backlinks_index as _core_load_backlinks_index,
    page_link_summary as _core_page_link_summary,
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
MAX_QUERY_TEXT = 500
MAX_PROPOSAL_SOURCE_BYTES = 64 * 1024
MAX_RAW_SOURCE_BYTES = 60 * 1024
LOCAL_ACTION_HEADER = "X-Link-Local-Action"
LOCAL_ACTION_VALUES = {"1", "true", "yes"}
MUTATION_RATE_LIMIT = 180
MUTATION_RATE_WINDOW_SECONDS = 60
CONTENT_SECURITY_POLICY = _core_content_security_policy
PERMISSIONS_POLICY = _core_permissions_policy
SVG_CONTENT_SECURITY_POLICY = _core_svg_content_security_policy
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
CACHE_MTIME_CHECK_INTERVAL_SECONDS = 0.5
_pages_cache: list | None = None
_pages_cache_mtime: float = 0.0
_pages_cache_checked_at: float = 0.0
_page_index: dict[str, Path] = {}  # stem.lower() → path
_fulltext_index: dict[str, str] = {}  # stem.lower() → full text (for search)
_normalized_fulltext_index: dict[str, str] = {}  # punctuation-normalized full text
_text_words_index: dict[str, set[str]] = {}  # stem.lower() → normalized fulltext words
_meta_words_index: dict[str, set[str]] = {}  # stem.lower() → normalized metadata words
_snippet_index: dict[str, str] = {}  # stem.lower() → pre-extracted first snippet
_token_index: dict[str, set[str]] = {}  # token → set of page stems that contain it
_page_map: dict[str, dict] = {}  # stem.lower() → page dict (for O(1) lookup in search)
_meta_token_index: dict[str, set[str]] = {}  # token → stems with that token in title/alias/tag/tldr
_forward_links_index: dict[str, list[str]] = {}  # page name → canonical outbound wikilinks
_fts_index = None
_search_backend = "token-index"
_cache_read_warnings: list[dict[str, str]] = []
_mutation_rate_limiter = _CoreLocalRateLimiter(
    max_events=MUTATION_RATE_LIMIT,
    window_seconds=MUTATION_RATE_WINDOW_SECONDS,
)

def _invalidate_pages_cache() -> None:
    global _pages_cache, _pages_cache_mtime, _pages_cache_checked_at, _forward_links_index, _fts_index, _search_backend, _cache_read_warnings
    _core_close_wiki_cache({"fts_index": _fts_index})
    _pages_cache = None
    _pages_cache_mtime = 0.0
    _pages_cache_checked_at = 0.0
    _forward_links_index = {}
    _fts_index = None
    _search_backend = "token-index"
    _cache_read_warnings = []


def _wiki_mtime() -> float:
    return _core_wiki_mtime(WIKI_DIR)


def _get_all_pages(force_check: bool = False) -> list:
    global _pages_cache, _pages_cache_mtime, _pages_cache_checked_at, _page_index, _fulltext_index, _normalized_fulltext_index, _text_words_index, _meta_words_index, _snippet_index, _token_index, _page_map, _meta_token_index, _forward_links_index, _fts_index, _search_backend, _cache_read_warnings
    now = time.monotonic()
    if (
        _pages_cache is not None
        and not force_check
        and CACHE_MTIME_CHECK_INTERVAL_SECONDS > 0
        and now - _pages_cache_checked_at < CACHE_MTIME_CHECK_INTERVAL_SECONDS
    ):
        return _pages_cache
    mtime = _wiki_mtime()
    _pages_cache_checked_at = now
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
    _forward_links_index = cache.get("forward_links_index", {})
    _fts_index = cache.get("fts_index")
    _search_backend = str(cache.get("search_backend") or "token-index")
    _cache_read_warnings = cache.get("read_warnings") if isinstance(cache.get("read_warnings"), list) else []
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
        "forward_links_index": _forward_links_index,
        "fts_index": _fts_index,
        "search_backend": _search_backend,
        "read_warning_count": len(_cache_read_warnings),
        "read_warnings": _cache_read_warnings,
    }


def _find_page(name: str) -> Path | None:
    # Ensure cache is warm — _get_all_pages populates _page_index as a side effect
    _get_all_pages()
    return _page_index.get(name.strip().lower())


# Keep _all_pages as alias for API compatibility
def _all_pages() -> list:
    return _get_all_pages()


def _page_list_payload(
    category: str = "",
    page_type: str = "",
    maturity: str = "",
    limit: int = 100,
    offset: int = 0,
    include_all: bool = False,
) -> dict:
    return _core_list_pages(
        _current_wiki_cache(),
        category=category,
        page_type=page_type,
        maturity=maturity,
        limit=limit,
        offset=offset,
        include_all=include_all,
    )


def _load_backlinks_index() -> tuple[dict, str | None]:
    return _core_load_backlinks_index(WIKI_DIR / "_backlinks.json")


def _page_links_payload(
    page_name: str,
    limit: int = 100,
    offset: int = 0,
    include_all: bool = False,
) -> tuple[dict, int]:
    backlinks, error = _load_backlinks_index()
    if error:
        return {"error": error}, 500
    if not page_name.strip():
        return {"error": "page parameter required", "inbound": [], "forward": []}, 400
    return _core_page_link_summary(
        backlinks,
        page_name,
        limit=limit,
        offset=offset,
        include_all=include_all,
    ), 200


def _parse_search_limit(raw: object) -> tuple[int | None, str | None]:
    return _core_parse_bounded_int(raw, "limit", 20, 1, 50)


def _query_text(query: dict[str, list[str]], *names: str, max_len: int = MAX_QUERY_TEXT) -> str:
    for name in names:
        values = query.get(name)
        if values:
            text = _clean_text_input(values[0], max_len=max_len)
            if text:
                return text
    return ""


def _utc_timestamp() -> str:
    return _core_utc_timestamp()


def _append_log(timestamp: str, operation: str, description: str, lines: list[str]) -> None:
    _core_append_log(WIKI_DIR, timestamp, operation, description, lines)


def _page_href(name: str) -> str:
    return "/page/" + urllib.parse.quote(name.strip(), safe="")


def _plural_type_label(page_type: str) -> str:
    return _core_plural_type_label(page_type)


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
        allow_duplicate=False,
        allow_conflict=False,
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
        allow_conflict=False,
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
    summary = _core_capture_review_summary(
        WIKI_DIR.parent,
        limit=limit,
        project=project_name,
        commands_for=_core_cli_capture_commands,
    )
    project_query = f"?project={urllib.parse.quote(project_name, safe='')}" if project_name else ""
    project_arg = f' --project "{project_name}"' if project_name else ""
    summary["href"] = f"/captures{project_query}"
    summary["command"] = f"python3 link.py capture-inbox .{project_arg}"
    return summary


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
            "recommended": bool(captures["count"] or captures.get("read_warning_count")),
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
    captures = _capture_review_summary(project=project_name, limit=min(limit, 10))
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
    return _core_safe_resolve(path)


def _is_relative_to(path: Path, root: Path) -> bool:
    return _core_is_relative_to(path, root)


def _is_allowed_static_file(path: Path) -> bool:
    root = Path(__file__).parent.resolve()
    return _core_is_allowed_static_file(
        path,
        RAW_DIR,
        (root / "logo.svg", root / "logo.png"),
        RAW_STATIC_TYPES,
    )


def _resolve_raw_static_path(url_fragment: str) -> tuple[Path | None, str | None]:
    return _core_resolve_raw_static_path(RAW_DIR, url_fragment, RAW_STATIC_TYPES)


def _proposal_sources(limit: int = 50) -> dict[str, object]:
    return _core_proposal_sources(
        RAW_DIR,
        suffixes=PROPOSAL_SOURCE_SUFFIXES,
        max_bytes=MAX_PROPOSAL_SOURCE_BYTES,
        limit=limit,
    )


def _proposal_source_payload(source_path: str) -> tuple[dict[str, object], int]:
    return _core_proposal_source_payload(
        RAW_DIR,
        source_path,
        suffixes=PROPOSAL_SOURCE_SUFFIXES,
        max_bytes=MAX_PROPOSAL_SOURCE_BYTES,
    )


def _create_raw_source_payload(payload: dict[str, object]) -> tuple[dict[str, object], int]:
    return _core_create_raw_source_payload(
        WIKI_DIR.parent,
        WIKI_DIR,
        payload,
        max_bytes=MAX_RAW_SOURCE_BYTES,
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _md_to_html(md):
    return _core_markdown_to_html(md, page_href=_page_href)


# ---------------------------------------------------------------------------
# CSS + layout
# ---------------------------------------------------------------------------

def _header_html():
    return _core_render_header_html()


def _footer_html():
    return _core_render_footer_html()


def _layout(title, body, page_class: str = ""):
    return _core_render_layout(title, body, page_class=page_class)


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def _render_home():
    return _core_render_home_page(
        _get_all_pages(),
        starter_prompts=_starter_prompts_payload(),
        page_href=_page_href,
        layout=_layout,
    )


def _starter_prompts_payload(project: str | None = None) -> dict[str, object]:
    return _core_starter_prompt_payload(WIKI_DIR, project=project)


def _render_prompts(project: str | None = None):
    return _core_render_prompts_page(_starter_prompts_payload(project=project), layout=_layout)


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
    return _core_render_wiki_page(str(title), category=cat, meta=meta, body_html=body_html, layout=_layout)


def _render_all(query: dict[str, list[str]] | None = None):
    query = query or {}
    pages = _get_all_pages()
    total = len(pages)
    limit_raw = query.get("limit", ["250"])[0]
    offset_raw = query.get("offset", ["0"])[0]
    limit, limit_error = _core_parse_bounded_int(limit_raw, "limit", 250, 1, 500)
    offset, offset_error = _core_parse_bounded_int(offset_raw, "offset", 0, 0, 1000000)
    error = limit_error or offset_error
    if error:
        limit = 250
        offset = 0
    assert limit is not None
    assert offset is not None
    sorted_pages = sorted(pages, key=lambda x: x["title"])
    window = sorted_pages[offset:offset + limit]
    return _core_render_all_pages(
        window,
        total=total,
        limit=limit,
        offset=offset,
        page_href=_page_href,
        layout=_layout,
        error=error or "",
    )


def _render_memory_card(record: dict[str, object], include_issues: bool = False) -> str:
    return _core_render_memory_card(
        record,
        page_href=_page_href,
        action_hints=_memory_action_hints,
        include_issues=include_issues,
    )


def _render_memory_section(title: str, records: list[dict[str, object]], empty: str, href: str = "", include_issues: bool = False) -> str:
    return _core_render_memory_section(
        title,
        records,
        empty,
        page_href=_page_href,
        action_hints=_memory_action_hints,
        href=href,
        include_issues=include_issues,
    )


def _render_brief(query: str = "", project: str | None = None):
    return _core_render_brief_page(
        _memory_brief(query=query, limit=8, project=project),
        query,
        page_href=_page_href,
        action_hints=_memory_action_hints,
        layout=_layout,
    )


def _render_memory_dashboard(project: str | None = None):
    return _core_render_memory_dashboard_page(
        _memory_dashboard(limit=8, project=project),
        page_href=_page_href,
        action_hints=_memory_action_hints,
        layout=_layout,
    )


def _render_profile(project: str | None = None):
    return _core_render_profile_page(_memory_profile(limit=12, project=project), page_href=_page_href, layout=_layout)


def _render_memory_audit(project: str | None = None):
    return _core_render_memory_audit_page(
        _memory_audit(limit=10, project=project),
        page_href=_page_href,
        action_hints=_memory_action_hints,
        layout=_layout,
    )


def _render_captures(project: str | None = None):
    return _core_render_captures_page(_capture_inbox(limit=50, project=project), layout=_layout)


def _render_propose(project: str | None = None, source: str | None = None):
    project_value = html.escape(_clean_text_input(project, max_len=80), quote=True)
    source_value = html.escape(_clean_text_input(source, max_len=500), quote=True)
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
    return _core_render_ingest_page(_ingest_status(), page_href=_page_href, layout=_layout)


def _render_inbox(project: str | None = None):
    return _core_render_inbox_page(_memory_inbox(limit=50, project=project), page_href=_page_href, layout=_layout)


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
    full_graph = _get_graph_data()
    summary_graph = None
    if _core_graph_needs_bounded_overview(full_graph):
        summary = _get_graph_summary(
            limit=_core_graph_initial_summary_node_limit,
            depth=1,
            max_edges=_core_graph_initial_summary_edge_limit,
        )
        summary_graph = {
            "nodes": summary.get("nodes", []),
            "edges": summary.get("edges", []),
        }
    graph_view = _core_graph_initial_payload(full_graph, summary_graph=summary_graph)
    visible_nodes = graph_view["nodes"]
    visible_edges = graph_view["edges"]
    node_count = int(graph_view["node_count"])
    edge_count = int(graph_view["edge_count"])
    total_node_count = int(graph_view["total_node_count"])
    total_edge_count = int(graph_view["total_edge_count"])
    graph_mode = str(graph_view["graph_mode"])
    graph_note = str(graph_view["graph_note"])
    nodes_json = _json_for_script(visible_nodes)
    edges_json = _json_for_script(visible_edges)

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

    cat_colors = _core_graph_category_colors
    category_options = _core_graph_category_options(visible_nodes)

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
  var loadFullButton = document.getElementById('graph-load-full');
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
  var LARGE_LABEL_LIMIT = 160;
  var FAST_RENDER_NODE_LIMIT = 450;
  var FAST_RENDER_EDGE_LIMIT = 1200;
  var OVERVIEW_NODE_LIMIT = 650;
  var SEARCH_LABEL_LIMIT = 60;
  var initialGraphMode = {_json_for_script(graph_mode)};
  var totalNodeCount = {total_node_count};
  var totalEdgeCount = {total_edge_count};
  var fullGraphLoaded = initialGraphMode === 'full';
  var fullGraphLoading = false;
  var nodeById = {{}};

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
  function seedNodePosition(n, i, total) {{
    var lobe = i % 2 === 0 ? -1 : 1;
    var a = i * 2.399963 + stableNoise(n.id, 7) * 0.7;
    var r = 50 + Math.sqrt((i + 1) / Math.max(total, 1)) * 155;
    var categoryDrop = n.category === 'sources' ? 58 : (n.category === 'memories' ? -34 : (n.category === 'entities' ? 24 : -6));
    pos[n.id] = {{
      x: lobe * 78 + Math.cos(a) * r * 0.78,
      y: Math.sin(a) * r * 0.58 + categoryDrop
    }};
    vel[n.id] = {{ x: 0, y: 0 }};
  }}

  function seedMissingPositions() {{
    nodes.forEach(function(n, i) {{
      if (!pos[n.id]) seedNodePosition(n, i, nodes.length);
      if (!vel[n.id]) vel[n.id] = {{ x: 0, y: 0 }};
    }});
  }}

  function reseedVisiblePositions() {{
    var currentNodes = visibleNodes();
    currentNodes.forEach(function(n, i) {{
      if (!pinned[n.id]) seedNodePosition(n, i, currentNodes.length);
    }});
  }}

  // Adjacency
  var adj = {{}}, degree = {{}};
  function rebuildGraphIndexes() {{
    nodeById = {{}};
    adj = {{}};
    degree = {{}};
    nodes.forEach(function(n) {{
      nodeById[n.id] = n;
      adj[n.id] = [];
      degree[n.id] = 0;
    }});
    edges.forEach(function(e) {{
      if (adj[e.source]) {{ adj[e.source].push(e.target); degree[e.source]++; }}
      if (adj[e.target]) {{ adj[e.target].push(e.source); degree[e.target]++; }}
    }});
  }}

  rebuildGraphIndexes();
  seedMissingPositions();
  var lockedOverviewIds = null;
  if (initialGraphMode !== 'full') {{
    lockedOverviewIds = {{}};
    nodes.forEach(function(n) {{ lockedOverviewIds[n.id] = true; }});
  }}

  var dragging = null, dragOffX = 0, dragOffY = 0, hoverNode = null, selectedNode = null;
  var panX = 0, panY = 0, panStartX = 0, panStartY = 0, panning = false, didPan = false;
  var downX = 0, downY = 0, didDrag = false, suppressClick = false;
  var zoom = 1;
  var frame = 0;
  var showAllLabels = false;
  var motionPaused = (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) || nodes.length > LARGE_GRAPH_LIMIT;
  var SETTLE = 200; // frames of physics
  var searchTerm = '';
  var cachedSearchTerm = '';
  var cachedSearchMatches = 0;
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
  function invalidateSearchCache() {{ cachedSearchTerm = ''; cachedSearchMatches = 0; }}
  function escapeHtml(value) {{
    return String(value).replace(/[&<>"']/g, function(ch) {{
      return {{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }}[ch];
    }});
  }}
  function syncCategoryOptions() {{
    if (!categoryFilter) return;
    var categories = [];
    nodes.forEach(function(n) {{
      if (n.category && n.category !== 'root' && categories.indexOf(n.category) === -1) categories.push(n.category);
    }});
    categories.sort();
    categoryFilter.innerHTML = '<option value="all">all types</option>' + categories.map(function(category) {{
      return '<option value="' + escapeHtml(category) + '">' + escapeHtml(category) + '</option>';
    }}).join('');
    if (categories.indexOf(categoryValue) === -1) categoryValue = 'all';
    categoryFilter.value = categoryValue;
  }}
  function nodeSearchText(n) {{
    return (n.title + ' ' + n.id + ' ' + n.category).toLowerCase();
  }}
  function searchMatches(n) {{
    return searchTerm && nodeSearchText(n).indexOf(searchTerm) !== -1;
  }}
  function totalSearchMatches() {{
    if (!searchTerm) return 0;
    if (cachedSearchTerm === searchTerm) return cachedSearchMatches;
    cachedSearchTerm = searchTerm;
    cachedSearchMatches = nodes.filter(searchMatches).length;
    return cachedSearchMatches;
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
  function capEligibleNodes(eligible) {{
    if (eligible.length <= OVERVIEW_NODE_LIMIT) return eligible;
    if (fullGraphLoaded && lockedOverviewIds && !searchTerm && categoryValue === 'all' && depthValue === 'all' && !selectedNode) {{
      var locked = eligible.filter(function(n) {{ return lockedOverviewIds[n.id]; }});
      if (locked.length) return locked;
    }}
    var keep = {{}};
    var keepCount = 0;
    function markKeep(n) {{
      if (n && !keep[n.id]) {{
        keep[n.id] = true;
        keepCount++;
      }}
    }}
    var highSignalLimit = Math.floor(OVERVIEW_NODE_LIMIT * 0.65);
    var sampleLimit = Math.max(0, OVERVIEW_NODE_LIMIT - highSignalLimit);
    eligible
      .slice()
      .sort(function(a, b) {{
        var degreeDiff = (degree[b.id] || 0) - (degree[a.id] || 0);
        if (degreeDiff) return degreeDiff;
        return String(a.title || a.id).localeCompare(String(b.title || b.id));
      }})
      .slice(0, highSignalLimit)
      .forEach(markKeep);
    for (var i = 0; i < sampleLimit; i++) {{
      var sampled = eligible[Math.floor((i + 0.5) * eligible.length / Math.max(sampleLimit, 1))];
      markKeep(sampled);
    }}
    var fillIndex = 0;
    while (keepCount < OVERVIEW_NODE_LIMIT && fillIndex < eligible.length) {{
      markKeep(eligible[fillIndex]);
      fillIndex++;
    }}
    eligible.forEach(function(n) {{
      if (searchMatches(n)) markKeep(n);
      if (selectedNode && (n.id === selectedNode.id || isNeighbor(selectedNode.id, n.id))) markKeep(n);
    }});
    return eligible.filter(function(n) {{ return keep[n.id]; }});
  }}
  function visibleIds() {{
    if (visibleCache) return visibleCache;
    var byDepth = depthMap();
    var ids = {{}};
    var eligible = [];
    nodes.forEach(function(n) {{
      var categoryOk = categoryValue === 'all' || n.category === categoryValue;
      var depthOk = !byDepth || byDepth[n.id] !== undefined;
      var keepSelected = selectedNode && selectedNode.id === n.id;
      if ((categoryOk || keepSelected) && depthOk) eligible.push(n);
    }});
    capEligibleNodes(eligible).forEach(function(n) {{
      ids[n.id] = true;
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
  function graphTooLargeForDefaultLabels() {{
    return visibleNodes().length > LARGE_LABEL_LIMIT;
  }}
  function graphNeedsFastRender(currentNodes, currentEdges) {{
    return currentNodes.length > FAST_RENDER_NODE_LIMIT || currentEdges.length > FAST_RENDER_EDGE_LIMIT;
  }}
  function syncLabelsButton() {{
    if (!labelsButton) return;
    labelsButton.setAttribute('aria-pressed', showAllLabels ? 'true' : 'false');
    labelsButton.textContent = showAllLabels ? 'Hide labels' : (graphTooLargeForDefaultLabels() ? 'Show labels' : 'Labels');
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
      currentNodes.length + '/' + totalNodeCount + ' nodes',
      currentEdges.length + '/' + totalEdgeCount + ' edges',
      Math.round(zoom * 100) + '%'
    ];
    if (!fullGraphLoaded) parts.push('fast overview');
    if (categoryValue !== 'all') parts.push(categoryValue);
    if (depthValue !== 'all') parts.push('depth ' + depthValue);
    if (graphTooLargeForMotion()) parts.push('motion capped');
    if (graphTooLargeForDefaultLabels() && !showAllLabels) parts.push('labels sparse');
    if (graphNeedsFastRender(currentNodes, currentEdges)) parts.push('fast render');
    if (nodes.length > OVERVIEW_NODE_LIMIT && currentNodes.length < nodes.length) parts.push('overview capped');
    if (fullGraphLoaded && initialGraphMode !== 'full') parts.push('data loaded');
    if (fullGraphLoading) parts.push('loading graph data');
    if (showAllLabels) parts.push('labels all');
    if (searchTerm) {{
      var matches = totalSearchMatches();
      parts.push(matches + ' match' + (matches === 1 ? '' : 'es'));
      if (matches > SEARCH_LABEL_LIMIT) parts.push('match labels capped');
    }}
    var locked = pinnedCount();
    if (locked) parts.push(locked + ' placed');
    if (selectedNode) parts.push('selected ' + selectedNode.id);
    status.textContent = parts.join(' · ');
    syncLabelsButton();
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

  function strokeEdgeBatch(edgeList, strokeStyle, lineWidth) {{
    if (!edgeList.length) return;
    ctx.beginPath();
    edgeList.forEach(function(e) {{
      var a = toScreen(pos[e.source].x, pos[e.source].y);
      var b = toScreen(pos[e.target].x, pos[e.target].y);
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
    }});
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  }}

  function draw() {{
    ctx.clearRect(0, 0, W, H);
    var time = frame * 0.018;
    var currentNodes = visibleNodes();
    var currentEdges = visibleEdges();
    var animateFlow = !motionPaused && !graphTooLargeForMotion();
    var largeLabelSet = currentNodes.length > LARGE_LABEL_LIMIT;
    var fastRender = graphNeedsFastRender(currentNodes, currentEdges);

    if (fastRender) {{
      if (hoverNode) {{
        var activeEdges = [];
        var inactiveEdges = [];
        currentEdges.forEach(function(e) {{
          if (e.source === hoverNode.id || e.target === hoverNode.id) activeEdges.push(e);
          else inactiveEdges.push(e);
        }});
        strokeEdgeBatch(inactiveEdges, 'rgba(139,148,158,0.035)', 0.45);
        strokeEdgeBatch(activeEdges, 'rgba(88,166,255,0.42)', 1.1);
      }} else {{
        strokeEdgeBatch(currentEdges, 'rgba(88,166,255,0.07)', 0.45);
      }}
    }} else {{
      // Detailed edges for smaller or focused graph neighborhoods.
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
    }}

    // Nodes
    currentNodes.forEach(function(n) {{
      var s = toScreen(pos[n.id].x, pos[n.id].y);
      var r = nodeRadius(n) * Math.max(0.65, Math.min(1.2, zoom));
      var color = nodeColor(n);
      var pulse = fastRender ? 1 : Math.sin(time * 1.2 + (pos[n.id].x + pos[n.id].y) * 0.01) * 0.12 + 0.88;
      var activeNode = isActiveNode(n);
      var selected = selectedNode && selectedNode.id === n.id;
      var matched = searchMatches(n);
      ctx.save();
      ctx.globalAlpha = (hoverNode && !activeNode) || (searchTerm && !matched) ? 0.28 : 1;

      if (!fastRender || selected || matched || (hoverNode && activeNode)) {{
        // Radial glow stays off in large overview mode except for focused nodes.
        var glowR = r * 3.5 * pulse;
        var grad = ctx.createRadialGradient(s.x, s.y, r * 0.3, s.x, s.y, glowR);
        grad.addColorStop(0, color + '30');
        grad.addColorStop(1, color + '00');
        ctx.beginPath(); ctx.arc(s.x, s.y, glowR, 0, Math.PI*2);
        ctx.fillStyle = grad; ctx.fill();
      }}

      // Node body
      ctx.beginPath(); ctx.arc(s.x, s.y, r, 0, Math.PI*2);
      ctx.fillStyle = fastRender ? color + '28' : color + '40'; ctx.fill();

      // Node border
      ctx.beginPath(); ctx.arc(s.x, s.y, r, 0, Math.PI*2);
      ctx.strokeStyle = selected || matched ? '#ffffff' : color; ctx.lineWidth = selected || matched ? 2.4 : (fastRender ? 0.75 : 1.5);
      ctx.globalAlpha = 0.85; ctx.stroke(); ctx.globalAlpha = 1;

      // Inner bright core
      if (!fastRender || selected || matched || (hoverNode && activeNode)) {{
        ctx.beginPath(); ctx.arc(s.x, s.y, r * 0.35, 0, Math.PI*2);
        ctx.fillStyle = color + 'cc'; ctx.fill();
      }}

      // Labels stay sparse until a node is hovered.
      var label = n.title.length > 22 ? n.title.slice(0, 20) + '…' : n.title;
      var defaultSparseLabel = !largeLabelSet && n.category !== 'sources' && degree[n.id] >= 2;
      var showMatchLabel = matched && totalSearchMatches() <= SEARCH_LABEL_LIMIT;
      var showLabel = showAllLabels || selected || showMatchLabel || (hoverNode ? activeNode : defaultSparseLabel);
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
    invalidateSearchCache();
    categoryValue = 'all';
    depthValue = 'all';
    if (searchInput) searchInput.value = '';
    if (categoryFilter) categoryFilter.value = 'all';
    if (depthFilter) depthFilter.value = 'all';
    invalidateFilters();
    reseedVisiblePositions();
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

  function applyGraphPayload(payload) {{
    var nextNodes = (payload.nodes || []).filter(function(n) {{ return n.category !== 'root'; }});
    var ids = {{}};
    nextNodes.forEach(function(n) {{ ids[n.id] = true; }});
    var nextEdges = (payload.edges || []).filter(function(e) {{ return ids[e.source] && ids[e.target]; }});
    nodes = nextNodes;
    edges = nextEdges;
    totalNodeCount = nodes.length;
    totalEdgeCount = edges.length;
    fullGraphLoaded = true;
    fullGraphLoading = false;
    pinned = {{}};
    selectedNode = null;
    hoverNode = null;
    depthValue = 'all';
    if (depthFilter) depthFilter.value = 'all';
    rebuildGraphIndexes();
    syncCategoryOptions();
    invalidateSearchCache();
    invalidateFilters();
    if (!lockedOverviewIds) reseedVisiblePositions();
    frame = SETTLE;
    autoFit();
    updateInspector();
    setMotionPaused(true);
    if (loadFullButton) {{
      loadFullButton.disabled = true;
      loadFullButton.textContent = 'Graph data loaded';
    }}
  }}

  function loadFullGraph() {{
    if (fullGraphLoaded || fullGraphLoading) return;
    fullGraphLoading = true;
    if (loadFullButton) {{
      loadFullButton.disabled = true;
      loadFullButton.textContent = 'Loading graph data...';
    }}
    updateStatus();
    fetch('/api/graph')
      .then(function(response) {{
        if (!response.ok) throw new Error('graph load failed');
        return response.json();
      }})
      .then(function(payload) {{
        applyGraphPayload(payload);
        updateStatus();
        drawSoon();
      }})
      .catch(function() {{
        fullGraphLoading = false;
        if (loadFullButton) {{
          loadFullButton.disabled = false;
          loadFullButton.textContent = 'Retry graph data';
        }}
        if (status) status.textContent = 'Full graph load failed; local API did not return graph data.';
      }});
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
      syncLabelsButton();
      updateStatus();
      drawSoon();
      e.preventDefault();
    }}
  }});

  if (resetButton) resetButton.addEventListener('click', resetView);
  if (labelsButton) labelsButton.addEventListener('click', function() {{
    showAllLabels = !showAllLabels;
    syncLabelsButton();
    updateStatus();
    drawSoon();
  }});
  if (motionButton) motionButton.addEventListener('click', function() {{
    setMotionPaused(!motionPaused);
  }});
  if (fullscreenButton) fullscreenButton.addEventListener('click', function() {{
    setFullscreen(!frameEl.classList.contains('is-fullscreen'));
  }});
  if (loadFullButton) loadFullButton.addEventListener('click', loadFullGraph);
  if (inspectorOpen) inspectorOpen.addEventListener('click', function() {{ openNode(selectedNode); }});
  if (inspectorFocus) inspectorFocus.addEventListener('click', function() {{
    if (!selectedNode) return;
    depthValue = '1';
    if (depthFilter) depthFilter.value = '1';
    invalidateFilters();
    reseedVisiblePositions();
    setMotionPaused(motionPaused);
    autoFit();
    updateStatus();
    drawSoon();
  }});
  if (searchInput) {{
    searchInput.addEventListener('input', function() {{
      searchTerm = searchInput.value.trim().toLowerCase();
      invalidateSearchCache();
      invalidateFilters();
      if (searchTerm && !fullGraphLoaded) loadFullGraph();
      reseedVisiblePositions();
      autoFit();
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
    reseedVisiblePositions();
    setMotionPaused(motionPaused);
    autoFit();
    updateStatus();
    drawSoon();
  }});
  if (depthFilter) depthFilter.addEventListener('change', function() {{
    depthValue = depthFilter.value || 'all';
    invalidateFilters();
    reseedVisiblePositions();
    setMotionPaused(motionPaused);
    autoFit();
    updateStatus();
    drawSoon();
  }});

  window.addEventListener('resize', function() {{ resize(); if (fitted) autoFit(); updateStatus(); drawSoon(); }});
  resize();
  if (motionPaused) {{ reseedVisiblePositions(); autoFit(); fitted = true; frame = SETTLE; }}
  setMotionPaused(motionPaused);
  syncCategoryOptions();
  syncLabelsButton();
  updateInspector();
  updateStatus();
  if (shouldRunContinuously()) startLoop();
  else drawSoon();
}})();
</script>"""

    legend_items = _core_graph_legend_items(cat_colors)
    load_full_button = ""
    if graph_mode != "full":
        load_full_button = (
            f'<button id="graph-load-full" type="button">'
            f'Load graph data ({total_node_count} nodes)</button>'
        )

    body = (
        f'<div class="breadcrumb"><a href="/">Link</a> / graph</div>'
        f'<h1>Knowledge Graph</h1>'
        f'<p class="meta">For large wikis, use fullscreen, zoom, pan, and sparse labels. '
        f'The graph is for exploring neighborhoods, not reading every label at once.'
        f'{html.escape(graph_note)}</p>'
        f'<section id="graph-frame" class="graph-frame">'
        f'<div class="graph-toolbar" aria-label="Graph controls">'
        f'<button id="graph-reset" type="button">Reset</button>'
        f'<button id="graph-labels" type="button" aria-pressed="false">Labels</button>'
        f'<button id="graph-motion" type="button" aria-pressed="false">Motion on</button>'
        f'<button id="graph-fullscreen" type="button" aria-pressed="false">Fullscreen</button>'
        f'{load_full_button}'
        f'<label class="graph-control">Find'
        f'<input id="graph-search" type="search" placeholder="node title"></label>'
        f'<label class="graph-control">Type'
        f'<select id="graph-category">{category_options}</select></label>'
        f'<label class="graph-control">Neighborhood'
        f'<select id="graph-depth"><option value="all">all</option><option value="1">1 hop</option>'
        f'<option value="2">2 hops</option><option value="3">3 hops</option></select></label>'
        f'<span id="graph-status" class="graph-status" aria-live="polite">'
        f'{node_count}/{total_node_count} nodes · {edge_count}/{total_edge_count} edges</span>'
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
    results = _search_pages(q, limit=30) if q else []
    return _core_render_search_page(
        query,
        results,
        page_href=_page_href,
        layout=_layout,
        limit=30,
    )


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


def _get_graph_summary(topic: str = "", limit: int = 40, depth: int = 1, max_edges: int = 120) -> dict:
    """Return bounded graph context for agents and large local wikis."""
    return _core_graph_summary(
        _current_wiki_cache(),
        topic=topic,
        limit=limit,
        depth=depth,
        max_edges=max_edges,
    )


def _rebuild_backlinks_payload() -> dict[str, object]:
    try:
        result = _build_backlinks()
    except OSError as exc:
        return {"rebuilt": False, "error": f"Could not rebuild backlinks: {exc}"}
    bl_path = WIKI_DIR / "_backlinks.json"
    _core_atomic_write_json(bl_path, result)
    # Invalidate pages cache so next request picks up the new backlinks mtime.
    _invalidate_pages_cache()
    return {"rebuilt": True, "pages": len(result.get("backlinks", {}))}


def _rebuild_index_payload() -> dict[str, object]:
    try:
        result = _core_rebuild_index(WIKI_DIR, cache=_current_wiki_cache())
    except OSError as exc:
        return {"rebuilt": False, "error": f"Could not rebuild index: {exc}"}
    _invalidate_pages_cache()
    return result


def _validate_wiki_payload(strict: bool = False) -> dict[str, object]:
    return _core_validate_wiki(WIKI_DIR, strict=strict)


def _link_status_payload(include_validation: bool = False) -> dict[str, object]:
    payload = _core_link_status(
        WIKI_DIR,
        version=LINK_VERSION,
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
        try:
            self.do_GET()
        finally:
            self._head_only = False

    def do_OPTIONS(self):
        self._head_only = False
        if not self._require_allowed_host():
            return
        self._json(
            {"error": "CORS preflight is not supported; Link is localhost-only"},
            status=405,
            headers={"Allow": "GET, HEAD, POST"},
        )

    def do_PUT(self):
        self._method_not_allowed()

    def do_PATCH(self):
        self._method_not_allowed()

    def do_DELETE(self):
        self._method_not_allowed()

    def do_TRACE(self):
        self._method_not_allowed()

    def do_CONNECT(self):
        self._method_not_allowed()

    def do_POST(self):
        self._head_only = False
        if not self._require_allowed_host():
            return
        if not self._require_mutation_rate_limit():
            return
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
        if path == "/api/raw-source":
            if not self._require_local_action_header({"created": False}):
                return
            payload, error, status = self._read_json_body()
            if error:
                self._json({"created": False, "error": error}, status=status)
                return
            assert payload is not None
            result, http_status = _create_raw_source_payload(payload)
            self._json(result, status=http_status)
            return
        if path == "/api/propose-memories":
            payload, error, status = self._read_json_body()
            if error:
                self._json({"proposed": False, "error": error, "count": 0, "proposals": []}, status=status)
                return
            assert payload is not None
            text = _clean_text_input(payload.get("text"), max_len=MAX_POST_BYTES)
            if not text.strip():
                self._json({"proposed": False, "error": "text required", "count": 0, "proposals": []}, status=400)
                return
            source = _clean_text_input(payload.get("source") or "http", max_len=500) or "http"
            limit, limit_error = _parse_search_limit(str(payload.get("limit", "10")))
            if limit_error:
                self._json({"proposed": False, "error": limit_error, "count": 0, "proposals": []}, status=400)
                return
            result = _propose_memories_from_text(
                text,
                source=source,
                limit=min(limit, 20),
                project=_clean_text_input(payload.get("project"), max_len=80),
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
        if not self._require_allowed_host():
            return
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
            self._ok(_render_brief(
                query=_query_text(query, "q", "query"),
                project=_query_text(query, "project", max_len=80),
            ))
        elif path == "/propose":
            self._ok(_render_propose(
                project=_query_text(query, "project", max_len=80),
                source=_query_text(query, "source", max_len=500),
            ))
        elif path == "/prompts":
            self._ok(_render_prompts(project=_query_text(query, "project", max_len=80)))
        elif path == "/memory":
            self._ok(_render_memory_dashboard(project=_query_text(query, "project", max_len=80)))
        elif path == "/audit":
            self._ok(_render_memory_audit(project=_query_text(query, "project", max_len=80)))
        elif path == "/inbox":
            self._ok(_render_inbox(project=_query_text(query, "project", max_len=80)))
        elif path == "/captures":
            self._ok(_render_captures(project=_query_text(query, "project", max_len=80)))
        elif path == "/explain-memory":
            identifier = _query_text(query, "memory", "name", max_len=300)
            self._ok(_render_explain_memory(identifier))
        elif path == "/profile":
            self._ok(_render_profile(project=_query_text(query, "project", max_len=80)))
        elif path == "/all":
            self._ok(_render_all(query))
        elif path == "/graph":
            self._ok(_render_graph())
        elif path == "/search":
            self._ok(_render_search(_query_text(query, "q")))
        elif path.startswith("/page/"):
            page = _find_page(urllib.parse.unquote(path[6:]))
            if page: self._ok(_render_page(page))
            else: self._err(urllib.parse.unquote(path[6:]))
        elif path == "/api/pages":
            self._json(_all_pages())
        elif path == "/api/page-list":
            limit, limit_error = _core_parse_bounded_int(query.get("limit", ["100"])[0], "limit", 100, 1, 1000)
            offset, offset_error = _core_parse_bounded_int(query.get("offset", ["0"])[0], "offset", 0, 0, 1000000)
            error = limit_error or offset_error
            if error:
                self._json({"error": error}, status=400)
            else:
                assert limit is not None
                assert offset is not None
                self._json(_page_list_payload(
                    category=query.get("category", [""])[0],
                    page_type=query.get("type", [""])[0] or query.get("page_type", [""])[0],
                    maturity=query.get("maturity", [""])[0],
                    limit=limit,
                    offset=offset,
                    include_all=query.get("all", ["false"])[0].lower() in {"1", "true", "yes"},
                ))
        elif path == "/api/status":
            include_validation = query.get("validate", ["false"])[0].lower() in {"1", "true", "yes"}
            self._json(_link_status_payload(include_validation=include_validation))
        elif path == "/api/prompts":
            self._json(_starter_prompts_payload(project=_query_text(query, "project", max_len=80)))
        elif path == "/api/ingest-status":
            self._json(_ingest_status())
        elif path == "/api/backlinks":
            data, error = _load_backlinks_index()
            if error:
                self._json({"error": error}, status=500)
            else:
                self._json(data)
        elif path == "/api/page-links":
            limit, limit_error = _core_parse_bounded_int(query.get("limit", ["100"])[0], "limit", 100, 1, 1000)
            offset, offset_error = _core_parse_bounded_int(query.get("offset", ["0"])[0], "offset", 0, 0, 1000000)
            error = limit_error or offset_error
            if error:
                self._json({"error": error}, status=400)
            else:
                assert limit is not None
                assert offset is not None
                payload, status = _page_links_payload(
                    query.get("page", [""])[0] or query.get("page_name", [""])[0],
                    limit=limit,
                    offset=offset,
                    include_all=query.get("all", ["false"])[0].lower() in {"1", "true", "yes"},
                )
                self._json(payload, status=status)
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
        elif path == "/api/graph-summary":
            limit, limit_error = _core_parse_bounded_int(query.get("limit", ["40"])[0], "limit", 40, 1, 250)
            depth, depth_error = _core_parse_bounded_int(query.get("depth", ["1"])[0], "depth", 1, 0, 3)
            max_edges, edge_error = _core_parse_bounded_int(query.get("max_edges", ["120"])[0], "max_edges", 120, 0, 1000)
            error = limit_error or depth_error or edge_error
            if error:
                self._json({"error": error}, status=400)
            else:
                assert limit is not None
                assert depth is not None
                assert max_edges is not None
                self._json(_get_graph_summary(
                    topic=_query_text(query, "topic", "q"),
                    limit=limit,
                    depth=depth,
                    max_edges=max_edges,
                ))
        elif path == "/api/memory-profile":
            limit, error = _parse_search_limit(query.get("limit", ["10"])[0])
            if error:
                self._json({"error": error}, status=400)
            else:
                self._json(_memory_profile(limit=limit, project=_query_text(query, "project", max_len=80)))
        elif path == "/api/memory-dashboard":
            limit, error = _parse_search_limit(query.get("limit", ["12"])[0])
            if error:
                self._json({"error": error}, status=400)
            else:
                self._json(_memory_dashboard(limit=limit, project=_query_text(query, "project", max_len=80)))
        elif path == "/api/memory-brief":
            limit, error = _parse_search_limit(query.get("limit", ["6"])[0])
            if error:
                self._json({"error": error}, status=400)
            else:
                self._json(_memory_brief(
                    query=_query_text(query, "q", "query"),
                    limit=limit,
                    project=_query_text(query, "project", max_len=80),
                ))
        elif path == "/api/query-link":
            query_text = _query_text(query, "q", "query")
            if not query_text.strip():
                self._json({"found": False, "error": "query parameter required", "context_packet": []}, status=400)
            else:
                self._json(_query_link(
                    query=query_text,
                    budget=query.get("budget", ["medium"])[0],
                    project=_query_text(query, "project", max_len=80),
                ))
        elif path == "/api/memory-audit":
            limit, error = _parse_search_limit(query.get("limit", ["10"])[0])
            if error:
                self._json({"error": error}, status=400)
            else:
                self._json(_memory_audit(limit=limit, project=_query_text(query, "project", max_len=80)))
        elif path == "/api/memory-inbox":
            limit, error = _parse_search_limit(query.get("limit", ["20"])[0])
            if error:
                self._json({"error": error}, status=400)
            else:
                include_archived = query.get("include_archived", ["false"])[0].lower() in {"1", "true", "yes"}
                self._json(_memory_inbox(
                    limit=limit,
                    include_archived=include_archived,
                    project=_query_text(query, "project", max_len=80),
                ))
        elif path == "/api/capture-inbox":
            limit, error = _parse_search_limit(query.get("limit", ["20"])[0])
            if error:
                self._json({"error": error}, status=400)
            else:
                self._json(_capture_inbox(
                    limit=limit,
                    project=_query_text(query, "project", max_len=80),
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
        elif path == "/api/raw-source":
            self._json({"error": "use POST with JSON body: {\"text\": \"...\"}"}, status=405)
        elif path == "/api/propose-memories":
            self._json({"error": "use POST with JSON body: {\"text\": \"...\"}"}, status=405)
        elif path in {"/api/review-memory", "/api/archive-memory", "/api/restore-memory"}:
            self._json({"error": "use POST with JSON body: {\"memory\": \"...\"}"}, status=405)
        elif path == "/api/explain-memory":
            identifier = _query_text(query, "memory", "name", max_len=300)
            if not identifier:
                self._json({"found": False, "error": "memory parameter required"}, status=400)
            else:
                try:
                    self._json(_memory_explanation(identifier))
                except ValueError as exc:
                    self._json({"found": False, "error": str(exc)}, status=404)
        elif path == "/api/search":
            q = _query_text(query, "q")
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
            topic = _query_text(query, "topic", "q")
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
        self._no_store_headers()
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(encoded)

    def _err(self, name: str):
        encoded = _layout("Not Found", f"<h1>Not found</h1><p>No page: {html.escape(name)}</p>").encode()
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._security_headers()
        self.send_header("Content-Length", str(len(encoded)))
        self._no_store_headers()
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(encoded)

    def _json(self, data, status: int = 200, headers=None):
        encoded = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._security_headers()
        self._no_store_headers()
        for key, value in (headers or {}).items():
            self.send_header(str(key), str(value))
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(encoded)

    def _require_allowed_host(self) -> bool:
        allowed, error = _core_validate_local_host_header(self.headers.get("Host", ""))
        if allowed:
            return True
        self._json({"error": error}, status=403)
        return False

    def _require_local_action_header(self, error_payload: dict[str, object] | None = None) -> bool:
        value = self.headers.get(LOCAL_ACTION_HEADER, "").strip().lower()
        if value in LOCAL_ACTION_VALUES:
            allowed, error = _core_validate_local_browser_source_headers(
                self.headers.get("Origin", ""),
                self.headers.get("Referer", ""),
            )
            if allowed:
                return True
            payload = dict(error_payload or {"updated": False})
            payload["error"] = error
            self._json(payload, status=403)
            return False
        payload = dict(error_payload or {"updated": False})
        payload["error"] = f"{LOCAL_ACTION_HEADER} header required for local mutations"
        self._json({
            **payload,
        }, status=403)
        return False

    def _require_mutation_rate_limit(self) -> bool:
        client_host = self.client_address[0] if self.client_address else "local"
        allowed, retry_after = _mutation_rate_limiter.check(client_host)
        if allowed:
            return True
        self._json(
            {
                "error": "local mutation rate limit exceeded",
                "retry_after_seconds": retry_after,
            },
            status=429,
            headers={"Retry-After": str(retry_after)},
        )
        return False

    def _method_not_allowed(self) -> None:
        self._head_only = False
        if not self._require_allowed_host():
            return
        self._json(
            {"error": "method not allowed; Link supports GET, HEAD, and POST"},
            status=405,
            headers={"Allow": "GET, HEAD, POST"},
        )

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

    def _security_headers(self, content_security_policy: str = CONTENT_SECURITY_POLICY):
        for key, value in _core_local_security_headers(API_VERSION, content_security_policy):
            self.send_header(key, value)

    def _no_store_headers(self):
        for key, value in _core_local_no_store_headers():
            self.send_header(key, value)

    def _file(self, fpath, content_type):
        fpath = _safe_resolve(fpath)
        if not fpath or not _is_allowed_static_file(fpath):
            self._err("file")
            return
        if fpath.exists() and fpath.is_file():
            data = fpath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            if content_type == "image/svg+xml":
                self._security_headers(content_security_policy=SVG_CONTENT_SECURITY_POLICY)
            else:
                self._security_headers()
            self._no_store_headers()
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if not getattr(self, '_head_only', False):
                self.wfile.write(data)
        else:
            self._err("file")

    def log_message(self, *a): pass


def _parse_serve_args(argv: list[str], default_port: int = PORT, default_root: Path = ROOT) -> tuple[int, Path]:
    port = default_port
    root = default_root
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
        elif arg == "--root":
            if index + 1 >= len(argv):
                raise SystemExit("--root requires a value")
            root = Path(argv[index + 1]).expanduser().resolve()
        elif arg.startswith("--root="):
            root = Path(arg.split("=", 1)[1]).expanduser().resolve()
    if port < 1 or port > 65535:
        raise SystemExit("--port must be between 1 and 65535")
    return port, root


def _parse_serve_port(argv: list[str], default: int = PORT) -> int:
    port, _ = _parse_serve_args(argv, default_port=default, default_root=ROOT)
    return port


def _serve_bind_error_message(exc: OSError, port: int) -> str:
    if exc.errno in {errno.EADDRINUSE, 48, 98}:
        next_port = port + 1 if port < 65535 else 3000
        return (
            f"Link could not start because 127.0.0.1:{port} is already in use.\n"
            f"Try another port, for example: python serve.py --port {next_port}"
        )
    return f"Link could not start local server on 127.0.0.1:{port}: {exc}"


def main():
    global PORT, WIKI_DIR, RAW_DIR
    PORT, root = _parse_serve_args(sys.argv[1:], default_port=PORT, default_root=ROOT)
    WIKI_DIR = root / "wiki"
    RAW_DIR = root / "raw"
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as s:
            print(f"  Link → http://127.0.0.1:{PORT}")
            print("  Local-only: bound to 127.0.0.1; no public host mode.")
            print("  No auth: do not expose this server without your own authentication layer.")
            try: s.serve_forever()
            except KeyboardInterrupt: print("\n  stopped.")
    except OSError as exc:
        print(_serve_bind_error_message(exc, PORT), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
