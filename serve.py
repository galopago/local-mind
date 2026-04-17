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
_token_index: dict[str, set[str]] = {}  # token → set of page stems that contain it


def _wiki_mtime() -> float:
    """Return a cheap mtime signal for the wiki directory tree.
    Checks the wiki dir and each of its immediate subdirectories (O(subdirs), not O(files)).
    On macOS/Linux, a directory's mtime updates when files inside it are added, removed,
    or renamed — but NOT when file contents change. We also spot-check the key top-level
    files (index.md, log.md, _backlinks.json) which are written on every wiki operation,
    covering the content-change case for the most frequently updated files.
    """
    try:
        t = WIKI_DIR.stat().st_mtime
        # Check each immediate subdirectory (sources, concepts, entities, comparisons, explorations)
        for child in WIKI_DIR.iterdir():
            if child.is_dir():
                t = max(t, child.stat().st_mtime)
        # Spot-check key top-level files that change on every wiki write
        for name in ("index.md", "log.md", "_backlinks.json"):
            p = WIKI_DIR / name
            if p.exists():
                t = max(t, p.stat().st_mtime)
        return t
    except Exception:
        return 0.0


def _get_all_pages() -> list:
    global _pages_cache, _pages_cache_mtime, _page_index, _fulltext_index, _token_index
    mtime = _wiki_mtime()
    if _pages_cache is not None and mtime == _pages_cache_mtime:
        return _pages_cache
    pages = []
    index: dict[str, Path] = {}
    fulltext: dict[str, str] = {}
    token_idx: dict[str, set[str]] = {}
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
        # Build inverted token index: token → set of page stems
        for token in re.split(r"\W+", text_lower):
            if len(token) >= 3:
                if token not in token_idx:
                    token_idx[token] = set()
                token_idx[token].add(stem)
        # Also index by alias so _find_page works with alternate names
        for alias in aliases:
            if alias not in index:
                index[alias] = md
    _pages_cache = pages
    _pages_cache_mtime = mtime
    _page_index = index  # share the same scan — no second mtime check needed
    _fulltext_index = fulltext  # in-memory full-text for fast search
    _token_index = token_idx  # inverted index for O(1) token lookup
    return pages


def _find_page(name: str) -> Path | None:
    # Ensure cache is warm — _get_all_pages populates _page_index as a side effect
    _get_all_pages()
    return _page_index.get(name.strip().lower())


# Keep _all_pages as alias for API compatibility
def _all_pages() -> list:
    return _get_all_pages()


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
    def _wl(m):
        inner = m.group(1)
        t, d = (inner.split("|", 1) if "|" in inner else (inner, inner))
        return f'<a href="/page/{urllib.parse.quote(t.strip())}">{html.escape(d.strip())}</a>'
    # Process backtick code spans FIRST to protect their content from further substitution
    # Replace backtick spans with placeholders, process other markup, then restore
    code_spans: list[str] = []
    def _save_code(m):
        code_spans.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00CODE{len(code_spans)-1}\x00"
    text = re.sub(r"`([^`]+)`", _save_code, text)
    # Now process remaining inline markup (wikilinks, md links, bold, italic)
    text = re.sub(r"\[\[([^\]]+)\]\]", _wl, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Guard: only match single * that are not part of **
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    # Restore code spans
    for i, span in enumerate(code_spans):
        text = text.replace(f"\x00CODE{i}\x00", span)
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
header .logo a { color: #222; text-decoration: none; }
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
  footer { border-color: #333; }
  .home-stats .stat .num { color: #6ea8fe; }
}
"""


def _header_html():
    return """<header>
  <div class="logo"><a href="/"><img src="/logo.png" alt="Link" style="height:28px;vertical-align:middle;margin-right:8px">Link</a><small>knowledge wiki</small></div>
  <nav>
    <a href="/">home</a>
    <a href="/page/log">log</a>
    <a href="/all">all pages</a>
    <form action="/search" method="get">
      <input type="text" name="q" placeholder="search..." autocomplete="off">
    </form>
  </nav>
</header>"""


def _footer_html():
    return '<footer>Link — personal knowledge wiki · <a href="https://github.com/gowtham0992/link">github</a></footer>'


def _layout(title, body):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)} — Link</title>
<link rel="icon" href="/logo.png" type="image/png">
<style>{CSS}</style>
</head>
<body>
{_header_html()}
{body}
{_footer_html()}
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
    for t in ["source", "concept", "entity", "comparison", "exploration"]:
        if counts.get(t, 0) > 0:
            label = t + "s" if not t.endswith("s") else t
            stats_items += f'<div class="stat"><span class="num">{counts[t]}</span><span class="label">{label}</span></div>'
    stats = f'<div class="home-stats">{stats_items}</div>'

    cats = {}
    for p in pages:
        if p["category"] == "root": continue
        cats.setdefault(p["category"], []).append(p)

    sections = ""
    for cat in sorted(cats.keys()):
        items = "".join(
            f'<li><a href="/page/{urllib.parse.quote(p["name"])}">{html.escape(p["title"])}</a>'
            f'<span class="type">{p["type"]}</span></li>'
            for p in sorted(cats[cat], key=lambda x: x["title"])
        )
        sections += f'<h2>{html.escape(cat)}</h2><ul class="page-list">{items}</ul>'

    if not cats:
        sections = "<p>Wiki is empty. Drop sources into <code>raw/</code> and tell your agent to ingest them.</p>"

    return _layout("Link", f"<h1>Link</h1><p>Personal knowledge wiki. Knowledge compounds here.</p>{stats}{sections}")


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
        f'<li><a href="/page/{urllib.parse.quote(p["name"])}">{html.escape(p["title"])}</a>'
        f'<span class="type">{p["type"] or p["category"]}</span></li>'
        for p in sorted(pages, key=lambda x: x["title"])
    )
    return _layout("All Pages", f'<div class="breadcrumb"><a href="/">Link</a> / all pages</div>'
                   f"<h1>All Pages ({len(pages)})</h1><ul class='page-list'>{items}</ul>")


def _render_search(query):
    q = query.lower().strip()
    if not q:
        return _layout("Search",
            f'<div class="breadcrumb"><a href="/">Link</a> / search</div>'
            f'<h1>Search</h1><p>Enter a search term above.</p>')
    results = _search_pages(q, limit=30)
    total = len(results)
    cap_note = f" (showing 30 of {total})" if total > 30 else ""
    items = "".join(
        f'<li><a href="/page/{urllib.parse.quote(r["name"])}">{html.escape(r["title"])}</a>'
        f'<br><small style="color:#888">...{html.escape(r.get("snippet",""))}...</small></li>'
        for r in results[:30]
    )
    return _layout(f"Search: {query}",
        f'<div class="breadcrumb"><a href="/">Link</a> / search</div>'
        f'<h1>Search: {html.escape(query)}</h1>'
        f'<p>{total} result{"s" if total != 1 else ""}{cap_note}</p>'
        f'<ul class="page-list">{items}</ul>')


# ---------------------------------------------------------------------------
# Agent search helpers
# ---------------------------------------------------------------------------

def _search_pages(q: str, limit: int = 20) -> list:
    """Search pages by title, alias, tag, and full-text body.
    Returns ranked results with snippet. Uses in-memory fulltext index — zero file I/O.
    """
    q_lower = q.lower()
    pages = _get_all_pages()  # also populates _fulltext_index
    scored: list[tuple[int, dict]] = []

    for p in pages:
        score = 0
        snippet = ""
        stem = p["name"].lower()

        # Title match (highest priority)
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

        # Full-text match — use inverted token index for O(1) lookup, then get snippet
        text_lower = _fulltext_index.get(stem, "")
        in_fulltext = False
        # Check token index first (fast path for single-word queries)
        if q_lower in _token_index:
            in_fulltext = stem in _token_index[q_lower]
        elif text_lower and q_lower in text_lower:
            # Multi-word or substring query — fall back to string search in memory
            in_fulltext = True
        if in_fulltext:
            score += 2
            if text_lower:
                idx = text_lower.find(q_lower)
                if idx >= 0:
                    # Get snippet from original text for display
                    path = _page_index.get(stem)
                    if path and path.exists():
                        orig = path.read_text(encoding="utf-8", errors="replace")
                        snippet = orig[max(0, idx-60):idx+len(q)+60].replace("\n", " ").strip()

        if score > 0:
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
            backlinks_data = json.loads(bl_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    inbound = backlinks_data.get(primary_name, [])

    # Load forward links (pages this page links to)
    forward: list[str] = []
    path = _page_index.get(primary_name)
    if path and path.exists():
        text = path.read_text(encoding="utf-8", errors="replace")
        _, body = _parse_frontmatter(text)
        wl_re = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
        page_set = {p["name"].lower() for p in pages}
        for m in wl_re.finditer(body):
            target = m.group(1).strip().lower()
            if target in page_set and target != primary_name:
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
    page_set = {p["name"].lower() for p in pages}
    nodes = [{"id": p["name"], "title": p["title"], "category": p["category"], "type": p["type"]} for p in pages]

    edges = []
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
            target = m.group(1).strip()
            if target.lower() in page_set and target.lower() != source.lower():
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
        if path == "/logo.png":
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
        elif path == "/all":
            self._ok(_render_all())
        elif path == "/search":
            self._ok(_render_search(query.get("q", [""])[0]))
        elif path.startswith("/page/"):
            page = _find_page(urllib.parse.unquote(path[6:]))
            if page: self._ok(_render_page(page))
            else: self._err(urllib.parse.unquote(path[6:]))
        elif path == "/api/pages":
            self._json(_all_pages())
        elif path == "/api/backlinks":
            bl_path = WIKI_DIR / "_backlinks.json"
            if bl_path.exists():
                data = json.loads(bl_path.read_text(encoding="utf-8"))
                # Support both old format (flat dict) and new format (with backlinks/forward keys)
                if "backlinks" in data:
                    self._json(data["backlinks"])
                else:
                    self._json(data)
            else:
                self._json({})
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
        elif path == "/api/search":
            q = query.get("q", [""])[0].strip()
            limit = int(query.get("limit", ["20"])[0])
            if not q:
                self._json({"error": "q parameter required", "results": []})
            else:
                results = _search_pages(q, limit=min(limit, 50))
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
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(encoded)

    def _err(self, name: str):
        encoded = _layout("Not Found", f"<h1>Not found</h1><p>No page: {html.escape(name)}</p>").encode()
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(encoded)

    def _json(self, data):
        encoded = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(encoded)

    def _file(self, fpath, content_type):
        fpath = fpath.resolve()
        # Ensure the resolved path is within the expected parent directory
        # (prevents path traversal via /raw/../../sensitive-file)
        raw_resolved = RAW_DIR.resolve()
        logo_resolved = (Path(__file__).parent / "logo.png").resolve()
        if fpath != logo_resolved and not str(fpath).startswith(str(raw_resolved) + "/") and fpath != raw_resolved:
            self._err("forbidden")
            return
        if fpath.exists() and fpath.is_file():
            data = fpath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if not getattr(self, '_head_only', False):
                self.wfile.write(data)
        else:
            self._err(str(fpath))

    def log_message(self, *a): pass


def main():
    global PORT
    for i, a in enumerate(sys.argv[1:]):
        if a == "--port" and i + 1 < len(sys.argv) - 1: PORT = int(sys.argv[i+2])
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as s:
        print(f"  Link → http://localhost:{PORT}")
        try: s.serve_forever()
        except KeyboardInterrupt: print("\n  stopped.")


if __name__ == "__main__":
    main()
