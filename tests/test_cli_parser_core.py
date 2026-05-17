import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.cli_parser import build_cli_parser  # noqa: E402


class CliParserCoreTests(unittest.TestCase):
    def test_demo_uses_custom_default_directory(self):
        parser = build_cli_parser(default_demo_dir="custom-demo")

        args = parser.parse_args(["demo"])

        self.assertEqual(args.command, "demo")
        self.assertEqual(args.target, "custom-demo")
        self.assertFalse(args.force)

    def test_query_alias_and_budget_options(self):
        parser = build_cli_parser()

        args = parser.parse_args(["query-link", "agent memory", "/tmp/link", "--budget", "small", "--json"])

        self.assertEqual(args.command, "query-link")
        self.assertEqual(args.query, "agent memory")
        self.assertEqual(args.target, "/tmp/link")
        self.assertEqual(args.budget, "small")
        self.assertTrue(args.json)

    def test_memory_choices_are_enforced(self):
        parser = build_cli_parser()

        args = parser.parse_args(["remember", "prefers concise answers", "--type", "preference", "--scope", "user"])

        self.assertEqual(args.memory_type, "preference")
        self.assertEqual(args.scope, "user")
        with self.assertRaises(SystemExit):
            parser.parse_args(["remember", "bad", "--type", "unsupported"])


if __name__ == "__main__":
    unittest.main()
