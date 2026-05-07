import json
import os
import tempfile
import time
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import serve
from link_core.schema import write_schema


def reset_wiki(wiki_dir: Path) -> None:
    close = getattr(getattr(serve, "_fts_index", None), "close", None)
    if callable(close):
        close()
    serve.WIKI_DIR = wiki_dir
    serve.RAW_DIR = wiki_dir.parent / "raw"
    serve._pages_cache = None
    serve._pages_cache_mtime = 0.0
    serve._pages_cache_checked_at = 0.0
    serve.CACHE_MTIME_CHECK_INTERVAL_SECONDS = 0.0
    serve._page_index = {}
    serve._fulltext_index = {}
    serve._normalized_fulltext_index = {}
    serve._text_words_index = {}
    serve._meta_words_index = {}
    serve._snippet_index = {}
    serve._token_index = {}
    serve._page_map = {}
    serve._meta_token_index = {}
    serve._fts_index = None
    serve._search_backend = "token-index"


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


def post_json(path: str, payload: dict[str, object], local_action: bool = True):
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }
    if local_action:
        headers["X-Link-Local-Action"] = "true"
    return run_handler(
        "POST",
        path,
        body,
        headers,
    )


class ServeTests(unittest.TestCase):
    def make_wiki(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="link-test-"))
        wiki = tmp / "wiki"
        wiki.mkdir()
        write_page(wiki, "index.md", "# Index\n")
        write_page(wiki, "log.md", "# Log\n")
        (wiki / "_backlinks.json").write_text("{}", encoding="utf-8")
        write_schema(wiki)
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
        self.assertIn("data-theme-toggle", html)
        self.assertIn("localStorage.getItem('link-theme')", html)
        self.assertIn("navigator.clipboard.writeText", html)
        self.assertIn("data-copy-text", html)
        self.assertIn("data-raw-source-form", html)
        self.assertIn("/api/raw-source", html)
        self.assertIn('<a href="/ingest">ingest</a>', html)
        self.assertIn('<a href="/brief">brief</a>', html)
        self.assertIn('<a href="/propose">propose</a>', html)
        self.assertIn('<a href="/audit">audit</a>', html)
        self.assertIn('<a href="/captures">captures</a>', html)

    def test_css_has_mobile_overflow_guards(self):
        self.assertIn("* { box-sizing: border-box; margin: 0; padding: 0; }", serve.CSS)
        self.assertIn("html { overflow-x: hidden; background: var(--bg); }", serve.CSS)
        self.assertIn("overflow-x: hidden; overflow-wrap: anywhere", serve.CSS)
        self.assertIn("a, p, li, code { overflow-wrap: anywhere; }", serve.CSS)
        self.assertIn("header .header-top { display: flex;", serve.CSS)
        self.assertIn("header nav { display: flex; gap: 10px 16px;", serve.CSS)
        self.assertIn("flex-wrap: wrap; min-width: 0", serve.CSS)
        self.assertIn(".raw-source-controls { grid-template-columns: minmax(0, 1fr); }", serve.CSS)
        self.assertIn(".memory-grid { grid-template-columns: minmax(0, 1fr); }", serve.CSS)
        self.assertIn(".memory-actions code, .memory-next code { word-break: break-word; }", serve.CSS)

    def test_security_headers_include_api_version(self):
        handler = object.__new__(serve.Handler)
        headers = []
        handler.send_header = lambda key, value: headers.append((key, value))

        handler._security_headers()

        self.assertIn(("X-Link-API-Version", serve.API_VERSION), headers)
        self.assertIn(("X-Content-Type-Options", "nosniff"), headers)

    def test_server_args_stay_local_only(self):
        self.assertEqual(serve._parse_serve_port(["--port", "3010"], default=3000), 3010)
        self.assertEqual(serve._parse_serve_port(["--port=3011"], default=3000), 3011)
        with self.assertRaises(SystemExit):
            serve._parse_serve_port(["--host", "0.0.0.0"], default=3000)
        with self.assertRaises(SystemExit):
            serve._parse_serve_port(["--bind=0.0.0.0"], default=3000)

    def test_home_page_shows_first_agent_prompts(self):
        self.make_wiki()

        html = serve._render_home()

        self.assertIn('<a href="/prompts">prompts</a>', html)
        self.assertIn("Try These Prompts", html)
        self.assertIn("is Link ready?", html)
        self.assertIn("brief me from Link before we continue", html)
        self.assertIn("ingest raw/&lt;file&gt; into Link", html)
        self.assertIn("query Link for what you know about me", html)
        self.assertIn("propose memories from raw/&lt;file&gt;", html)
        self.assertIn("Open starter prompts", html)

    def test_prompts_page_and_api_share_starter_prompts(self):
        self.make_wiki()

        html = serve._render_prompts(project="Client Launch")
        status, payload = run_handler("GET", "/api/prompts?project=Client%20Launch")

        self.assertEqual(status, 200)
        self.assertEqual(payload["project"], "client-launch")
        self.assertEqual(payload["prompts"][0]["prompt"], "is Link ready?")
        self.assertIn("this project uses Link", payload["prompts"][2]["prompt"])
        self.assertIn("Starter Prompts", html)
        self.assertIn("Ask Your Agent", html)
        self.assertIn("Local Checks", html)
        self.assertIn("Project examples are scoped to <code>client-launch</code>", html)
        self.assertIn("link status --validate", html)

    def test_css_has_explicit_black_dark_theme(self):
        self.assertIn(':root[data-theme="dark"]', serve.CSS)
        self.assertIn("--bg: #000000;", serve.CSS)
        self.assertIn("body { font-family: Georgia", serve.CSS)
        self.assertIn("background: var(--bg); color: var(--text);", serve.CSS)
        self.assertNotIn("background: #1a1a1a", serve.CSS)

    def test_raw_static_paths_stay_under_raw_directory(self):
        wiki = self.make_wiki()
        raw = wiki.parent / "raw"
        raw.mkdir()
        asset = raw / "asset.png"
        asset.write_bytes(b"not really a png")

        good_path, good_type = serve._resolve_raw_static_path("asset.png")
        parent_path, parent_type = serve._resolve_raw_static_path("../logo.png")
        encoded_path, encoded_type = serve._resolve_raw_static_path("%2e%2e/logo.png")
        wiki_path, wiki_type = serve._resolve_raw_static_path("../wiki/index.png")

        self.assertEqual(good_path, asset.resolve())
        self.assertEqual(good_type, "image/png")
        self.assertIsNone(parent_path)
        self.assertIsNone(parent_type)
        self.assertIsNone(encoded_path)
        self.assertIsNone(encoded_type)
        self.assertIsNone(wiki_path)
        self.assertIsNone(wiki_type)

    def test_graph_labels_are_clamped_inside_canvas(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/a.md",
            "---\ntype: concept\ntitle: A\n---\n# A\n\n[[b]]\n",
        )
        write_page(
            wiki,
            "concepts/b.md",
            "---\ntype: concept\ntitle: B\n---\n# B\n",
        )
        html = serve._render_graph()

        self.assertIn("var labelWidth = ctx.measureText(label).width;", html)
        self.assertIn("var labelX = Math.max(labelWidth / 2 + 4", html)
        self.assertIn("ctx.fillText(label, labelX", html)

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

    def test_context_api_requires_topic_with_bad_request(self):
        self.make_wiki()

        status, payload = run_handler("GET", "/api/context")

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "topic parameter required")

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

        allowed = serve._safe_resolve(raw_dir / "image.png")
        unsupported = serve._safe_resolve(raw_dir / "note.txt")
        denied = serve._safe_resolve(raw_dir / "../serve.py")

        self.assertIsNotNone(allowed)
        self.assertIsNotNone(unsupported)
        self.assertIsNotNone(denied)
        self.assertTrue(serve._is_allowed_static_file(allowed))
        self.assertFalse(serve._is_allowed_static_file(unsupported))
        self.assertFalse(serve._is_allowed_static_file(denied))

    def test_static_file_resolve_handles_malformed_paths(self):
        self.assertIsNone(serve._safe_resolve(Path("bad\0path")))

    def test_memory_dashboard_next_actions_empty_and_ready_states(self):
        empty_actions = serve._memory_dashboard_next_actions(
            memory_count=0,
            review_count=0,
            updated_count=0,
            archived_count=0,
        )
        ready_actions = serve._memory_dashboard_next_actions(
            memory_count=2,
            review_count=0,
            updated_count=0,
            archived_count=0,
        )

        self.assertEqual(empty_actions[0]["label"], "Create the first memory")
        self.assertIn("remember", empty_actions[0]["command"])
        self.assertEqual(ready_actions[0]["label"], "Memory is recall-ready")
        self.assertEqual(ready_actions[0]["href"], "/profile")

    def test_memory_dashboard_next_actions_uses_singular_memory_label(self):
        actions = serve._memory_dashboard_next_actions(
            memory_count=1,
            review_count=1,
            updated_count=0,
            archived_count=0,
        )

        self.assertIn("1 memory needs confirmation", actions[0]["detail"])
        self.assertNotIn("memoryy", actions[0]["detail"])

    def test_memory_dashboard_surfaces_raw_captures_and_secret_warnings(self):
        wiki = self.make_wiki()
        capture_dir = wiki.parent / "raw" / "memory-captures"
        capture_dir.mkdir(parents=True)
        fake_key = "sk-" + ("D" * 24)
        (capture_dir / "session.md").write_text(
            "---\n"
            "title: \"Session capture\"\n"
            "source_type: conversation\n"
            "date_captured: \"2026-05-05T00:00:00Z\"\n"
            "project: \"link\"\n"
            "---\n\n"
            "# Session capture\n\n"
            "## Notes\n\n"
            f"Remember that dashboard capture review is visible. Test key {fake_key}\n",
            encoding="utf-8",
        )

        dashboard = serve._memory_dashboard(limit=8)
        html = serve._render_memory_dashboard()

        self.assertEqual(dashboard["capture_count"], 1)
        self.assertEqual(dashboard["capture_warning_count"], 1)
        self.assertEqual(dashboard["captures"][0]["secret_warnings"], ["OpenAI API key"])
        self.assertIn("[redacted-secret]", dashboard["captures"][0]["snippet"])
        self.assertNotIn(fake_key, dashboard["captures"][0]["snippet"])
        self.assertIn("Redact capture warnings", dashboard["next_actions"][0]["label"])
        self.assertIn("accept-capture", dashboard["captures"][0]["commands"]["accept"])
        self.assertIn("Raw captures", html)
        self.assertIn("redact-capture", html)
        self.assertNotIn(fake_key, html)

    def test_capture_inbox_page_and_api_redact_secret_values(self):
        wiki = self.make_wiki()
        capture_dir = wiki.parent / "raw" / "memory-captures"
        capture_dir.mkdir(parents=True)
        fake_key = "sk-" + ("K" * 24)
        (capture_dir / "alpha.md").write_text(
            "---\n"
            "title: \"Alpha capture\"\n"
            "source_type: conversation\n"
            "date_captured: \"2026-05-05T00:00:00Z\"\n"
            "project: \"alpha\"\n"
            "---\n\n"
            "# Alpha capture\n\n"
            "## Notes\n\n"
            f"Remember that capture inbox is first class. Test key {fake_key}\n",
            encoding="utf-8",
        )
        (capture_dir / "beta.md").write_text(
            "---\n"
            "title: \"Beta capture\"\n"
            "source_type: conversation\n"
            "date_captured: \"2026-05-05T00:00:00Z\"\n"
            "project: \"beta\"\n"
            "---\n\n"
            "# Beta capture\n\n"
            "## Notes\n\n"
            "Remember that beta capture stays separate.\n",
            encoding="utf-8",
        )

        status, payload = run_handler("GET", "/api/capture-inbox?project=alpha")
        html = serve._render_captures(project="alpha")

        self.assertEqual(status, 200)
        self.assertEqual(payload["project"], "alpha")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["warning_count"], 1)
        self.assertEqual(payload["captures"][0]["secret_warnings"], ["OpenAI API key"])
        self.assertIn("[redacted-secret]", payload["captures"][0]["snippet"])
        self.assertNotIn(fake_key, json.dumps(payload))
        self.assertIn("Raw Capture Inbox", html)
        self.assertIn("Alpha capture", html)
        self.assertNotIn("Beta capture", html)
        self.assertIn("redact-capture", html)
        self.assertNotIn(fake_key, html)

    def test_memory_brief_page_and_api_include_capture_status(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "memories/alpha-brief.md",
            (
                "---\n"
                "type: memory\n"
                "title: \"Alpha brief\"\n"
                "memory_type: project\n"
                "scope: project\n"
                "project: \"alpha\"\n"
                "status: active\n"
                "date_captured: \"2026-05-05T00:00:00Z\"\n"
                "source: \"unit test\"\n"
                "review_status: pending\n"
                "---\n\n"
                "# Alpha brief\n\n"
                "> **TLDR:** Alpha project uses memory brief before work.\n\n"
                "## Memory\n\nAlpha project uses memory brief before work.\n"
            ),
        )
        capture_dir = wiki.parent / "raw" / "memory-captures"
        capture_dir.mkdir(parents=True)
        fake_key = "sk-" + ("L" * 24)
        (capture_dir / "alpha.md").write_text(
            "---\n"
            "title: \"Alpha brief capture\"\n"
            "source_type: conversation\n"
            "date_captured: \"2026-05-05T00:00:00Z\"\n"
            "project: \"alpha\"\n"
            "---\n\n"
            "# Alpha brief capture\n\n"
            "## Notes\n\n"
            f"Remember that brief surfaces capture status. Test key {fake_key}\n",
            encoding="utf-8",
        )

        status, payload = run_handler("GET", "/api/memory-brief?q=brief&project=alpha")
        html = serve._render_brief(query="brief", project="alpha")

        self.assertEqual(status, 200)
        self.assertEqual(payload["query"], "brief")
        self.assertEqual(payload["project"], "alpha")
        self.assertEqual(payload["relevant_count"], 1)
        self.assertEqual(payload["captures"]["count"], 1)
        self.assertEqual(payload["captures"]["warning_count"], 1)
        self.assertIn("Redact raw captures", "\n".join(payload["agent_guidance"]))
        self.assertNotIn(fake_key, json.dumps(payload))
        self.assertIn("Memory Brief", html)
        self.assertIn("Agent Guidance", html)
        self.assertIn("Alpha brief", html)
        self.assertIn("Alpha brief capture", html)
        self.assertNotIn(fake_key, html)

    def test_query_link_api_returns_context_packet(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/agent-memory.md",
            "---\ntype: concept\ntitle: Agent memory\ntags: [memory]\n---\n\n"
            "# Agent memory\n\n"
            "> **TLDR:** Agents use durable local memory.\n\n"
            "## Overview\n\nAgent memory connects to [[retrieval]].\n",
        )
        write_page(
            wiki,
            "concepts/retrieval.md",
            "---\ntype: concept\ntitle: Retrieval\n---\n\n"
            "# Retrieval\n\n> **TLDR:** Retrieval selects context.\n",
        )
        write_page(
            wiki,
            "memories/prefer-local-memory.md",
            "---\n"
            "type: memory\n"
            "title: Prefer local memory\n"
            "memory_type: preference\n"
            "scope: user\n"
            "status: active\n"
            "date_captured: \"2026-05-05T00:00:00Z\"\n"
            "source: unit-test\n"
            "review_status: reviewed\n"
            "tags: [memory]\n"
            "---\n\n"
            "# Prefer local memory\n\n"
            "> **TLDR:** User prefers local agent memory.\n\n"
            "## Memory\n\nUser prefers local agent memory.\n",
        )
        (wiki / "_backlinks.json").write_text(json.dumps(serve._build_backlinks()), encoding="utf-8")
        reset_wiki(wiki)

        status, payload = run_handler("GET", "/api/query-link?q=agent%20memory&budget=small")

        self.assertEqual(status, 200)
        self.assertTrue(payload["found"])
        self.assertEqual(payload["budget"], "small")
        self.assertEqual(payload["wiki"]["primary"], "agent-memory")
        self.assertEqual(payload["memory"]["items"][0]["name"], "prefer-local-memory")
        self.assertIn("context_packet", payload)
        self.assertIn("budget_report", payload)
        self.assertIn("follow_up", payload)

    def test_status_api_returns_readiness_summary(self):
        wiki = self.make_wiki()
        for dirname in ("sources", "concepts", "entities", "memories", "comparisons", "explorations"):
            (wiki / dirname).mkdir(exist_ok=True)
        write_page(
            wiki,
            "memories/prefer-local-memory.md",
            "---\n"
            "type: memory\n"
            "title: Prefer local memory\n"
            "memory_type: preference\n"
            "scope: user\n"
            "status: active\n"
            "date_captured: \"2026-05-05T00:00:00Z\"\n"
            "source: unit-test\n"
            "review_status: reviewed\n"
            "---\n\n"
            "# Prefer local memory\n\n"
            "> **TLDR:** User prefers local memory.\n\n"
            "## Memory\n\nUser prefers local memory.\n\n"
            "## Source\n\nunit-test\n",
        )
        (wiki / "_backlinks.json").write_text(json.dumps(serve._build_backlinks()), encoding="utf-8")
        reset_wiki(wiki)

        status, payload = run_handler("GET", "/api/status?validate=true")

        self.assertEqual(status, 200)
        self.assertEqual(payload["api_version"], serve.API_VERSION)
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["memory_count"], 1)
        self.assertIn(payload["search_backend"], {"sqlite-fts", "token-index"})
        self.assertTrue(payload["validation"]["passed"])
        self.assertEqual(payload["next_actions"][0]["tool"], "query_link")

    def test_memory_inbox_and_explain_render_action_commands(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "memories/prefer-reviewable-memory.md",
            (
                "---\n"
                "type: memory\n"
                "title: \"Prefer reviewable memory\"\n"
                "memory_type: preference\n"
                "scope: user\n"
                "status: active\n"
                "date_captured: \"2026-05-05T00:00:00Z\"\n"
                "source: \"unit test\"\n"
                "review_status: pending\n"
                "---\n\n"
                "# Prefer reviewable memory\n\n"
                "> **TLDR:** User prefers visible memory actions.\n\n"
                "## Memory\n\nUser prefers visible memory actions.\n"
            ),
        )

        inbox_html = serve._render_inbox()
        explain_html = serve._render_explain_memory("prefer-reviewable-memory")

        self.assertIn("Next:</strong> Review", inbox_html)
        self.assertIn("review-memory", inbox_html)
        self.assertIn('data-memory-action="review"', inbox_html)
        self.assertIn('data-memory="prefer-reviewable-memory"', inbox_html)
        self.assertIn("archive-memory", inbox_html)
        self.assertIn('data-memory-action="archive"', inbox_html)
        self.assertIn("forget-memory", inbox_html)
        self.assertIn("<h2>Actions</h2>", explain_html)
        self.assertIn("Next:</strong> Review", explain_html)
        self.assertIn("forget-memory", explain_html)

    def test_memory_action_post_endpoints_update_pages(self):
        wiki = self.make_wiki()
        page = write_page(
            wiki,
            "memories/prefer-web-review.md",
            (
                "---\n"
                "type: memory\n"
                "title: \"Prefer web review\"\n"
                "memory_type: preference\n"
                "scope: user\n"
                "status: active\n"
                "date_captured: \"2026-05-05T00:00:00Z\"\n"
                "source: \"unit test\"\n"
                "review_status: pending\n"
                "---\n\n"
                "# Prefer web review\n\n"
                "> **TLDR:** User prefers safe web memory review.\n\n"
                "## Memory\n\nUser prefers safe web memory review.\n"
            ),
        )

        review_status, review_payload = post_json(
            "/api/review-memory",
            {"memory": "prefer-web-review", "note": "confirmed from web"},
        )
        archive_status, archive_payload = post_json(
            "/api/archive-memory",
            {"memory": "prefer-web-review", "reason": "validated archive"},
        )
        restore_status, restore_payload = post_json(
            "/api/restore-memory",
            {"memory": "Prefer web review"},
        )
        text = page.read_text(encoding="utf-8")
        log_text = (wiki / "log.md").read_text(encoding="utf-8")

        self.assertEqual(review_status, 200)
        self.assertTrue(review_payload["updated"])
        self.assertEqual(review_payload["review_status"], "reviewed")
        self.assertEqual(archive_status, 200)
        self.assertEqual(archive_payload["status"], "archived")
        self.assertEqual(restore_status, 200)
        self.assertEqual(restore_payload["status"], "active")
        self.assertIn("review_status: reviewed", text)
        self.assertIn('review_note: "confirmed from web"', text)
        self.assertIn("status: active", text)
        self.assertIn("review-memory", log_text)
        self.assertIn("archive-memory", log_text)
        self.assertIn("restore-memory", log_text)

    def test_memory_action_post_requires_memory_identifier(self):
        wiki = self.make_wiki()
        status, payload = post_json("/api/review-memory", {})

        self.assertEqual(status, 400)
        self.assertFalse(payload["updated"])
        self.assertEqual(payload["error"], "memory required")

    def test_memory_action_post_requires_local_action_header(self):
        wiki = self.make_wiki()
        status, payload = post_json(
            "/api/review-memory",
            {"memory": "prefer-web-review"},
            local_action=False,
        )

        self.assertEqual(status, 403)
        self.assertFalse(payload["updated"])
        self.assertIn("X-Link-Local-Action", payload["error"])

    def test_memory_audit_page_and_api_report_backlog(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "memories/alpha-review.md",
            (
                "---\n"
                "type: memory\n"
                "title: \"Alpha review\"\n"
                "memory_type: project\n"
                "scope: project\n"
                "project: \"alpha\"\n"
                "status: active\n"
                "date_captured: \"2026-05-05T00:00:00Z\"\n"
                "source: \"unit test\"\n"
                "review_status: pending\n"
                "---\n\n"
                "# Alpha review\n\n"
                "> **TLDR:** Alpha memory needs review.\n"
            ),
        )
        capture_dir = wiki.parent / "raw" / "memory-captures"
        capture_dir.mkdir(parents=True)
        fake_key = "sk-" + ("H" * 24)
        (capture_dir / "alpha.md").write_text(
            "---\n"
            "title: \"Alpha capture\"\n"
            "source_type: conversation\n"
            "date_captured: \"2026-05-05T00:00:00Z\"\n"
            "project: \"alpha\"\n"
            "---\n\n"
            "# Alpha capture\n\n"
            "## Notes\n\n"
            f"Remember that web audit reports capture risks. Test key {fake_key}\n",
            encoding="utf-8",
        )

        audit = serve._memory_audit(project="alpha")
        status, payload = run_handler("GET", "/api/memory-audit?project=alpha")
        html = serve._render_memory_audit(project="alpha")

        self.assertEqual(status, 200)
        self.assertEqual(audit["status"], "needs_attention")
        self.assertEqual(payload["project"], "alpha")
        self.assertEqual(payload["captures"]["warning_count"], 1)
        self.assertIn("capture_secret_warnings", [item["code"] for item in payload["risk_factors"]])
        self.assertIn("Memory Audit", html)
        self.assertIn("memory-inbox", html)
        self.assertIn("capture-inbox", html)
        self.assertNotIn(fake_key, html)

    def test_memory_dashboard_filters_project_memory_and_captures(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "memories/global-style.md",
            (
                "---\n"
                "type: memory\n"
                "title: \"Global style\"\n"
                "memory_type: preference\n"
                "scope: user\n"
                "status: active\n"
                "date_captured: \"2026-05-05T00:00:00Z\"\n"
                "source: \"unit test\"\n"
                "review_status: reviewed\n"
                "---\n\n"
                "# Global style\n\n"
                "> **TLDR:** User prefers concise updates.\n"
            ),
        )
        for project in ("alpha", "beta"):
            write_page(
                wiki,
                f"memories/{project}-imports.md",
                (
                    "---\n"
                    "type: memory\n"
                    f"title: \"{project.title()} imports\"\n"
                    "memory_type: project\n"
                    "scope: project\n"
                    f"project: \"{project}\"\n"
                    "status: active\n"
                    "date_captured: \"2026-05-05T00:00:00Z\"\n"
                    "source: \"unit test\"\n"
                    "review_status: reviewed\n"
                    "---\n\n"
                    f"# {project.title()} imports\n\n"
                    f"> **TLDR:** {project.title()} has project-specific imports.\n"
                ),
            )
        capture_dir = wiki.parent / "raw" / "memory-captures"
        capture_dir.mkdir(parents=True)
        for project in ("alpha", "beta"):
            (capture_dir / f"{project}.md").write_text(
                "---\n"
                f"title: \"{project.title()} capture\"\n"
                "source_type: conversation\n"
                "date_captured: \"2026-05-05T00:00:00Z\"\n"
                f"project: \"{project}\"\n"
                "---\n\n"
                "# Capture\n\n## Notes\n\nMemory capture.\n",
                encoding="utf-8",
            )

        dashboard = serve._memory_dashboard(limit=8, project="alpha")
        status, payload = run_handler("GET", "/api/memory-dashboard?project=alpha")
        html = serve._render_memory_dashboard(project="alpha")

        self.assertEqual(status, 200)
        self.assertEqual(dashboard["project"], "alpha")
        self.assertEqual(payload["project"], "alpha")
        self.assertEqual({record["name"] for record in dashboard["active"]}, {"global-style", "alpha-imports"})
        self.assertEqual([capture["project"] for capture in dashboard["captures"]], ["alpha"])
        self.assertIn("Project:</strong> alpha", html)
        self.assertNotIn("Beta imports", html)

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

    def test_cache_mtime_check_is_throttled_for_hot_navigation(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/a.md",
            "---\ntype: concept\ntitle: A\n---\n# A\n",
        )
        serve.CACHE_MTIME_CHECK_INTERVAL_SECONDS = 60.0

        with patch("serve._wiki_mtime", wraps=serve._wiki_mtime) as mtime:
            first = serve._get_all_pages()
            second = serve._get_all_pages()
            forced = serve._get_all_pages(force_check=True)

        self.assertIs(first, second)
        self.assertIs(first, forced)
        self.assertEqual(mtime.call_count, 2)

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

    def test_graph_summary_is_bounded_for_api_agents(self):
        wiki = self.make_wiki()
        for index in range(8):
            links = " ".join(f"[[node-{target}]]" for target in range(8) if target != index)
            write_page(
                wiki,
                f"concepts/node-{index}.md",
                f"---\ntype: concept\ntitle: Node {index}\n---\n# Node {index}\n\n{links}\n",
            )

        summary = serve._get_graph_summary(limit=4, max_edges=3)

        self.assertEqual(summary["returned_nodes"], 4)
        self.assertEqual(summary["returned_edges"], 3)
        self.assertTrue(summary["truncated"])
        self.assertIn("get_graph", {item["tool"] for item in summary["follow_up"]})

    def test_graph_data_uses_served_cache_forward_links_without_rereading_pages(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/agent-memory.md",
            "---\ntype: concept\ntitle: Agent Memory\n---\n# Agent Memory\n\n[[link]]\n",
        )
        write_page(wiki, "entities/link.md", "---\ntype: entity\ntitle: Link\n---\n# Link\n")
        serve._get_all_pages()

        with patch.object(Path, "read_text", side_effect=AssertionError("serve graph should use cache")):
            graph = serve._get_graph_data()

        self.assertIn({"source": "agent-memory", "target": "link"}, graph["edges"])

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
        self.assertEqual(payload["proposals"][0]["primary_action"]["tool"], "update_memory")
        self.assertIn("update-memory", payload["proposals"][0]["primary_action"]["command"])
        self.assertEqual(payload["proposals"][1]["suggested_action"], "remember")
        self.assertEqual(payload["proposals"][1]["primary_action"]["tool"], "remember_memory")
        self.assertEqual(before_files, after_files)
        self.assertEqual(get_status, 405)
        self.assertIn("use POST", get_payload["error"])
        self.assertEqual(bad_type_status, 415)
        self.assertIn("application/json", bad_type_payload["error"])

    def test_propose_page_renders_read_only_workflow(self):
        wiki = self.make_wiki()

        html = serve._render_propose(project="link", source="raw/first-memory.md")

        self.assertIn('<a href="/propose">propose</a>', html)
        self.assertIn('data-proposal-sources', html)
        self.assertIn('data-proposal-form', html)
        self.assertIn('data-initial-source="raw/first-memory.md"', html)
        self.assertIn('data-proposal-results', html)
        self.assertIn('value="link"', html)
        self.assertIn("without writing anything", html)
        self.assertIn("Save only preferences", html)
        self.assertIn("Review Gate", html)
        self.assertIn("Before saving memory", html)
        self.assertIn("ordinary facts in wiki pages", html)
        self.assertIn("Memory proposal path", html)
        self.assertIn("Approve explicitly", html)
        self.assertIn("This step never writes durable memory", html)
        self.assertIn("Proposal-only: no durable memory has been written yet.", html)
        self.assertIn("Manual review required", html)
        self.assertIn("Conflict found: use the approval prompt", html)
        self.assertIn("Writes durable local memory only after this explicit approval.", html)
        self.assertIn("Approve and save", html)
        self.assertIn("/api/remember-memory", html)
        self.assertIn("/api/update-memory", html)
        self.assertIn("Copy approval prompt", html)
        self.assertIn("navigator.clipboard.writeText", html)
        self.assertIn("var initialSource = form.getAttribute('data-initial-source')", html)

    def test_memory_approval_api_requires_header_and_writes_memory(self):
        wiki = self.make_wiki()
        payload = {
            "memory": "User wants Link memory approvals to stay explicit.",
            "title": "Explicit approvals",
            "memory_type": "preference",
            "scope": "user",
            "source": "web proposal",
        }

        denied_status, denied_payload = post_json("/api/remember-memory", payload, local_action=False)
        create_status, created = post_json("/api/remember-memory", payload)
        duplicate_status, duplicate = post_json("/api/remember-memory", payload)
        update_status, updated = post_json(
            "/api/update-memory",
            {
                "memory": created["name"],
                "text": "User also wants the web proposal flow to preserve review.",
                "source": "web proposal",
            },
        )
        page_text = (wiki / "memories" / f"{created['name']}.md").read_text(encoding="utf-8")

        self.assertEqual(denied_status, 403)
        self.assertIn("X-Link-Local-Action", denied_payload["error"])
        self.assertEqual(create_status, 200)
        self.assertTrue(created["saved"])
        self.assertTrue(created["created"])
        self.assertEqual(created["path"], f"wiki/memories/{created['name']}.md")
        self.assertEqual(duplicate_status, 409)
        self.assertFalse(duplicate["saved"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(update_status, 200)
        self.assertTrue(updated["saved"])
        self.assertTrue(updated["updated"])
        self.assertEqual(updated["review_status"], "pending")
        self.assertIn("User also wants the web proposal flow", page_text)

    def test_proposal_sources_api_lists_safe_raw_files(self):
        wiki = self.make_wiki()
        raw = wiki.parent / "raw"
        raw.mkdir()
        (raw / "first-memory.md").write_text(
            "# First Memory\n\nI prefer local-first agent memory.",
            encoding="utf-8",
        )
        fake_secret = "sk-" + ("a" * 24)
        (raw / "secret-note.md").write_text(
            f"# Secret Note\n\nToken {fake_secret} should not be loaded.",
            encoding="utf-8",
        )
        (raw / "big-note.md").write_text(
            "# Big Note\n\n" + ("large source text\n" * 5000),
            encoding="utf-8",
        )
        (raw / "image.png").write_bytes(b"not listed")
        reset_wiki(wiki)

        list_status, list_payload = run_handler("GET", "/api/proposal-sources")
        load_status, load_payload = run_handler("GET", "/api/proposal-source?path=raw/first-memory.md")
        secret_status, secret_payload = run_handler("GET", "/api/proposal-source?path=raw/secret-note.md")
        big_status, big_payload = run_handler("GET", "/api/proposal-source?path=raw/big-note.md")
        traversal_status, traversal_payload = run_handler("GET", "/api/proposal-source?path=../serve.py")

        self.assertEqual(list_status, 200)
        self.assertEqual(list_payload["count"], 3)
        sources = {item["path"]: item for item in list_payload["sources"]}
        self.assertTrue(sources["raw/first-memory.md"]["loadable"])
        self.assertEqual(sources["raw/first-memory.md"]["action"], "load")
        self.assertEqual(sources["raw/first-memory.md"]["action_label"], "Use in form")
        self.assertFalse(sources["raw/secret-note.md"]["loadable"])
        self.assertEqual(sources["raw/secret-note.md"]["action"], "redact")
        self.assertEqual(sources["raw/secret-note.md"]["action_label"], "Redact first")
        self.assertEqual(sources["raw/secret-note.md"]["secret_warnings"], ["OpenAI API key"])
        self.assertNotIn(fake_secret, sources["raw/secret-note.md"]["snippet"])
        self.assertFalse(sources["raw/big-note.md"]["loadable"])
        self.assertTrue(sources["raw/big-note.md"]["truncated"])
        self.assertEqual(sources["raw/big-note.md"]["action"], "split")
        self.assertEqual(sources["raw/big-note.md"]["action_label"], "Split file")
        self.assertEqual(load_status, 200)
        self.assertIn("local-first agent memory", load_payload["text"])
        self.assertEqual(load_payload["source"], "raw/first-memory.md")
        self.assertEqual(secret_status, 409)
        self.assertIn("redact", secret_payload["error"])
        self.assertNotIn("text", secret_payload)
        self.assertEqual(big_status, 413)
        self.assertIn("too large", big_payload["error"])
        self.assertNotIn("text", big_payload)
        self.assertEqual(traversal_status, 404)
        self.assertFalse(traversal_payload["found"])

    def test_raw_source_api_creates_local_source_for_ingest(self):
        wiki = self.make_wiki()

        status, payload = post_json(
            "/api/raw-source",
            {
                "title": "Project Notes",
                "filename": "Project Notes.md",
                "text": "User wants a web path for adding Link sources.",
            },
        )
        duplicate_status, duplicate_payload = post_json(
            "/api/raw-source",
            {
                "title": "Project Notes",
                "filename": "Project Notes.md",
                "text": "# Project Notes\n\nSecond source.",
            },
        )
        missing_header_status, missing_header = post_json(
            "/api/raw-source",
            {"title": "No Header", "text": "Should not save."},
            local_action=False,
        )

        self.assertEqual(status, 201)
        self.assertTrue(payload["created"])
        self.assertEqual(payload["path"], "raw/project-notes.md")
        self.assertEqual(payload["next_prompt"], "ingest raw/project-notes.md into Link")
        self.assertTrue((wiki.parent / payload["path"]).exists())
        self.assertIn("# Project Notes", (wiki.parent / payload["path"]).read_text(encoding="utf-8"))
        self.assertIn("add-raw-source", (wiki / "log.md").read_text(encoding="utf-8"))
        self.assertEqual(duplicate_status, 201)
        self.assertEqual(duplicate_payload["path"], "raw/project-notes-2.md")
        self.assertEqual(missing_header_status, 403)
        self.assertFalse(missing_header["created"])

    def test_raw_source_api_blocks_secret_and_unsafe_names(self):
        wiki = self.make_wiki()

        secret_status, secret_payload = post_json(
            "/api/raw-source",
            {
                "title": "Secret",
                "filename": "secret.md",
                "text": "Do not save sk-" + ("a" * 25),
            },
        )
        unsafe_status, unsafe_payload = post_json(
            "/api/raw-source",
            {
                "title": "Unsafe",
                "filename": "../unsafe.md",
                "text": "Safe text.",
            },
        )
        get_status, get_payload = run_handler("GET", "/api/raw-source")

        self.assertEqual(secret_status, 422)
        self.assertFalse(secret_payload["created"])
        self.assertEqual(secret_payload["secret_warnings"], ["OpenAI API key"])
        self.assertFalse((wiki.parent / "raw" / "secret.md").exists())
        self.assertEqual(unsafe_status, 400)
        self.assertIn("filename", unsafe_payload["error"])
        self.assertEqual(get_status, 405)
        self.assertIn("POST", get_payload["error"])

    def test_ingest_page_and_api_show_pending_raw(self):
        wiki = self.make_wiki()
        raw = wiki.parent / "raw"
        raw.mkdir()
        (raw / "new-source.md").write_text("# New source\n", encoding="utf-8")
        reset_wiki(wiki)

        api_status, payload = run_handler("GET", "/api/ingest-status")
        html = serve._render_ingest()

        self.assertEqual(api_status, 200)
        self.assertEqual(payload["pending_count"], 1)
        self.assertEqual(payload["guidance"]["state"], "pending_raw")
        self.assertEqual(payload["safety"]["status"], "clear")
        self.assertEqual(payload["plan"]["batch"][0]["suggested_source_page"], "wiki/sources/new-source.md")
        self.assertIn("Add Raw Source", html)
        self.assertIn('data-raw-source-form', html)
        self.assertIn('data-raw-source-status', html)
        self.assertIn("Save to raw/", html)
        self.assertIn("blocks secret-looking values", html)
        self.assertIn("Next step", html)
        self.assertIn("Raw safety: clear", html)
        self.assertIn("No secret-looking values detected in raw sources.", html)
        self.assertIn("Copy this into your agent chat", html)
        self.assertIn('data-copy-text="ingest raw/new-source.md into Link"', html)
        self.assertIn("Copy prompt", html)
        self.assertIn("Copy command", html)
        self.assertIn('data-copy-text="link validate"', html)
        self.assertIn("ingest raw/new-source.md into Link", html)
        self.assertIn("open memory proposals first", html)
        self.assertIn("Ingest path", html)
        self.assertIn("Optional memory", html)
        self.assertIn("propose memories from raw/new-source.md", html)
        self.assertIn("Post-ingest checks", html)
        self.assertIn("run before reporting done", html)
        self.assertIn("Ingest pending raw sources", html)
        self.assertIn("wiki/sources/new-source.md", html)
        self.assertIn('/propose?source=raw/new-source.md', html)
        self.assertIn("Pending Raw Files", html)

    def test_ingest_page_shows_completion_for_represented_raw(self):
        wiki = self.make_wiki()
        raw = wiki.parent / "raw"
        raw.mkdir()
        (raw / "represented-source.md").write_text("# Represented source\n", encoding="utf-8")
        (wiki / "sources").mkdir(parents=True, exist_ok=True)
        (wiki / "sources" / "represented-source.md").write_text(
            "---\ntype: source\ntitle: Represented Source\n---\n\n"
            "# Represented Source\n\n"
            "## Raw Source\n\n`raw/represented-source.md`\n",
            encoding="utf-8",
        )
        reset_wiki(wiki)

        api_status, payload = run_handler("GET", "/api/ingest-status")
        html = serve._render_ingest()

        self.assertEqual(api_status, 200)
        self.assertEqual(payload["guidance"]["state"], "ready")
        self.assertEqual(payload["completion"]["items"][0]["source_pages"][0]["title"], "Represented Source")
        self.assertIn("Ingest completion", html)
        self.assertIn("All 1 raw source(s) are represented", html)
        self.assertIn("raw/represented-source.md", html)
        self.assertIn('/page/represented-source', html)
        self.assertIn("Represented Source", html)
        self.assertIn('/propose?source=raw/represented-source.md', html)
        self.assertIn('data-copy-text="propose memories from raw/represented-source.md"', html)
        self.assertIn('data-copy-text="query Link for represented source"', html)
        self.assertIn("brief me from Link before we continue", html)

    def test_ingest_page_blocks_secret_looking_raw(self):
        wiki = self.make_wiki()
        raw = wiki.parent / "raw"
        raw.mkdir()
        (raw / "a-safe-note.md").write_text(
            "# Safe note\n\nThis should stay available for memory proposals.\n",
            encoding="utf-8",
        )
        (raw / "secret-note.md").write_text(
            "# Secret note\n\nDo not ingest sk-" + ("a" * 25) + "\n",
            encoding="utf-8",
        )
        reset_wiki(wiki)

        api_status, payload = run_handler("GET", "/api/ingest-status")
        html = serve._render_ingest()

        self.assertEqual(api_status, 200)
        self.assertEqual(payload["guidance"]["state"], "blocked_secrets")
        self.assertIsNone(payload["guidance"]["agent_prompt"])
        self.assertEqual(payload["safety"]["status"], "blocked")
        self.assertEqual(payload["safety"]["blocked_raw"], ["raw/secret-note.md"])
        self.assertIn("Raw safety: blocked", html)
        self.assertIn('data-copy-text="edit raw/secret-note.md"', html)
        self.assertIn("Copy next step", html)
        self.assertIn("Redact raw sources before ingest", html)
        self.assertIn("redact secret-looking values in raw/secret-note.md before ingest", html)
        self.assertIn("secret warning: OpenAI API key", html)
        self.assertIn("redact before ingest", html)
        self.assertIn('/propose?source=raw/a-safe-note.md', html)
        self.assertNotIn('/propose?source=raw/secret-note.md', html)

    def test_rebuild_backlinks_requires_json_post(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/a.md",
            "---\ntype: concept\ntitle: A\n---\n# A\n\n[[b]]\n",
        )
        write_page(
            wiki,
            "concepts/b.md",
            "---\ntype: concept\ntitle: B\n---\n# B\n",
        )
        backlinks_path = wiki / "_backlinks.json"
        backlinks_path.write_text(json.dumps({"backlinks": {}, "forward": {}}), encoding="utf-8")

        get_status, get_payload = run_handler("GET", "/api/rebuild-backlinks")
        bad_post_status, bad_post_payload = run_handler("POST", "/api/rebuild-backlinks")
        missing_header_status, missing_header_payload = run_handler(
            "POST",
            "/api/rebuild-backlinks",
            body=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": "2"},
        )
        post_status, post_payload = run_handler(
            "POST",
            "/api/rebuild-backlinks",
            body=b"{}",
            headers={
                "Content-Type": "application/json",
                "Content-Length": "2",
                "X-Link-Local-Action": "true",
            },
        )
        rebuilt = json.loads(backlinks_path.read_text(encoding="utf-8"))

        self.assertEqual(get_status, 405)
        self.assertIn("use POST", get_payload["error"])
        self.assertEqual(bad_post_status, 403)
        self.assertFalse(bad_post_payload["rebuilt"])
        self.assertIn("X-Link-Local-Action", bad_post_payload["error"])
        self.assertEqual(missing_header_status, 403)
        self.assertFalse(missing_header_payload["rebuilt"])
        self.assertIn("X-Link-Local-Action", missing_header_payload["error"])
        self.assertEqual(post_status, 200)
        self.assertTrue(post_payload["rebuilt"])
        self.assertEqual(rebuilt["backlinks"], {"b": ["a"]})
        self.assertEqual(rebuilt["forward"], {"a": ["b"]})

    def test_rebuild_backlinks_rejects_bad_json_after_local_header(self):
        wiki = self.make_wiki()

        bad_post_status, bad_post_payload = run_handler(
            "POST",
            "/api/rebuild-backlinks",
            headers={"X-Link-Local-Action": "true"},
        )

        self.assertEqual(bad_post_status, 415)
        self.assertFalse(bad_post_payload["rebuilt"])

    def test_rebuild_index_requires_json_post(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/a.md",
            "---\ntype: concept\ntitle: A\n---\n# A\n\n> **TLDR:** A page.\n",
        )
        index_path = wiki / "index.md"
        index_path.write_text("# Broken Index\n", encoding="utf-8")

        get_status, get_payload = run_handler("GET", "/api/rebuild-index")
        bad_post_status, bad_post_payload = run_handler("POST", "/api/rebuild-index")
        missing_header_status, missing_header_payload = run_handler(
            "POST",
            "/api/rebuild-index",
            body=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": "2"},
        )
        post_status, post_payload = run_handler(
            "POST",
            "/api/rebuild-index",
            body=b"{}",
            headers={
                "Content-Type": "application/json",
                "Content-Length": "2",
                "X-Link-Local-Action": "true",
            },
        )
        index_text = index_path.read_text(encoding="utf-8")

        self.assertEqual(get_status, 405)
        self.assertIn("use POST", get_payload["error"])
        self.assertEqual(bad_post_status, 403)
        self.assertFalse(bad_post_payload["rebuilt"])
        self.assertIn("X-Link-Local-Action", bad_post_payload["error"])
        self.assertEqual(missing_header_status, 403)
        self.assertFalse(missing_header_payload["rebuilt"])
        self.assertIn("X-Link-Local-Action", missing_header_payload["error"])
        self.assertEqual(post_status, 200)
        self.assertTrue(post_payload["rebuilt"])
        self.assertIn("[[a]]", index_text)
        self.assertEqual(post_payload["category_counts"]["concepts"], 1)

    def test_rebuild_index_rejects_bad_json_after_local_header(self):
        wiki = self.make_wiki()

        bad_post_status, bad_post_payload = run_handler(
            "POST",
            "/api/rebuild-index",
            headers={"X-Link-Local-Action": "true"},
        )

        self.assertEqual(bad_post_status, 415)
        self.assertFalse(bad_post_payload["rebuilt"])

    def test_validate_api_reports_wiki_gate_status(self):
        wiki = self.make_wiki()
        for dirname in ("sources", "concepts", "entities", "memories", "comparisons", "explorations"):
            (wiki / dirname).mkdir(exist_ok=True)
        write_page(
            wiki,
            "sources/example-source.md",
            "---\ntype: source\ntitle: Example Source\n---\n\n"
            "# Example Source\n\n"
            "> **TLDR:** A valid source page.\n\n"
            "## Summary\n\nUseful source.\n\n"
            "## Raw Source\n\n`raw/example.md`\n",
        )
        write_page(
            wiki,
            "concepts/example-concept.md",
            "---\ntype: concept\ntitle: Example Concept\n---\n\n"
            "# Example Concept\n\n"
            "> **TLDR:** A valid concept page.\n\n"
            "## Overview\n\nConcept cites [[example-source]].\n\n"
            "## Sources\n\n- [[example-source]]\n",
        )
        (wiki / "_backlinks.json").write_text(json.dumps(serve._build_backlinks()), encoding="utf-8")

        status, payload = run_handler("GET", "/api/validate")

        self.assertEqual(status, 200)
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["error_count"], 0)

    def test_validate_api_uses_422_for_failed_gate(self):
        wiki = self.make_wiki()
        for dirname in ("sources", "concepts", "entities", "memories", "comparisons", "explorations"):
            (wiki / dirname).mkdir(exist_ok=True)
        write_page(
            wiki,
            "concepts/bad-page.md",
            "---\ntype: source\n---\n\n"
            "# Bad Page\n\n"
            "Mentions [[missing-page]].\n",
        )
        (wiki / "_backlinks.json").write_text(json.dumps(serve._build_backlinks()), encoding="utf-8")

        status, payload = run_handler("GET", "/api/validate?strict=true")
        codes = {finding["code"] for finding in payload["findings"]}

        self.assertEqual(status, 422)
        self.assertFalse(payload["passed"])
        self.assertIn("type_directory_mismatch", codes)
        self.assertIn("dead_wikilink", codes)

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
        self.assertLess(html.index('id="graph-search"'), html.index("var searchInput ="))
        self.assertLess(html.index('id="graph-category"'), html.index("var categoryFilter ="))
        self.assertLess(html.index('id="graph-depth"'), html.index("var depthFilter ="))
        self.assertLess(html.index('id="graph-inspector"'), html.index("var inspector ="))
        self.assertLess(html.index('id="graph-focus"'), html.index("var inspectorFocus ="))
        self.assertIn('id="graph-status"', html)
        self.assertIn("Focus neighborhood", html)
        self.assertIn('id="graph-open"', html)
        self.assertIn('tabindex="0"', html)
        self.assertIn('role="img"', html)
        self.assertIn('<option value="concepts">concepts</option>', html)
        self.assertIn("function visibleNodes()", html)
        self.assertIn("function visibleEdges()", html)
        self.assertIn("function syncDepthControl()", html)
        self.assertIn("depthValue = '1'", html)
        self.assertIn("depthFilter.disabled = !selectedNode;", html)
        self.assertIn("Select a node before filtering by neighborhood.", html)
        self.assertIn("var LARGE_GRAPH_LIMIT = 350;", html)
        self.assertIn("var LARGE_LABEL_LIMIT = 160;", html)
        self.assertIn("var FAST_RENDER_NODE_LIMIT = 450;", html)
        self.assertIn("var FAST_RENDER_EDGE_LIMIT = 1200;", html)
        self.assertIn("function syncLabelsButton()", html)
        self.assertIn("function graphNeedsFastRender(currentNodes, currentEdges)", html)
        self.assertIn("function graphTooLargeForMotion()", html)
        self.assertIn("searchInput.addEventListener('input'", html)

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

    def test_graph_motion_is_capped_for_large_visible_sets(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/a.md",
            "---\ntype: concept\ntitle: A\n---\n# A\n",
        )

        html = serve._render_graph()

        self.assertIn("var simNodes = visibleNodes();", html)
        self.assertIn("if (simNodes.length > LARGE_GRAPH_LIMIT) return;", html)
        self.assertIn("if (graphTooLargeForMotion()) parts.push('motion capped');", html)
        self.assertIn("motionButton.textContent = graphTooLargeForMotion() ? 'Motion capped'", html)
        self.assertIn("var renderQueued = false;", html)
        self.assertIn("function shouldRunContinuously()", html)
        self.assertIn("function drawSoon()", html)
        self.assertIn("var animateFlow = !motionPaused && !graphTooLargeForMotion();", html)
        self.assertIn("if (activeEdge && animateFlow)", html)
        self.assertIn("if (shouldRunContinuously()) startLoop();", html)

    def test_graph_uses_fast_canvas_rendering_for_large_visible_sets(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/a.md",
            "---\ntype: concept\ntitle: A\n---\n# A\n",
        )

        html = serve._render_graph()

        self.assertIn("if (graphNeedsFastRender(currentNodes, currentEdges)) parts.push('fast render');", html)
        self.assertIn("function strokeEdgeBatch(edgeList, strokeStyle, lineWidth)", html)
        self.assertIn("if (fastRender) {", html)
        self.assertIn("strokeEdgeBatch(currentEdges, 'rgba(88,166,255,0.07)', 0.45);", html)
        self.assertIn("Radial glow stays off in large overview mode except for focused nodes.", html)
        self.assertIn("ctx.fillStyle = fastRender ? color + '28' : color + '40';", html)

    def test_graph_caps_default_overview_for_huge_visible_sets(self):
        wiki = self.make_wiki()
        for index in range(700):
            write_page(
                wiki,
                f"concepts/topic-{index}.md",
                "---\ntype: concept\ntitle: Topic\n---\n"
                f"# Topic {index}\n\n[[topic-{(index + 1) % 700}]]\n",
            )
        reset_wiki(wiki)

        html = serve._render_graph()

        self.assertIn("var OVERVIEW_NODE_LIMIT = 650;", html)
        self.assertIn("function capEligibleNodes(eligible)", html)
        self.assertIn(".slice(0, OVERVIEW_NODE_LIMIT)", html)
        self.assertIn("if (searchMatches(n)) keep[n.id] = true;", html)
        self.assertIn("parts.push('overview capped');", html)

    def test_graph_labels_are_sparse_for_large_visible_sets(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/a.md",
            "---\ntype: concept\ntitle: A\n---\n# A\n",
        )

        html = serve._render_graph()

        self.assertIn("function graphTooLargeForDefaultLabels()", html)
        self.assertIn("if (graphTooLargeForDefaultLabels() && !showAllLabels) parts.push('labels sparse');", html)
        self.assertIn("labelsButton.textContent = showAllLabels ? 'Hide labels'", html)
        self.assertIn("var largeLabelSet = currentNodes.length > LARGE_LABEL_LIMIT;", html)
        self.assertIn("var defaultSparseLabel = !largeLabelSet", html)

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
