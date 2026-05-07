import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.wiki import (  # noqa: E402
    build_index_markdown,
    build_backlinks,
    build_wiki_cache,
    context_for_topic,
    graph_data,
    graph_summary,
    list_pages,
    load_backlinks_index,
    rebuild_index,
    search_pages,
    wiki_mtime,
)


def write_page(wiki: Path, rel: str, text: str) -> Path:
    path = wiki / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class WikiCoreTests(unittest.TestCase):
    def make_wiki(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="link-wiki-core-"))
        wiki = root / "wiki"
        wiki.mkdir()
        write_page(wiki, "index.md", "# Index\n")
        write_page(wiki, "log.md", "# Log\n")
        return wiki

    def test_cache_search_context_and_graph(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/agent-memory.md",
            (
                "---\n"
                "type: concept\n"
                "title: Agent Memory\n"
                "aliases: [durable context]\n"
                "tags: [agents, memory]\n"
                "maturity: growing\n"
                "---\n"
                "# Agent Memory\n\n"
                "> **TLDR:** Durable memory for agents.\n\n"
                "Links to [[link]] and [[retrieval]].\n"
            ),
        )
        write_page(
            wiki,
            "entities/link.md",
            "---\ntype: entity\ntitle: Link\n---\n# Link\n\nLink references [[agent-memory]].\n",
        )
        write_page(
            wiki,
            "concepts/retrieval.md",
            "---\ntype: concept\ntitle: Retrieval\n---\n# Retrieval\n",
        )
        (wiki / "_backlinks.json").write_text(
            json.dumps({"backlinks": {"agent-memory": ["link"]}, "forward": {"link": ["agent-memory"]}}),
            encoding="utf-8",
        )

        cache = build_wiki_cache(wiki)
        search = search_pages("durable", cache)
        context = context_for_topic(wiki, "agent memory", cache)
        graph = graph_data(cache)

        self.assertEqual(search[0]["name"], "agent-memory")
        self.assertIn("date_published", search[0])
        self.assertIn(cache["search_backend"], {"sqlite-fts", "token-index"})
        if cache["search_backend"] == "sqlite-fts":
            self.assertIsNotNone(cache["fts_index"])
        self.assertIn("durable", cache["meta_words_index"]["agent-memory"])
        self.assertIn("references", cache["text_words_index"]["link"])
        self.assertEqual(context["primary"], "agent-memory")
        self.assertEqual(context["inbound_count"], 1)
        self.assertEqual(context["forward_count"], 2)
        self.assertEqual([page["name"] for page in context["pages"]], ["agent-memory", "link", "retrieval"])
        self.assertEqual(cache["forward_links_index"]["agent-memory"], ["link", "retrieval"])
        self.assertIn({"source": "agent-memory", "target": "link"}, graph["edges"])
        self.assertIn({"source": "agent-memory", "target": "retrieval"}, graph["edges"])

    def test_graph_data_uses_cached_forward_links_without_rereading_pages(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/agent-memory.md",
            "---\ntype: concept\ntitle: Agent Memory\n---\n# Agent Memory\n\n[[link]]\n",
        )
        write_page(wiki, "entities/link.md", "---\ntype: entity\ntitle: Link\n---\n# Link\n")
        cache = build_wiki_cache(wiki)

        with patch.object(Path, "read_text", side_effect=AssertionError("graph_data should use cache")):
            graph = graph_data(cache)

        self.assertIn({"source": "agent-memory", "target": "link"}, graph["edges"])

    def test_list_pages_is_bounded_and_paginated_by_default(self):
        wiki = self.make_wiki()
        for index in range(5):
            write_page(
                wiki,
                f"concepts/page-{index}.md",
                f"---\ntype: concept\ntitle: Page {index}\nmaturity: growing\n---\n# Page {index}\n",
            )
        cache = build_wiki_cache(wiki)

        first = list_pages(cache, category="concepts", limit=2)
        second = list_pages(cache, category="concepts", limit=2, offset=2)
        full = list_pages(cache, category="concepts", limit=2, include_all=True)

        self.assertEqual(first["count"], 5)
        self.assertEqual(first["returned_count"], 2)
        self.assertTrue(first["truncated"])
        self.assertEqual(first["follow_up"][0]["arguments"]["offset"], 2)
        self.assertEqual(second["returned_count"], 2)
        self.assertEqual(full["returned_count"], 5)
        self.assertFalse(full["truncated"])

    def test_graph_summary_caps_overview_for_agent_context(self):
        wiki = self.make_wiki()
        for index in range(6):
            links = " ".join(f"[[page-{target}]]" for target in range(6) if target != index)
            write_page(
                wiki,
                f"concepts/page-{index}.md",
                f"---\ntype: concept\ntitle: Page {index}\n---\n# Page {index}\n\n{links}\n",
            )
        cache = build_wiki_cache(wiki)

        summary = graph_summary(cache, limit=3, max_edges=2)

        self.assertEqual(summary["mode"], "overview")
        self.assertEqual(summary["node_count"], 8)
        self.assertEqual(summary["returned_nodes"], 3)
        self.assertEqual(summary["returned_edges"], 2)
        self.assertTrue(summary["truncated"])
        self.assertTrue(summary["edge_truncated"])
        self.assertEqual(summary["follow_up"][-1]["tool"], "get_graph")

    def test_graph_summary_topic_returns_bounded_neighborhood(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/agent-memory.md",
            "---\ntype: concept\ntitle: Agent Memory\n---\n# Agent Memory\n\n[[link]] [[retrieval]]\n",
        )
        write_page(wiki, "entities/link.md", "---\ntype: entity\ntitle: Link\n---\n# Link\n\n[[agent-memory]]\n")
        write_page(wiki, "concepts/retrieval.md", "---\ntype: concept\ntitle: Retrieval\n---\n# Retrieval\n")
        write_page(wiki, "concepts/isolated.md", "---\ntype: concept\ntitle: Isolated\n---\n# Isolated\n")
        cache = build_wiki_cache(wiki)

        summary = graph_summary(cache, topic="agent memory", limit=10, depth=1)
        node_ids = {node["id"] for node in summary["nodes"]}

        self.assertEqual(summary["mode"], "topic-neighborhood")
        self.assertTrue(summary["found"])
        self.assertIn("agent-memory", node_ids)
        self.assertIn("link", node_ids)
        self.assertIn("retrieval", node_ids)
        self.assertNotIn("isolated", node_ids)
        self.assertEqual(summary["nodes"][0]["why_selected"], "matched topic")
        self.assertEqual(summary["follow_up"][0]["tool"], "get_context")

    def test_multi_token_search_uses_token_relevance_without_exact_phrase(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/local-memory.md",
            "---\ntype: concept\ntitle: Local Recall\n---\n\n"
            "# Local Recall\n\n"
            "Agent workflows keep durable project notes as private memory.\n",
        )
        write_page(
            wiki,
            "concepts/agent-only.md",
            "---\ntype: concept\ntitle: Agent Runtime\n---\n\n"
            "# Agent Runtime\n\n"
            "Agent execution details without user preference storage.\n",
        )
        write_page(
            wiki,
            "concepts/memory-only.md",
            "---\ntype: concept\ntitle: Memory Archive\n---\n\n"
            "# Memory Archive\n\n"
            "Memory storage details for archival notes.\n",
        )

        results = search_pages("agent memory", build_wiki_cache(wiki), limit=5)

        self.assertEqual(results[0]["name"], "local-memory")
        self.assertNotIn("agent-only", {result["name"] for result in results})
        self.assertNotIn("memory-only", {result["name"] for result in results})

    def test_search_falls_back_without_optional_fts_index(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/agent-memory.md",
            "---\ntype: concept\ntitle: Agent Memory\n---\n\n"
            "# Agent Memory\n\n"
            "Source-backed local memory for agents.\n",
        )
        cache = build_wiki_cache(wiki)
        cache["fts_index"] = None
        cache["search_backend"] = "token-index"

        results = search_pages("local memory", cache, limit=5)

        self.assertEqual(results[0]["name"], "agent-memory")

    def test_backlinks_loader_and_builder_shapes(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/a.md",
            "---\ntype: concept\ntitle: A\nrelated: [[frontmatter-only]]\n---\n# A\n\n[[b]] [[b]]\n",
        )
        write_page(wiki, "concepts/b.md", "---\ntype: concept\ntitle: B\n---\n# B\n")
        backlinks_path = wiki / "_backlinks.json"
        backlinks_path.write_text(json.dumps({"a": ["b"]}), encoding="utf-8")

        loaded, error = load_backlinks_index(backlinks_path)
        body_only = build_backlinks(wiki)
        full_text = build_backlinks(wiki, body_only=False)

        self.assertIsNone(error)
        self.assertEqual(loaded, {"backlinks": {"a": ["b"]}, "forward": {}})
        self.assertEqual(body_only["backlinks"], {"b": ["a"]})
        self.assertEqual(body_only["forward"], {"a": ["b"]})
        self.assertIn("frontmatter-only", full_text["backlinks"])

    def test_wiki_mtime_sees_existing_page_edits(self):
        wiki = self.make_wiki()
        page = write_page(wiki, "concepts/a.md", "# A\n")
        before = wiki_mtime(wiki)
        future = time.time() + 2
        page.write_text("# A2\n", encoding="utf-8")
        os.utime(page, (future, future))

        self.assertGreater(wiki_mtime(wiki), before)

    def test_empty_context_can_report_tool_error(self):
        wiki = self.make_wiki()
        cache = build_wiki_cache(wiki)

        result = context_for_topic(wiki, " ", cache, empty_error="topic required")

        self.assertFalse(result["found"])
        self.assertEqual(result["error"], "topic required")

    def test_rebuild_index_generates_category_catalog(self):
        wiki = self.make_wiki()
        write_page(
            wiki,
            "concepts/agent-memory.md",
            "---\ntype: concept\ntitle: Agent Memory\n---\n\n"
            "# Agent Memory\n\n> **TLDR:** Durable memory for agents.\n",
        )
        write_page(
            wiki,
            "sources/session.md",
            "---\ntype: source\ntitle: Session Notes\n---\n\n"
            "# Session Notes\n\n> **TLDR:** Source notes for Link.\n",
        )
        write_page(
            wiki,
            "memories/prefer-local.md",
            "---\ntype: memory\ntitle: Prefer Local\n---\n\n"
            "# Prefer Local\n\n> **TLDR:** User prefers local memory.\n",
        )

        markdown = build_index_markdown(wiki, generated_at="2026-05-06T00:00:00Z")
        result = rebuild_index(wiki, generated_at="2026-05-06T00:00:00Z")
        index_text = (wiki / "index.md").read_text(encoding="utf-8")

        self.assertIn("3 pages | 1 sources | 1 memories", markdown)
        self.assertIn("### concepts", index_text)
        self.assertIn("- [[agent-memory]] - Durable memory for agents. (concept)", index_text)
        self.assertIn("- [[session]] - Source notes for Link. (source)", index_text)
        self.assertIn("- [[prefer-local]] - User prefers local memory. (memory)", index_text)
        self.assertEqual(result["page_count"], 3)
        self.assertEqual(result["category_counts"]["concepts"], 1)
        self.assertEqual(result["next_actions"][0]["tool"], "rebuild_backlinks")

    def test_index_build_closes_owned_cache(self):
        wiki = self.make_wiki()

        class FakeIndex:
            closed = False

            def close(self):
                self.closed = True

        fake = FakeIndex()
        cache = {
            "pages": [
                {
                    "name": "agent-memory",
                    "title": "Agent Memory",
                    "category": "concepts",
                    "type": "concept",
                    "tldr": "Durable memory.",
                }
            ],
            "snippet_index": {},
            "fts_index": fake,
        }

        with patch("link_core.wiki.build_wiki_cache", return_value=cache):
            markdown = build_index_markdown(wiki)

        self.assertIn("[[agent-memory]]", markdown)
        self.assertTrue(fake.closed)

    def test_rebuild_index_closes_owned_cache(self):
        wiki = self.make_wiki()

        class FakeIndex:
            closed = False

            def close(self):
                self.closed = True

        fake = FakeIndex()
        cache = {
            "pages": [
                {
                    "name": "agent-memory",
                    "title": "Agent Memory",
                    "category": "concepts",
                    "type": "concept",
                    "tldr": "Durable memory.",
                }
            ],
            "snippet_index": {},
            "fts_index": fake,
        }

        with patch("link_core.wiki.build_wiki_cache", return_value=cache):
            result = rebuild_index(wiki)

        self.assertEqual(result["page_count"], 1)
        self.assertTrue(fake.closed)


if __name__ == "__main__":
    unittest.main()
