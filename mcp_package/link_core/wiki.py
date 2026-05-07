"""Shared wiki indexing, search, context, and graph helpers for Link."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .frontmatter import parse_frontmatter


WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
INDEX_CATEGORY_ORDER = (
    "memories",
    "concepts",
    "entities",
    "sources",
    "comparisons",
    "explorations",
    "root",
)
INDEX_CATEGORY_TITLES = {
    "memories": "Memories",
    "concepts": "Concepts",
    "entities": "Entities",
    "sources": "Sources",
    "comparisons": "Comparisons",
    "explorations": "Explorations",
    "root": "Other Pages",
}


def normalized_search_text(value: object) -> str:
    """Normalize punctuation differences so natural queries match page slugs."""
    text = str(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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
    normalized_fulltext: dict[str, str] = {}
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
        normalized_fulltext[stem] = normalized_search_text(text_lower)
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
        "normalized_fulltext": normalized_fulltext,
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
    q_normalized = normalized_search_text(q)
    query_tokens = [token for token in re.split(r"\W+", q_lower) if len(token) >= 3]
    pages = cache["pages"]
    page_map = cache["page_map"]
    token_index = cache["token_index"]
    meta_token_index = cache["meta_token_index"]
    fulltext = cache["fulltext"]
    normalized_fulltext = cache.get("normalized_fulltext", {})
    snippet_index = cache["snippet_index"]

    is_single_token = bool(re.match(r"^\w+$", q_lower))
    if is_single_token and q_lower in token_index:
        candidates = token_index[q_lower] | meta_token_index.get(q_lower, set())
    elif query_tokens:
        token_sets = [
            token_index.get(token, set()) | meta_token_index.get(token, set())
            for token in query_tokens
            if token in token_index or token in meta_token_index
        ]
        if token_sets:
            intersection = set.intersection(*token_sets)
            candidates = intersection if intersection else set.union(*token_sets)
        else:
            candidates = {page["name"].lower() for page in pages}
    else:
        candidates = {page["name"].lower() for page in pages}

    scored: list[tuple[int, dict[str, Any]]] = []
    for stem in candidates:
        page = page_map.get(stem)
        if not page:
            continue
        score = 0
        title_normalized = normalized_search_text(page["title"])
        stem_normalized = normalized_search_text(stem)
        aliases = page.get("aliases", [])
        tags = page.get("tags", [])
        tldr = page.get("tldr", "")
        text_lower = fulltext.get(stem, "")
        meta_words = set(re.split(
            r"\W+",
            normalized_search_text(" ".join([
                str(page["title"]),
                stem,
                str(tldr),
                " ".join(str(alias) for alias in aliases),
                " ".join(str(tag) for tag in tags),
            ])),
        ))

        if q_lower in str(page["title"]).lower() or (q_normalized and q_normalized in title_normalized):
            score += 10
        if q_lower == stem or (q_normalized and q_normalized == stem_normalized):
            score += 20
        if any(q_lower in alias or (q_normalized and q_normalized in normalized_search_text(alias)) for alias in aliases):
            score += 8
        if any(q_lower in str(tag).lower() or (q_normalized and q_normalized in normalized_search_text(tag)) for tag in tags):
            score += 5
        if q_lower in str(tldr).lower() or (q_normalized and q_normalized in normalized_search_text(tldr)):
            score += 3
        text_normalized = normalized_fulltext.get(stem, "")
        if text_lower and (q_lower in text_lower or (q_normalized and q_normalized in text_normalized)):
            score += 2
        if query_tokens and all(token in meta_words for token in query_tokens):
            score += 6
        elif query_tokens and any(token in meta_words for token in query_tokens):
            score += 1
        if query_tokens and text_normalized:
            text_words = set(re.split(r"\W+", text_normalized))
            if all(token in text_words for token in query_tokens):
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


def _index_pages(cache: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        page for page in cache["pages"]
        if str(page.get("name") or "").lower() not in {"index", "log"}
    ]


def _category_sort_key(category: str) -> tuple[int, str]:
    try:
        index = INDEX_CATEGORY_ORDER.index(category)
    except ValueError:
        index = len(INDEX_CATEGORY_ORDER)
    return index, category


def _page_sort_key(page: dict[str, Any]) -> tuple[tuple[int, str], str]:
    return _category_sort_key(str(page.get("category") or "root")), str(page.get("title") or "").lower()


def _page_summary(page: dict[str, Any], cache: dict[str, Any]) -> str:
    name = str(page.get("name") or "").lower()
    tldr = str(page.get("tldr") or "").strip()
    snippet = str(cache.get("snippet_index", {}).get(name, "")).strip()
    title = str(page.get("title") or page.get("name") or "").strip()
    return tldr or snippet or title


def _index_entry(page: dict[str, Any], cache: dict[str, Any]) -> str:
    name = str(page.get("name") or "")
    title = str(page.get("title") or name)
    summary = _page_summary(page, cache)
    metadata = [
        value for value in (
            str(page.get("type") or "").strip(),
            str(page.get("maturity") or "").strip(),
        )
        if value
    ]
    meta = f" ({', '.join(metadata)})" if metadata else ""
    if summary and summary != title:
        return f"- [[{name}]] - {summary}{meta}"
    return f"- [[{name}]]{meta}"


def build_index_markdown(
    wiki_dir: Path,
    cache: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> str:
    """Build a deterministic, human-readable catalog for a Link wiki."""
    cache = cache or build_wiki_cache(wiki_dir)
    pages = sorted(_index_pages(cache), key=_page_sort_key)
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    source_count = sum(
        1 for page in pages
        if str(page.get("category") or "") == "sources" or str(page.get("type") or "") == "source"
    )
    memory_count = sum(
        1 for page in pages
        if str(page.get("category") or "") == "memories" or str(page.get("type") or "") == "memory"
    )

    categories: dict[str, list[dict[str, Any]]] = {}
    for page in pages:
        categories.setdefault(str(page.get("category") or "root"), []).append(page)

    lines = [
        "# Link Wiki Index",
        "",
        f"> Last updated: {generated_at} | {len(pages)} pages | {source_count} sources | {memory_count} memories",
        "",
        "## Categories",
        "",
    ]
    for category in sorted(categories, key=_category_sort_key):
        title = INDEX_CATEGORY_TITLES.get(category, category.replace("-", " ").title())
        lines.append(f"- {title}: {len(categories[category])}")
    if not categories:
        lines.append("- No pages yet")

    for category in sorted(categories, key=_category_sort_key):
        title = INDEX_CATEGORY_TITLES.get(category, category.replace("-", " ").title())
        lines.extend(["", f"### {category}", ""])
        for page in categories[category]:
            lines.append(_index_entry(page, cache))

    lines.extend([
        "",
        "## Recent",
        "",
        "See [[log]] for the append-only local audit trail.",
        "",
    ])
    return "\n".join(lines)


def rebuild_index(
    wiki_dir: Path,
    cache: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Regenerate wiki/index.md from the current Markdown pages."""
    cache = cache or build_wiki_cache(wiki_dir)
    markdown = build_index_markdown(wiki_dir, cache=cache, generated_at=generated_at)
    index_path = wiki_dir / "index.md"
    index_path.write_text(markdown, encoding="utf-8")
    pages = _index_pages(cache)
    category_counts: dict[str, int] = {}
    for page in pages:
        category = str(page.get("category") or "root")
        category_counts[category] = category_counts.get(category, 0) + 1
    return {
        "rebuilt": True,
        "path": "wiki/index.md",
        "page_count": len(pages),
        "source_count": sum(
            1 for page in pages
            if str(page.get("category") or "") == "sources" or str(page.get("type") or "") == "source"
        ),
        "memory_count": sum(
            1 for page in pages
            if str(page.get("category") or "") == "memories" or str(page.get("type") or "") == "memory"
        ),
        "category_counts": dict(sorted(category_counts.items(), key=lambda item: _category_sort_key(item[0]))),
        "next_actions": [
            {
                "tool": "rebuild_backlinks",
                "command": "link rebuild-backlinks",
                "reason": "Regenerated index links change graph edges; rebuild backlinks before validation.",
            }
        ],
    }
