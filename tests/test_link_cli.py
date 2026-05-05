import importlib.util
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("link_cli", ROOT / "link.py")
link_cli = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(link_cli)


def create_demo_quiet(target: Path, force: bool = False) -> None:
    with redirect_stdout(StringIO()):
        link_cli.create_demo(target, force=force)


class LinkCliTests(unittest.TestCase):
    def test_demo_creates_preingested_wiki(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-demo-test-"))
        target = tmp / "demo"

        create_demo_quiet(target)

        self.assertTrue((target / ".link-demo").exists())
        self.assertTrue((target / "serve.py").exists())
        self.assertTrue((target / "link.py").exists())
        self.assertTrue((target / "LINK.md").exists())
        self.assertTrue((target / "raw/agent-memory-session.md").exists())
        self.assertTrue((target / "wiki/concepts/agent-memory.md").exists())
        self.assertTrue((target / "wiki/entities/link.md").exists())

        backlinks = json.loads((target / "wiki/_backlinks.json").read_text(encoding="utf-8"))
        self.assertIn("backlinks", backlinks)
        self.assertIn("forward", backlinks)
        self.assertIn("agent-memory", backlinks["backlinks"])
        self.assertIn("link", backlinks["backlinks"])
        self.assertIn("agent-memory", backlinks["forward"]["link"])

    def test_demo_refuses_to_overwrite_non_demo_directory(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-demo-test-"))
        target = tmp / "not-demo"
        target.mkdir()
        (target / "keep.txt").write_text("do not replace", encoding="utf-8")

        with self.assertRaises(SystemExit):
            link_cli.create_demo(target, force=True)

        self.assertEqual((target / "keep.txt").read_text(encoding="utf-8"), "do not replace")

    def test_demo_force_replaces_demo_directory(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-demo-test-"))
        target = tmp / "demo"

        create_demo_quiet(target)
        (target / "extra.txt").write_text("old", encoding="utf-8")
        create_demo_quiet(target, force=True)

        self.assertFalse((target / "extra.txt").exists())
        self.assertTrue((target / "wiki/index.md").exists())

    def test_doctor_accepts_demo_wiki(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-doctor-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.doctor(target)

        self.assertEqual(code, 0)
        self.assertIn("Result: healthy", out.getvalue())
        self.assertIn("OK wiki pages have summaries", out.getvalue())
        self.assertIn("OK source-backed pages cite sources", out.getvalue())
        self.assertIn("OK no sensitive-looking file contents", out.getvalue())

    def test_ingest_status_accepts_demo_wiki(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-ingest-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.ingest_status(target)

        self.assertEqual(code, 0)
        self.assertIn("Raw files: 3", out.getvalue())
        self.assertIn("Pending ingest: 0", out.getvalue())
        self.assertIn("Backlinks: current", out.getvalue())

    def test_ingest_status_reports_pending_raw_file(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-ingest-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        (target / "raw/new-source.md").write_text("# New source\n", encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.ingest_status(target)

        self.assertEqual(code, 0)
        self.assertIn("Pending ingest: 1", out.getvalue())
        self.assertIn("raw/new-source.md", out.getvalue())
        self.assertIn("Ask your agent: ingest raw/new-source.md", out.getvalue())

    def test_ingest_status_json(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-ingest-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        (target / "raw/new-source.md").write_text("# New source\n", encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.ingest_status(target, json_output=True)

        data = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(data["raw_count"], 4)
        self.assertEqual(data["pending_count"], 1)
        self.assertEqual(data["pending_raw"][0]["raw"], "raw/new-source.md")

    def test_ingest_status_reports_stale_backlinks(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-ingest-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        backlinks_path = target / "wiki/_backlinks.json"
        backlinks_path.write_text(json.dumps({"backlinks": {}, "forward": {}}), encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.ingest_status(target)

        self.assertEqual(code, 0)
        self.assertIn("Backlinks: stale", out.getvalue())
        self.assertIn("Repair graph index", out.getvalue())

    def test_remember_creates_memory_page_and_updates_backlinks(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.remember(
                target,
                "User prefers release branches for Link work.",
                title="Prefer release branches",
                memory_type="preference",
                scope="project",
                tags="git, release",
                source="unit test",
            )

        memory_path = target / "wiki/memories/prefer-release-branches.md"
        backlinks = json.loads((target / "wiki/_backlinks.json").read_text(encoding="utf-8"))
        index_text = (target / "wiki/index.md").read_text(encoding="utf-8")
        log_text = (target / "wiki/log.md").read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertTrue(memory_path.exists())
        self.assertIn("memory_type: preference", memory_path.read_text(encoding="utf-8"))
        self.assertIn("[[prefer-release-branches]]", index_text)
        self.assertIn("Created: memories/prefer-release-branches.md", log_text)
        self.assertIn("prefer-release-branches", backlinks["backlinks"])
        self.assertIn("Memory saved", out.getvalue())

    def test_recall_finds_memory_pages(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        with redirect_stdout(StringIO()):
            link_cli.remember(
                target,
                "User prefers release branches for Link work.",
                title="Prefer release branches",
                memory_type="preference",
                scope="project",
            )

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.recall(target, "release branches")

        self.assertEqual(code, 0)
        self.assertIn("Prefer release branches", out.getvalue())
        self.assertIn("wiki/memories/prefer-release-branches.md", out.getvalue())

    def test_recall_json(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        with redirect_stdout(StringIO()):
            link_cli.remember(target, "User likes local first memory.", title="Local memory preference")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.recall(target, "local memory", json_output=True)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["memories"][0]["name"], "local-memory-preference")

    def test_profile_summarizes_memories(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        with redirect_stdout(StringIO()):
            link_cli.remember(
                target,
                "User decided to keep Memory Mode local.",
                title="Keep Memory Mode local",
                memory_type="decision",
                scope="project",
                tags="product",
            )

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.profile(target)

        self.assertEqual(code, 0)
        self.assertIn("Link memory profile", out.getvalue())
        self.assertIn("2 memories", out.getvalue())
        self.assertIn("preference: 1", out.getvalue())
        self.assertIn("decision: 1", out.getvalue())
        self.assertIn("Keep Memory Mode local", out.getvalue())

    def test_profile_json(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.profile(target, json_output=True)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["memory_count"], 1)
        self.assertEqual(payload["by_type"]["preference"], 1)
        self.assertEqual(payload["preferences"][0]["name"], "prefer-local-personal-memory")

    def test_verify_mcp_ready(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-verify-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.verify_mcp(
                target,
                python_cmd="/tmp/python",
                import_check=lambda _: {"installed": True, "version": "9.9.9", "error": None},
            )

        self.assertEqual(code, 0)
        self.assertIn("link-mcp: installed (9.9.9)", out.getvalue())
        self.assertIn('"command": "/tmp/python"', out.getvalue())
        self.assertIn("Result: ready", out.getvalue())

    def test_verify_mcp_uses_installer_python_marker(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-verify-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        (target / ".link-mcp-python").write_text("/tmp/link-mcp-venv/bin/python\n", encoding="utf-8")
        checked = []

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.verify_mcp(
                target,
                import_check=lambda cmd: checked.append(cmd) or {"installed": True, "version": "9.9.9", "error": None},
            )

        self.assertEqual(code, 0)
        self.assertEqual(checked, ["/tmp/link-mcp-venv/bin/python"])
        self.assertIn('"command": "/tmp/link-mcp-venv/bin/python"', out.getvalue())

    def test_verify_mcp_explicit_python_overrides_marker(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-verify-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        (target / ".link-mcp-python").write_text("/tmp/link-mcp-venv/bin/python\n", encoding="utf-8")
        checked = []

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.verify_mcp(
                target,
                python_cmd="/tmp/explicit-python",
                json_output=True,
                import_check=lambda cmd: checked.append(cmd) or {"installed": True, "version": "9.9.9", "error": None},
            )

        self.assertEqual(code, 0)
        self.assertEqual(checked, ["/tmp/explicit-python"])

    def test_verify_mcp_json(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-verify-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.verify_mcp(
                target,
                json_output=True,
                python_cmd="/tmp/python",
                import_check=lambda _: {"installed": True, "version": "9.9.9", "error": None},
            )

        data = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(data["ready"])
        self.assertEqual(data["link_mcp"]["version"], "9.9.9")
        self.assertEqual(data["config"]["mcpServers"]["link"]["command"], "/tmp/python")

    def test_verify_mcp_reports_missing_package(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-verify-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.verify_mcp(
                target,
                python_cmd="/tmp/python",
                import_check=lambda _: {"installed": False, "version": None, "error": "No module named link_mcp"},
            )

        self.assertEqual(code, 1)
        self.assertIn("link-mcp: missing", out.getvalue())
        self.assertIn("python3 -m pip install --upgrade link-mcp", out.getvalue())

    def test_verify_mcp_reports_missing_wiki(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-verify-test-"))
        target = tmp / "empty"
        target.mkdir()

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.verify_mcp(
                target,
                python_cmd="/tmp/python",
                import_check=lambda _: {"installed": True, "version": "9.9.9", "error": None},
            )

        self.assertEqual(code, 1)
        self.assertIn("Wiki: missing", out.getvalue())
        self.assertIn("python3 link.py demo", out.getvalue())

    def test_doctor_reports_dead_links(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-doctor-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        page = target / "wiki/concepts/agent-memory.md"
        page.write_text(page.read_text(encoding="utf-8") + "\n[[missing-page]]\n", encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.doctor(target)

        self.assertEqual(code, 1)
        self.assertIn("dead wikilinks", out.getvalue())

    def test_doctor_reports_stale_backlinks(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-doctor-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        backlinks_path = target / "wiki/_backlinks.json"
        backlinks_path.write_text(json.dumps({"backlinks": {}, "forward": {}}), encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.doctor(target)

        self.assertEqual(code, 1)
        self.assertIn("stale", out.getvalue())

    def test_rebuild_backlinks_repairs_stale_index(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-doctor-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        backlinks_path = target / "wiki/_backlinks.json"
        backlinks_path.write_text(json.dumps({"backlinks": {}, "forward": {}}), encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            rebuild_code = link_cli.rebuild_backlinks(target)
            doctor_code = link_cli.doctor(target)

        rebuilt = json.loads(backlinks_path.read_text(encoding="utf-8"))
        self.assertEqual(rebuild_code, 0)
        self.assertEqual(doctor_code, 0)
        self.assertIn("Rebuilt", out.getvalue())
        self.assertIn("agent-memory", rebuilt["backlinks"])

    def test_doctor_fix_repairs_stale_backlinks(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-doctor-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        backlinks_path = target / "wiki/_backlinks.json"
        backlinks_path.write_text(json.dumps({"backlinks": {}, "forward": {}}), encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.doctor(target, fix=True)

        rebuilt = json.loads(backlinks_path.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertIn("rebuilt wiki/_backlinks.json", out.getvalue())
        self.assertIn("Result: healthy", out.getvalue())
        self.assertIn("agent-memory", rebuilt["backlinks"])

    def test_doctor_fix_creates_missing_structure(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-doctor-test-"))
        target = tmp / "empty"
        target.mkdir()

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.doctor(target, fix=True)

        self.assertEqual(code, 0)
        self.assertTrue((target / "raw").is_dir())
        self.assertTrue((target / "wiki/sources").is_dir())
        self.assertTrue((target / "wiki/concepts").is_dir())
        self.assertTrue((target / "wiki/memories").is_dir())
        self.assertTrue((target / "wiki/_backlinks.json").exists())
        self.assertIn("created raw", out.getvalue())
        self.assertIn("created wiki/index.md", out.getvalue())
        self.assertIn("Result: healthy", out.getvalue())

    def test_doctor_fix_does_not_hide_content_errors(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-doctor-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        page = target / "wiki/concepts/agent-memory.md"
        page.write_text(page.read_text(encoding="utf-8") + "\n[[missing-page]]\n", encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.doctor(target, fix=True)

        self.assertEqual(code, 1)
        self.assertIn("dead wikilinks", out.getvalue())

    def test_doctor_warns_on_missing_summary(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-doctor-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        page = target / "wiki/concepts/agent-memory.md"
        page.write_text(
            page.read_text(encoding="utf-8").replace("> **TLDR:**", "> **Summary:**", 1),
            encoding="utf-8",
        )

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.doctor(target)

        self.assertEqual(code, 0)
        self.assertIn("pages missing TLDR/query summary", out.getvalue())

    def test_doctor_fails_on_secret_like_content(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-doctor-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        fake_key = "AKIA" + ("A" * 16)
        (target / "raw/leak.md").write_text(f"key = {fake_key}\n", encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.doctor(target)

        self.assertEqual(code, 1)
        self.assertIn("sensitive-looking file contents", out.getvalue())

    def test_doctor_fails_on_google_api_key_content(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-doctor-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        fake_key = "AIza" + ("A" * 35)
        (target / "raw/google-leak.md").write_text(f"key = {fake_key}\n", encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.doctor(target)

        self.assertEqual(code, 1)
        self.assertIn("Google API key", out.getvalue())

    def test_doctor_fails_on_sensitive_filename(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-doctor-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        (target / ".env.local").write_text("placeholder=true\n", encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.doctor(target)

        self.assertEqual(code, 1)
        self.assertIn("sensitive-looking filenames", out.getvalue())

    def test_doctor_fails_on_service_account_filename(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-doctor-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        (target / "raw/service-account-prod.json").write_text("{}", encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.doctor(target)

        self.assertEqual(code, 1)
        self.assertIn("service-account-prod.json", out.getvalue())


if __name__ == "__main__":
    unittest.main()
