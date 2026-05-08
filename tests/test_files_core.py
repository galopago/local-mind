import json
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.files import append_text, atomic_write_json, atomic_write_text  # noqa: E402


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

    def test_atomic_write_recovers_stale_lock_file(self):
        root = Path(tempfile.mkdtemp(prefix="link-files-core-"))
        path = root / "wiki/index.md"
        path.parent.mkdir(parents=True)
        lock = path.parent / ".index.md.lock"
        lock.write_text("old-pid", encoding="utf-8")
        os.utime(lock, (0, 0))

        atomic_write_text(path, "new\n")

        self.assertEqual(path.read_text(encoding="utf-8"), "new\n")
        self.assertFalse(lock.exists())

    def test_append_text_initializes_and_serializes_audit_log(self):
        root = Path(tempfile.mkdtemp(prefix="link-files-core-"))
        path = root / "wiki/log.md"

        def append(index: int) -> None:
            append_text(path, f"entry-{index}\n", initial_text="# Log\n\n")

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(append, range(25)))

        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count("# Log"), 1)
        for index in range(25):
            self.assertIn(f"entry-{index}\n", text)
        self.assertEqual(list(path.parent.glob(".*.lock")), [])


if __name__ == "__main__":
    unittest.main()
