import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.memory import memory_records  # noqa: E402
from link_core.query import query_link  # noqa: E402
from link_core.wiki import build_backlinks, build_wiki_cache, graph_data  # noqa: E402


def write_page(wiki: Path, rel: str, text: str) -> None:
    path = wiki / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class LargeWikiSmokeTests(unittest.TestCase):
    def test_smart_query_and_graph_handle_hundreds_of_pages(self):
        root = Path(tempfile.mkdtemp(prefix="link-large-wiki-"))
        wiki = root / "wiki"
        wiki.mkdir()
        write_page(wiki, "index.md", "# Index\n")
        write_page(wiki, "log.md", "# Log\n")

        for index in range(12):
            write_page(
                wiki,
                f"sources/source-{index}.md",
                "---\n"
                "type: source\n"
                f"title: Source {index}\n"
                "---\n\n"
                f"# Source {index}\n\n"
                f"> **TLDR:** Source {index} covers local agent memory topic {index}.\n\n"
                "## Summary\n\n"
                "Synthetic source for large-wiki smoke coverage.\n\n"
                f"## Raw Source\n\n`raw/source-{index}.md`\n",
            )

        page_count = 260
        for index in range(page_count):
            next_index = (index + 1) % page_count
            source_index = index % 12
            write_page(
                wiki,
                f"concepts/topic-{index}.md",
                "---\n"
                "type: concept\n"
                f"title: Topic {index} Agent Memory\n"
                "tags: [agent-memory, large-wiki]\n"
                "---\n\n"
                f"# Topic {index} Agent Memory\n\n"
                f"> **TLDR:** Topic {index} describes local agent memory behavior.\n\n"
                "## Overview\n\n"
                f"Topic {index} links to [[topic-{next_index}]] and [[source-{source_index}]]. "
                "The repeated phrase keeps search realistic without requiring a full scan.\n\n"
                "## Sources\n\n"
                f"- [[source-{source_index}]]\n",
            )

        for index in range(16):
            topic = 42 if index == 0 else index
            write_page(
                wiki,
                f"memories/prefer-topic-{topic}.md",
                "---\n"
                "type: memory\n"
                f"title: Prefer topic {topic}\n"
                "memory_type: preference\n"
                "scope: project\n"
                "project: large-wiki\n"
                "status: active\n"
                "date_captured: \"2026-05-06T00:00:00Z\"\n"
                "source: large-wiki-smoke\n"
                "review_status: reviewed\n"
                "---\n\n"
                f"# Prefer topic {topic}\n\n"
                f"> **TLDR:** User prefers topic {topic} local agent memory notes.\n\n"
                f"## Memory\n\nUser prefers topic {topic} local agent memory notes.\n",
            )

        (wiki / "_backlinks.json").write_text(json.dumps(build_backlinks(wiki)), encoding="utf-8")
        cache = build_wiki_cache(wiki)

        packet = query_link(
            wiki,
            "agent memory",
            cache,
            memory_records(wiki),
            budget="small",
            project="large-wiki",
        )
        graph = graph_data(cache)

        self.assertEqual(len(cache["pages"]), page_count + 30)
        self.assertTrue(packet["found"])
        self.assertLessEqual(len(packet["context_packet"]), 6)
        self.assertTrue(packet["budget_report"]["wiki_search"]["has_more"])
        self.assertLessEqual(packet["memory"]["count"], 3)
        self.assertEqual(packet["follow_up"][0]["tool"], "query_link")
        self.assertEqual(len(graph["nodes"]), page_count + 30)
        self.assertGreaterEqual(len(graph["edges"]), page_count)


if __name__ == "__main__":
    unittest.main()
