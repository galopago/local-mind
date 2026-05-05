import json
import os
import tempfile
import time
import unittest
from io import BytesIO
from pathlib import Path

import serve


def reset_wiki(wiki_dir: Path) -> None:
    serve.WIKI_DIR = wiki_dir
    serve.RAW_DIR = wiki_dir.parent / "raw"
    serve._pages_cache = None
    serve._pages_cache_mtime = 0.0
    serve._page_index = {}
    serve._fulltext_index = {}
    serve._snippet_index = {}
    serve._token_index = {}
    serve._page_map = {}
    serve._meta_token_index = {}


def write_page(wiki_dir: Path, rel: str, text: str) -> Path:
    path = wiki_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_handler(method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None):
    handler = object.__new__(serve.Handler)
    handler.command = method
    handler.path = path
    handler.request_version = "HTTP/1.1"
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.client_address = ("127.0.0.1", 0)
    handler.server = None
    handler.headers = headers or {}
    handler.rfile = BytesIO(body)
    handler.wfile = BytesIO()
    if method == "POST":
        handler.do_POST()
    elif method == "GET":
        handler.do_GET()
    else:
        raise ValueError(method)
    raw = handler.wfile.getvalue()
    header_bytes, _, body_bytes = raw.partition(b"\r\n\r\n")
    status_line = header_bytes.splitlines()[0].decode("ascii")
    status = int(status_line.split()[1])
    payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else None
    return status, payload


class ServeTests(unittest.TestCase):
    def make_wiki(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="link-test-"))
        wiki = tmp / "wiki"
        wiki.mkdir()
        write_page(wiki, "index.md", "# Index\n")
        write_page(wiki, "log.md", "# Log\n")
        (wiki / "_backlinks.json").write_text("{}", encoding="utf-8")
        reset_wiki(wiki)
        return wiki

    def test_plural_type_label_handles_entities(self):
        self.assertEqual(serve._plural_type_label("source"), "sources")
        self.assertEqual(serve._plural_type_label("concept"), "concepts")
        self.assertEqual(serve._plural_type_label("entity"), "entities")
        self.assertEqual(serve._plural_type_label("memory"), "memories")

    def test_layout_handles_search_enter_key(self):
        html = serve._layout("Test", "<p>Body</p>")

        self.assertIn("document.activeElement.id === 'search-input'", html)
        self.assertIn("window.location.href = '/search?q=' + encodeURIComponent(q);", html)

    def test_context_reads_current_backlinks_shape(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/a.md",
            "---\ntype: concept\ntitle: A\n---\n# A\n\nA body\n",
        )
        write_page(
            wiki,
            "concepts/b.md",
            "---\ntype: concept\ntitle: B\n---\n# B\n\nlinks [[a]]\n",
        )
        (wiki / "_backlinks.json").write_text(
            json.dumps({"backlinks": {"a": ["b"]}, "forward": {"b": ["a"]}}),
            encoding="utf-8",
        )

        ctx = serve._get_context("A")

        self.assertEqual(ctx["inbound_count"], 1)
        self.assertEqual([page["name"] for page in ctx["pages"]], ["a", "b"])

    def test_context_deduplicates_forward_links(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/a.md",
            "---\ntype: concept\ntitle: A\n---\n# A\n\n[[b]] [[b]] [[c]] [[b]]\n",
        )
        write_page(
            wiki,
            "concepts/b.md",
            "---\ntype: concept\ntitle: B\n---\n# B\n",
        )
        write_page(
            wiki,
            "concepts/c.md",
            "---\ntype: concept\ntitle: C\n---\n# C\n",
        )

        ctx = serve._get_context("A")

        self.assertEqual(ctx["forward_count"], 2)
        self.assertEqual([page["name"] for page in ctx["pages"]], ["a", "b", "c"])

    def test_inline_markdown_sanitizes_html_and_links(self):
        rendered = serve._md_to_html(
            "Hello <script>alert(1)</script> "
            "and [bad](javascript:alert%281%29) "
            "and [ok](https://example.com?a=1&b=2) "
            "and [[target|<b>label</b>]] "
            "and `<tag>`"
        )

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertIn('<a href="#">bad</a>', rendered)
        self.assertIn('<a href="https://example.com?a=1&amp;b=2">ok</a>', rendered)
        self.assertIn('<a href="/page/target">&lt;b&gt;label&lt;/b&gt;</a>', rendered)
        self.assertIn("<code>&lt;tag&gt;</code>", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("javascript:", rendered.lower())

    def test_wikilink_targets_encode_path_separators(self):
        rendered = serve._md_to_html("[[../raw/private|private]]")

        self.assertIn('<a href="/page/..%2Fraw%2Fprivate">private</a>', rendered)
        self.assertNotIn("/page/../raw/private", rendered)

    def test_json_for_script_escapes_script_end_tags(self):
        rendered = serve._json_for_script({"title": "</script><script>alert(1)</script>"})

        self.assertIn("\\u003c/script\\u003e", rendered)
        self.assertNotIn("</script>", rendered.lower())

    def test_static_file_allowlist_rejects_raw_traversal(self):
        wiki = self.make_wiki()
        raw_dir = wiki.parent / "raw"
        raw_dir.mkdir()
        reset_wiki(wiki)

        allowed = serve._safe_resolve(raw_dir / "note.txt")
        denied = serve._safe_resolve(raw_dir / "../serve.py")

        self.assertIsNotNone(allowed)
        self.assertIsNotNone(denied)
        self.assertTrue(serve._is_allowed_static_file(allowed))
        self.assertFalse(serve._is_allowed_static_file(denied))

    def test_static_file_resolve_handles_malformed_paths(self):
        self.assertIsNone(serve._safe_resolve(Path("bad\0path")))

    def test_cache_invalidation_sees_existing_page_edits(self):
        wiki = self.make_wiki()
        page = write_page(
            wiki,
            "concepts/a.md",
            "---\ntype: concept\ntitle: A\n---\n# A\n",
        )

        before = serve._get_all_pages()
        page.write_text("---\ntype: concept\ntitle: A2\n---\n# A2\n", encoding="utf-8")
        future = time.time() + 2
        os.utime(page, (future, future))
        after = serve._get_all_pages()

        self.assertEqual(next(p["title"] for p in before if p["name"] == "a"), "A")
        self.assertEqual(next(p["title"] for p in after if p["name"] == "a"), "A2")

    def test_backlinks_loader_returns_documented_shape(self):
        wiki = self.make_wiki()
        (wiki / "_backlinks.json").write_text(
            json.dumps({"backlinks": {"a": ["b"]}, "forward": {"b": ["a"]}}),
            encoding="utf-8",
        )

        data, error = serve._load_backlinks_index()

        self.assertIsNone(error)
        self.assertEqual(data, {"backlinks": {"a": ["b"]}, "forward": {"b": ["a"]}})

    def test_backlinks_loader_supports_old_flat_shape(self):
        wiki = self.make_wiki()
        (wiki / "_backlinks.json").write_text(json.dumps({"a": ["b"]}), encoding="utf-8")

        data, error = serve._load_backlinks_index()

        self.assertIsNone(error)
        self.assertEqual(data, {"backlinks": {"a": ["b"]}, "forward": {}})

    def test_graph_data_uses_canonical_node_ids(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/transformers.md",
            "---\ntype: concept\ntitle: Transformers\n---\n# Transformers\n",
        )
        write_page(
            wiki,
            "concepts/ai-evolution.md",
            (
                "---\ntype: concept\ntitle: AI evolution\n---\n"
                "# AI evolution\n\n"
                "[[Transformers]] and [[transformers]] and [[missing-page]]\n"
            ),
        )

        graph = serve._get_graph_data()

        self.assertIn({"source": "ai-evolution", "target": "transformers"}, graph["edges"])
        self.assertNotIn({"source": "ai-evolution", "target": "Transformers"}, graph["edges"])
        self.assertFalse(any(edge["target"] == "missing-page" for edge in graph["edges"]))
        self.assertEqual(
            sum(1 for edge in graph["edges"] if edge == {"source": "ai-evolution", "target": "transformers"}),
            1,
        )

    def test_graph_tooltip_exists_before_graph_script(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/a.md",
            "---\ntype: concept\ntitle: A\n---\n# A\n",
        )

        html = serve._render_graph()

        self.assertLess(html.index('id="graph-tooltip"'), html.index("var tooltip ="))

    def test_propose_memories_post_is_write_free(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "memories/prefer-release-branches.md",
            (
                "---\n"
                "type: memory\n"
                "title: \"Prefer release branches\"\n"
                "memory_type: preference\n"
                "scope: project\n"
                "status: active\n"
                "date_captured: \"2026-05-05T00:00:00Z\"\n"
                "source: \"unit test\"\n"
                "review_status: pending\n"
                "tags: [memory, preference]\n"
                "---\n\n"
                "# Prefer release branches\n\n"
                "> **TLDR:** User prefers release branches for Link work.\n\n"
                "## Memory\n\nUser prefers release branches for Link work.\n"
            ),
        )
        before_files = sorted(path.relative_to(wiki).as_posix() for path in wiki.rglob("*") if path.is_file())

        request_body = json.dumps({
            "text": "\n".join([
                "I prefer release branches for Link work.",
                "We decided to keep Memory Mode local and source-backed.",
                "Maybe we could add cloud sync later.",
            ]),
            "source": "unit test session",
        }).encode("utf-8")
        status, payload = run_handler(
            "POST",
            "/api/propose-memories",
            body=request_body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(request_body)),
            },
        )
        get_status, get_payload = run_handler("GET", "/api/propose-memories")
        bad_type_status, bad_type_payload = run_handler(
            "POST",
            "/api/propose-memories",
            body=request_body,
            headers={
                "Content-Type": "text/plain",
                "Content-Length": str(len(request_body)),
            },
        )

        after_files = sorted(path.relative_to(wiki).as_posix() for path in wiki.rglob("*") if path.is_file())

        self.assertEqual(status, 200)
        self.assertTrue(payload["proposed"])
        self.assertFalse(payload["writes_memory"])
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["proposals"][0]["suggested_action"], "update-memory")
        self.assertEqual(payload["proposals"][0]["duplicate_candidates"][0]["name"], "prefer-release-branches")
        self.assertEqual(payload["proposals"][1]["suggested_action"], "remember")
        self.assertEqual(before_files, after_files)
        self.assertEqual(get_status, 405)
        self.assertIn("use POST", get_payload["error"])
        self.assertEqual(bad_type_status, 415)
        self.assertIn("application/json", bad_type_payload["error"])

    def test_graph_controls_exist_before_graph_script(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/a.md",
            "---\ntype: concept\ntitle: A\n---\n# A\n",
        )

        html = serve._render_graph()

        self.assertLess(html.index('id="graph-reset"'), html.index("var resetButton ="))
        self.assertLess(html.index('id="graph-labels"'), html.index("var labelsButton ="))
        self.assertLess(html.index('id="graph-motion"'), html.index("var motionButton ="))
        self.assertLess(html.index('id="graph-inspector"'), html.index("var inspector ="))
        self.assertIn('id="graph-status"', html)
        self.assertIn('id="graph-open"', html)
        self.assertIn('tabindex="0"', html)
        self.assertIn('role="img"', html)

    def test_graph_empty_state_when_no_visible_pages(self):
        wiki = self.make_wiki()

        html = serve._render_graph()

        self.assertIn("No graph pages yet.", html)
        self.assertNotIn('id="graph-canvas"', html)

    def test_graph_drag_and_zoom_interactions_are_guarded(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/a.md",
            "---\ntype: concept\ntitle: A\n---\n# A\n",
        )

        html = serve._render_graph()

        self.assertIn("return dx * dx + dy * dy > 9;", html)
        self.assertIn("pinned[dragging.id] = didDrag;", html)
        self.assertIn("if (hit) selectNode(hit);", html)
        self.assertIn("canvas.addEventListener('dblclick'", html)
        self.assertIn("if (hit) openNode(hit);", html)
        self.assertIn("panX += after.x - before.x;", html)

    def test_graph_script_embeds_titles_safely(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/evil.md",
            "---\ntype: concept\ntitle: </script><script>alert(1)</script>\n---\n# Evil\n",
        )

        rendered = serve._render_graph()

        self.assertIn("\\u003c/script\\u003e\\u003cscript\\u003ealert(1)\\u003c/script\\u003e", rendered)
        self.assertNotIn("</script><script>alert(1)</script>", rendered.lower())

    def test_search_limit_validation(self):
        self.assertEqual(serve._parse_search_limit("3"), (3, None))
        self.assertEqual(serve._parse_search_limit("500"), (50, None))
        self.assertEqual(serve._parse_search_limit("bad"), (None, "limit must be an integer"))
        self.assertEqual(serve._parse_search_limit("0"), (None, "limit must be at least 1"))


if __name__ == "__main__":
    unittest.main()
