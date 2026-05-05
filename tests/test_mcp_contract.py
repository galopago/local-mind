import importlib.util
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LINK_SPEC = importlib.util.spec_from_file_location("link_cli_for_mcp_tests", ROOT / "link.py")
link_cli = importlib.util.module_from_spec(LINK_SPEC)
assert LINK_SPEC.loader is not None
LINK_SPEC.loader.exec_module(link_cli)


class FakeFastMCP:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def tool(self):
        def decorator(fn):
            return fn

        return decorator

    def run(self, transport: str = "stdio") -> None:
        return None


def install_mcp_stub() -> dict[str, types.ModuleType | None]:
    previous = {
        "mcp": sys.modules.get("mcp"),
        "mcp.server": sys.modules.get("mcp.server"),
        "mcp.server.fastmcp": sys.modules.get("mcp.server.fastmcp"),
    }
    mcp_mod = types.ModuleType("mcp")
    server_mod = types.ModuleType("mcp.server")
    fastmcp_mod = types.ModuleType("mcp.server.fastmcp")
    fastmcp_mod.FastMCP = FakeFastMCP
    server_mod.fastmcp = fastmcp_mod
    mcp_mod.server = server_mod
    sys.modules["mcp"] = mcp_mod
    sys.modules["mcp.server"] = server_mod
    sys.modules["mcp.server.fastmcp"] = fastmcp_mod
    return previous


def restore_mcp_modules(previous: dict[str, types.ModuleType | None]) -> None:
    for name, module in previous.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def create_demo_quiet(target: Path) -> None:
    with redirect_stdout(StringIO()):
        link_cli.create_demo(target, force=False)


def import_mcp_server(wiki_dir: Path):
    previous_modules = install_mcp_stub()
    previous_argv = sys.argv[:]
    module_name = f"link_mcp_server_contract_{id(wiki_dir)}"
    try:
        sys.argv = ["link_mcp.server", "--wiki", str(wiki_dir)]
        spec = importlib.util.spec_from_file_location(module_name, ROOT / "mcp_package/link_mcp/server.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module, previous_modules, previous_argv, module_name
    except BaseException:
        restore_mcp_modules(previous_modules)
        sys.argv = previous_argv
        raise


class McpContractTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-mcp-contract-"))
        self.target = tmp / "demo"
        create_demo_quiet(self.target)
        self.server, self.previous_modules, self.previous_argv, self.module_name = import_mcp_server(self.target / "wiki")

    def tearDown(self):
        sys.modules.pop(self.module_name, None)
        restore_mcp_modules(self.previous_modules)
        sys.argv = self.previous_argv

    def test_search_wiki_contract(self):
        payload = json.loads(self.server.search_wiki("agent memory", limit=5))

        self.assertEqual(payload["query"], "agent memory")
        self.assertGreaterEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["name"], "agent-memory")
        self.assertIn("score", payload["results"][0])
        self.assertIn("snippet", payload["results"][0])

    def test_search_wiki_handles_invalid_limits(self):
        bad_limit = json.loads(self.server.search_wiki("agent memory", limit="bad"))
        negative_limit = json.loads(self.server.search_wiki("agent memory", limit=-10))

        self.assertGreaterEqual(bad_limit["count"], 1)
        self.assertEqual(negative_limit["count"], 1)

    def test_search_wiki_rejects_empty_query(self):
        payload = json.loads(self.server.search_wiki("   ", limit=5))

        self.assertEqual(payload["error"], "query required")
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["results"], [])

    def test_get_context_contract(self):
        payload = json.loads(self.server.get_context("agent memory"))
        page_names = [page["name"] for page in payload["pages"]]

        self.assertTrue(payload["found"])
        self.assertEqual(payload["primary"], "agent-memory")
        self.assertEqual(payload["inbound_count"], 10)
        self.assertEqual(payload["forward_count"], 5)
        self.assertEqual(page_names[0], "agent-memory")
        self.assertIn("link", page_names)
        self.assertIn("agent-memory-session", page_names)
        self.assertEqual(payload["pages"][0]["relationship"], "primary")

    def test_get_context_rejects_empty_topic(self):
        payload = json.loads(self.server.get_context(""))

        self.assertFalse(payload["found"])
        self.assertEqual(payload["error"], "topic required")
        self.assertEqual(payload["pages"], [])

    def test_get_pages_filters_contract(self):
        concepts = json.loads(self.server.get_pages(category="concepts"))
        mature = json.loads(self.server.get_pages(maturity="growing"))
        sources = json.loads(self.server.get_pages(page_type="source"))

        self.assertEqual(concepts["count"], 5)
        self.assertEqual({page["category"] for page in concepts["pages"]}, {"concepts"})
        self.assertIn("agent-memory", {page["name"] for page in mature["pages"]})
        self.assertEqual(sources["count"], 3)
        self.assertEqual({page["type"] for page in sources["pages"]}, {"source"})

    def test_get_backlinks_contract(self):
        payload = json.loads(self.server.get_backlinks("agent-memory"))

        self.assertEqual(payload["page"], "agent-memory")
        self.assertEqual(len(payload["inbound"]), 10)
        self.assertEqual(len(payload["forward"]), 5)
        self.assertIn("link", payload["inbound"])
        self.assertIn("agent-memory-session", payload["forward"])

    def test_get_backlinks_rejects_empty_page_name(self):
        payload = json.loads(self.server.get_backlinks(""))

        self.assertEqual(payload["error"], "page_name required")
        self.assertEqual(payload["inbound"], [])
        self.assertEqual(payload["forward"], [])

    def test_get_graph_contract(self):
        payload = json.loads(self.server.get_graph())
        nodes = {node["id"] for node in payload["nodes"]}
        edges = {(edge["source"], edge["target"]) for edge in payload["edges"]}

        self.assertEqual(len(payload["nodes"]), 13)
        self.assertEqual(len(payload["edges"]), 58)
        self.assertEqual(len(edges), len(payload["edges"]))
        self.assertIn("agent-memory", nodes)
        self.assertIn("prefer-local-personal-memory", nodes)
        self.assertIn(("agent-memory", "link"), edges)
        self.assertIn(("prefer-local-personal-memory", "agent-memory"), edges)
        self.assertIn(("retrieval-augmented-generation", "transformers"), edges)

    def test_recall_memory_contract(self):
        payload = json.loads(self.server.recall_memory("local personal memory"))

        self.assertGreaterEqual(payload["count"], 1)
        self.assertEqual(payload["memories"][0]["name"], "prefer-local-personal-memory")
        self.assertEqual(payload["memories"][0]["memory_type"], "preference")

    def test_memory_profile_contract(self):
        payload = json.loads(self.server.memory_profile())

        self.assertEqual(payload["memory_count"], 1)
        self.assertEqual(payload["active_count"], 1)
        self.assertEqual(payload["review_count"], 1)
        self.assertEqual(payload["by_type"]["preference"], 1)
        self.assertEqual(payload["by_scope"]["user"], 1)
        self.assertEqual(payload["recent"][0]["name"], "prefer-local-personal-memory")
        self.assertEqual(payload["preferences"][0]["memory_type"], "preference")

    def test_memory_inbox_and_review_memory_contract(self):
        inbox = json.loads(self.server.memory_inbox())
        reviewed = json.loads(self.server.review_memory(
            "prefer-local-personal-memory",
            note="confirmed by MCP test",
        ))
        clear = json.loads(self.server.memory_inbox())

        self.assertEqual(inbox["review_count"], 1)
        self.assertEqual(inbox["items"][0]["name"], "prefer-local-personal-memory")
        self.assertEqual(inbox["items"][0]["issues"][0]["code"], "pending_review")
        self.assertTrue(reviewed["updated"])
        self.assertEqual(reviewed["review_status"], "reviewed")
        self.assertEqual(reviewed["remaining_issue_count"], 0)
        self.assertEqual(clear["review_count"], 0)

    def test_explain_memory_contract(self):
        payload = json.loads(self.server.explain_memory("prefer-local-personal-memory"))

        self.assertTrue(payload["found"])
        self.assertEqual(payload["memory"]["name"], "prefer-local-personal-memory")
        self.assertEqual(payload["provenance"]["source"], "demo")
        self.assertEqual(payload["recall"]["state"], "needs_review")
        self.assertEqual(payload["review"]["issues"][0]["code"], "pending_review")
        self.assertIn("agent-memory", payload["graph"]["forward"])

    def test_explain_memory_after_review_contract(self):
        self.server.review_memory("prefer-local-personal-memory")

        payload = json.loads(self.server.explain_memory("prefer-local-personal-memory"))

        self.assertEqual(payload["recall"]["state"], "ready")
        self.assertEqual(payload["review"]["issue_count"], 0)

    def test_archive_and_restore_memory_contract(self):
        archived = json.loads(self.server.archive_memory(
            "prefer-local-personal-memory",
            reason="unit test stale memory",
        ))
        recall_default = json.loads(self.server.recall_memory("local personal memory"))
        recall_archived = json.loads(self.server.recall_memory("local personal memory", include_archived=True))
        profile = json.loads(self.server.memory_profile())
        restored = json.loads(self.server.restore_memory("Prefer local personal memory"))
        recall_restored = json.loads(self.server.recall_memory("local personal memory"))

        self.assertTrue(archived["updated"])
        self.assertEqual(archived["status"], "archived")
        self.assertEqual(recall_default["count"], 0)
        self.assertEqual(recall_archived["memories"][0]["status"], "archived")
        self.assertEqual(profile["active_count"], 0)
        self.assertEqual(profile["archived"][0]["name"], "prefer-local-personal-memory")
        self.assertTrue(restored["updated"])
        self.assertEqual(restored["status"], "active")
        self.assertEqual(recall_restored["memories"][0]["name"], "prefer-local-personal-memory")

    def test_remember_memory_contract(self):
        payload = json.loads(self.server.remember_memory(
            "User prefers release branches for Link work.",
            title="Prefer release branches",
            memory_type="preference",
            scope="project",
            tags="git, release",
            source="unit test",
        ))
        recall = json.loads(self.server.recall_memory("release branches"))

        self.assertTrue(payload["created"])
        self.assertEqual(payload["name"], "prefer-release-branches")
        self.assertTrue((self.target / "wiki/memories/prefer-release-branches.md").exists())
        self.assertEqual(recall["memories"][0]["name"], "prefer-release-branches")

    def test_remember_memory_blocks_strong_duplicate(self):
        first = json.loads(self.server.remember_memory(
            "User prefers release branches for Link work.",
            title="Prefer release branches",
            memory_type="preference",
            scope="project",
        ))
        duplicate = json.loads(self.server.remember_memory(
            "User prefers release branches for Link work.",
            title="Prefer release branches",
            memory_type="preference",
            scope="project",
        ))
        override = json.loads(self.server.remember_memory(
            "User prefers release branches for Link work.",
            title="Prefer release branches",
            memory_type="preference",
            scope="project",
            allow_duplicate=True,
        ))

        self.assertTrue(first["created"])
        self.assertFalse(duplicate["created"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["candidates"][0]["name"], "prefer-release-branches")
        self.assertTrue(override["created"])
        self.assertTrue(override["duplicate_override"])
        self.assertEqual(override["name"], "prefer-release-branches-2")

    def test_update_memory_contract(self):
        reviewed = json.loads(self.server.review_memory("prefer-local-personal-memory", note="confirmed"))
        updated = json.loads(self.server.update_memory(
            "prefer-local-personal-memory",
            "Also prefer updating existing memories instead of creating duplicates.",
            source="unit test",
        ))
        explained = json.loads(self.server.explain_memory("prefer-local-personal-memory"))
        memory_text = (self.target / "wiki/memories/prefer-local-personal-memory.md").read_text(encoding="utf-8")
        log_text = (self.target / "wiki/log.md").read_text(encoding="utf-8")

        self.assertEqual(reviewed["review_status"], "reviewed")
        self.assertTrue(updated["updated"])
        self.assertEqual(updated["previous_review_status"], "reviewed")
        self.assertEqual(updated["review_status"], "pending")
        self.assertEqual(updated["update_count"], 1)
        self.assertTrue(updated["backlinks_rebuilt"])
        self.assertEqual(explained["review"]["status"], "pending")
        self.assertEqual(explained["recall"]["state"], "needs_review")
        self.assertIn("instead of creating duplicates", explained["body"])
        self.assertIn("update_count: 1", memory_text)
        self.assertNotIn("reviewed_at:", memory_text)
        self.assertIn("update-memory", log_text)

    def test_propose_memories_contract(self):
        created = json.loads(self.server.remember_memory(
            "User prefers release branches for Link work.",
            title="Prefer release branches",
            memory_type="preference",
            scope="project",
        ))
        payload = json.loads(self.server.propose_memories(
            "\n".join([
                "- I prefer release branches for Link work.",
                "- We decided to keep Memory Mode local and source-backed.",
                "- Maybe we could add cloud sync later.",
            ]),
            source="unit test session",
        ))

        self.assertTrue(created["created"])
        self.assertTrue(payload["proposed"])
        self.assertEqual(payload["count"], 2)
        self.assertGreaterEqual(payload["skipped_count"], 1)
        self.assertEqual(payload["proposals"][0]["memory_type"], "preference")
        self.assertEqual(payload["proposals"][0]["suggested_action"], "update-memory")
        self.assertEqual(payload["proposals"][0]["duplicate_candidates"][0]["name"], "prefer-release-branches")
        self.assertEqual(payload["proposals"][1]["memory_type"], "decision")
        self.assertEqual(payload["proposals"][1]["suggested_action"], "remember")

    def test_rebuild_backlinks_contract(self):
        backlinks_path = self.target / "wiki/_backlinks.json"
        backlinks_path.write_text(json.dumps({"backlinks": {}, "forward": {}}), encoding="utf-8")

        payload = json.loads(self.server.rebuild_backlinks())
        rebuilt = json.loads(backlinks_path.read_text(encoding="utf-8"))

        self.assertTrue(payload["rebuilt"])
        self.assertIn("agent-memory", rebuilt["backlinks"])
        self.assertIn("agent-memory", rebuilt["forward"])
        self.assertIn("link", rebuilt["backlinks"]["agent-memory"])


if __name__ == "__main__":
    unittest.main()
