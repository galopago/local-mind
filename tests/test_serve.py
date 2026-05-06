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
    serve._normalized_fulltext_index = {}
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
        self.assertIn('<a href="/brief">brief</a>', html)
        self.assertIn('<a href="/audit">audit</a>', html)
        self.assertIn('<a href="/captures">captures</a>', html)

    def test_css_has_mobile_overflow_guards(self):
        self.assertIn("* { box-sizing: border-box; margin: 0; padding: 0; }", serve.CSS)
        self.assertIn("html { overflow-x: hidden; background: var(--bg); }", serve.CSS)
        self.assertIn("overflow-x: hidden; overflow-wrap: anywhere", serve.CSS)
        self.assertIn("a, p, li, code { overflow-wrap: anywhere; }", serve.CSS)
        self.assertIn("header nav { display: flex; gap: 16px;", serve.CSS)
        self.assertIn("flex-wrap: wrap; min-width: 0", serve.CSS)
        self.assertIn(".memory-grid { grid-template-columns: minmax(0, 1fr); }", serve.CSS)
        self.assertIn(".memory-actions code, .memory-next code { word-break: break-word; }", serve.CSS)

    def test_css_has_explicit_black_dark_theme(self):
        self.assertIn(':root[data-theme="dark"]', serve.CSS)
        self.assertIn("--bg: #000000;", serve.CSS)
        self.assertIn("body { font-family: Georgia", serve.CSS)
        self.assertIn("background: var(--bg); color: var(--text);", serve.CSS)
        self.assertNotIn("background: #1a1a1a", serve.CSS)

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
        post_status, post_payload = run_handler(
            "POST",
            "/api/rebuild-backlinks",
            body=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": "2"},
        )
        rebuilt = json.loads(backlinks_path.read_text(encoding="utf-8"))

        self.assertEqual(get_status, 405)
        self.assertIn("use POST", get_payload["error"])
        self.assertEqual(bad_post_status, 415)
        self.assertFalse(bad_post_payload["rebuilt"])
        self.assertEqual(post_status, 200)
        self.assertTrue(post_payload["rebuilt"])
        self.assertEqual(rebuilt["backlinks"], {"b": ["a"]})
        self.assertEqual(rebuilt["forward"], {"a": ["b"]})

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
