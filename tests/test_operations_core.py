import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.operations import begin_operation, operation_journal, pending_operations  # noqa: E402


class OperationsCoreTests(unittest.TestCase):
    def test_operation_journal_clears_marker_on_success(self):
        wiki = Path(tempfile.mkdtemp(prefix="link-operations-core-")) / "wiki"
        wiki.mkdir(parents=True)

        with operation_journal(wiki, "remember", "Saved memory", timestamp="2026-05-17T00:00:00Z"):
            pass

        self.assertEqual(pending_operations(wiki), [])

    def test_operation_journal_leaves_failed_marker(self):
        wiki = Path(tempfile.mkdtemp(prefix="link-operations-core-")) / "wiki"
        wiki.mkdir(parents=True)

        with self.assertRaisesRegex(RuntimeError, "boom"):
            with operation_journal(wiki, "remember", "Saved memory", timestamp="2026-05-17T00:00:00Z"):
                raise RuntimeError("boom")

        operations = pending_operations(wiki)
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0]["operation"], "remember")
        self.assertEqual(operations[0]["status"], "failed")
        self.assertTrue(operations[0]["stale"])
        self.assertIn("boom", operations[0]["error"])

    def test_pending_operations_marks_old_marker_stale(self):
        wiki = Path(tempfile.mkdtemp(prefix="link-operations-core-")) / "wiki"
        wiki.mkdir(parents=True)
        begin_operation(wiki, "update-memory", "Update memory", timestamp="2026-05-17T00:00:00Z")

        operations = pending_operations(wiki, now=2_000_000_000, stale_after_seconds=60)

        self.assertEqual(len(operations), 1)
        self.assertTrue(operations[0]["stale"])
        self.assertEqual(operations[0]["operation"], "update-memory")


if __name__ == "__main__":
    unittest.main()
