import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.benchmark import benchmark_health  # noqa: E402


class BenchmarkCoreTests(unittest.TestCase):
    def test_benchmark_health_passes_fast_sqlite_search(self):
        payload = {
            "pages": 1200,
            "search_backend": "sqlite-fts",
            "timings": {
                "cache": 0.2,
                "search": 0.01,
                "query": 0.03,
                "graph_summary": 0.01,
                "page_list": 0.01,
                "graph": 0.04,
            },
        }

        health = benchmark_health(payload)

        self.assertEqual(health["status"], "pass")
        self.assertEqual(health["label"], "interactive")
        self.assertEqual(health["summary"], "Ready for interactive local agent memory.")
        self.assertEqual(health["warnings"], [])
        self.assertEqual(health["recommendations"], [])

    def test_benchmark_health_warns_on_slow_paths(self):
        payload = {
            "pages": 20,
            "search_backend": "sqlite-fts",
            "timings": {
                "cache": 0.2,
                "search": 1.5,
                "query": 0.03,
                "graph_summary": 0.01,
                "page_list": 0.01,
                "graph": 0.04,
            },
        }

        health = benchmark_health(payload)

        self.assertEqual(health["status"], "warn")
        self.assertEqual(health["label"], "review")
        self.assertIn("search took 1.5000s", health["warnings"][0])
        self.assertIn("Review recommended", health["summary"])
        self.assertIn("Run link doctor --fix", health["recommendations"][1])

    def test_benchmark_health_warns_on_large_token_fallback(self):
        payload = {
            "pages": 1000,
            "search_backend": "token-index",
            "timings": {
                "cache": 0.2,
                "search": 0.01,
                "query": 0.03,
                "graph_summary": 0.01,
                "page_list": 0.01,
                "graph": 0.04,
            },
        }

        health = benchmark_health(payload)

        self.assertEqual(health["status"], "warn")
        self.assertIn("SQLite FTS", health["warnings"][0])
        self.assertIn("SQLite FTS", health["recommendations"][0])


if __name__ == "__main__":
    unittest.main()
