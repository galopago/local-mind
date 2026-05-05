import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.memory import propose_memories_from_text  # noqa: E402


class MemoryCoreTests(unittest.TestCase):
    def test_proposals_are_duplicate_aware_and_write_free(self):
        records = [
            {
                "name": "prefer-release-branches",
                "path": "wiki/memories/prefer-release-branches.md",
                "title": "Prefer release branches",
                "memory_type": "preference",
                "scope": "project",
                "status": "active",
                "tldr": "User prefers release branches for Link work.",
                "snippet": "User prefers release branches for Link work.",
                "body": "User prefers release branches for Link work.",
            }
        ]

        payload = propose_memories_from_text(
            "\n".join([
                "- I prefer release branches for Link work.",
                "- We decided to keep Memory Mode local and source-backed.",
                "- Maybe we could add cloud sync later.",
            ]),
            records,
            source="unit test",
        )

        self.assertTrue(payload["proposed"])
        self.assertFalse(payload["writes_memory"])
        self.assertEqual(payload["count"], 2)
        self.assertGreaterEqual(payload["skipped_count"], 1)
        self.assertEqual(payload["proposals"][0]["suggested_action"], "update-memory")
        duplicate = payload["proposals"][0]["duplicate_candidates"][0]
        self.assertEqual(duplicate["name"], "prefer-release-branches")
        self.assertNotIn("body", duplicate)
        self.assertEqual(payload["proposals"][1]["memory_type"], "decision")


if __name__ == "__main__":
    unittest.main()
