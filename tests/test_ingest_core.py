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
        self.assertEqual(payload["guidance"]["agent_prompt"], "ingest raw/new-note.md into Link")

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
        self.assertEqual(payload["guidance"]["state"], "ready")


if __name__ == "__main__":
    unittest.main()
