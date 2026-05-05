"""Shared wiki indexing, search, context, and graph helpers for Link."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .frontmatter import parse_frontmatter


WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")


def wiki_mtime(wiki_dir: Path) -> float:
    """Return an mtime signal for files that affect wiki indexes."""
    try:
        timestamp = wiki_dir.stat().st_mtime
        for path in wiki_dir.rglob("*"):
            try:
                if path.is_dir() or path.suffix == ".md" or path.name == "_backlinks.json":
                    timestamp = max(timestamp, path.stat().st_mtime)
            except OSError:
                continue
        return timestamp
    except Exception:
        return 0.0


def _heading_title(body: str) -> str:
    match = re.search(r"^#\s+(.+)", body, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _tldr(body: str) -> str:
    match = re.search(r">\s*\*\*TLDR:\*\*\s*(.+)", body)
    return match.group(1).strip() if match else ""


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _body_snippet(body: str) -> str:
    body_lines = [
        line.strip()
        for line in body.split("\n")
        if line.strip() and not line.startswith("#") and not line.startswith(">")
    ]
    return body_lines[0][:200] if body_lines else ""


def build_wiki_cache(wiki_dir: Path) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    page_index: dict[str, Path] = {}
    fulltext: dict[str, str] = {}
    snippet_index: dict[str, str] = {}
    token_index: dict[str, set[str]] = {}
    meta_token_index: dict[str, set[str]] = {}

    for md in sorted(wiki_dir.rglob("*.md")):
        if md.name.startswith("."):
            continue
        rel = md.relative_to(wiki_dir)
        text = md.read_text(encoding="utf-8", errors="replace")
        meta, body = parse_frontmatter(text)

        title = str(meta.get("title") or _heading_title(body) or md.stem)
        tldr = _tldr(body)
        aliases_raw = _list_value(meta.get("aliases", []))
        aliases = [str(alias).lower() for alias in aliases_raw]
        tags_raw = _list_value(meta.get("tags", []))
        category = rel.parts[0] if len(rel.parts) > 1 else "root"
        stem = md.stem.lower()

        page = {
            "name": md.stem,
            "title": title,
            "category": category,
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
        snippet_index[stem] = _body_snippet(body)

        for token in re.split(r"\W+", text_lower):
            if len(token) >= 3:
                token_index.setdefault(token, set()).add(stem)

        meta_tokens: set[str] = set()
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

    return {
        "mtime": wiki_mtime(wiki_dir),
        "pages": pages,
        "page_index": page_index,
        "fulltext": fulltext,
        "snippet_index": snippet_index,
        "token_index": token_index,
        "meta_token_index": meta_token_index,
        "page_map": {page["name"].lower(): page for page in pages},
    }


def load_backlinks_index(
    backlinks_path: Path,
    missing_error: str | None = None,
    invalid_prefix: str = "invalid backlinks index",
) -> tuple[dict[str, dict[str, list[str]]], str | None]:
    empty: dict[str, dict[str, list[str]]] = {"backlinks": {}, "forward": {}}
    if not backlinks_path.exists():
        return empty, missing_error
    try:
        raw = json.loads(backlinks_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return empty, f"{invalid_prefix}: {exc}"
    if not isinstance(raw, dict):
        return empty, f"{invalid_prefix}: root must be an object"
    if "backlinks" not in raw:
        return {"backlinks": raw, "forward": {}}, None
    backlinks = raw.get("backlinks", {})
    forward = raw.get("forward", {})
    if not isinstance(backlinks, dict) or not isinstance(forward, dict):
        return empty, f"{invalid_prefix}: backlinks and forward must be objects"
    return {"backlinks": backlinks, "forward": forward}, None


def build_backlinks(wiki_dir: Path, body_only: bool = True) -> dict[str, dict[str, list[str]]]:
    backlinks: dict[str, list[str]] = {}
    forward_links: dict[str, list[str]] = {}
    for md in sorted(wiki_dir.rglob("*.md")):
        if md.name.startswith("."):
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        if body_only:
            _, text = parse_frontmatter(text)
        source = md.stem.lower()
        for match in WIKILINK_RE.finditer(text):
            target = match.group(1).strip().lower()
            if not target or target == source:
                continue
            backlinks.setdefault(target, [])
            if source not in backlinks[target]:
                backlinks[target].append(source)
            forward_links.setdefault(source, [])
            if target not in forward_links[source]:
                forward_links[source].append(target)
    return {"backlinks": backlinks, "forward": forward_links}


def search_pages(query: str, cache: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
    q = query.strip()
    if not q:
        return []
    q_lower = q.lower()
    pages = cache["pages"]
    page_map = cache["page_map"]
    token_index = cache["token_index"]
    meta_token_index = cache["meta_token_index"]
    fulltext = cache["fulltext"]
    snippet_index = cache["snippet_index"]

    is_single_token = bool(re.match(r"^\w+$", q_lower))
    if is_single_token and q_lower in token_index:
        candidates = token_index[q_lower] | meta_token_index.get(q_lower, set())
    else:
        candidates = {page["name"].lower() for page in pages}

    scored: list[tuple[int, dict[str, Any]]] = []
    for stem in candidates:
        page = page_map.get(stem)
        if not page:
            continue
        score = 0
        if q_lower in str(page["title"]).lower():
            score += 10
        if q_lower == stem:
            score += 20
        if any(q_lower in alias for alias in page.get("aliases", [])):
            score += 8
        if any(q_lower in str(tag).lower() for tag in page.get("tags", [])):
            score += 5
        if q_lower in str(page.get("tldr", "")).lower():
            score += 3
        text_lower = fulltext.get(stem, "")
        if text_lower and q_lower in text_lower:
            score += 2
        if score > 0:
            scored.append((score, {**page, "score": score, "snippet": snippet_index.get(stem, "")}))

    scored.sort(key=lambda item: (-item[0], str(item[1]["title"]).lower()))
    return [record for _, record in scored[:limit]]


def context_for_topic(
    wiki_dir: Path,
    topic: str,
    cache: dict[str, Any],
    limit: int = 10,
    empty_error: str | None = None,
) -> dict[str, Any]:
    q = topic.strip()
    if not q:
        result: dict[str, Any] = {"topic": "", "found": False, "pages": []}
        if empty_error:
            result["error"] = empty_error
        return result

    matches = search_pages(q, cache, limit=5)
    if not matches:
        return {"topic": topic, "found": False, "pages": []}

    primary = matches[0]
    primary_name = primary["name"].lower()
    backlinks_data, _ = load_backlinks_index(wiki_dir / "_backlinks.json")
    inbound = backlinks_data.get("backlinks", {}).get(primary_name, [])

    forward: list[str] = []
    forward_seen: set[str] = set()
    path = cache["page_index"].get(primary_name)
    if path and path.exists():
        text = path.read_text(encoding="utf-8", errors="replace")
        _, body = parse_frontmatter(text)
        page_set = {page["name"].lower() for page in cache["pages"]}
        for match in WIKILINK_RE.finditer(body):
            target = match.group(1).strip().lower()
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
    for name in context_names[:limit]:
        page_path = cache["page_index"].get(name)
        if not page_path or not page_path.exists():
            continue
        text = page_path.read_text(encoding="utf-8", errors="replace")
        meta, body = parse_frontmatter(text)
        is_primary = name == primary_name
        if is_primary:
            content = body
        else:
            summary_lines = []
            for line in body.split("\n")[:20]:
                summary_lines.append(line)
                if line.startswith("## ") and len(summary_lines) > 3:
                    break
            content = "\n".join(summary_lines)
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


def graph_data(cache: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    pages = cache["pages"]
    page_ids = {page["name"].lower(): page["name"] for page in pages}
    nodes = [
        {"id": page["name"], "title": page["title"], "category": page["category"], "type": page["type"]}
        for page in pages
    ]
    edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str]] = set()
    for page in pages:
        source = page["name"]
        path = cache["page_index"].get(source.lower())
        if not path or not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        _, body = parse_frontmatter(text)
        for match in WIKILINK_RE.finditer(body):
            target_key = match.group(1).strip().lower()
            target = page_ids.get(target_key)
            if not target or target_key == source.lower():
                continue
            edge_key = (source, target)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            edges.append({"source": source, "target": target})
    return {"nodes": nodes, "edges": edges}
