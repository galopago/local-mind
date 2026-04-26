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

mark { background: #fff3cd; color: inherit; border-radius: 2px; padding: 0 1px; }

#graph-canvas { width: 100%; height: 600px; border: 1px solid #eee; border-radius: 4px;
                cursor: grab; display: block; margin: 12px 0; }
#graph-canvas:active { cursor: grabbing; }
.graph-tooltip { position: fixed; background: #fff; border: 1px solid #ccc; border-radius: 4px;
                 padding: 6px 10px; font-size: 13px; pointer-events: none; display: none;
                 box-shadow: 0 2px 8px rgba(0,0,0,0.15); z-index: 100; }
.graph-legend { font-size: 12px; color: #888; font-family: sans-serif; margin-top: 8px; }
.graph-legend span { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
                     margin-right: 4px; vertical-align: middle; }

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
    logo_svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="28" height="28" style="vertical-align:middle;margin-right:8px">
  <defs>
    <filter id="glow"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <radialGradient id="bg" cx="40%" cy="40%" r="60%"><stop offset="0%" stop-color="#0d2137"/><stop offset="100%" stop-color="#060d18"/></radialGradient>
  </defs>
  <rect width="200" height="200" rx="32" fill="url(#bg)"/>
  <g stroke="#2dd4bf" stroke-width="3.5" filter="url(#glow)" opacity="0.9" stroke-linecap="round">
    <line x1="62" y1="32" x2="62" y2="152"/>
    <line x1="62" y1="152" x2="152" y2="152"/>
  </g>
  <g filter="url(#glow)">
    <circle cx="62"  cy="32"  r="7"   fill="#2dd4bf" opacity="0.95"/>
    <circle cx="62"  cy="72"  r="5.5" fill="#2dd4bf" opacity="0.8"/>
    <circle cx="62"  cy="112" r="5.5" fill="#2dd4bf" opacity="0.8"/>
    <circle cx="62"  cy="152" r="8.5" fill="#2dd4bf" opacity="1"/>
    <circle cx="107" cy="152" r="5.5" fill="#2dd4bf" opacity="0.8"/>
    <circle cx="152" cy="152" r="7"   fill="#2dd4bf" opacity="0.95"/>
  </g>
</svg>'''
    return f"""<header>
  <div class="logo"><a href="/">{logo_svg}Link</a><small>knowledge wiki</small></div>
  <nav>
    <a href="/">home</a>
    <a href="/page/log">log</a>
    <a href="/all">all pages</a>
    <a href="/graph">graph</a>
    <form action="/search" method="get">
      <input type="text" name="q" placeholder="search... (/)" autocomplete="off" id="search-input">
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
<div class="graph-tooltip" id="graph-tooltip"></div>
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


def _render_graph():
    graph = _get_graph_data()
    nodes_json = json.dumps(graph["nodes"])
    edges_json = json.dumps(graph["edges"])
    node_count = len(graph["nodes"])
    edge_count = len(graph["edges"])

    # Category → color mapping
    cat_colors = {"concepts": "#4e79a7", "entities": "#f28e2b", "sources": "#59a14f",
                  "comparisons": "#e15759", "explorations": "#76b7b2", "root": "#bab0ac"}

    graph_js = f"""
<script>
(function() {{
  var nodes = {nodes_json};
  var edges = {edges_json};
  var catColors = {json.dumps(cat_colors)};

  var canvas = document.getElementById('graph-canvas');
  var ctx = canvas.getContext('2d');
  var tooltip = document.getElementById('graph-tooltip');
  var W, H;

  // Fixed small node radius — Obsidian style, not scaled by connections
  var NODE_R = 6;
  var LABEL_FONT = '11px -apple-system, sans-serif';

  // Spread nodes in a circle initially so physics starts well-separated
  var pos = {{}}, vel = {{}}, pinned = {{}};
  var angleStep = (2 * Math.PI) / Math.max(nodes.length, 1);
  var initR = Math.max(80, nodes.length * 18);
  nodes.forEach(function(n, i) {{
    var a = i * angleStep;
    pos[n.id] = {{ x: Math.cos(a) * initR, y: Math.sin(a) * initR }};
    vel[n.id] = {{ x: 0, y: 0 }};
  }});

  // Adjacency
  var adj = {{}};
  nodes.forEach(function(n) {{ adj[n.id] = []; }});
  edges.forEach(function(e) {{
    if (adj[e.source]) adj[e.source].push(e.target);
    if (adj[e.target]) adj[e.target].push(e.source);
  }});

  var dragging = null, dragOffX = 0, dragOffY = 0;
  var panX = 0, panY = 0, panStartX = 0, panStartY = 0, panning = false, didPan = false;
  var zoom = 1;
  var frame = 0;
  var SETTLE = 200; // frames of physics

  function resize() {{
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = W * devicePixelRatio; canvas.height = H * devicePixelRatio;
    ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  }}

  function nodeColor(n) {{ return catColors[n.category] || '#8b949e'; }}

  function toScreen(x, y) {{
    return {{ x: (x + panX) * zoom + W/2, y: (y + panY) * zoom + H/2 }};
  }}
  function toWorld(sx, sy) {{
    return {{ x: (sx - W/2) / zoom - panX, y: (sy - H/2) / zoom - panY }};
  }}

  function simulate() {{
    // Tuned for Obsidian-like spread: strong repulsion, moderate spring, weak gravity
    var springLen = 120, springK = 0.04, repel = 8000, gravity = 0.008, damp = 0.82;
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
      // Weak center gravity
      fx -= p.x * gravity; fy -= p.y * gravity;
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
  }}

  var fitted = false;

  function draw() {{
    ctx.clearRect(0, 0, W, H);
    var time = frame * 0.018;

    // Edges — double draw: blurred glow + sharp line + flow particle
    edges.forEach(function(e) {{
      var a = toScreen(pos[e.source].x, pos[e.source].y);
      var b = toScreen(pos[e.target].x, pos[e.target].y);

      // Glow layer
      ctx.save();
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = 'rgba(88,166,255,0.12)';
      ctx.lineWidth = 3;
      ctx.filter = 'blur(2px)';
      ctx.stroke();
      ctx.restore();

      // Sharp line
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = 'rgba(139,148,158,0.2)';
      ctx.lineWidth = 0.8;
      ctx.stroke();

      // Flow particle
      var flowT = ((time * 0.5 + (a.x + b.y) * 0.001) % 2) / 2;
      var px = a.x + (b.x - a.x) * flowT;
      var py = a.y + (b.y - a.y) * flowT;
      var pa = Math.sin(flowT * Math.PI) * 0.5;
      ctx.beginPath(); ctx.arc(px, py, 1.5, 0, Math.PI*2);
      ctx.fillStyle = 'rgba(45,212,191,' + pa + ')';
      ctx.fill();
    }});

    // Nodes
    nodes.forEach(function(n) {{
      var s = toScreen(pos[n.id].x, pos[n.id].y);
      var r = NODE_R * Math.max(0.5, zoom);
      var color = nodeColor(n);
      var pulse = Math.sin(time * 1.2 + (pos[n.id].x + pos[n.id].y) * 0.01) * 0.12 + 0.88;

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

      // Label — always visible
      var label = n.title.length > 22 ? n.title.slice(0, 20) + '…' : n.title;
      ctx.font = LABEL_FONT;
      ctx.textAlign = 'center'; ctx.textBaseline = 'top';
      ctx.shadowColor = 'rgba(0,0,0,0.9)'; ctx.shadowBlur = 4;
      ctx.fillStyle = '#c9d1d9';
      ctx.fillText(label, s.x, s.y + r + 5);
      ctx.shadowBlur = 0;
    }});
  }}

  function loop() {{
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
    for (var i = nodes.length - 1; i >= 0; i--) {{
      var n = nodes[i];
      var p = pos[n.id];
      var r = NODE_R + 4; // slightly larger hit area
      var dx = w.x - p.x, dy = w.y - p.y;
      if (dx*dx + dy*dy <= r*r) return n;
    }}
    return null;
  }}

  canvas.addEventListener('mousedown', function(e) {{
    var rect = canvas.getBoundingClientRect();
    var sx = e.clientX - rect.left, sy = e.clientY - rect.top;
    var hit = hitTest(sx, sy);
    if (hit) {{
      dragging = hit; pinned[hit.id] = true;
      var w = toWorld(sx, sy);
      dragOffX = pos[hit.id].x - w.x; dragOffY = pos[hit.id].y - w.y;
    }} else {{
      panning = true; didPan = false;
      panStartX = sx - panX * zoom; panStartY = sy - panY * zoom;
    }}
  }});

  canvas.addEventListener('mousemove', function(e) {{
    var rect = canvas.getBoundingClientRect();
    var sx = e.clientX - rect.left, sy = e.clientY - rect.top;
    if (dragging) {{
      var w = toWorld(sx, sy);
      pos[dragging.id].x = w.x + dragOffX; pos[dragging.id].y = w.y + dragOffY;
    }} else if (panning) {{
      panX = (sx - panStartX) / zoom; panY = (sy - panStartY) / zoom;
      didPan = true;
    }} else {{
      var hit = hitTest(sx, sy);
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
    if (dragging) {{ pinned[dragging.id] = false; dragging = null; }}
    panning = false;
  }});

  canvas.addEventListener('click', function(e) {{
    if (didPan) {{ didPan = false; return; }}
    var rect = canvas.getBoundingClientRect();
    var hit = hitTest(e.clientX - rect.left, e.clientY - rect.top);
    if (hit) window.location.href = '/page/' + encodeURIComponent(hit.id);
  }});

  canvas.addEventListener('wheel', function(e) {{
    e.preventDefault();
    var factor = e.deltaY < 0 ? 1.12 : 0.9;
    zoom = Math.max(0.15, Math.min(6, zoom * factor));
  }}, {{ passive: false }});

  window.addEventListener('resize', function() {{ resize(); if (fitted) autoFit(); }});
  resize();
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
        f'<p style="color:#888;font-size:13px;font-family:sans-serif">'
        f'{node_count} nodes · {edge_count} edges · drag to move · scroll to zoom · click to open</p>'
        f'<canvas id="graph-canvas"></canvas>'
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
        f'<li><a href="/page/{urllib.parse.quote(r["name"])}">{_highlight(r["title"], query)}</a>'
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
