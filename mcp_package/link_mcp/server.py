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
        "Link is local personal memory for agents. Use memory_profile to inspect "
        "what Link remembers, recall_memory for user preferences, decisions, and "
        "project context, memory_inbox to find memories needing review, and "
        "explain_memory to audit why a memory exists. Use propose_memories for "
        "chat or session notes before writing memory. Use search_wiki to find "
        "general pages and get_context to retrieve a topic with its full graph "
        "neighborhood. Only call remember_memory when the user explicitly asks "
        "you to remember something; if it returns duplicate candidates, use "
        "update_memory on the existing memory instead of forcing a duplicate. "
        "Use archive_memory instead of deleting stale or wrong memories."
    ),
)

# ── In-memory indexes (built on first use, invalidated by mtime) ──────
_cache: dict = {}
_cache_mtime: float = 0.0
MAX_TEXT_INPUT = 200
MEMORY_TYPES = ("preference", "decision", "project", "fact", "note")
MEMORY_SCOPES = ("user", "project", "global")
MEMORY_REVIEW_STATUSES = ("pending", "reviewed", "needs_update")

from link_core.memory import (
    memory_duplicate_candidates as _core_memory_duplicate_candidates,
    propose_memories_from_text as _core_propose_memories_from_text,
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


def _wiki_mtime() -> float:
    try:
        t = WIKI_DIR.stat().st_mtime
        for path in WIKI_DIR.rglob("*"):
            try:
                if path.is_dir() or path.suffix == ".md" or path.name == "_backlinks.json":
                    t = max(t, path.stat().st_mtime)
            except OSError:
                continue
        return t
    except Exception:
        return 0.0


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    meta: dict = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            v = v.strip().strip('"').strip("'")
            if v.startswith("[") and v.endswith("]"):
                v = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",")]
            meta[k.strip()] = v
    return meta, text[end + 3:].strip()


def _build_cache() -> dict:
    global _cache, _cache_mtime
    mtime = _wiki_mtime()
    if _cache and mtime == _cache_mtime:
        return _cache

    pages = []
    page_index: dict[str, Path] = {}
    fulltext: dict[str, str] = {}
    snippet_index: dict[str, str] = {}
    token_index: dict[str, set] = {}
    meta_token_index: dict[str, set] = {}

    for md in sorted(WIKI_DIR.rglob("*.md")):
        if md.name.startswith("."):
            continue
        rel = md.relative_to(WIKI_DIR)
        text = md.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(text)

        title = meta.get("title", "")
        if not title:
            m = re.search(r"^#\s+(.+)", body, re.MULTILINE)
            title = m.group(1) if m else md.stem

        tldr = ""
        tldr_m = re.search(r">\s*\*\*TLDR:\*\*\s*(.+)", body)
        if tldr_m:
            tldr = tldr_m.group(1).strip()

        aliases_raw = meta.get("aliases", [])
        if isinstance(aliases_raw, str):
            aliases_raw = [a.strip() for a in aliases_raw.split(",") if a.strip()]
        aliases = [a.lower() for a in aliases_raw]

        tags_raw = meta.get("tags", [])
        if isinstance(tags_raw, str):
            tags_raw = [t.strip() for t in tags_raw.split(",") if t.strip()]

        cat = rel.parts[0] if len(rel.parts) > 1 else "root"
        stem = md.stem.lower()

        page = {
            "name": md.stem,
            "title": title,
            "category": cat,
            "type": meta.get("type", ""),
            "tags": tags_raw,
            "aliases": aliases,
            "maturity": meta.get("maturity", ""),
            "source_count": meta.get("source_count", ""),
            "tldr": tldr,
            "date_updated": meta.get("date_updated", ""),
            "date_published": meta.get("date_published", ""),
        }
        pages.append(page)
        page_index[stem] = md
        for alias in aliases:
            if alias not in page_index:
                page_index[alias] = md

        text_lower = text.lower()
        fulltext[stem] = text_lower
        body_lines = [l.strip() for l in body.split("\n") if l.strip() and not l.startswith("#") and not l.startswith(">")]
        snippet_index[stem] = body_lines[0][:200] if body_lines else ""

        for token in re.split(r"\W+", text_lower):
            if len(token) >= 3:
                token_index.setdefault(token, set()).add(stem)

        meta_tokens: set = set()
        for word in re.split(r"\W+", title.lower()):
            if len(word) >= 3:
                meta_tokens.add(word)
        for alias in aliases:
            for word in re.split(r"\W+", alias):
                if len(word) >= 3:
                    meta_tokens.add(word)
        for tag in tags_raw:
            for word in re.split(r"\W+", str(tag).lower()):
                if len(word) >= 3:
                    meta_tokens.add(word)
        if tldr:
            for word in re.split(r"\W+", tldr.lower()):
                if len(word) >= 3:
                    meta_tokens.add(word)
        for token in meta_tokens:
            meta_token_index.setdefault(token, set()).add(stem)

    page_map = {p["name"].lower(): p for p in pages}

    _cache = {
        "pages": pages,
        "page_index": page_index,
        "fulltext": fulltext,
        "snippet_index": snippet_index,
        "token_index": token_index,
        "meta_token_index": meta_token_index,
        "page_map": page_map,
    }
    _cache_mtime = mtime
    return _cache


def _search(q: str, limit: int = 20) -> list[dict]:
    q = _clean_text_input(q)
    limit = _parse_limit(limit)
    if not q:
        return []
    q_lower = q.lower()
    c = _build_cache()
    pages = c["pages"]
    page_map = c["page_map"]
    token_index = c["token_index"]
    meta_token_index = c["meta_token_index"]
    fulltext = c["fulltext"]
    snippet_index = c["snippet_index"]

    is_single = bool(re.match(r"^\w+$", q_lower))
    if is_single and q_lower in token_index:
        candidates = token_index[q_lower] | meta_token_index.get(q_lower, set())
    else:
        candidates = {p["name"].lower() for p in pages}

    scored = []
    for stem in candidates:
        p = page_map.get(stem)
        if not p:
            continue
        score = 0
        if q_lower in p["title"].lower():
            score += 10
        if q_lower == stem:
            score += 20
        if any(q_lower in a for a in p.get("aliases", [])):
            score += 8
        if any(q_lower in str(t).lower() for t in p.get("tags", [])):
            score += 5
        if q_lower in p.get("tldr", "").lower():
            score += 3
        if fulltext.get(stem, "") and q_lower in fulltext[stem]:
            score += 2
        if score > 0:
            scored.append((score, {**p, "score": score, "snippet": snippet_index.get(stem, "")}))

    scored.sort(key=lambda x: (-x[0], x[1]["title"].lower()))
    return [r for _, r in scored[:limit]]


def _get_context(topic: str) -> dict:
    topic = _clean_text_input(topic)
    if not topic:
        return {"topic": "", "found": False, "error": "topic required", "pages": []}

    c = _build_cache()
    matches = _search(topic, limit=5)
    if not matches:
        return {"topic": topic, "found": False, "pages": []}

    primary = matches[0]
    primary_name = primary["name"].lower()

    bl_path = WIKI_DIR / "_backlinks.json"
    backlinks_data: dict = {}
    if bl_path.exists():
        try:
            raw = json.loads(bl_path.read_text(encoding="utf-8"))
            backlinks_data = raw.get("backlinks", raw)
        except Exception:
            pass

    inbound = backlinks_data.get(primary_name, [])

    forward: list[str] = []
    forward_seen: set[str] = set()
    path = c["page_index"].get(primary_name)
    if path and path.exists():
        text = path.read_text(encoding="utf-8", errors="replace")
        _, body = _parse_frontmatter(text)
        page_set = {p["name"].lower() for p in c["pages"]}
        for m in re.finditer(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", body):
            target = m.group(1).strip().lower()
            if target in page_set and target != primary_name and target not in forward_seen:
                forward_seen.add(target)
                forward.append(target)

    seen = {primary_name}
    context_names = [primary_name]
    for name in inbound + forward:
        if name not in seen:
            seen.add(name)
            context_names.append(name)

    context_pages = []
    for name in context_names[:10]:
        p_path = c["page_index"].get(name)
        if not p_path or not p_path.exists():
            continue
        text = p_path.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(text)
        is_primary = name == primary_name
        if is_primary:
            content = body
        else:
            lines = body.split("\n")
            summary = []
            for line in lines[:20]:
                summary.append(line)
                if line.startswith("## ") and len(summary) > 3:
                    break
            content = "\n".join(summary)

        page_meta = c["page_map"].get(name, {})
        context_pages.append({
            "name": name,
            "title": meta.get("title", name),
            "type": meta.get("type", ""),
            "is_primary": is_primary,
            "relationship": "primary" if is_primary else ("inbound" if name in inbound else "forward"),
            "content": content,
        })

    return {
        "topic": topic,
        "found": True,
        "primary": primary["name"],
        "inbound_count": len(inbound),
        "forward_count": len(forward),
        "pages": context_pages,
    }


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(value: str, fallback: str = "memory") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def _frontmatter_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _csv_values(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _meta_tags(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip().strip("\"'") for item in _csv_values(str(value).strip("[]"))]


def _yaml_list(values: list[str]) -> str:
    return "[" + ", ".join(values) + "]"


def _memory_title(text: str, explicit_title: str | None = None) -> str:
    if explicit_title and explicit_title.strip():
        return explicit_title.strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "Memory")
    first_sentence = re.split(r"(?<=[.!?])\s+", first_line, maxsplit=1)[0].strip()
    if len(first_sentence) <= 70:
        return first_sentence.rstrip(".")
    return first_sentence[:67].rstrip() + "..."


def _unique_page_path(directory: Path, slug: str) -> Path:
    candidate = directory / f"{slug}.md"
    index = 2
    while candidate.exists():
        candidate = directory / f"{slug}-{index}.md"
        index += 1
    return candidate


def _extract_tldr(body: str) -> str:
    match = re.search(r">\s*\*\*TLDR:\*\*\s*(.+)", body)
    return match.group(1).strip() if match else ""


def _first_body_snippet(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith(">"):
            return stripped[:200]
    return ""


def _memory_records() -> list[dict[str, object]]:
    memories_dir = WIKI_DIR / "memories"
    if not memories_dir.exists():
        return []
    records: list[dict[str, object]] = []
    for path in sorted(memories_dir.rglob("*.md")):
        if path.name.startswith("."):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(text)
        title = meta.get("title") or _memory_title(body)
        records.append({
            "name": path.stem,
            "path": f"wiki/{path.relative_to(WIKI_DIR).as_posix()}",
            "title": title,
            "memory_type": meta.get("memory_type") or "note",
            "scope": meta.get("scope") or "user",
            "status": meta.get("status") or "active",
            "date_captured": meta.get("date_captured", ""),
            "updated_at": meta.get("updated_at", ""),
            "update_count": meta.get("update_count", "0"),
            "last_update_source": meta.get("last_update_source", ""),
            "archived_at": meta.get("archived_at", ""),
            "archive_reason": meta.get("archive_reason", ""),
            "restored_at": meta.get("restored_at", ""),
            "source": meta.get("source", ""),
            "review_status": meta.get("review_status") or "pending",
            "reviewed_at": meta.get("reviewed_at", ""),
            "review_note": meta.get("review_note", ""),
            "tags": _meta_tags(meta.get("tags", "")),
            "tldr": _extract_tldr(body),
            "snippet": _first_body_snippet(body),
            "body": body,
        })
    return records


def _slim_memory(record: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in record.items() if key != "body"}


def _is_active_memory(record: dict[str, object]) -> bool:
    return str(record.get("status") or "active").lower() not in {"archived", "stale"}


def _memory_review_issues(record: dict[str, object]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    status = str(record.get("status") or "active").lower()
    review_status = str(record.get("review_status") or "pending").lower()
    memory_type = str(record.get("memory_type") or "")
    scope = str(record.get("scope") or "")

    if review_status in {"pending", "needs_review"}:
        issues.append({
            "code": "pending_review",
            "severity": "medium",
            "message": "Memory has not been reviewed by the user.",
            "suggested_action": "Confirm it is still accurate, then run review_memory.",
        })
    elif review_status == "needs_update":
        issues.append({
            "code": "needs_update",
            "severity": "high",
            "message": "Memory is marked as needing an update.",
            "suggested_action": "Edit the memory page or archive it if it is no longer useful.",
        })
    elif review_status not in MEMORY_REVIEW_STATUSES:
        issues.append({
            "code": "invalid_review_status",
            "severity": "high",
            "message": f"Unknown review_status: {review_status}.",
            "suggested_action": "Use pending, reviewed, or needs_update.",
        })

    if status == "stale":
        issues.append({
            "code": "stale_status",
            "severity": "high",
            "message": "Memory is marked stale and is excluded from default recall.",
            "suggested_action": "Archive it, restore it, or update the memory text.",
        })
    if memory_type not in MEMORY_TYPES:
        issues.append({
            "code": "invalid_memory_type",
            "severity": "high",
            "message": f"Unknown memory_type: {memory_type or 'missing'}.",
            "suggested_action": f"Use one of: {', '.join(MEMORY_TYPES)}.",
        })
    if scope not in MEMORY_SCOPES:
        issues.append({
            "code": "invalid_scope",
            "severity": "high",
            "message": f"Unknown scope: {scope or 'missing'}.",
            "suggested_action": f"Use one of: {', '.join(MEMORY_SCOPES)}.",
        })
    if not str(record.get("source") or "").strip():
        issues.append({
            "code": "missing_source",
            "severity": "medium",
            "message": "Memory has no source metadata.",
            "suggested_action": "Add source metadata so future agents know why this memory exists.",
        })
    if not str(record.get("date_captured") or "").strip():
        issues.append({
            "code": "missing_date_captured",
            "severity": "medium",
            "message": "Memory has no date_captured metadata.",
            "suggested_action": "Add the capture timestamp or recreate the memory.",
        })
    if not (str(record.get("tldr") or "").strip() or str(record.get("snippet") or "").strip()):
        issues.append({
            "code": "missing_summary",
            "severity": "medium",
            "message": "Memory has no usable summary.",
            "suggested_action": "Add a TLDR line or a clear first paragraph.",
        })
    return issues


def _memory_inbox(limit: int = 20, include_archived: bool = False) -> dict[str, object]:
    limit = max(1, min(limit, 50))
    items: list[dict[str, object]] = []
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    for record in _memory_records():
        if not include_archived and str(record.get("status") or "").lower() == "archived":
            continue
        issues = _memory_review_issues(record)
        if not issues:
            continue
        item = _slim_memory(record)
        item["issues"] = issues
        item["issue_count"] = len(issues)
        item["highest_severity"] = min(
            (issue["severity"] for issue in issues),
            key=lambda severity: severity_rank.get(severity, 9),
        )
        items.append(item)
    items.sort(key=lambda item: (
        severity_rank.get(str(item["highest_severity"]), 9),
        -int(item["issue_count"]),
        str(item.get("date_captured") or ""),
        str(item.get("title") or "").lower(),
    ))
    counts_by_severity: dict[str, int] = {}
    for item in items:
        severity = str(item["highest_severity"])
        counts_by_severity[severity] = counts_by_severity.get(severity, 0) + 1
    return {
        "review_count": len(items),
        "counts_by_severity": counts_by_severity,
        "include_archived": include_archived,
        "items": items[:limit],
    }


def _extract_wikilinks(text: str) -> list[str]:
    links: list[str] = []
    for match in re.finditer(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", text):
        target = match.group(1).strip()
        if target and target not in links:
            links.append(target)
    return links


def _load_backlinks() -> dict[str, dict[str, list[str]]]:
    bl_path = WIKI_DIR / "_backlinks.json"
    if not bl_path.exists():
        return {"backlinks": {}, "forward": {}}
    try:
        raw = json.loads(bl_path.read_text(encoding="utf-8"))
    except Exception:
        return {"backlinks": {}, "forward": {}}
    if "backlinks" not in raw:
        return {"backlinks": raw if isinstance(raw, dict) else {}, "forward": {}}
    backlinks = raw.get("backlinks", {})
    forward = raw.get("forward", {})
    if not isinstance(backlinks, dict) or not isinstance(forward, dict):
        return {"backlinks": {}, "forward": {}}
    return {"backlinks": backlinks, "forward": forward}


def _memory_log_entries(record: dict[str, object], limit: int = 8) -> list[str]:
    log_path = WIKI_DIR / "log.md"
    if not log_path.exists():
        return []
    text = log_path.read_text(encoding="utf-8", errors="replace")
    needles = {
        str(record.get("name") or ""),
        str(record.get("title") or ""),
        f"memories/{record.get('name')}.md",
    }
    needles = {needle.lower() for needle in needles if needle}
    blocks = [block.strip() for block in re.split(r"\n---\n", text) if block.strip()]
    matches = [
        block for block in blocks
        if any(needle in block.lower() for needle in needles)
    ]
    return matches[-limit:]


def _recall_state(record: dict[str, object], issues: list[dict[str, str]]) -> dict[str, object]:
    default_enabled = _is_active_memory(record)
    high_issues = [issue for issue in issues if issue["severity"] == "high"]
    if not default_enabled:
        state = "disabled"
        reason = f"Memory status is {record.get('status')}; default recall excludes archived and stale memories."
    elif high_issues:
        state = "unsafe"
        reason = "Memory is active but has high-severity quality issues."
    elif issues:
        state = "needs_review"
        reason = "Memory is active but still needs review or stronger metadata."
    else:
        state = "ready"
        reason = "Memory is active, reviewed, and has no detected quality issues."
    return {
        "default_enabled": default_enabled,
        "state": state,
        "reason": reason,
    }


def _memory_explanation(identifier: str) -> dict[str, object]:
    page_path, resolved_record, error = _resolve_memory_page(identifier)
    if error:
        raise ValueError(error)
    assert page_path is not None and resolved_record is not None

    record = next(
        (item for item in _memory_records() if item["name"] == resolved_record["name"]),
        resolved_record,
    )
    body = str(record.get("body") or "")
    issues = _memory_review_issues(record)
    backlinks = _load_backlinks()
    name = str(record["name"])
    graph = {
        "forward": sorted(backlinks.get("forward", {}).get(name, [])),
        "inbound": sorted(backlinks.get("backlinks", {}).get(name, [])),
        "wikilinks": _extract_wikilinks(body),
    }
    return {
        "found": True,
        "memory": _slim_memory(record),
        "recall": _recall_state(record, issues),
        "review": {
            "status": record.get("review_status", "pending"),
            "reviewed_at": record.get("reviewed_at", ""),
            "review_note": record.get("review_note", ""),
            "issues": issues,
            "issue_count": len(issues),
        },
        "provenance": {
            "source": record.get("source", ""),
            "date_captured": record.get("date_captured", ""),
            "path": record.get("path", ""),
        },
        "lifecycle": {
            "status": record.get("status", "active"),
            "archived_at": record.get("archived_at", ""),
            "archive_reason": record.get("archive_reason", ""),
            "restored_at": record.get("restored_at", ""),
        },
        "graph": graph,
        "log_entries": _memory_log_entries(record),
        "body": body,
    }


def _count_values(records: list[dict[str, object]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(field) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _top_tags(records: list[dict[str, object]], limit: int = 12) -> list[dict[str, object]]:
    counts: dict[str, int] = {}
    skip = {"memory", *MEMORY_TYPES}
    for record in records:
        for tag in record.get("tags", []):
            tag_text = str(tag).strip()
            if not tag_text or tag_text in skip:
                continue
            counts[tag_text] = counts.get(tag_text, 0) + 1
    return [
        {"tag": tag, "count": count}
        for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _recent_memories(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        records,
        key=lambda record: (
            str(record.get("date_captured") or ""),
            str(record.get("title") or "").lower(),
        ),
        reverse=True,
    )


def _memory_profile(limit: int = 10) -> dict[str, object]:
    limit = max(1, min(limit, 50))
    records = _memory_records()
    active_records = [record for record in records if _is_active_memory(record)]
    archived_records = [
        record for record in records
        if str(record.get("status") or "").lower() == "archived"
    ]
    recent = [_slim_memory(record) for record in _recent_memories(active_records)]

    def typed(memory_type: str) -> list[dict[str, object]]:
        return [
            _slim_memory(record)
            for record in _recent_memories(active_records)
            if str(record.get("memory_type") or "") == memory_type
        ][:limit]

    return {
        "memory_count": len(records),
        "active_count": len(active_records),
        "review_count": _memory_inbox(limit=limit)["review_count"],
        "by_type": _count_values(records, "memory_type"),
        "by_scope": _count_values(records, "scope"),
        "by_status": _count_values(records, "status"),
        "top_tags": _top_tags(records),
        "recent": recent[:limit],
        "preferences": typed("preference"),
        "decisions": typed("decision"),
        "projects": typed("project"),
        "archived": [_slim_memory(record) for record in _recent_memories(archived_records)][:limit],
    }


def _score_memory(record: dict[str, object], query: str) -> int:
    q = query.lower().strip()
    tokens = [token for token in re.split(r"\W+", q) if len(token) >= 3]
    title = str(record.get("title", "")).lower()
    tldr = str(record.get("tldr", "")).lower()
    body = str(record.get("body", "")).lower()
    tags = " ".join(str(tag).lower() for tag in record.get("tags", []))
    score = 0
    if q and q in title:
        score += 20
    if q and q in tldr:
        score += 12
    if q and q in tags:
        score += 8
    if q and q in body:
        score += 4
    for token in tokens:
        if token in title:
            score += 6
        if token in tldr:
            score += 4
        if token in tags:
            score += 3
        if token in body:
            score += 1
    return score


def _recall_memories(query: str, limit: int = 10, include_archived: bool = False) -> list[dict[str, object]]:
    query = _clean_text_input(query)
    if not query:
        return []
    scored: list[tuple[int, dict[str, object]]] = []
    for record in _memory_records():
        if not include_archived and not _is_active_memory(record):
            continue
        score = _score_memory(record, query)
        if score > 0:
            slim = _slim_memory(record)
            slim["score"] = score
            scored.append((score, slim))
    scored.sort(key=lambda item: (-item[0], str(item[1]["title"]).lower()))
    return [record for _, record in scored[:limit]]


def _memory_duplicate_candidates(
    text: str,
    title: str,
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


def _propose_memories_from_text(text: str, source: str = "mcp", limit: int = 10) -> dict[str, object]:
    return _core_propose_memories_from_text(
        text,
        _memory_records(),
        source=source,
        limit=limit,
        writes_memory=False,
    )


def _update_memory_index(page_name: str, title: str, summary: str, memory_type: str, scope: str) -> None:
    index_path = WIKI_DIR / "index.md"
    if not index_path.exists():
        index_path.write_text(
            "# Link Wiki Index\n\n"
            "> Last updated: not yet ingested | 0 pages | 0 sources\n\n"
            "## Categories\n\n"
            "## Recent\n\n"
            "| Date | Operation | Pages Touched |\n"
            "|------|-----------|---------------|\n",
            encoding="utf-8",
        )
    text = index_path.read_text(encoding="utf-8", errors="replace")
    if f"[[{page_name}]]" in text:
        return
    entry = f"- [[{page_name}]] - {summary} {memory_type} · {scope}\n"
    if "### memories" in text:
        pattern = re.compile(r"(### memories\n)(.*?)(?=\n### |\n## Recent|\Z)", flags=re.DOTALL)
        text = pattern.sub(lambda m: m.group(1) + m.group(2).rstrip() + "\n" + entry, text, count=1)
    elif "\n## Recent" in text:
        text = text.replace("\n## Recent", f"\n### memories\n{entry}\n## Recent", 1)
    else:
        text = text.rstrip() + f"\n\n### memories\n{entry}"
    index_path.write_text(text, encoding="utf-8")


def _append_log(timestamp: str, operation: str, description: str, lines: list[str]) -> None:
    log_path = WIKI_DIR / "log.md"
    if not log_path.exists():
        log_path.write_text("# Link Wiki Log\n\n*Append-only record of wiki operations.*\n", encoding="utf-8")
    entry = [f"## [{timestamp}] {operation} | {description}", ""]
    entry.extend(f"- {line}" for line in lines)
    entry.extend(["", "---", ""])
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(entry))


def _update_frontmatter_fields(text: str, updates: dict[str, str], remove: set[str] | None = None) -> str:
    remove = remove or set()
    if not text.startswith("---\n"):
        frontmatter = [f"{key}: {value}" for key, value in updates.items()]
        return "---\n" + "\n".join(frontmatter) + "\n---\n\n" + text.lstrip("\n")

    end = text.find("\n---", 4)
    if end == -1:
        frontmatter = [f"{key}: {value}" for key, value in updates.items()]
        return "---\n" + "\n".join(frontmatter) + "\n---\n\n" + text

    seen: set[str] = set()
    lines: list[str] = []
    for line in text[4:end].splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            lines.append(line)
            continue
        key = line.split(":", 1)[0].strip()
        if key in remove:
            continue
        if key in updates:
            lines.append(f"{key}: {updates[key]}")
            seen.add(key)
        else:
            lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}: {value}")
    return "---\n" + "\n".join(lines) + "\n---" + text[end + 4:]


def _frontmatter_int(value: object) -> int:
    try:
        return int(str(value or "0").strip())
    except ValueError:
        return 0


def _replace_markdown_body(text: str, body: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            return text[:end + 4] + "\n\n" + body.strip() + "\n"
    return body.strip() + "\n"


def _append_memory_update(body: str, update_text: str, timestamp: str, source: str) -> str:
    source_label = source.strip() or "mcp"
    update_block = f"Update ({timestamp}, {source_label}):\n\n{update_text.strip()}"
    pattern = re.compile(r"(## Memory\n)(.*?)(?=\n## |\Z)", flags=re.DOTALL)
    match = pattern.search(body)
    if not match:
        return body.rstrip() + f"\n\n## Memory\n\n{update_block}\n"
    existing = match.group(2).rstrip()
    merged = (existing + "\n\n" if existing else "") + update_block + "\n\n"
    return body[:match.start(2)] + merged + body[match.end(2):]


def _resolve_memory_page(identifier: str) -> tuple[Path | None, dict[str, object] | None, str | None]:
    needle = _clean_text_input(identifier, max_len=300)
    if not needle:
        return None, None, "memory name or title is required"
    memories_dir = WIKI_DIR / "memories"
    direct_candidates = []
    raw_path = Path(needle)
    if raw_path.suffix == ".md" or "/" in needle:
        rel = Path(needle.removeprefix("wiki/"))
        direct_candidates.append((WIKI_DIR / rel).resolve())
        direct_candidates.append((memories_dir / raw_path.name).resolve())
    else:
        direct_candidates.append((memories_dir / f"{needle}.md").resolve())
        direct_candidates.append((memories_dir / f"{_slugify(needle)}.md").resolve())

    memories_root = memories_dir.resolve()
    for candidate in direct_candidates:
        try:
            candidate.relative_to(memories_root)
        except ValueError:
            continue
        if candidate.exists() and candidate.is_file():
            text = candidate.read_text(encoding="utf-8", errors="replace")
            meta, body = _parse_frontmatter(text)
            return candidate, {
                "name": candidate.stem,
                "path": f"wiki/{candidate.relative_to(WIKI_DIR).as_posix()}",
                "title": meta.get("title") or _memory_title(body),
                "memory_type": meta.get("memory_type") or "note",
                "scope": meta.get("scope") or "user",
                "status": meta.get("status") or "active",
                "date_captured": meta.get("date_captured", ""),
                "updated_at": meta.get("updated_at", ""),
                "update_count": meta.get("update_count", "0"),
                "last_update_source": meta.get("last_update_source", ""),
                "source": meta.get("source", ""),
                "review_status": meta.get("review_status") or "pending",
                "reviewed_at": meta.get("reviewed_at", ""),
                "review_note": meta.get("review_note", ""),
                "tldr": _extract_tldr(body),
                "snippet": _first_body_snippet(body),
            }, None

    lowered = needle.lower()
    slug = _slugify(needle)
    matches = [
        record for record in _memory_records()
        if lowered in {str(record["name"]).lower(), str(record["title"]).lower()}
        or slug == str(record["name"]).lower()
    ]
    if len(matches) > 1:
        names = ", ".join(str(record["name"]) for record in matches[:5])
        return None, None, f"memory identifier is ambiguous: {names}"
    if not matches:
        return None, None, f"memory not found: {identifier}"
    record = matches[0]
    return WIKI_DIR / str(record["path"]).removeprefix("wiki/"), record, None


def _set_memory_status(identifier: str, status: str, reason: str = "") -> dict[str, object]:
    page_path, record, error = _resolve_memory_page(identifier)
    if error:
        raise ValueError(error)
    assert page_path is not None and record is not None

    timestamp = _utc_timestamp()
    current_status = str(record.get("status") or "active")
    reason = _clean_text_input(reason, max_len=500)
    if status == "archived":
        updates = {
            "status": "archived",
            "archived_at": f'"{timestamp}"',
        }
        if reason:
            updates["archive_reason"] = f'"{_frontmatter_string(reason)}"'
        remove = {"restored_at"}
        operation = "archive-memory"
    elif status == "active":
        updates = {
            "status": "active",
            "restored_at": f'"{timestamp}"',
        }
        remove = {"archived_at", "archive_reason"}
        operation = "restore-memory"
    else:
        raise ValueError("unsupported memory status")

    changed = current_status != status
    if changed:
        text = page_path.read_text(encoding="utf-8", errors="replace")
        page_path.write_text(_update_frontmatter_fields(text, updates, remove=remove), encoding="utf-8")
        log_lines = [
            f"Updated: memories/{page_path.name}",
            f"Previous status: {current_status}",
            f"New status: {status}",
        ]
        if reason:
            log_lines.append(f"Reason: {reason}")
        _append_log(timestamp, operation, str(record["title"]), log_lines)
        _cache.clear()

    return {
        "updated": changed,
        "name": record["name"],
        "path": record["path"],
        "title": record["title"],
        "previous_status": current_status,
        "status": status,
    }


def _mark_memory_reviewed(identifier: str, note: str = "") -> dict[str, object]:
    page_path, record, error = _resolve_memory_page(identifier)
    if error:
        raise ValueError(error)
    assert page_path is not None and record is not None

    timestamp = _utc_timestamp()
    previous_review_status = str(record.get("review_status") or "pending")
    note = _clean_text_input(note, max_len=500)
    updates = {
        "review_status": "reviewed",
        "reviewed_at": f'"{timestamp}"',
    }
    if note:
        updates["review_note"] = f'"{_frontmatter_string(note)}"'
    changed = previous_review_status != "reviewed" or bool(note)
    if changed:
        text = page_path.read_text(encoding="utf-8", errors="replace")
        page_path.write_text(_update_frontmatter_fields(text, updates), encoding="utf-8")
        log_lines = [
            f"Reviewed: memories/{page_path.name}",
            f"Previous review status: {previous_review_status}",
            "New review status: reviewed",
        ]
        if note:
            log_lines.append(f"Note: {note}")
        _append_log(timestamp, "review-memory", str(record["title"]), log_lines)
        _cache.clear()

    _, updated_record, _ = _resolve_memory_page(str(record["name"]))
    updated_record = updated_record or record
    issues = _memory_review_issues(updated_record)
    return {
        "updated": changed,
        "name": record["name"],
        "path": record["path"],
        "title": record["title"],
        "previous_review_status": previous_review_status,
        "review_status": "reviewed",
        "remaining_issue_count": len(issues),
        "remaining_issues": issues,
    }


def _update_memory_page(identifier: str, text: str, source: str = "mcp") -> dict[str, object]:
    clean_text = _clean_text_input(text, max_len=4000)
    if not clean_text:
        raise ValueError("memory update text required")
    clean_source = _clean_text_input(source, max_len=500) or "mcp"
    page_path, record, error = _resolve_memory_page(identifier)
    if error:
        raise ValueError(error)
    assert page_path is not None and record is not None
    if not _is_active_memory(record):
        raise ValueError("cannot update archived or stale memory; restore it first")

    timestamp = _utc_timestamp()
    previous_review_status = str(record.get("review_status") or "pending")
    previous_update_count = _frontmatter_int(record.get("update_count"))
    next_update_count = previous_update_count + 1
    original = page_path.read_text(encoding="utf-8", errors="replace")
    _, body = _parse_frontmatter(original)
    updated_body = _append_memory_update(body, clean_text, timestamp, clean_source)
    updates = {
        "updated_at": f'"{timestamp}"',
        "update_count": str(next_update_count),
        "last_update_source": f'"{_frontmatter_string(clean_source)}"',
        "review_status": "pending",
    }
    updated_text = _update_frontmatter_fields(original, updates, remove={"reviewed_at", "review_note"})
    page_path.write_text(_replace_markdown_body(updated_text, updated_body), encoding="utf-8")
    _append_log(
        timestamp,
        "update-memory",
        str(record["title"]),
        [
            f"Updated: memories/{page_path.name}",
            f"Previous review status: {previous_review_status}",
            "New review status: pending",
            f"Update count: {next_update_count}",
            f"Source: {clean_source}",
        ],
    )
    rebuilt = json.loads(rebuild_backlinks())
    _cache.clear()

    _, updated_record, _ = _resolve_memory_page(str(record["name"]))
    updated_record = updated_record or record
    issues = _memory_review_issues(updated_record)
    return {
        "updated": True,
        "name": updated_record["name"],
        "path": updated_record["path"],
        "title": updated_record["title"],
        "previous_review_status": previous_review_status,
        "review_status": updated_record.get("review_status", "pending"),
        "updated_at": timestamp,
        "update_count": next_update_count,
        "source": clean_source,
        "remaining_issue_count": len(issues),
        "remaining_issues": issues,
        "backlinks_rebuilt": bool(rebuilt.get("rebuilt")),
    }


def _write_memory_page(
    text: str,
    title: str = "",
    memory_type: str = "note",
    scope: str = "user",
    tags: str = "",
    source: str = "mcp",
    allow_duplicate: bool = False,
) -> dict[str, object]:
    clean_text = _clean_text_input(text, max_len=4000)
    if not clean_text:
        raise ValueError("memory text required")
    memory_type = _clean_text_input(memory_type).lower() or "note"
    scope = _clean_text_input(scope).lower() or "user"
    if memory_type not in MEMORY_TYPES:
        raise ValueError(f"memory_type must be one of: {', '.join(MEMORY_TYPES)}")
    if scope not in MEMORY_SCOPES:
        raise ValueError(f"scope must be one of: {', '.join(MEMORY_SCOPES)}")

    timestamp = _utc_timestamp()
    memory_title = _memory_title(clean_text, _clean_text_input(title))
    summary = clean_text.splitlines()[0].strip()
    if len(summary) > 180:
        summary = summary[:177].rstrip() + "..."
    duplicate_candidates = _memory_duplicate_candidates(
        clean_text,
        _clean_text_input(title),
        memory_type,
        scope,
    )
    if duplicate_candidates and not allow_duplicate:
        return {
            "created": False,
            "duplicate": True,
            "message": "Similar active memory already exists. Review or update the existing memory, or pass allow_duplicate if this is intentional.",
            "title": memory_title,
            "memory_type": memory_type,
            "scope": scope,
            "candidates": duplicate_candidates,
        }
    memories_dir = WIKI_DIR / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)
    page_path = _unique_page_path(memories_dir, _slugify(memory_title))
    page_name = page_path.stem
    tag_values = ["memory", memory_type]
    for tag in _csv_values(tags):
        slug_tag = _slugify(tag, fallback="")
        if slug_tag and slug_tag not in tag_values:
            tag_values.append(slug_tag)

    page = f"""---
type: memory
title: "{_frontmatter_string(memory_title)}"
memory_type: {memory_type}
scope: {scope}
status: active
date_captured: "{timestamp}"
source: "{_frontmatter_string(source)}"
review_status: pending
tags: {_yaml_list(tag_values)}
---

# {memory_title}

> **TLDR:** {summary}

## Memory

{clean_text}

## Use This When

- An agent needs relevant {scope} context for future work.
- A future answer depends on this {memory_type}.

## Source

{source}
"""
    page_path.write_text(page, encoding="utf-8")
    _update_memory_index(page_name, memory_title, summary, memory_type, scope)
    _append_log(
        timestamp,
        "remember",
        memory_title,
        [
            f"Created: memories/{page_path.name}",
            f"Type: {memory_type}",
            f"Scope: {scope}",
        ],
    )
    rebuilt = json.loads(rebuild_backlinks())
    _cache.clear()
    return {
        "created": True,
        "name": page_name,
        "path": f"wiki/memories/{page_path.name}",
        "title": memory_title,
        "memory_type": memory_type,
        "scope": scope,
        "backlinks_rebuilt": bool(rebuilt.get("rebuilt")),
        "duplicate_override": bool(duplicate_candidates and allow_duplicate),
        "duplicate_candidates": duplicate_candidates,
    }


# ── MCP Tools ─────────────────────────────────────────────────────────

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
def recall_memory(query: str, limit: int = 10, include_archived: bool = False) -> str:
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
    memories = _recall_memories(query, limit=limit, include_archived=include_archived)
    return json.dumps({
        "query": query,
        "count": len(memories),
        "include_archived": include_archived,
        "memories": memories,
    }, ensure_ascii=False)


@mcp.tool()
def propose_memories(text: str, source: str = "mcp", limit: int = 10) -> str:
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
    return json.dumps(_propose_memories_from_text(clean_text, source=source, limit=limit), ensure_ascii=False)


@mcp.tool()
def memory_profile(limit: int = 10) -> str:
    """Summarize what Link currently remembers.

    Use this to inspect the local memory profile before doing personalized work.
    Returns counts by type/scope/status, top tags, recent memories, and focused
    lists for preferences, decisions, and project context.
    """
    limit = _parse_limit(limit, default=10)
    return json.dumps(_memory_profile(limit=limit), ensure_ascii=False)


@mcp.tool()
def memory_inbox(limit: int = 20, include_archived: bool = False) -> str:
    """List memories that need user review.

    Use this to surface pending, stale, invalid, or underspecified memories for
    human confirmation. Archived memories are excluded unless include_archived
    is true.
    """
    limit = _parse_limit(limit, default=20)
    return json.dumps(_memory_inbox(limit=limit, include_archived=include_archived), ensure_ascii=False)


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
def update_memory(identifier: str, memory: str, source: str = "mcp") -> str:
    """Merge new information into an existing active memory.

    Use this when remember_memory returns a duplicate candidate or when the user
    asks to update something Link already remembers. The update is appended to
    the memory body, logged, and marked pending review.
    """
    try:
        result = _update_memory_page(identifier, memory, source=source)
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
) -> str:
    """Save a local agent memory as a Markdown page.

    Use only when the user explicitly asks you to remember something. The memory
    is written under wiki/memories/, indexed, logged, and kept local. Strong
    duplicates are refused unless allow_duplicate is true.
    memory_type: preference, decision, project, fact, or note.
    scope: user, project, or global.
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
    bl_path = WIKI_DIR / "_backlinks.json"
    if not bl_path.exists():
        return json.dumps({"error": "backlinks not built — run rebuild_backlinks first"})
    try:
        raw = json.loads(bl_path.read_text(encoding="utf-8"))
    except Exception as e:
        return json.dumps({"error": str(e)})

    page_name = _clean_text_input(page_name)
    if not page_name:
        return json.dumps({"error": "page_name required", "inbound": [], "forward": []})

    name = page_name.lower().replace(" ", "-")
    backlinks = raw.get("backlinks", raw)
    forward = raw.get("forward", {})
    return json.dumps({
        "page": page_name,
        "inbound": backlinks.get(name, []),
        "forward": forward.get(name, []),
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
    c = _build_cache()
    pages = c["pages"]
    page_ids = {p["name"].lower(): p["name"] for p in pages}
    nodes = [{"id": p["name"], "title": p["title"], "category": p["category"], "type": p["type"]} for p in pages]

    edges = []
    seen_edges: set[tuple[str, str]] = set()
    wl_re = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
    for p in pages:
        source = p["name"]
        path = c["page_index"].get(source.lower())
        if not path or not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        _, body = _parse_frontmatter(text)
        for m in wl_re.finditer(body):
            target_key = m.group(1).strip().lower()
            target = page_ids.get(target_key)
            if not target or target_key == source.lower():
                continue
            edge_key = (source, target)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            edges.append({"source": source, "target": target})

    return json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False)


@mcp.tool()
def rebuild_backlinks() -> str:
    """Rebuild the wiki's backlink index by scanning all [[wikilinks]].

    Call this after ingesting new sources or running lint to ensure
    the graph index is up to date. Updates wiki/_backlinks.json with
    both reverse links (backlinks) and forward links.
    """
    backlinks: dict[str, list] = {}
    forward_links: dict[str, list] = {}
    wl_re = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")

    for md in WIKI_DIR.rglob("*.md"):
        if md.name.startswith("."):
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        _, body = _parse_frontmatter(text)
        source = md.stem.lower()
        for m in wl_re.finditer(body):
            target = m.group(1).strip().lower()
            if target != source:
                backlinks.setdefault(target, [])
                if source not in backlinks[target]:
                    backlinks[target].append(source)
                forward_links.setdefault(source, [])
                if target not in forward_links[source]:
                    forward_links[source].append(target)

    result = {"backlinks": backlinks, "forward": forward_links}
    bl_path = WIKI_DIR / "_backlinks.json"
    bl_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    # Invalidate cache
    global _cache, _cache_mtime
    _cache = {}
    _cache_mtime = 0.0

    return json.dumps({"rebuilt": True, "pages_indexed": len(backlinks)})


# ── Entry point ───────────────────────────────────────────────────────

def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
