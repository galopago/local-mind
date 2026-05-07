import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.files import atomic_write_json, atomic_write_text  # noqa: E402


class FilesCoreTests(unittest.TestCase):
    def test_atomic_write_text_replaces_existing_file(self):
        root = Path(tempfile.mkdtemp(prefix="link-files-core-"))
        path = root / "wiki/index.md"
        path.parent.mkdir(parents=True)
        path.write_text("old\n", encoding="utf-8")

        atomic_write_text(path, "new\n")

        self.assertEqual(path.read_text(encoding="utf-8"), "new\n")
        self.assertEqual(list(path.parent.glob(".*.tmp")), [])

    def test_atomic_write_json_adds_trailing_newline(self):
        root = Path(tempfile.mkdtemp(prefix="link-files-core-"))
        path = root / "wiki/_backlinks.json"

        atomic_write_json(path, {"backlinks": {}, "forward": {}})

        self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"backlinks": {}, "forward": {}})

    def test_atomic_write_preserves_existing_file_on_replace_failure(self):
        root = Path(tempfile.mkdtemp(prefix="link-files-core-"))
        path = root / "wiki/index.md"
        path.parent.mkdir(parents=True)
        path.write_text("old\n", encoding="utf-8")

        with patch.object(os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                atomic_write_text(path, "new\n")

        self.assertEqual(path.read_text(encoding="utf-8"), "old\n")
        self.assertEqual(list(path.parent.glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
