#!/usr/bin/env python3
"""
Link MCP Server

Exposes the Link personal knowledge wiki as MCP tools.
Agents can search, query context, and traverse the knowledge graph
without reading files directly.

Install:
  pip install link-mcp

Usage:
  python -m link_mcp                      # uses ~/link/wiki/
  python -m link_mcp --wiki /path/wiki    # custom wiki path

Add to your MCP client config:
  {
    "mcpServers": {
      "link": {
        "command": "python3",
        "args": ["-m", "link_mcp"]
      }
    }
  }
"""
from __future__ import annotations
import argparse, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

# ── Resolve wiki directory ────────────────────────────────────────────
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--wiki", default=None)
args, _ = parser.parse_known_args()

if args.wiki:
    WIKI_DIR = Path(args.wiki).expanduser().resolve()
else:
    WIKI_DIR = Path.home() / "link" / "wiki"

if not WIKI_DIR.exists():
    print(f"[link-mcp] Wiki not found at {WIKI_DIR}. Run install.sh first.", file=sys.stderr)
    sys.exit(1)

# ── Import MCP SDK ────────────────────────────────────────────────────
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("[link-mcp] mcp package not found. Install with: pip install mcp", file=sys.stderr)
    sys.exit(1)

mcp = FastMCP(
    "link",
    instructions=(
        "Link is local personal memory for agents. Start with memory_brief at "
        "session start or before personalized/project work; pass the user's "
        "task as the query when available. Use recall_memory for focused user "
        "preferences, decisions, and project context, memory_profile to inspect "
        "what Link remembers, memory_inbox to find memories needing review, and "
        "explain_memory to audit why a memory exists. Use capture_session for "
        "long chat or session notes that should be stored locally before memory "
        "approval, and capture_inbox to review saved captures before accepting, "
        "redacting, or deleting them; use propose_memories when no raw capture is needed. Use search_wiki to find "
        "general pages and get_context to retrieve a topic with its full graph "
        "neighborhood. Only call remember_memory when the user explicitly asks "
        "you to remember something; if it returns duplicate candidates, use "
        "update_memory on the existing memory instead of forcing a duplicate. "
        "If it returns conflict candidates, ask the user whether to update or "
        "archive the older memory before forcing a conflict. "
        "Use archive_memory instead of deleting stale or wrong memories."
    ),
)

# ── In-memory indexes (built on first use, invalidated by mtime) ──────
_cache: dict = {}
_cache_mtime: float = 0.0
MAX_TEXT_INPUT = 200
MAX_CAPTURE_INPUT = 12000

from link_core.memory import (
    count_values as _core_count_values,
    mark_memory_reviewed as _core_mark_memory_reviewed,
    memory_brief as _core_memory_brief,
    memory_explanation as _core_memory_explanation,
    memory_inbox as _core_memory_inbox,
    memory_profile as _core_memory_profile,
    memory_records as _core_memory_records,
    normalize_project as _core_normalize_project,
    memory_review_issues as _core_memory_review_issues,
    propose_memories_from_text as _core_propose_memories_from_text,
    recall_memories as _core_recall_memories,
    recent_memories as _core_recent_memories,
    resolve_memory_page as _core_resolve_memory_page,
    set_memory_status as _core_set_memory_status,
    slim_memory as _core_slim_memory,
    slugify as _core_slugify,
    top_tags as _core_top_tags,
    update_memory_page as _core_update_memory_page,
    write_memory_page as _core_write_memory_page,
)
from link_core.frontmatter import (
    frontmatter_string as _frontmatter_string,
    parse_frontmatter as _parse_frontmatter,
)
from link_core.security import (
    redact_secret_values as _redact_secret_values,
    secret_value_warnings as _secret_value_warnings,
)
from link_core.wiki import (
    build_backlinks as _core_build_backlinks,
    build_wiki_cache as _core_build_wiki_cache,
    context_for_topic as _core_context_for_topic,
    graph_data as _core_graph_data,
    load_backlinks_index as _core_load_backlinks_index,
    search_pages as _core_search_pages,
    wiki_mtime as _core_wiki_mtime,
)


def _clean_text_input(value, max_len: int = MAX_TEXT_INPUT) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text[:max_len]


def _parse_limit(value, default: int = 20, max_limit: int = 50) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(limit, 1), max_limit)


def _default_project() -> str:
    root = WIKI_DIR.parent
    if (root / ".git").exists():
        return _core_slugify(root.name, fallback="")
    return ""


def _wiki_mtime() -> float:
    return _core_wiki_mtime(WIKI_DIR)


def _build_cache() -> dict:
    global _cache, _cache_mtime
    mtime = _wiki_mtime()
    if _cache and mtime == _cache_mtime:
        return _cache

    _cache = _core_build_wiki_cache(WIKI_DIR)
    _cache_mtime = mtime
    return _cache


def _search(q: str, limit: int = 20) -> list[dict]:
    q = _clean_text_input(q)
    limit = _parse_limit(limit)
    if not q:
        return []
    return _core_search_pages(q, _build_cache(), limit=limit)


def _get_context(topic: str) -> dict:
    topic = _clean_text_input(topic)
    return _core_context_for_topic(WIKI_DIR, topic, _build_cache(), empty_error="topic required")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _memory_records() -> list[dict[str, object]]:
    return _core_memory_records(WIKI_DIR)


def _slim_memory(record: dict[str, object]) -> dict[str, object]:
    return _core_slim_memory(record)


def _memory_review_issues(record: dict[str, object]) -> list[dict[str, str]]:
    return _core_memory_review_issues(record, review_command="review_memory")


def _memory_inbox(limit: int = 20, include_archived: bool = False, project: str = "") -> dict[str, object]:
    return _core_memory_inbox(
        _memory_records(),
        limit=limit,
        include_archived=include_archived,
        review_command="review_memory",
        project=project,
    )


def _memory_explanation(identifier: str) -> dict[str, object]:
    return _core_memory_explanation(
        WIKI_DIR,
        identifier,
        records=_memory_records(),
        review_command="review_memory",
    )


def _count_values(records: list[dict[str, object]], field: str) -> dict[str, int]:
    return _core_count_values(records, field)


def _top_tags(records: list[dict[str, object]], limit: int = 12) -> list[dict[str, object]]:
    return _core_top_tags(records, limit=limit)


def _recent_memories(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return _core_recent_memories(records)


def _resolve_project(project: str = "") -> str:
    return _clean_text_input(project) or _default_project()


def _memory_profile(limit: int = 10, project: str = "") -> dict[str, object]:
    return _core_memory_profile(
        _memory_records(),
        limit=limit,
        review_command="review_memory",
        project=_resolve_project(project),
    )


def _memory_brief(query: str = "", limit: int = 6, project: str = "") -> dict[str, object]:
    return _core_memory_brief(
        _memory_records(),
        query=_clean_text_input(query, max_len=500),
        limit=limit,
        review_command="review_memory",
        project=_resolve_project(project),
    )


def _recall_memories(
    query: str,
    limit: int = 10,
    include_archived: bool = False,
    project: str = "",
) -> list[dict[str, object]]:
    query = _clean_text_input(query)
    return _core_recall_memories(
        _memory_records(),
        query,
        limit=limit,
        include_archived=include_archived,
        project=_resolve_project(project),
    )


def _propose_memories_from_text(
    text: str,
    source: str = "mcp",
    limit: int = 10,
    project: str = "",
) -> dict[str, object]:
    return _core_propose_memories_from_text(
        text,
        _memory_records(),
        source=source,
        limit=limit,
        writes_memory=False,
        project=_resolve_project(project),
    )


def _capture_title(text: str, source: str, title: str = "") -> str:
    if title.strip():
        return " ".join(title.split())
    if source.strip() and source.strip() != "mcp":
        return f"Memory capture: {' '.join(source.strip().split())[:120]}"
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "Session notes")
    short = " ".join(first_line.split()[:10]).strip(" .")
    return f"Memory capture: {short or 'Session notes'}"


def _capture_filename(timestamp: str, title: str, raw_dir: Path) -> Path:
    safe_stamp = timestamp.replace("-", "").replace(":", "")
    slug = _core_slugify(title.replace("Memory capture:", ""), fallback="session-notes")
    base = f"{safe_stamp}-{slug}"
    candidate = raw_dir / f"{base}.md"
    counter = 2
    while candidate.exists():
        candidate = raw_dir / f"{base}-{counter}.md"
        counter += 1
    return candidate


def _capture_session(
    text: str,
    title: str = "",
    source: str = "mcp",
    limit: int = 10,
    project: str = "",
) -> dict[str, object]:
    clean_text = _clean_text_input(text, max_len=MAX_CAPTURE_INPUT)
    if not clean_text:
        raise ValueError("session text required")
    clean_source = _clean_text_input(source, max_len=500) or "mcp"
    project_name = _resolve_project(project)
    timestamp = _utc_timestamp()
    capture_title = _capture_title(clean_text, clean_source, _clean_text_input(title, max_len=200))
    secret_warnings = _secret_value_warnings(clean_text)
    root = WIKI_DIR.parent
    capture_dir = root / "raw" / "memory-captures"
    capture_dir.mkdir(parents=True, exist_ok=True)
    capture_path = _capture_filename(timestamp, capture_title, capture_dir)
    project_line = f'project: "{_frontmatter_string(project_name)}"\n' if project_name else ""
    capture_path.write_text(
        f"""---
title: "{_frontmatter_string(capture_title)}"
source_type: conversation
date_captured: "{timestamp}"
{project_line}---

# {capture_title}

Captured locally for Link memory review. This raw note is proposal-only until the user approves durable memories.

## Source Input

{clean_source}

## Notes

{clean_text}
""",
        encoding="utf-8",
    )
    rel_path = capture_path.relative_to(root).as_posix()
    proposals = _propose_memories_from_text(
        clean_text,
        source=rel_path,
        limit=limit,
        project=project_name,
    )
    _append_log(
        timestamp,
        "capture-session",
        f"Captured proposal-only session notes at {rel_path}",
        [
            f"Source input: {clean_source}",
            f"Project: {project_name or 'none'}",
            f"Secret warnings: {', '.join(secret_warnings) if secret_warnings else 'none'}",
            f"Proposals: {proposals['count']}",
        ],
    )
    _cache.clear()
    return {
        "captured": True,
        "path": rel_path,
        "source": clean_source,
        "title": capture_title,
        "project": project_name,
        "secret_warnings": secret_warnings,
        "proposals": proposals,
    }


def _resolve_capture_file(capture: str) -> Path | None:
    root = WIKI_DIR.parent
    raw = _clean_text_input(capture, max_len=500)
    if not raw:
        return None
    candidates = [Path(raw).expanduser()]
    if not Path(raw).is_absolute():
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


def _capture_notes_from_markdown(text: str) -> tuple[dict[str, object], str]:
    meta, body = _parse_frontmatter(text)
    match = re.search(r"^## Notes\s*(.*?)(?=^## |\Z)", body, flags=re.MULTILINE | re.DOTALL)
    notes = match.group(1).strip() if match else body.strip()
    return meta, notes


def _capture_records(limit: int = 20, project: str = "") -> list[dict[str, object]]:
    root = WIKI_DIR.parent
    capture_dir = root / "raw" / "memory-captures"
    if not capture_dir.exists():
        return []
    project_name = _core_normalize_project(project)
    records: list[dict[str, object]] = []
    for path in sorted(capture_dir.rglob("*.md")):
        if path.name.startswith("."):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            stat = path.stat()
        except OSError:
            continue
        meta, notes = _capture_notes_from_markdown(text)
        capture_project = _core_normalize_project(str(meta.get("project") or ""))
        if project_name and capture_project and capture_project != project_name:
            continue
        rel = path.relative_to(root).as_posix()
        warnings = _secret_value_warnings(text)
        safe_notes, _, _ = _redact_secret_values(notes)
        records.append({
            "path": rel,
            "title": str(meta.get("title") or path.stem),
            "project": capture_project,
            "date_captured": str(meta.get("date_captured") or ""),
            "size_bytes": stat.st_size,
            "secret_warnings": warnings,
            "warning_count": len(warnings),
            "snippet": re.sub(r"\s+", " ", safe_notes).strip()[:180],
            "commands": {
                "accept": f'accept_capture(capture="{rel}", index=1)',
                "redact": f'redact_capture(capture="{rel}")',
                "delete": f'delete_capture(capture="{rel}", confirm=true)',
            },
        })
    records.sort(key=lambda item: (str(item["date_captured"]), str(item["path"])), reverse=True)
    return records[:max(1, min(limit, 50))]


def _capture_inbox(limit: int = 20, project: str = "") -> dict[str, object]:
    project_name = _core_normalize_project(project)
    captures = _capture_records(limit=limit, project=project_name)
    return {
        "count": len(captures),
        "warning_count": sum(1 for capture in captures if capture["warning_count"]),
        "project": project_name,
        "captures": captures,
    }


def _accept_capture(
    capture: str,
    index: int = 1,
    title: str = "",
    memory_type: str = "",
    scope: str = "",
    tags: str = "",
    project: str = "",
    allow_duplicate: bool = False,
    allow_conflict: bool = False,
) -> dict[str, object]:
    try:
        proposal_index = int(index)
    except (TypeError, ValueError):
        raise ValueError("proposal index must be an integer")
    if proposal_index < 1:
        raise ValueError("proposal index must be 1 or greater")

    root = WIKI_DIR.parent
    capture_path = _resolve_capture_file(capture)
    if capture_path is None:
        raise ValueError(f"capture not found: {_clean_text_input(capture, max_len=500)}")
    raw_text = capture_path.read_text(encoding="utf-8", errors="replace")
    meta, notes = _capture_notes_from_markdown(raw_text)
    if not notes:
        raise ValueError("capture has no notes")

    rel_path = capture_path.relative_to(root).as_posix()
    project_name = _core_slugify(
        _clean_text_input(project) or str(meta.get("project") or "") or _default_project(),
        fallback="",
    )
    proposals = _propose_memories_from_text(
        notes,
        source=rel_path,
        limit=max(1, min(max(proposal_index, 10), 50)),
        project=project_name,
    )
    if proposal_index > len(proposals["proposals"]):
        raise ValueError(f"capture has {len(proposals['proposals'])} proposal(s); index {proposal_index} is unavailable")
    proposal = proposals["proposals"][proposal_index - 1]
    chosen_scope = _clean_text_input(scope).lower() or str(proposal["scope"])
    chosen_project = project_name if chosen_scope == "project" else ""
    result = _write_memory_page(
        str(proposal["memory"]),
        title=_clean_text_input(title) or str(proposal["title"]),
        memory_type=_clean_text_input(memory_type).lower() or str(proposal["memory_type"]),
        scope=chosen_scope,
        tags=tags,
        source=rel_path,
        allow_duplicate=allow_duplicate,
        allow_conflict=allow_conflict,
        project=chosen_project,
    )
    payload = {
        "accepted": bool(result.get("created")),
        "capture": rel_path,
        "proposal_index": proposal_index,
        "proposal": proposal,
        "result": result,
    }
    if result.get("created"):
        _append_log(
            _utc_timestamp(),
            "accept-capture",
            f"Accepted proposal {proposal_index} from {rel_path}",
            [
                f"Memory: {result['path']}",
                f"Project: {result.get('project') or 'none'}",
            ],
        )
    return payload


def _redact_capture(capture: str, replacement: str = "[redacted-secret]") -> dict[str, object]:
    root = WIKI_DIR.parent
    capture_path = _resolve_capture_file(capture)
    if capture_path is None:
        raise ValueError(f"capture not found: {_clean_text_input(capture, max_len=500)}")
    original = capture_path.read_text(encoding="utf-8", errors="replace")
    redacted, labels, replacement_count = _redact_secret_values(
        original,
        replacement=_clean_text_input(replacement, max_len=100) or "[redacted-secret]",
    )
    rel_path = capture_path.relative_to(root).as_posix()
    if replacement_count:
        capture_path.write_text(redacted, encoding="utf-8")
        _append_log(
            _utc_timestamp(),
            "redact-capture",
            f"Redacted secret-looking values from {rel_path}",
            [
                f"Labels: {', '.join(labels)}",
                f"Replacement count: {replacement_count}",
            ],
        )
    return {
        "redacted": bool(replacement_count),
        "path": rel_path,
        "labels": labels,
        "replacement_count": replacement_count,
    }


def _delete_capture(capture: str, confirm: bool = False) -> dict[str, object]:
    root = WIKI_DIR.parent
    capture_path = _resolve_capture_file(capture)
    if capture_path is None:
        raise ValueError(f"capture not found: {_clean_text_input(capture, max_len=500)}")
    rel_path = capture_path.relative_to(root).as_posix()
    payload = {
        "deleted": False,
        "path": rel_path,
        "confirmation_required": not confirm,
    }
    if not confirm:
        return payload
    capture_path.unlink()
    _append_log(
        _utc_timestamp(),
        "delete-capture",
        f"Deleted raw capture {rel_path}",
        ["Deleted file only; capture contents were not logged."],
    )
    payload["deleted"] = True
    payload["confirmation_required"] = False
    return payload


def _append_log(timestamp: str, operation: str, description: str, lines: list[str]) -> None:
    log_path = WIKI_DIR / "log.md"
    if not log_path.exists():
        log_path.write_text("# Link Wiki Log\n\n*Append-only record of wiki operations.*\n", encoding="utf-8")
    entry = [f"## [{timestamp}] {operation} | {description}", ""]
    entry.extend(f"- {line}" for line in lines)
    entry.extend(["", "---", ""])
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(entry))


def _resolve_memory_page(identifier: str) -> tuple[Path | None, dict[str, object] | None, str | None]:
    return _core_resolve_memory_page(
        WIKI_DIR,
        identifier,
        records=_memory_records(),
        max_identifier_len=300,
    )


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
        _cache.clear()
    return result


def _mark_memory_reviewed(identifier: str, note: str = "") -> dict[str, object]:
    result = _core_mark_memory_reviewed(
        WIKI_DIR,
        _clean_text_input(identifier, max_len=300),
        note=_clean_text_input(note, max_len=500),
        timestamp=_utc_timestamp(),
        records=_memory_records(),
        review_command="review_memory",
        log_writer=_append_log,
    )
    if result["updated"]:
        _cache.clear()
    return result


def _update_memory_page(
    identifier: str,
    text: str,
    source: str = "mcp",
    allow_conflict: bool = False,
    project: str = "",
) -> dict[str, object]:
    clean_text = _clean_text_input(text, max_len=4000)
    if not clean_text:
        raise ValueError("memory update text required")
    clean_source = _clean_text_input(source, max_len=500) or "mcp"

    def rebuild_memory_backlinks() -> bool:
        rebuilt = json.loads(rebuild_backlinks())
        return bool(rebuilt.get("rebuilt"))

    result = _core_update_memory_page(
        WIKI_DIR,
        _clean_text_input(identifier, max_len=300),
        clean_text,
        source=clean_source,
        timestamp=_utc_timestamp(),
        records=_memory_records(),
        review_command="review_memory",
        allow_conflict=allow_conflict,
        project=_resolve_project(project),
        log_writer=_append_log,
        rebuild_backlinks=rebuild_memory_backlinks,
    )
    _cache.clear()
    return result


def _write_memory_page(
    text: str,
    title: str = "",
    memory_type: str = "note",
    scope: str = "user",
    tags: str = "",
    source: str = "mcp",
    allow_duplicate: bool = False,
    allow_conflict: bool = False,
    project: str = "",
) -> dict[str, object]:
    clean_text = _clean_text_input(text, max_len=4000)
    if not clean_text:
        raise ValueError("memory text required")
    memory_type = _clean_text_input(memory_type).lower() or "note"
    scope = _clean_text_input(scope).lower() or "user"

    def rebuild_memory_backlinks() -> bool:
        rebuilt = json.loads(rebuild_backlinks())
        return bool(rebuilt.get("rebuilt"))

    result = _core_write_memory_page(
        WIKI_DIR,
        clean_text,
        title=_clean_text_input(title),
        memory_type=memory_type,
        scope=scope,
        tags=_clean_text_input(tags, max_len=500),
        source=_clean_text_input(source, max_len=500),
        timestamp=_utc_timestamp(),
        project=_resolve_project(project),
        records=_memory_records(),
        allow_duplicate=allow_duplicate,
        allow_conflict=allow_conflict,
        log_writer=_append_log,
        rebuild_backlinks=rebuild_memory_backlinks,
    )
    if result.get("created"):
        _cache.clear()
    return result


# ── MCP Tools ─────────────────────────────────────────────────────────

@mcp.tool()
def memory_brief(query: str = "", limit: int = 6, project: str = "") -> str:
    """Prime the agent with local memory before answering or coding.

    Call this at the start of a session or before a user task that may depend
    on preferences, project decisions, or personal context. It returns profile
    counts, relevant memories for the query, review warnings, and rules for
    safe memory use.
    """
    limit = _parse_limit(limit, default=6, max_limit=20)
    return json.dumps(_memory_brief(query=query, limit=limit, project=project), ensure_ascii=False)


@mcp.tool()
def search_wiki(query: str, limit: int = 20) -> str:
    """Search the Link wiki by title, alias, tag, and full-text content.

    Returns ranked results with scores and snippets. Scoring:
    - Exact name match: 20pts
    - Title match: 10pts
    - Alias match: 8pts
    - Tag match: 5pts
    - TLDR match: 3pts
    - Full-text match: 2pts

    Use this to find relevant pages before calling get_context.
    """
    query = _clean_text_input(query)
    limit = _parse_limit(limit)
    if not query:
        return json.dumps({"error": "query required", "query": "", "count": 0, "results": []})

    results = _search(query, limit=limit)
    if not results:
        return json.dumps({"query": query, "count": 0, "results": []})
    # Strip heavy fields for the search response
    slim = [{k: v for k, v in r.items() if k not in ("aliases",)} for r in results]
    return json.dumps({"query": query, "count": len(slim), "results": slim}, ensure_ascii=False)


@mcp.tool()
def recall_memory(query: str, limit: int = 10, include_archived: bool = False, project: str = "") -> str:
    """Search local agent memory pages first.

    Use this when the user asks about preferences, decisions, project context,
    or anything the agent should remember across sessions. Returns only pages
    under wiki/memories/. Archived and stale memories are excluded unless
    include_archived is true.
    """
    query = _clean_text_input(query)
    limit = _parse_limit(limit, default=10)
    if not query:
        return json.dumps({"error": "query required", "query": "", "count": 0, "memories": []})
    project_name = _resolve_project(project)
    memories = _recall_memories(query, limit=limit, include_archived=include_archived, project=project_name)
    return json.dumps({
        "query": query,
        "count": len(memories),
        "include_archived": include_archived,
        "project": project_name,
        "memories": memories,
    }, ensure_ascii=False)


@mcp.tool()
def propose_memories(text: str, source: str = "mcp", limit: int = 10, project: str = "") -> str:
    """Propose durable memories from chat or session notes without writing them.

    Returns conservative memory proposals with type, scope, confidence, reason,
    duplicate candidates, and a suggested follow-up action. Use remember_memory
    or update_memory after the user confirms a proposal.
    """
    clean_text = _clean_text_input(text, max_len=12000)
    if not clean_text:
        return json.dumps({"proposed": False, "error": "text required", "count": 0, "proposals": []})
    source = _clean_text_input(source, max_len=500) or "mcp"
    limit = _parse_limit(limit, default=10, max_limit=20)
    return json.dumps(_propose_memories_from_text(clean_text, source=source, limit=limit, project=project), ensure_ascii=False)


@mcp.tool()
def capture_session(text: str, title: str = "", source: str = "mcp", limit: int = 10, project: str = "") -> str:
    """Save long chat/session notes locally and return memory proposals only.

    Writes a raw note under raw/memory-captures/ and logs the capture, but does
    not create durable memory pages. Use this when the user wants the session
    preserved for review before approving remember_memory or update_memory.
    """
    limit = _parse_limit(limit, default=10, max_limit=20)
    try:
        result = _capture_session(text, title=title, source=source, limit=limit, project=project)
    except ValueError as exc:
        return json.dumps({
            "captured": False,
            "error": str(exc),
            "proposals": {"proposed": False, "count": 0, "proposals": []},
        })
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def capture_inbox(limit: int = 20, project: str = "") -> str:
    """List saved raw session captures without changing them.

    Returns saved captures, secret-warning labels, redacted snippets, and the
    next MCP tool calls for accepting, redacting, or deleting a capture.
    """
    limit = _parse_limit(limit, default=20, max_limit=50)
    return json.dumps(_capture_inbox(limit=limit, project=project), ensure_ascii=False)


@mcp.tool()
def accept_capture(
    capture: str,
    index: int = 1,
    title: str = "",
    memory_type: str = "",
    scope: str = "",
    tags: str = "",
    project: str = "",
    allow_duplicate: bool = False,
    allow_conflict: bool = False,
) -> str:
    """Accept one proposal from a saved raw session capture.

    Recomputes proposals from raw/memory-captures, selects the 1-based index,
    and writes the chosen memory through duplicate/conflict-safe creation.
    """
    try:
        result = _accept_capture(
            capture,
            index=index,
            title=title,
            memory_type=memory_type,
            scope=scope,
            tags=tags,
            project=project,
            allow_duplicate=allow_duplicate,
            allow_conflict=allow_conflict,
        )
    except ValueError as exc:
        return json.dumps({"accepted": False, "error": str(exc)})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def redact_capture(capture: str, replacement: str = "[redacted-secret]") -> str:
    """Redact secret-looking values from a saved raw session capture.

    Use after capture_session returns secret_warnings and the user approves
    redaction. Logs warning labels and counts only, never secret values.
    """
    try:
        result = _redact_capture(capture, replacement=replacement)
    except ValueError as exc:
        return json.dumps({"redacted": False, "error": str(exc)})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def delete_capture(capture: str, confirm: bool = False) -> str:
    """Delete a saved raw session capture after explicit user confirmation.

    The tool refuses to delete unless confirm is true. It logs the capture path
    and deletion operation only, never the capture contents.
    """
    try:
        result = _delete_capture(capture, confirm=confirm)
    except ValueError as exc:
        return json.dumps({"deleted": False, "error": str(exc)})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def memory_profile(limit: int = 10, project: str = "") -> str:
    """Summarize what Link currently remembers.

    Use this to inspect the local memory profile before doing personalized work.
    Returns counts by type/scope/status, top tags, recent memories, and focused
    lists for preferences, decisions, and project context.
    """
    limit = _parse_limit(limit, default=10)
    return json.dumps(_memory_profile(limit=limit, project=project), ensure_ascii=False)


@mcp.tool()
def memory_inbox(limit: int = 20, include_archived: bool = False, project: str = "") -> str:
    """List memories that need user review.

    Use this to surface pending, stale, invalid, or underspecified memories for
    human confirmation. Archived memories are excluded unless include_archived
    is true. Pass project to include broad user/global memory plus that
    project's scoped memories while excluding other explicit projects.
    """
    limit = _parse_limit(limit, default=20)
    return json.dumps(_memory_inbox(limit=limit, include_archived=include_archived, project=project), ensure_ascii=False)


@mcp.tool()
def review_memory(identifier: str, note: str = "") -> str:
    """Mark a memory as reviewed after user confirmation."""
    try:
        result = _mark_memory_reviewed(identifier, note=note)
    except ValueError as exc:
        return json.dumps({"updated": False, "error": str(exc)})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def explain_memory(identifier: str) -> str:
    """Explain why a memory exists and whether it is ready for recall.

    Returns provenance, review state, lifecycle state, graph links, recent log
    entries, and detected quality issues for one memory.
    """
    try:
        result = _memory_explanation(identifier)
    except ValueError as exc:
        return json.dumps({"found": False, "error": str(exc)})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def update_memory(
    identifier: str,
    memory: str,
    source: str = "mcp",
    allow_conflict: bool = False,
    project: str = "",
) -> str:
    """Merge new information into an existing active memory.

    Use this when remember_memory returns a duplicate candidate or when the user
    asks to update something Link already remembers. The update is appended to
    the memory body, logged, and marked pending review.
    """
    try:
        result = _update_memory_page(
            identifier,
            memory,
            source=source,
            allow_conflict=allow_conflict,
            project=project,
        )
    except ValueError as exc:
        return json.dumps({"updated": False, "error": str(exc)})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def archive_memory(identifier: str, reason: str = "") -> str:
    """Archive a memory without deleting its Markdown page.

    Use this when the user says a memory is stale, wrong, or no longer useful.
    The page remains local and inspectable, recall_memory hides it by default,
    and the operation is appended to wiki/log.md.
    """
    try:
        result = _set_memory_status(identifier, "archived", reason=reason)
    except ValueError as exc:
        return json.dumps({"updated": False, "error": str(exc)})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def restore_memory(identifier: str) -> str:
    """Restore an archived memory to active status."""
    try:
        result = _set_memory_status(identifier, "active")
    except ValueError as exc:
        return json.dumps({"updated": False, "error": str(exc)})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def remember_memory(
    memory: str,
    title: str = "",
    memory_type: str = "note",
    scope: str = "user",
    tags: str = "",
    source: str = "mcp",
    allow_duplicate: bool = False,
    allow_conflict: bool = False,
    project: str = "",
) -> str:
    """Save a local agent memory as a Markdown page.

    Use only when the user explicitly asks you to remember something. The memory
    is written under wiki/memories/, indexed, logged, and kept local. Strong
    duplicates are refused unless allow_duplicate is true.
    Potential conflicts are refused unless allow_conflict is true.
    memory_type: preference, decision, project, fact, or note.
    scope: user, project, or global.
    project: optional project key for project-scoped memories.
    tags: optional comma-separated tags.
    """
    try:
        result = _write_memory_page(
            memory,
            title=title,
            memory_type=memory_type,
            scope=scope,
            tags=tags,
            source=source,
            allow_duplicate=allow_duplicate,
            allow_conflict=allow_conflict,
            project=project,
        )
    except ValueError as exc:
        return json.dumps({"created": False, "error": str(exc)})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def get_context(topic: str) -> str:
    """Get full context for a topic from the Link wiki.

    Returns the best matching page (full content) plus all related pages
    via graph traversal (inbound links + forward links). This is the
    primary tool for answering questions — one call gives you everything
    needed to synthesize an answer.

    The response includes:
    - primary: the best matching page with full markdown content
    - inbound: pages that link TO this page
    - forward: pages this page links TO
    - relationship field on each page: "primary", "inbound", or "forward"
    """
    result = _get_context(topic)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def get_pages(category: str = "", page_type: str = "", maturity: str = "") -> str:
    """List all pages in the Link wiki with metadata.

    Optional filters:
    - category: "memories", "concepts", "entities", "sources", "comparisons", "explorations"
    - page_type: "memory", "concept", "entity", "source", "comparison", "exploration"
    - maturity: "seed", "growing", "mature", "established"

    Returns pages with: name, title, category, type, tags, aliases, maturity,
    source_count, tldr, date_updated. Does not include full page content.
    """
    c = _build_cache()
    pages = c["pages"]
    category = _clean_text_input(category).lower()
    page_type = _clean_text_input(page_type).lower()
    maturity = _clean_text_input(maturity).lower()
    if category:
        pages = [p for p in pages if p["category"] == category]
    if page_type:
        pages = [p for p in pages if p["type"] == page_type]
    if maturity:
        pages = [p for p in pages if p["maturity"] == maturity]
    return json.dumps({"count": len(pages), "pages": pages}, ensure_ascii=False)


@mcp.tool()
def get_backlinks(page_name: str) -> str:
    """Get all pages that link to or from a given wiki page.

    Returns:
    - inbound: pages that link TO this page (who references it)
    - forward: pages this page links TO (what it references)

    Useful for understanding a page's position in the knowledge graph.
    """
    backlinks, error = _core_load_backlinks_index(WIKI_DIR / "_backlinks.json", missing_error="backlinks not built — run rebuild_backlinks first")
    if error:
        return json.dumps({"error": error})

    page_name = _clean_text_input(page_name)
    if not page_name:
        return json.dumps({"error": "page_name required", "inbound": [], "forward": []})

    name = page_name.lower().replace(" ", "-")
    return json.dumps({
        "page": page_name,
        "inbound": backlinks.get("backlinks", {}).get(name, []),
        "forward": backlinks.get("forward", {}).get(name, []),
    }, ensure_ascii=False)


@mcp.tool()
def get_graph() -> str:
    """Get the full knowledge graph as nodes and edges.

    Returns:
    - nodes: all wiki pages with id, title, category, type
    - edges: all [[wikilinks]] as {source, target} pairs

    Useful for understanding the overall structure of the wiki,
    finding highly-connected pages, or detecting isolated clusters.
    """
    return json.dumps(_core_graph_data(_build_cache()), ensure_ascii=False)


@mcp.tool()
def rebuild_backlinks() -> str:
    """Rebuild the wiki's backlink index by scanning all [[wikilinks]].

    Call this after ingesting new sources or running lint to ensure
    the graph index is up to date. Updates wiki/_backlinks.json with
    both reverse links (backlinks) and forward links.
    """
    result = _core_build_backlinks(WIKI_DIR)
    bl_path = WIKI_DIR / "_backlinks.json"
    bl_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    # Invalidate cache
    global _cache, _cache_mtime
    _cache = {}
    _cache_mtime = 0.0

    return json.dumps({"rebuilt": True, "pages_indexed": len(result["backlinks"])})


# ── Entry point ───────────────────────────────────────────────────────

def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
