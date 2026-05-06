import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.status import link_status  # noqa: E402
from link_core.schema import write_schema  # noqa: E402
from link_core.wiki import build_backlinks, build_wiki_cache  # noqa: E402


def write_page(wiki: Path, rel: str, text: str) -> None:
    path = wiki / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class StatusCoreTests(unittest.TestCase):
    def make_wiki(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="link-status-core-"))
        wiki = root / "wiki"
        for dirname in ("sources", "concepts", "entities", "memories", "comparisons", "explorations"):
            (wiki / dirname).mkdir(parents=True, exist_ok=True)
        write_page(wiki, "index.md", "# Index\n")
        write_page(wiki, "log.md", "# Log\n")
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
        (wiki / "_backlinks.json").write_text(json.dumps(build_backlinks(wiki, body_only=False)), encoding="utf-8")
        write_schema(wiki)
        return wiki

    def test_link_status_reports_ready_wiki(self):
        wiki = self.make_wiki()

        payload = link_status(wiki, version="9.9.9", cache=build_wiki_cache(wiki), include_validation=True)

        self.assertTrue(payload["ready"])
        self.assertEqual(payload["version"], "9.9.9")
        self.assertEqual(payload["page_count"], 3)
        self.assertEqual(payload["memory_count"], 1)
        self.assertEqual(payload["active_memory_count"], 1)
        self.assertEqual(payload["schema"]["status"], "current")
        self.assertTrue(payload["validation"]["passed"])
        self.assertEqual(payload["next_actions"][0]["tool"], "query_link")

    def test_link_status_reports_missing_structure(self):
        wiki = Path(tempfile.mkdtemp(prefix="link-status-core-")) / "wiki"

        payload = link_status(wiki, include_validation=True)

        self.assertFalse(payload["ready"])
        self.assertIn("wiki", payload["missing"])
        self.assertEqual(payload["schema"]["status"], "missing")
        self.assertEqual(payload["page_count"], 0)
        self.assertEqual(payload["next_actions"][0]["tool"], "doctor")


if __name__ == "__main__":
    unittest.main()
