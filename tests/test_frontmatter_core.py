import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.frontmatter import parse_frontmatter, update_frontmatter_fields  # noqa: E402


class FrontmatterCoreTests(unittest.TestCase):
    def test_parse_frontmatter_preserves_colons_and_lists(self):
        meta, body = parse_frontmatter(
            "---\n"
            "title: \"My: Project\"\n"
            "tags: [memory, \"release:notes\", local-first]\n"
            "---\n\n"
            "# Body\n"
        )

        self.assertEqual(meta["title"], "My: Project")
        self.assertEqual(meta["tags"], ["memory", "release:notes", "local-first"])
        self.assertEqual(body, "\n# Body\n")

    def test_update_frontmatter_formats_lists_and_removes_fields(self):
        updated = update_frontmatter_fields(
            "---\n"
            "title: Old\n"
            "tags: [old]\n"
            "reviewed_at: \"2026-05-05T00:00:00Z\"\n"
            "---\n\n"
            "Body\n",
            {
                "tags": ["memory", "release:notes"],
                "review_status": "pending",
            },
            remove={"reviewed_at"},
        )

        self.assertIn("tags: [memory, \"release:notes\"]", updated)
        self.assertIn("review_status: pending", updated)
        self.assertNotIn("reviewed_at:", updated)
        self.assertTrue(updated.endswith("\nBody\n"))


if __name__ == "__main__":
    unittest.main()
