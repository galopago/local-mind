import importlib.util
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import serve


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("link_cli", ROOT / "link.py")
link_cli = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(link_cli)


EXPECTED_RAW_FILES = {
    "agent-memory-session.md",
    "local-release-notes.md",
    "transformer-reading-notes.md",
}

EXPECTED_WIKI_PAGES = {
    "agent-memory",
    "agent-memory-session",
    "index",
    "knowledge-graph",
    "link",
    "local-first-software",
    "local-release-notes",
    "log",
    "prefer-local-personal-memory",
    "retrieval-augmented-generation",
    "transformer-reading-notes",
    "transformers",
    "why-link-helps-agents",
}

EXPECTED_KEY_EDGES = {
    ("agent-memory", "agent-memory-session"),
    ("agent-memory", "link"),
    ("agent-memory", "retrieval-augmented-generation"),
    ("agent-memory", "local-first-software"),
    ("knowledge-graph", "agent-memory"),
    ("link", "knowledge-graph"),
    ("link", "retrieval-augmented-generation"),
    ("prefer-local-personal-memory", "agent-memory"),
    ("prefer-local-personal-memory", "link"),
    ("retrieval-augmented-generation", "transformers"),
    ("why-link-helps-agents", "agent-memory"),
}


def create_demo_quiet(target: Path) -> None:
    with redirect_stdout(StringIO()):
        link_cli.create_demo(target, force=False)


def reset_serve_wiki(wiki_dir: Path) -> None:
    serve.WIKI_DIR = wiki_dir
    serve.RAW_DIR = wiki_dir.parent / "raw"
    serve._pages_cache = None
    serve._pages_cache_mtime = 0.0
    serve._page_index = {}
    serve._fulltext_index = {}
    serve._snippet_index = {}
    serve._token_index = {}
    serve._page_map = {}
    serve._meta_token_index = {}


class DemoSnapshotTests(unittest.TestCase):
    def make_demo(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="link-demo-snapshot-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        return target

    def test_demo_file_snapshot_and_health(self):
        target = self.make_demo()

        raw_files = {path.name for path in (target / "raw").iterdir() if path.is_file() and not path.name.startswith(".")}
        wiki_pages = {path.stem for path in (target / "wiki").rglob("*.md") if not path.name.startswith(".")}

        self.assertEqual(raw_files, EXPECTED_RAW_FILES)
        self.assertEqual(wiki_pages, EXPECTED_WIKI_PAGES)
        self.assertTrue((target / "logo.svg").exists())

        status = link_cli._collect_ingest_status(target)
        self.assertEqual(status["raw_count"], 3)
        self.assertEqual(status["source_page_count"], 3)
        self.assertEqual(status["pending_count"], 0)
        self.assertEqual(status["backlinks_status"], "current")

        with redirect_stdout(StringIO()):
            self.assertEqual(link_cli.doctor(target), 0)

    def test_demo_graph_snapshot(self):
        target = self.make_demo()
        reset_serve_wiki(target / "wiki")

        graph = serve._get_graph_data()
        node_ids = {node["id"] for node in graph["nodes"]}
        edges = {(edge["source"], edge["target"]) for edge in graph["edges"]}

        self.assertEqual(node_ids, EXPECTED_WIKI_PAGES)
        self.assertEqual(len(graph["nodes"]), 13)
        self.assertEqual(len(graph["edges"]), 58)
        self.assertEqual(len(edges), len(graph["edges"]))
        self.assertTrue(EXPECTED_KEY_EDGES.issubset(edges))

    def test_demo_home_shows_memories(self):
        target = self.make_demo()
        reset_serve_wiki(target / "wiki")

        html = serve._render_home()

        self.assertIn('<span class="label">memories</span>', html)
        self.assertIn("Prefer local personal memory", html)

    def test_demo_context_snapshot(self):
        target = self.make_demo()
        reset_serve_wiki(target / "wiki")

        ctx = serve._get_context("agent memory")
        page_names = [page["name"] for page in ctx["pages"]]
        relationships = {page["name"]: page["relationship"] for page in ctx["pages"]}

        self.assertTrue(ctx["found"])
        self.assertEqual(ctx["primary"], "agent-memory")
        self.assertEqual(ctx["inbound_count"], 10)
        self.assertEqual(ctx["forward_count"], 5)
        self.assertEqual(page_names[0], "agent-memory")
        self.assertIn("link", page_names)
        self.assertIn("agent-memory-session", page_names)
        self.assertIn("retrieval-augmented-generation", page_names)
        self.assertEqual(relationships["agent-memory"], "primary")
        self.assertEqual(relationships["link"], "inbound")


if __name__ == "__main__":
    unittest.main()
