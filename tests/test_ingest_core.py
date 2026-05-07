import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.ingest import collect_ingest_status  # noqa: E402
from link_core.wiki import build_backlinks  # noqa: E402


def write_page(wiki: Path, rel: str, text: str) -> None:
    path = wiki / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class IngestCoreTests(unittest.TestCase):
    def test_collect_ingest_status_reports_missing_structure(self):
        root = Path(tempfile.mkdtemp(prefix="link-ingest-core-"))

        payload = collect_ingest_status(root)

        self.assertFalse(payload["has_raw_dir"])
        self.assertFalse(payload["has_wiki_dir"])
        self.assertEqual(payload["guidance"]["state"], "missing_structure")

    def test_collect_ingest_status_reports_pending_raw(self):
        root = Path(tempfile.mkdtemp(prefix="link-ingest-core-"))
        raw = root / "raw"
        wiki = root / "wiki"
        raw.mkdir()
        (raw / "new-note.md").write_text("# New note\n", encoding="utf-8")
        write_page(wiki, "index.md", "# Index\n")
        write_page(wiki, "log.md", "# Log\n")
        (wiki / "sources").mkdir(parents=True, exist_ok=True)
        (wiki / "_backlinks.json").write_text(json.dumps(build_backlinks(wiki)), encoding="utf-8")

        payload = collect_ingest_status(root)

        self.assertEqual(payload["pending_count"], 1)
        self.assertEqual(payload["pending_raw"][0]["raw"], "raw/new-note.md")
        self.assertEqual(payload["guidance"]["state"], "pending_raw")
        self.assertEqual(payload["safety"]["status"], "clear")
        self.assertEqual(payload["guidance"]["agent_prompt"], "ingest raw/new-note.md into Link")
        self.assertEqual(payload["plan"]["title"], "Ingest pending raw sources")
        self.assertEqual(payload["plan"]["batch"][0]["suggested_source_page"], "wiki/sources/new-note.md")
        self.assertEqual(payload["plan"]["memory_prompt"], "propose memories from raw/new-note.md")
        self.assertIn("link rebuild-index", payload["plan"]["post_checks"])

    def test_collect_ingest_status_blocks_secret_looking_raw(self):
        root = Path(tempfile.mkdtemp(prefix="link-ingest-core-"))
        raw = root / "raw"
        wiki = root / "wiki"
        raw.mkdir()
        (raw / "secret-note.md").write_text(
            "# Secret note\n\nDo not ingest sk-" + ("a" * 25) + "\n",
            encoding="utf-8",
        )
        write_page(wiki, "index.md", "# Index\n")
        write_page(wiki, "log.md", "# Log\n")
        (wiki / "sources").mkdir(parents=True, exist_ok=True)
        (wiki / "_backlinks.json").write_text(json.dumps(build_backlinks(wiki)), encoding="utf-8")

        payload = collect_ingest_status(root)

        self.assertEqual(payload["pending_count"], 1)
        self.assertEqual(payload["raw_secret_warning_count"], 1)
        self.assertEqual(payload["safety"]["status"], "blocked")
        self.assertEqual(payload["safety"]["blocked_count"], 1)
        self.assertEqual(payload["safety"]["labels"], ["OpenAI API key"])
        self.assertEqual(payload["safety"]["blocked_raw"], ["raw/secret-note.md"])
        self.assertEqual(payload["pending_raw"][0]["secret_warnings"], ["OpenAI API key"])
        self.assertEqual(payload["guidance"]["state"], "blocked_secrets")
        self.assertIsNone(payload["guidance"]["agent_prompt"])
        self.assertEqual(payload["plan"]["title"], "Redact raw sources before ingest")
        self.assertEqual(payload["plan"]["batch"][0]["secret_warnings"], ["OpenAI API key"])
        self.assertIn("Do not ask an agent to ingest", payload["guidance"]["notes"][0])

    def test_collect_ingest_status_reports_represented_raw(self):
        root = Path(tempfile.mkdtemp(prefix="link-ingest-core-"))
        raw = root / "raw"
        wiki = root / "wiki"
        raw.mkdir()
        (raw / "source.md").write_text("# Source\n", encoding="utf-8")
        write_page(wiki, "index.md", "# Index\n")
        write_page(wiki, "log.md", "# Log\n")
        write_page(
            wiki,
            "sources/source.md",
            "---\ntype: source\ntitle: Source\n---\n\n"
            "# Source\n\n"
            "## Raw Source\n\n`raw/source.md`\n",
        )
        (wiki / "_backlinks.json").write_text(json.dumps(build_backlinks(wiki)), encoding="utf-8")

        payload = collect_ingest_status(root)

        self.assertEqual(payload["pending_count"], 0)
        self.assertEqual(payload["represented_count"], 1)
        self.assertEqual(payload["represented_raw"][0]["source_pages"], ["source"])
        self.assertEqual(payload["represented_raw"][0]["source_page_paths"], ["wiki/sources/source.md"])
        self.assertEqual(payload["represented_raw"][0]["source_page_titles"], ["Source"])
        self.assertEqual(payload["safety"]["status"], "clear")
        self.assertEqual(payload["guidance"]["state"], "ready")
        self.assertEqual(payload["plan"]["title"], "Ready for new sources")
        self.assertEqual(payload["completion"]["represented_count"], 1)
        self.assertEqual(payload["completion"]["pending_count"], 0)
        self.assertEqual(payload["completion"]["items"][0]["raw"], "raw/source.md")
        self.assertEqual(payload["completion"]["items"][0]["source_pages"][0]["path"], "wiki/sources/source.md")
        self.assertEqual(payload["completion"]["items"][0]["memory_prompt"], "propose memories from raw/source.md")
        self.assertEqual(payload["completion"]["next_prompt"], "brief me from Link before we continue")

    def test_collect_ingest_status_warns_on_represented_secret_raw(self):
        root = Path(tempfile.mkdtemp(prefix="link-ingest-core-"))
        raw = root / "raw"
        wiki = root / "wiki"
        raw.mkdir()
        (raw / "source.md").write_text(
            "# Source\n\nHistorical token sk-" + ("a" * 25) + "\n",
            encoding="utf-8",
        )
        write_page(wiki, "index.md", "# Index\n")
        write_page(wiki, "log.md", "# Log\n")
        write_page(
            wiki,
            "sources/source.md",
            "---\ntype: source\ntitle: Source\n---\n\n"
            "# Source\n\n"
            "## Raw Source\n\n`raw/source.md`\n",
        )
        (wiki / "_backlinks.json").write_text(json.dumps(build_backlinks(wiki)), encoding="utf-8")

        payload = collect_ingest_status(root)

        self.assertEqual(payload["pending_count"], 0)
        self.assertEqual(payload["represented_count"], 1)
        self.assertEqual(payload["safety"]["status"], "warning")
        self.assertEqual(payload["safety"]["blocked_count"], 0)
        self.assertEqual(payload["safety"]["labels"], ["OpenAI API key"])
        self.assertEqual(payload["guidance"]["state"], "ready")


if __name__ == "__main__":
    unittest.main()
