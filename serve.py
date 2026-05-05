#!/usr/bin/env python3
"""Link — local wiki viewer. python serve.py → http://localhost:3000"""
from __future__ import annotations
import html, http.server, json, re, socketserver, sys, urllib.parse
from pathlib import Path

WIKI_DIR = Path(__file__).parent / "wiki"
RAW_DIR = Path(__file__).parent / "raw"
PORT = 3000

# ---------------------------------------------------------------------------
# In-memory caches — invalidated on each request by mtime check
# ---------------------------------------------------------------------------
_pages_cache: list | None = None
_pages_cache_mtime: float = 0.0
_page_index: dict[str, Path] = {}  # stem.lower() → path
_fulltext_index: dict[str, str] = {}  # stem.lower() → full text (for search)
_snippet_index: dict[str, str] = {}  # stem.lower() → pre-extracted first snippet
_token_index: dict[str, set[str]] = {}  # token → set of page stems that contain it
_page_map: dict[str, dict] = {}  # stem.lower() → page dict (for O(1) lookup in search)
_meta_token_index: dict[str, set[str]] = {}  # token → stems with that token in title/alias/tag/tldr


def _wiki_mtime() -> float:
    """Return an mtime signal for all files that affect wiki indexes.
    Directory mtimes catch added/removed files; file mtimes catch normal edits
    made from Obsidian, an editor, or an agent without touching index.md/log.md.
    """
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


def _get_all_pages() -> list:
    global _pages_cache, _pages_cache_mtime, _page_index, _fulltext_index, _snippet_index, _token_index, _page_map, _meta_token_index
    mtime = _wiki_mtime()
    if _pages_cache is not None and mtime == _pages_cache_mtime:
        return _pages_cache
    pages = []
    index: dict[str, Path] = {}
    fulltext: dict[str, str] = {}
    snippets: dict[str, str] = {}
    token_idx: dict[str, set[str]] = {}
    meta_idx: dict[str, set[str]] = {}
    for md in sorted(WIKI_DIR.rglob("*.md")):
        if md.name.startswith("."): continue
        rel = md.relative_to(WIKI_DIR)
        text = md.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(text)
        title = meta.get("title", "")
        if not title:
            m = re.search(r"^#\s+(.+)", body, re.MULTILINE)
            title = m.group(1) if m else md.stem
        cat = rel.parts[0] if len(rel.parts) > 1 else "root"

        # Extract TLDR for quick summaries
        tldr = ""
        tldr_m = re.search(r">\s*\*\*TLDR:\*\*\s*(.+)", body)
        if tldr_m:
            tldr = tldr_m.group(1).strip()

        # Normalize aliases to list
        aliases_raw = meta.get("aliases", [])
        if isinstance(aliases_raw, str):
            aliases_raw = [a.strip() for a in aliases_raw.split(",") if a.strip()]
        aliases = [a.lower() for a in aliases_raw]

        # Normalize tags to list
        tags_raw = meta.get("tags", [])
        if isinstance(tags_raw, str):
            tags_raw = [t.strip() for t in tags_raw.split(",") if t.strip()]

        stem = md.stem.lower()
        pages.append({
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
        })
        index[stem] = md
        # Store full text in memory for zero-IO search
        text_lower = text.lower()
        fulltext[stem] = text_lower
        # Pre-extract snippet: first non-empty body line after frontmatter
        body_lines = [l.strip() for l in body.split("\n") if l.strip() and not l.startswith("#") and not l.startswith(">")]
        snippets[stem] = body_lines[0][:200] if body_lines else ""
        # Build inverted token index: token → set of page stems
        for token in re.split(r"\W+", text_lower):
            if len(token) >= 3:
                if token not in token_idx:
                    token_idx[token] = set()
                token_idx[token].add(stem)
        # Build meta token index: tokens from title/aliases/tags/tldr → stems
        meta_tokens = set()
        for word in re.split(r"\W+", title.lower()):
            if len(word) >= 3: meta_tokens.add(word)
        for alias in aliases:
            for word in re.split(r"\W+", alias):
                if len(word) >= 3: meta_tokens.add(word)
        for tag in tags_raw:
            for word in re.split(r"\W+", str(tag).lower()):
                if len(word) >= 3: meta_tokens.add(word)
        if tldr:
            for word in re.split(r"\W+", tldr.lower()):
                if len(word) >= 3: meta_tokens.add(word)
        for token in meta_tokens:
            if token not in meta_idx:
                meta_idx[token] = set()
            meta_idx[token].add(stem)
        # Also index by alias so _find_page works with alternate names
        for alias in aliases:
            if alias not in index:
                index[alias] = md
    _pages_cache = pages
    _pages_cache_mtime = mtime
    _page_index = index
    _fulltext_index = fulltext
    _snippet_index = snippets
    _token_index = token_idx
    _meta_token_index = meta_idx
    _page_map = {p["name"].lower(): p for p in pages}
    return pages


def _find_page(name: str) -> Path | None:
    # Ensure cache is warm — _get_all_pages populates _page_index as a side effect
    _get_all_pages()
    return _page_index.get(name.strip().lower())


# Keep _all_pages as alias for API compatibility
def _all_pages() -> list:
    return _get_all_pages()


def _load_backlinks_index() -> tuple[dict, str | None]:
    bl_path = WIKI_DIR / "_backlinks.json"
    empty = {"backlinks": {}, "forward": {}}
    if not bl_path.exists():
        return empty, None
    try:
        data = json.loads(bl_path.read_text(encoding="utf-8"))
    except Exception as e:
        return empty, f"invalid backlinks index: {e}"
    if not isinstance(data, dict):
        return empty, "invalid backlinks index: root must be an object"
    if "backlinks" not in data:
        return {"backlinks": data, "forward": {}}, None
    backlinks = data.get("backlinks", {})
    forward = data.get("forward", {})
    if not isinstance(backlinks, dict) or not isinstance(forward, dict):
        return empty, "invalid backlinks index: backlinks and forward must be objects"
    return {"backlinks": backlinks, "forward": forward}, None


def _parse_search_limit(raw: str) -> tuple[int | None, str | None]:
    try:
        limit = int(raw)
    except ValueError:
        return None, "limit must be an integer"
    if limit < 1:
        return None, "limit must be at least 1"
    return min(limit, 50), None


def _page_href(name: str) -> str:
    return "/page/" + urllib.parse.quote(name.strip(), safe="")


def _plural_type_label(page_type: str) -> str:
    irregular = {"entity": "entities", "memory": "memories"}
    if page_type in irregular:
        return irregular[page_type]
    return page_type if page_type.endswith("s") else page_type + "s"


def _meta_tags(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raw = str(value or "").strip("[]")
    return [item.strip().strip("\"'") for item in raw.split(",") if item.strip()]


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
    records = []
    for path in sorted(memories_dir.rglob("*.md")):
        if path.name.startswith("."):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(text)
        title = meta.get("title", "")
        if not title:
            match = re.search(r"^#\s+(.+)", body, re.MULTILINE)
            title = match.group(1) if match else path.stem
        records.append({
            "name": path.stem,
            "path": f"wiki/{path.relative_to(WIKI_DIR).as_posix()}",
            "title": title,
            "memory_type": meta.get("memory_type") or "note",
            "scope": meta.get("scope") or "user",
            "status": meta.get("status") or "active",
            "date_captured": meta.get("date_captured", ""),
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
        })
    return records


def _count_values(records: list[dict[str, object]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(field) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _is_active_memory(record: dict[str, object]) -> bool:
    return str(record.get("status") or "active").lower() not in {"archived", "stale"}


def _memory_review_issues(record: dict[str, object]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    status = str(record.get("status") or "active").lower()
    review_status = str(record.get("review_status") or "pending").lower()
    memory_type = str(record.get("memory_type") or "")
    scope = str(record.get("scope") or "")
    memory_types = {"preference", "decision", "project", "fact", "note"}
    memory_scopes = {"user", "project", "global"}
    review_statuses = {"pending", "reviewed", "needs_update"}

    if review_status in {"pending", "needs_review"}:
        issues.append({
            "code": "pending_review",
            "severity": "medium",
            "message": "Memory has not been reviewed by the user.",
            "suggested_action": "Confirm it is still accurate, then run review-memory.",
        })
    elif review_status == "needs_update":
        issues.append({
            "code": "needs_update",
            "severity": "high",
            "message": "Memory is marked as needing an update.",
            "suggested_action": "Edit the memory page or archive it if it is no longer useful.",
        })
    elif review_status not in review_statuses:
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
            "message": "Memory is marked stale and excluded from default recall.",
            "suggested_action": "Archive it, restore it, or update the memory text.",
        })
    if memory_type not in memory_types:
        issues.append({
            "code": "invalid_memory_type",
            "severity": "high",
            "message": f"Unknown memory_type: {memory_type or 'missing'}.",
            "suggested_action": "Use preference, decision, project, fact, or note.",
        })
    if scope not in memory_scopes:
        issues.append({
            "code": "invalid_scope",
            "severity": "high",
            "message": f"Unknown scope: {scope or 'missing'}.",
            "suggested_action": "Use user, project, or global.",
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
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    items = []
    for record in _memory_records():
        if not include_archived and str(record.get("status") or "").lower() == "archived":
            continue
        issues = _memory_review_issues(record)
        if not issues:
            continue
        item = dict(record)
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
    counts_by_severity = {}
    for item in items:
        severity = str(item["highest_severity"])
        counts_by_severity[severity] = counts_by_severity.get(severity, 0) + 1
    return {
        "review_count": len(items),
        "counts_by_severity": counts_by_severity,
        "include_archived": include_archived,
        "items": items[:limit],
    }


def _memory_profile(limit: int = 10) -> dict[str, object]:
    limit = max(1, min(limit, 50))
    records = _memory_records()
    active_records = [
        record for record in records
        if _is_active_memory(record)
    ]
    archived_records = [
        record for record in records
        if str(record.get("status") or "").lower() == "archived"
    ]
    recent_active = sorted(
        active_records,
        key=lambda record: (
            str(record.get("date_captured") or ""),
            str(record.get("title") or "").lower(),
        ),
        reverse=True,
    )

    def typed(memory_type: str) -> list[dict[str, object]]:
        return [
            record for record in recent_active
            if str(record.get("memory_type") or "") == memory_type
        ][:limit]

    archived = sorted(
        archived_records,
        key=lambda record: (
            str(record.get("date_captured") or ""),
            str(record.get("title") or "").lower(),
        ),
        reverse=True,
    )
    return {
        "memory_count": len(records),
        "active_count": len(active_records),
        "review_count": _memory_inbox(limit=limit)["review_count"],
        "by_type": _count_values(records, "memory_type"),
        "by_scope": _count_values(records, "scope"),
        "by_status": _count_values(records, "status"),
        "recent": recent_active[:limit],
        "preferences": typed("preference"),
        "decisions": typed("decision"),
        "projects": typed("project"),
        "archived": archived[:limit],
    }


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
    return path in allowed_root_files or _is_relative_to(path, raw_root)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_frontmatter(text):
    if not text.startswith("---"): return {}, text
    end = text.find("---", 3)
    if end == -1: return {}, text
    meta = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            v = v.strip().strip('"').strip("'")
            if v.startswith("[") and v.endswith("]"):
                v = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",")]
            meta[k.strip()] = v
    return meta, text[end+3:].strip()


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
body { font-family: Georgia, "Times New Roman", serif; background: #fff; color: #222;
       max-width: 760px; margin: 0 auto; padding: 20px; }
a { color: #0645ad; }
a:hover { text-decoration: underline; }

header { border-bottom: 1px solid #ccc; padding-bottom: 12px; margin-bottom: 24px;
         display: flex; align-items: center; justify-content: space-between; }
header .logo { font-size: 24px; font-weight: bold; letter-spacing: -0.5px; }
header .logo a { color: #222; text-decoration: none; display: inline-flex; align-items: center; gap: 8px; }
header .logo img { width: 28px; height: 28px; border-radius: 7px; flex: none; }
header .logo small { font-weight: normal; font-size: 13px; color: #888; margin-left: 8px; }
header nav { display: flex; gap: 16px; font-size: 14px; font-family: sans-serif; }
header form { display: inline; }
header input { padding: 4px 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; width: 160px; }

.breadcrumb { font-size: 13px; color: #888; margin-bottom: 12px; font-family: sans-serif; }
.breadcrumb a { color: #0645ad; }

.meta { font-size: 13px; color: #666; margin-bottom: 16px; font-family: sans-serif; }
.meta .badge { background: #eee; padding: 1px 8px; border-radius: 3px; font-size: 12px; }

h1 { font-size: 26px; margin-bottom: 4px; line-height: 1.3; }
h2 { font-size: 20px; margin-top: 28px; margin-bottom: 10px; border-bottom: 1px solid #eee; padding-bottom: 4px; }
h3 { font-size: 17px; margin-top: 20px; margin-bottom: 8px; }
p { line-height: 1.7; margin-bottom: 12px; }
ul, ol { margin: 8px 0 12px 28px; line-height: 1.7; }
li { margin-bottom: 3px; }
blockquote { border-left: 3px solid #ccc; padding: 6px 16px; margin: 12px 0; color: #555; }
pre { background: #f6f6f6; padding: 14px; border-radius: 4px; overflow-x: auto; margin: 12px 0;
      font-size: 13px; font-family: Menlo, monospace; }
code { font-family: Menlo, monospace; font-size: 0.9em; }
p code { background: #f0f0f0; padding: 1px 5px; border-radius: 3px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 15px; }
th, td { border: 1px solid #ddd; padding: 7px 12px; text-align: left; }
th { background: #f8f8f8; }
hr { border: none; border-top: 1px solid #ddd; margin: 24px 0; }

.home-stats { display: flex; gap: 24px; margin: 20px 0; font-family: sans-serif; font-size: 14px; }
.home-stats .stat { text-align: center; }
.home-stats .stat .num { font-size: 28px; font-weight: bold; color: #0645ad; display: block; }
.home-stats .stat .label { color: #888; font-size: 12px; }

.page-list { list-style: none; padding: 0; margin: 12px 0; }
.page-list li { padding: 6px 0; border-bottom: 1px solid #f0f0f0; }
.page-list li:last-child { border-bottom: none; }
.page-list .type { font-size: 11px; color: #888; font-family: sans-serif; margin-left: 6px; }
.memory-profile { margin: 18px 0; }
.memory-profile .summary { color: #666; font-family: sans-serif; margin-bottom: 16px; }
.memory-profile .memory-meta { color: #888; font-size: 12px; font-family: sans-serif; }
.memory-issues { margin-top: 6px; }
.memory-issues li { border: none; padding: 0; color: #666; font-size: 13px; }
.memory-issues .severity { font-family: sans-serif; font-size: 11px; text-transform: uppercase; color: #8a6d3b; }

mark { background: #fff3cd; color: inherit; border-radius: 2px; padding: 0 1px; }

#graph-canvas { width: 100%; height: min(64vh, 620px); min-height: 420px;
                border: 1px solid #eee; border-radius: 4px; background: #101418;
                cursor: grab; display: block; margin: 12px 0; }
#graph-canvas:active { cursor: grabbing; }
#graph-canvas:focus { outline: 2px solid #6ea8fe; outline-offset: 2px; }
.graph-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
                 margin: 12px 0 8px; font: 13px -apple-system, BlinkMacSystemFont, sans-serif; }
.graph-toolbar button { border: 1px solid #d0d7de; background: #fff; color: #24292f;
                        border-radius: 4px; padding: 5px 9px; cursor: pointer; }
.graph-toolbar button:hover { background: #f6f8fa; }
.graph-toolbar button[aria-pressed="true"] { background: #0969da; border-color: #0969da; color: #fff; }
.graph-status { color: #666; margin-left: auto; }
.graph-tooltip { position: fixed; background: #fff; border: 1px solid #ccc; border-radius: 4px;
                 padding: 6px 10px; font-size: 13px; pointer-events: none; display: none;
                 box-shadow: 0 2px 8px rgba(0,0,0,0.15); z-index: 100; }
.graph-legend { font-size: 12px; color: #888; font-family: sans-serif; margin-top: 8px; }
.graph-legend span { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
                     margin-right: 4px; vertical-align: middle; }
.graph-empty { border: 1px solid #eee; border-radius: 4px; padding: 28px; background: #fafafa;
               color: #666; font-family: sans-serif; margin: 12px 0; }

footer { margin-top: 40px; padding-top: 12px; border-top: 1px solid #eee;
         font-size: 12px; color: #aaa; font-family: sans-serif; }

@media (prefers-color-scheme: dark) {
  body { background: #1a1a1a; color: #ddd; }
  a { color: #6ea8fe; }
  header { border-color: #333; }
  header .logo a { color: #ddd; }
  header input { background: #222; color: #ddd; border-color: #444; }
  .meta .badge { background: #333; }
  h2 { border-color: #333; }
  blockquote { border-color: #444; color: #aaa; }
  pre { background: #222; }
  p code { background: #2a2a2a; }
  th { background: #252525; }
  th, td { border-color: #333; }
  .page-list li { border-color: #2a2a2a; }
  .memory-profile .summary { color: #aaa; }
  .memory-issues li { color: #aaa; }
  footer { border-color: #333; }
  .home-stats .stat .num { color: #6ea8fe; }
  .graph-toolbar button { background: #222; color: #ddd; border-color: #444; }
  .graph-toolbar button:hover { background: #2a2a2a; }
  .graph-status { color: #aaa; }
  .graph-empty { background: #222; border-color: #333; color: #aaa; }
}
"""


def _header_html():
    return f"""<header>
  <div class="logo"><a href="/"><img src="/logo.svg" alt="">Link</a><small>agent memory</small></div>
  <nav>
    <a href="/">home</a>
    <a href="/inbox">inbox</a>
    <a href="/profile">profile</a>
    <a href="/page/log">log</a>
    <a href="/all">all pages</a>
    <a href="/graph">graph</a>
    <form action="/search" method="get">
      <input type="text" name="q" placeholder="search... (/)" autocomplete="off" id="search-input">
    </form>
  </nav>
</header>"""


def _footer_html():
    return '<footer>Link — local agent memory · <a href="https://github.com/gowtham0992/link">github</a></footer>'


def _layout(title, body):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)} — Link</title>
<link rel="icon" href="/logo.svg" type="image/svg+xml">
<style>{CSS}</style>
</head>
<body>
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

    return _layout("Link", f"<h1>Link</h1><p>Local agent memory. Knowledge compounds here.</p>{stats}{sections}")


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


def _render_profile():
    profile = _memory_profile(limit=12)
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
                f'{f"<small>{html.escape(str(summary))}</small>" if summary else ""}</li>'
            )
        return f"<h2>{html.escape(title)}</h2><ul class='page-list'>{items}</ul>"

    body = (
        f'<div class="breadcrumb"><a href="/">Link</a> / profile</div>'
        f'<h1>Memory Profile</h1>'
        f'<div class="memory-profile">'
        f'<p class="summary">What Link currently remembers about the user, projects, decisions, and preferences.</p>'
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


def _render_inbox():
    inbox = _memory_inbox(limit=50)
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
            items += (
                f'<li><a href="{_page_href(str(item["name"]))}">{html.escape(str(item["title"]))}</a>'
                f'<div class="memory-meta">{html.escape(meta)}</div>'
                f'{f"<small>{html.escape(str(summary))}</small>" if summary else ""}'
                f'<ul class="memory-issues">{issues}</ul></li>'
            )
        content = f"<ul class='page-list'>{items}</ul>"

    body = (
        f'<div class="breadcrumb"><a href="/">Link</a> / inbox</div>'
        f'<h1>Memory Review Inbox</h1>'
        f'<div class="memory-profile">'
        f'<p class="summary">Memories that need confirmation, stronger metadata, or cleanup.</p>'
        f'{stats}'
        f'{severity_html}'
        f'{content}'
        f'</div>'
    )
    return _layout("Memory Review Inbox", body)


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
  var status = document.getElementById('graph-status');
  var W, H;

  // Compact neural-map sizing: concepts lead, sources recede.
  var NODE_R = 6;
  var LABEL_FONT = '11px -apple-system, sans-serif';
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

  var dragging = null, dragOffX = 0, dragOffY = 0, hoverNode = null;
  var panX = 0, panY = 0, panStartX = 0, panStartY = 0, panning = false, didPan = false;
  var downX = 0, downY = 0, didDrag = false, suppressClick = false;
  var zoom = 1;
  var frame = 0;
  var showAllLabels = false;
  var motionPaused = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var SETTLE = 200; // frames of physics

  function resize() {{
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = W * devicePixelRatio; canvas.height = H * devicePixelRatio;
    ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  }}

  function nodeColor(n) {{ return catColors[n.category] || '#8b949e'; }}
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
    var parts = [
      nodes.length + ' nodes',
      edges.length + ' edges',
      Math.round(zoom * 100) + '%'
    ];
    var locked = pinnedCount();
    if (locked) parts.push(locked + ' placed');
    status.textContent = parts.join(' · ');
  }}

  function toScreen(x, y) {{
    return {{ x: (x + panX) * zoom + W/2, y: (y + panY) * zoom + H/2 }};
  }}
  function toWorld(sx, sy) {{
    return {{ x: (sx - W/2) / zoom - panX, y: (sy - H/2) / zoom - panY }};
  }}

  function simulate() {{
    // Tuned for a brain-like neural map: broad lobes, readable spacing, gentle drift.
    var springLen = 135, springK = 0.032, repel = 13500, gravity = 0.005, damp = 0.84;
    nodes.forEach(function(n) {{
      if (pinned[n.id]) return;
      var fx = 0, fy = 0;
      var p = pos[n.id];
      // Repulsion between all pairs
      nodes.forEach(function(m) {{
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
    if (nodes.length === 0) return;
    var minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    nodes.forEach(function(n) {{
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

    // Edges — double draw: blurred glow + sharp line + flow particle
    edges.forEach(function(e) {{
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
      if (activeEdge) {{
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
    nodes.forEach(function(n) {{
      var s = toScreen(pos[n.id].x, pos[n.id].y);
      var r = nodeRadius(n) * Math.max(0.65, Math.min(1.2, zoom));
      var color = nodeColor(n);
      var pulse = Math.sin(time * 1.2 + (pos[n.id].x + pos[n.id].y) * 0.01) * 0.12 + 0.88;
      var activeNode = isActiveNode(n);
      ctx.save();
      ctx.globalAlpha = hoverNode && !activeNode ? 0.28 : 1;

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
      ctx.strokeStyle = color; ctx.lineWidth = 1.5;
      ctx.globalAlpha = 0.85; ctx.stroke(); ctx.globalAlpha = 1;

      // Inner bright core
      ctx.beginPath(); ctx.arc(s.x, s.y, r * 0.35, 0, Math.PI*2);
      ctx.fillStyle = color + 'cc'; ctx.fill();

      // Labels stay sparse until a node is hovered.
      var label = n.title.length > 22 ? n.title.slice(0, 20) + '…' : n.title;
      var showLabel = showAllLabels || (hoverNode ? activeNode : (n.category !== 'sources' && degree[n.id] >= 2));
      if (showLabel) {{
        ctx.font = LABEL_FONT;
        ctx.textAlign = 'center'; ctx.textBaseline = 'top';
        ctx.shadowColor = 'rgba(0,0,0,0.9)'; ctx.shadowBlur = 4;
        ctx.fillStyle = '#dce7f2';
        ctx.fillText(label, s.x, s.y + r + 5);
        ctx.shadowBlur = 0;
      }}
      ctx.restore();
    }});
  }}

  function loop() {{
    if (!motionPaused && frame < SETTLE) {{
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
    for (var i = nodes.length - 1; i >= 0; i--) {{
      var n = nodes[i];
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
    frame = SETTLE;
    autoFit();
    updateStatus();
  }}

  function setMotionPaused(next) {{
    motionPaused = next;
    if (motionButton) {{
      motionButton.setAttribute('aria-pressed', motionPaused ? 'true' : 'false');
      motionButton.textContent = motionPaused ? 'Motion paused' : 'Motion on';
    }}
    updateStatus();
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
    }} else if (panning) {{
      panX = (sx - panStartX) / zoom; panY = (sy - panStartY) / zoom;
      if (movedPastThreshold(sx, sy)) didPan = true;
      updateStatus();
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
    }}
  }});

  canvas.addEventListener('mouseup', function() {{
    if (dragging) {{
      pinned[dragging.id] = didDrag;
      dragging = null;
      suppressClick = didDrag;
      updateStatus();
    }}
    if (panning) {{ suppressClick = didPan; }}
    panning = false;
    canvas.style.cursor = hoverNode ? 'pointer' : 'grab';
  }});

  canvas.addEventListener('mouseleave', function() {{
    hoverNode = null;
    if (tooltip) tooltip.style.display = 'none';
  }});

  canvas.addEventListener('click', function(e) {{
    if (suppressClick) {{ suppressClick = false; return; }}
    var rect = canvas.getBoundingClientRect();
    var hit = hitTest(e.clientX - rect.left, e.clientY - rect.top);
    if (hit) window.location.href = '/page/' + encodeURIComponent(hit.id);
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
  }}, {{ passive: false }});

  canvas.addEventListener('keydown', function(e) {{
    if (e.key === '+' || e.key === '=') {{ zoom = Math.min(6, zoom * 1.12); updateStatus(); e.preventDefault(); }}
    if (e.key === '-' || e.key === '_') {{ zoom = Math.max(0.15, zoom * 0.9); updateStatus(); e.preventDefault(); }}
    if (e.key === '0') {{ resetView(); e.preventDefault(); }}
    if (e.key === 'l' || e.key === 'L') {{
      showAllLabels = !showAllLabels;
      if (labelsButton) labelsButton.setAttribute('aria-pressed', showAllLabels ? 'true' : 'false');
      e.preventDefault();
    }}
  }});

  if (resetButton) resetButton.addEventListener('click', resetView);
  if (labelsButton) labelsButton.addEventListener('click', function() {{
    showAllLabels = !showAllLabels;
    labelsButton.setAttribute('aria-pressed', showAllLabels ? 'true' : 'false');
  }});
  if (motionButton) motionButton.addEventListener('click', function() {{
    setMotionPaused(!motionPaused);
  }});

  window.addEventListener('resize', function() {{ resize(); if (fitted) autoFit(); updateStatus(); }});
  resize();
  if (motionPaused) {{ autoFit(); fitted = true; frame = SETTLE; }}
  setMotionPaused(motionPaused);
  updateStatus();
  loop();
}})();
</script>"""

    legend_items = "".join(
        f'<span style="background:{c}"></span>{cat} '
        for cat, c in cat_colors.items() if cat != "root"
    )

    body = (
        f'<div class="breadcrumb"><a href="/">Link</a> / graph</div>'
        f'<h1>Knowledge Graph</h1>'
        f'<div class="graph-toolbar" aria-label="Graph controls">'
        f'<button id="graph-reset" type="button">Reset</button>'
        f'<button id="graph-labels" type="button" aria-pressed="false">Labels</button>'
        f'<button id="graph-motion" type="button" aria-pressed="false">Motion on</button>'
        f'<span id="graph-status" class="graph-status" aria-live="polite">'
        f'{node_count} nodes · {edge_count} edges</span>'
        f'</div>'
        f'<canvas id="graph-canvas" tabindex="0" role="img" '
        f'aria-label="Knowledge graph with {node_count} nodes and {edge_count} edges"></canvas>'
        f'<div class="graph-legend">{legend_items}</div>'
        f'{graph_js}'
    )
    return _layout("Knowledge Graph", body)


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
    q_lower = q.lower()
    pages = _get_all_pages()
    # Use pre-built page_map — no dict comprehension per call
    scored: list[tuple[int, dict]] = []

    # Build candidate set: pages that could possibly match
    # For single-word queries: use token index (O(1)) to get exact candidate set
    # For multi-word/substring: fall back to all pages
    is_single_token = bool(re.match(r"^\w+$", q_lower))
    if is_single_token and q_lower in _token_index:
        # Fast path: union of fulltext candidates + meta candidates — both O(1)
        token_candidates = _token_index[q_lower]
        meta_candidates = _meta_token_index.get(q_lower, set())
        candidates = token_candidates | meta_candidates
    else:
        # Substring query — must check all pages
        candidates = {p["name"].lower() for p in pages}

    for stem in candidates:
        p = _page_map.get(stem)
        if not p:
            continue
        score = 0

        # Title match
        if q_lower in p["title"].lower():
            score += 10
        # Exact name match
        if q_lower == stem:
            score += 20
        # Alias match
        if any(q_lower in a for a in p.get("aliases", [])):
            score += 8
        # Tag match
        if any(q_lower in str(t).lower() for t in p.get("tags", [])):
            score += 5
        # TLDR match
        if q_lower in p.get("tldr", "").lower():
            score += 3
        # Fulltext match
        text_lower = _fulltext_index.get(stem, "")
        if text_lower and q_lower in text_lower:
            score += 2

        if score > 0:
            # Use pre-extracted snippet — zero file I/O
            snippet = _snippet_index.get(stem, "")
            result = {**p, "score": score, "snippet": snippet}
            scored.append((score, result))

    scored.sort(key=lambda x: (-x[0], x[1]["title"].lower()))
    return [r for _, r in scored[:limit]]


def _get_context(topic: str) -> dict:
    """Return everything an agent needs to answer a question about a topic.
    Finds the best matching page, then returns:
    - The page's full content
    - Its backlinks (pages that reference it)
    - Its forward links (pages it references)
    - Related pages (shared tags or backlink overlap)
    """
    q = topic.lower().strip()
    pages = _get_all_pages()

    # Find best matching page
    matches = _search_pages(q, limit=5)
    if not matches:
        return {"topic": topic, "found": False, "pages": []}

    primary = matches[0]
    primary_name = primary["name"].lower()

    # Load backlinks
    bl_path = WIKI_DIR / "_backlinks.json"
    backlinks_data: dict = {}
    if bl_path.exists():
        try:
            raw = json.loads(bl_path.read_text(encoding="utf-8"))
            backlinks_data = raw.get("backlinks", raw)
        except Exception:
            pass

    inbound = backlinks_data.get(primary_name, [])

    # Load forward links (pages this page links to)
    forward: list[str] = []
    forward_seen: set[str] = set()
    path = _page_index.get(primary_name)
    if path and path.exists():
        text = path.read_text(encoding="utf-8", errors="replace")
        _, body = _parse_frontmatter(text)
        wl_re = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
        page_set = {p["name"].lower() for p in pages}
        for m in wl_re.finditer(body):
            target = m.group(1).strip().lower()
            if target in page_set and target != primary_name and target not in forward_seen:
                forward_seen.add(target)
                forward.append(target)

    # Build context pages list: primary + inbound + forward (deduplicated)
    seen = {primary_name}
    context_names = [primary_name]
    for name in (inbound + forward):
        if name not in seen:
            seen.add(name)
            context_names.append(name)

    # Load page summaries for context
    context_pages = []
    for name in context_names[:10]:  # cap at 10 to keep context lean
        p_path = _page_index.get(name)
        if not p_path or not p_path.exists():
            continue
        text = p_path.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(text)
        # Include full content for primary, TLDR+summary for related
        is_primary = name == primary_name
        if is_primary:
            content = body
        else:
            # Extract just TLDR + first paragraph
            lines = body.split("\n")
            summary_lines = []
            for line in lines[:20]:
                summary_lines.append(line)
                if line.startswith("## ") and len(summary_lines) > 3:
                    break
            content = "\n".join(summary_lines)

        page_meta = next((p for p in pages if p["name"].lower() == name), {})
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


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------

def _build_backlinks() -> dict[str, list[str]]:
    """Scan all wiki pages for [[wikilinks]] and build a reverse index.
    Returns {target_stem: [source_stem, ...]} mapping.
    """
    backlinks: dict[str, list[str]] = {}
    forward_links: dict[str, list[str]] = {}
    wikilink_re = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
    for md in WIKI_DIR.rglob("*.md"):
        if md.name.startswith("."): continue
        text = md.read_text(encoding="utf-8", errors="replace")
        _, body = _parse_frontmatter(text)
        source = md.stem.lower()
        for m in wikilink_re.finditer(body):
            target = m.group(1).strip().lower()
            if target != source:
                # Reverse index
                backlinks.setdefault(target, [])
                if source not in backlinks[target]:
                    backlinks[target].append(source)
                # Forward index
                forward_links.setdefault(source, [])
                if target not in forward_links[source]:
                    forward_links[source].append(target)
    return {"backlinks": backlinks, "forward": forward_links}


def _get_graph_data() -> dict:
    """Return graph nodes and edges for visualization.
    Uses in-memory fulltext index — no separate rglob scan.
    """
    pages = _get_all_pages()
    page_ids = {p["name"].lower(): p["name"] for p in pages}
    nodes = [{"id": p["name"], "title": p["title"], "category": p["category"], "type": p["type"]} for p in pages]

    edges = []
    seen_edges: set[tuple[str, str]] = set()
    wikilink_re = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
    for p in pages:
        source = p["name"]
        text_lower = _fulltext_index.get(source.lower(), "")
        if not text_lower:
            continue
        # Use original text for wikilink extraction (case-sensitive targets)
        path = _page_index.get(source.lower())
        if not path or not path.exists():
            continue
        orig = path.read_text(encoding="utf-8", errors="replace")
        _, body = _parse_frontmatter(orig)
        for m in wikilink_re.finditer(body):
            target_key = m.group(1).strip().lower()
            target = page_ids.get(target_key)
            if not target or target_key == source.lower():
                continue
            edge_key = (source, target)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            edges.append({"source": source, "target": target})

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        """HEAD requests: send headers only, no body."""
        self._head_only = True
        self.do_GET()
        self._head_only = False

    def do_GET(self):
        self._head_only = getattr(self, '_head_only', False)
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        if path == "/logo.svg":
            self._file(Path(__file__).parent / "logo.svg", "image/svg+xml")
        elif path == "/logo.png":
            self._file(Path(__file__).parent / "logo.png", "image/png")
        elif path.startswith("/raw/"):
            raw_path = Path(__file__).parent / "raw" / urllib.parse.unquote(path[5:])
            ext = raw_path.suffix.lower()
            ctypes = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                      ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
                      ".pdf": "application/pdf"}
            self._file(raw_path, ctypes.get(ext, "application/octet-stream"))
        elif path in ("/", ""):
            self._ok(_render_home())
        elif path == "/inbox":
            self._ok(_render_inbox())
        elif path == "/profile":
            self._ok(_render_profile())
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
        elif path == "/api/backlinks":
            data, error = _load_backlinks_index()
            if error:
                self._json({"error": error}, status=500)
            else:
                self._json(data)
        elif path == "/api/rebuild-backlinks":
            result = _build_backlinks()
            bl_path = WIKI_DIR / "_backlinks.json"
            bl_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            # Invalidate pages cache so next request picks up the new backlinks mtime
            global _pages_cache, _pages_cache_mtime
            _pages_cache = None
            _pages_cache_mtime = 0.0
            self._json({"rebuilt": True, "pages": len(result.get("backlinks", {}))})
        elif path == "/api/graph":
            self._json(_get_graph_data())
        elif path == "/api/memory-profile":
            limit, error = _parse_search_limit(query.get("limit", ["10"])[0])
            if error:
                self._json({"error": error}, status=400)
            else:
                self._json(_memory_profile(limit=limit))
        elif path == "/api/memory-inbox":
            limit, error = _parse_search_limit(query.get("limit", ["20"])[0])
            if error:
                self._json({"error": error}, status=400)
            else:
                include_archived = query.get("include_archived", ["false"])[0].lower() in {"1", "true", "yes"}
                self._json(_memory_inbox(limit=limit, include_archived=include_archived))
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
                self._json({"error": "topic parameter required"})
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

    def _security_headers(self):
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


def main():
    global PORT
    for i, a in enumerate(sys.argv[1:]):
        if a == "--port" and i + 1 < len(sys.argv) - 1: PORT = int(sys.argv[i+2])
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as s:
        print(f"  Link → http://localhost:{PORT}")
        try: s.serve_forever()
        except KeyboardInterrupt: print("\n  stopped.")


if __name__ == "__main__":
    main()
