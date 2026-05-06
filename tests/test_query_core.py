import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.memory import memory_records  # noqa: E402
from link_core.query import query_link  # noqa: E402
from link_core.wiki import build_backlinks, build_wiki_cache  # noqa: E402


def write_page(wiki: Path, rel: str, text: str) -> None:
    path = wiki / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class QueryCoreTests(unittest.TestCase):
    def test_query_link_returns_budgeted_memory_and_graph_context(self):
        root = Path(tempfile.mkdtemp(prefix="link-query-core-"))
        wiki = root / "wiki"
        wiki.mkdir()
        write_page(wiki, "index.md", "# Index\n")
        write_page(wiki, "log.md", "# Log\n")
        write_page(
            wiki,
            "concepts/agent-memory.md",
            "---\n"
            "type: concept\n"
            "title: Agent memory\n"
            "tags: [agents, memory]\n"
            "---\n\n"
            "# Agent memory\n\n"
            "> **TLDR:** Agents use durable memory to preserve context.\n\n"
            "## Overview\n\n"
            "Agent memory links to [[retrieval-augmented-generation]] for source-backed recall.\n",
        )
        write_page(
            wiki,
            "concepts/retrieval-augmented-generation.md",
            "---\n"
            "type: concept\n"
            "title: Retrieval-augmented generation\n"
            "---\n\n"
            "# Retrieval-augmented generation\n\n"
            "> **TLDR:** Retrieval adds external context before generation.\n",
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
            "> **TLDR:** User prefers local agent memory over cloud memory.\n\n"
            "## Memory\n\nUser prefers local agent memory over cloud memory.\n",
        )
        (wiki / "_backlinks.json").write_text(json.dumps(build_backlinks(wiki)), encoding="utf-8")

        payload = query_link(
            wiki,
            "agent memory",
            build_wiki_cache(wiki),
            memory_records(wiki),
            budget="small",
        )

        self.assertTrue(payload["found"])
        self.assertEqual(payload["budget"], "small")
        self.assertEqual(payload["strategy"]["mode"], "memory+wiki")
        self.assertEqual(payload["memory"]["items"][0]["name"], "prefer-local-memory")
        self.assertEqual(payload["memory"]["items"][0]["recall"]["state"], "ready")
        self.assertEqual(payload["memory"]["review"]["items"], [])
        self.assertEqual(payload["wiki"]["primary"], "agent-memory")
        self.assertLessEqual(len(payload["context_packet"]), 4)
        self.assertIn("why_selected", payload["context_packet"][0])
        self.assertIn("do not read the whole wiki", payload["agent_guidance"][0])
        self.assertIn("budget_report", payload)
        self.assertEqual(payload["follow_up"][0]["tool"], "get_context")

    def test_query_link_reports_budget_overflow_and_followups(self):
        root = Path(tempfile.mkdtemp(prefix="link-query-core-"))
        wiki = root / "wiki"
        wiki.mkdir()
        write_page(wiki, "index.md", "# Index\n")
        write_page(wiki, "log.md", "# Log\n")
        for index in range(6):
            write_page(
                wiki,
                f"concepts/agent-memory-{index}.md",
                "---\n"
                "type: concept\n"
                f"title: Agent memory {index}\n"
                "tags: [agents, memory]\n"
                "---\n\n"
                f"# Agent memory {index}\n\n"
                "> **TLDR:** Agents use durable memory.\n\n"
                "## Overview\n\n"
                "Agent memory supports source-backed local recall.\n",
            )
        for index in range(4):
            write_page(
                wiki,
                f"memories/prefer-local-memory-{index}.md",
                "---\n"
                "type: memory\n"
                f"title: Prefer local memory {index}\n"
                "memory_type: preference\n"
                "scope: user\n"
                "status: active\n"
                "date_captured: \"2026-05-05T00:00:00Z\"\n"
                "source: unit-test\n"
                "review_status: reviewed\n"
                "tags: [memory]\n"
                "---\n\n"
                f"# Prefer local memory {index}\n\n"
                "> **TLDR:** User prefers local agent memory.\n\n"
                "## Memory\n\nUser prefers local agent memory.\n",
            )
        (wiki / "_backlinks.json").write_text(json.dumps(build_backlinks(wiki)), encoding="utf-8")

        payload = query_link(
            wiki,
            "agent memory",
            build_wiki_cache(wiki),
            memory_records(wiki),
            budget="small",
        )

        self.assertTrue(payload["budget_report"]["memories"]["has_more"])
        self.assertTrue(payload["budget_report"]["wiki_search"]["has_more"])
        self.assertLessEqual(payload["budget_report"]["memories"]["selected"], 3)
        self.assertEqual(payload["follow_up"][0]["tool"], "query_link")
        self.assertEqual(payload["follow_up"][0]["arguments"]["budget"], "medium")
        self.assertIn("budget-limited", payload["agent_guidance"][1])


if __name__ == "__main__":
    unittest.main()
