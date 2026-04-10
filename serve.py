#!/usr/bin/env python3
"""Link — local wiki viewer. python serve.py → http://localhost:3000"""
from __future__ import annotations
import html, http.server, json, re, socketserver, sys, urllib.parse
from pathlib import Path

WIKI_DIR = Path(__file__).parent / "wiki"
PORT = 3000

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
        t, d = (inner.split("|",1) if "|" in inner else (inner, inner))
        return f'<a href="/page/{urllib.parse.quote(t.strip())}">{html.escape(d.strip())}</a>'
    text = re.sub(r"\[\[([^\]]+)\]\]", _wl, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    return text

def _md_to_html(md):
    out, in_code, in_table, in_list, lt = [], False, False, False, None
    for line in md.split("\n"):
        s = line.strip()
        if s.startswith("```"):
            if in_code: out.append("</code></pre>"); in_code=False
            else: out.append(f'<pre><code>'); in_code=True
            continue
        if in_code: out.append(html.escape(line)); continue
        if in_table and not s.startswith("|"): out.append("</tbody></table>"); in_table=False
        if in_list and not re.match(r"^\s*[-*]\s|^\s*\d+\.\s", line) and s:
            out.append(f'</{"ul" if lt=="ul" else "ol"}>'); in_list=False
        if s in ("---","***","___") and not in_table: out.append("<hr>"); continue
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m: out.append(f'<h{len(m.group(1))}>{_inline(m.group(2))}</h{len(m.group(1))}>'); continue
        if s.startswith(">"): out.append(f"<blockquote>{_inline(s[1:].strip())}</blockquote>"); continue
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.match(r"^[-:]+$",c) for c in cells): continue
            if not in_table:
                out.append("<table><thead><tr>"+"".join(f"<th>{_inline(c)}</th>" for c in cells)+"</tr></thead><tbody>"); in_table=True
            else: out.append("<tr>"+"".join(f"<td>{_inline(c)}</td>" for c in cells)+"</tr>")
            continue
        m = re.match(r"^\s*[-*]\s+(.*)", line)
        if m:
            if not in_list or lt!="ul":
                if in_list: out.append(f'</{"ul" if lt=="ul" else "ol"}>')
                out.append("<ul>"); in_list,lt=True,"ul"
            out.append(f"<li>{_inline(m.group(1))}</li>"); continue
        m = re.match(r"^\s*\d+\.\s+(.*)", line)
        if m:
            if not in_list or lt!="ol":
                if in_list: out.append(f'</{"ul" if lt=="ul" else "ol"}>')
                out.append("<ol>"); in_list,lt=True,"ol"
            out.append(f"<li>{_inline(m.group(1))}</li>"); continue
        if not s: out.append(""); continue
        out.append(f"<p>{_inline(s)}</p>")
    if in_code: out.append("</code></pre>")
    if in_table: out.append("</tbody></table>")
    if in_list: out.append(f'</{"ul" if lt=="ul" else "ol"}>')
    return "\n".join(out)

def _find_page(name):
    for md in WIKI_DIR.rglob("*.md"):
        if md.stem.lower() == name.strip().lower(): return md
    return None

def _all_pages():
    pages = []
    for md in sorted(WIKI_DIR.rglob("*.md")):
        if md.name.startswith("."): continue
        rel = md.relative_to(WIKI_DIR)
        text = md.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(text)
        title = meta.get("title","")
        if not title:
            m = re.search(r"^#\s+(.+)", body, re.MULTILINE)
            title = m.group(1) if m else md.stem
        cat = rel.parts[0] if len(rel.parts) > 1 else "root"
        pages.append({"name":md.stem,"title":title,"category":cat,"type":meta.get("type","")})
    return pages


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


def _render_home():
    pages = _all_pages()
    sources = sum(1 for p in pages if p["type"]=="source")
    concepts = sum(1 for p in pages if p["type"]=="concept")
    entities = sum(1 for p in pages if p["type"]=="entity")

    stats = f"""<div class="home-stats">
  <div class="stat"><span class="num">{len(pages)}</span><span class="label">pages</span></div>
  <div class="stat"><span class="num">{sources}</span><span class="label">sources</span></div>
  <div class="stat"><span class="num">{concepts}</span><span class="label">concepts</span></div>
  <div class="stat"><span class="num">{entities}</span><span class="label">entities</span></div>
</div>"""

    # Group by category
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

    title = meta.get("title","")
    if not title:
        m = re.search(r"^#\s+(.+)", body, re.MULTILINE)
        title = m.group(1) if m else page_path.stem

    # Breadcrumb
    rel = page_path.relative_to(WIKI_DIR)
    cat = rel.parts[0] if len(rel.parts) > 1 else ""
    crumb = f'<div class="breadcrumb"><a href="/">Link</a>'
    if cat:
        crumb += f' / {html.escape(cat)}'
    crumb += f' / {html.escape(title)}</div>'

    # Meta line
    parts = []
    if meta.get("type"): parts.append(f'<span class="badge">{html.escape(str(meta["type"]))}</span>')
    if meta.get("maturity"): parts.append(html.escape(str(meta["maturity"])))
    if meta.get("source_count"): parts.append(f'{meta["source_count"]} sources')
    if meta.get("date_updated"): parts.append(f'updated {meta["date_updated"]}')
    meta_line = f'<div class="meta">{" · ".join(parts)}</div>' if parts else ""

    return _layout(title, crumb + meta_line + body_html)


def _render_all():
    pages = _all_pages()
    items = "".join(
        f'<li><a href="/page/{urllib.parse.quote(p["name"])}">{html.escape(p["title"])}</a>'
        f'<span class="type">{p["type"] or p["category"]}</span></li>'
        for p in sorted(pages, key=lambda x: x["title"])
    )
    return _layout("All Pages", f'<div class="breadcrumb"><a href="/">Link</a> / all pages</div>'
                    f"<h1>All Pages ({len(pages)})</h1><ul class='page-list'>{items}</ul>")


def _render_search(query):
    q = query.lower()
    results = []
    for md in WIKI_DIR.rglob("*.md"):
        if md.name.startswith("."): continue
        text = md.read_text(encoding="utf-8", errors="replace")
        if q in text.lower():
            meta, body = _parse_frontmatter(text)
            title = meta.get("title","")
            if not title:
                m = re.search(r"^#\s+(.+)", body, re.MULTILINE)
                title = m.group(1) if m else md.stem
            idx = text.lower().find(q)
            snippet = text[max(0,idx-60):idx+len(query)+60].replace("\n"," ").strip()
            results.append((md.stem, title, snippet))
    items = "".join(
        f'<li><a href="/page/{urllib.parse.quote(n)}">{html.escape(t)}</a>'
        f'<br><small style="color:#888">...{html.escape(s)}...</small></li>'
        for n,t,s in results[:30]
    )
    return _layout(f"Search: {query}",
        f'<div class="breadcrumb"><a href="/">Link</a> / search</div>'
        f'<h1>Search: {html.escape(query)}</h1>'
        f'<p>{len(results)} result{"s" if len(results)!=1 else ""}</p>'
        f'<ul class="page-list">{items}</ul>')


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        if path == "/logo.png": self._file(Path(__file__).parent / "logo.png", "image/png")
        elif path.startswith("/raw/"):
            raw_path = Path(__file__).parent / "raw" / urllib.parse.unquote(path[5:])
            ext = raw_path.suffix.lower()
            ctypes = {".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",
                      ".gif":"image/gif",".webp":"image/webp",".svg":"image/svg+xml",
                      ".pdf":"application/pdf"}
            self._file(raw_path, ctypes.get(ext, "application/octet-stream"))
        elif path in ("/", ""): self._ok(_render_home())
        elif path == "/all": self._ok(_render_all())
        elif path == "/search": self._ok(_render_search(query.get("q",[""])[0]))
        elif path.startswith("/page/"):
            page = _find_page(urllib.parse.unquote(path[6:]))
            if page: self._ok(_render_page(page))
            else: self._err(urllib.parse.unquote(path[6:]))
        elif path == "/api/pages": self._json(_all_pages())
        else: self._err("page")

    def _ok(self, body):
        self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
        self.end_headers(); self.wfile.write(body.encode())

    def _err(self, name):
        self.send_response(404); self.send_header("Content-Type","text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_layout("Not Found",f"<h1>Not found</h1><p>No page: {html.escape(name)}</p>").encode())

    def _json(self, data):
        self.send_response(200); self.send_header("Content-Type","application/json")
        self.end_headers(); self.wfile.write(json.dumps(data).encode())

    def _file(self, fpath, content_type):
        fpath = fpath.resolve()
        if fpath.exists() and fpath.is_file():
            self.send_response(200); self.send_header("Content-Type", content_type)
            self.end_headers(); self.wfile.write(fpath.read_bytes())
        else:
            self._err(str(fpath))

    def log_message(self, *a): pass

def main():
    global PORT
    for i,a in enumerate(sys.argv[1:]):
        if a=="--port" and i+1<len(sys.argv)-1: PORT=int(sys.argv[i+2])
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("",PORT),Handler) as s:
        print(f"  Link → http://localhost:{PORT}")
        try: s.serve_forever()
        except KeyboardInterrupt: print("\n  stopped.")

if __name__=="__main__": main()
