import json
import os
import tempfile
import time
import unittest
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
