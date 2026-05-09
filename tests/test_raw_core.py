import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.raw import RawSourceError, create_raw_source, raw_source_filename  # noqa: E402


class RawCoreTests(unittest.TestCase):
    def test_create_raw_source_writes_safe_unique_file(self):
        root = Path(tempfile.mkdtemp(prefix="link-raw-core-"))

        first = create_raw_source(
            root,
            title="Release Notes",
            filename="Release Notes.md",
            text="User wants Link onboarding to stay simple.",
        )
        second = create_raw_source(
            root,
            title="Release Notes",
            filename="Release Notes.md",
            text="# Existing Heading\n\nSecond note.",
        )

        self.assertEqual(first["path"], "raw/release-notes.md")
        self.assertEqual(second["path"], "raw/release-notes-2.md")
        self.assertEqual(first["next_prompt"], "ingest raw/release-notes.md into Link")
        self.assertIn("# Release Notes", (root / first["path"]).read_text(encoding="utf-8"))
        self.assertTrue((root / second["path"]).read_text(encoding="utf-8").startswith("# Existing Heading"))

    def test_raw_source_filename_rejects_folders_and_bad_suffixes(self):
        self.assertEqual(raw_source_filename("My Notes.txt"), "my-notes.txt")
        with self.assertRaises(RawSourceError):
            raw_source_filename("../secret.md")
        with self.assertRaises(RawSourceError):
            raw_source_filename("image.png")

    def test_create_raw_source_blocks_empty_large_and_secret_values(self):
        root = Path(tempfile.mkdtemp(prefix="link-raw-core-"))

        with self.assertRaises(RawSourceError) as empty:
            create_raw_source(root, text="")
        self.assertEqual(empty.exception.status, 400)

        with self.assertRaises(RawSourceError) as large:
            create_raw_source(root, text="x" * 20, max_bytes=10)
        self.assertEqual(large.exception.status, 413)

        with self.assertRaises(RawSourceError) as secret:
            create_raw_source(root, text="Do not save sk-" + ("a" * 25))
        self.assertEqual(secret.exception.status, 422)
        self.assertEqual(secret.exception.labels, ["OpenAI API key"])
        self.assertFalse((root / "raw").exists())


if __name__ == "__main__":
    unittest.main()
