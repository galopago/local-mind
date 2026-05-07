import importlib.util
import json
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("link_cli", ROOT / "link.py")
link_cli = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(link_cli)


def create_demo_quiet(target: Path, force: bool = False) -> None:
    with redirect_stdout(StringIO()):
        link_cli.create_demo(target, force=force)


class LinkCliTests(unittest.TestCase):
    def test_init_creates_empty_wiki(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-init-test-"))
        target = tmp / "my-link"

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.init_wiki(target)

        self.assertEqual(code, 0)
        self.assertTrue((target / "serve.py").exists())
        self.assertTrue((target / "link.py").exists())
        self.assertTrue((target / "LINK.md").exists())
        self.assertTrue((target / "link_core/frontmatter.py").exists())
        self.assertTrue((target / "raw").is_dir())
        self.assertTrue((target / "wiki/index.md").exists())
        self.assertTrue((target / "wiki/log.md").exists())
        self.assertTrue((target / "wiki/_backlinks.json").exists())
        self.assertTrue((target / "wiki/_link_schema.json").exists())
        self.assertTrue((target / "wiki/sources").is_dir())
        self.assertTrue((target / "wiki/memories").is_dir())

        backlinks = json.loads((target / "wiki/_backlinks.json").read_text(encoding="utf-8"))
        self.assertIn("backlinks", backlinks)
        self.assertIn("forward", backlinks)
        self.assertIn("link status --validate", out.getvalue())
        self.assertIn("link serve", out.getvalue())

    def test_init_preserves_existing_pages(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-init-test-"))
        target = tmp / "my-link"
        page = target / "wiki/concepts/custom.md"
        page.parent.mkdir(parents=True)
        page.write_text("# Custom\n", encoding="utf-8")

        with redirect_stdout(StringIO()):
            code = link_cli.init_wiki(target)

        self.assertEqual(code, 0)
        self.assertEqual(page.read_text(encoding="utf-8"), "# Custom\n")

    def test_init_copies_core_from_installed_runtime_layout(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-init-test-"))
        runtime = tmp / "runtime"
        runtime.mkdir()
        for name in ("serve.py", "link.py", "LINK.md", ".linkignore"):
            (runtime / name).write_text(f"# {name}\n", encoding="utf-8")
        (runtime / "link_core").mkdir()
        (runtime / "link_core/frontmatter.py").write_text("# core\n", encoding="utf-8")
        target = tmp / "my-link"

        with patch.object(link_cli, "ROOT", runtime), redirect_stdout(StringIO()):
            code = link_cli.init_wiki(target)

        self.assertEqual(code, 0)
        self.assertTrue((target / "link_core/frontmatter.py").exists())

    def test_serve_runs_target_viewer(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-serve-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        with patch.object(link_cli.subprocess, "run") as run:
            run.return_value.returncode = 0
            code = link_cli.serve_wiki(target, port=3010)

        self.assertEqual(code, 0)
        run.assert_called_once_with([sys.executable, str(target.resolve() / "serve.py"), "--port", "3010"])

    def test_serve_reports_missing_viewer(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-serve-test-"))

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.serve_wiki(tmp / "missing")

        self.assertEqual(code, 1)
        self.assertIn("Link viewer missing", out.getvalue())
        self.assertIn("link init", out.getvalue())

    def test_demo_creates_preingested_wiki(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-demo-test-"))
        target = tmp / "demo"

        create_demo_quiet(target)

        self.assertTrue((target / ".link-demo").exists())
        self.assertTrue((target / "serve.py").exists())
        self.assertTrue((target / "link.py").exists())
        self.assertTrue((target / "link_core/frontmatter.py").exists())
        self.assertTrue((target / "link_core/memory.py").exists())
        self.assertTrue((target / "LINK.md").exists())
        self.assertTrue((target / "START_HERE.md").exists())
        self.assertTrue((target / "raw/agent-memory-session.md").exists())
        self.assertTrue((target / "wiki/concepts/agent-memory.md").exists())
        self.assertTrue((target / "wiki/entities/link.md").exists())
        self.assertTrue((target / "wiki/_link_schema.json").exists())
        guide = (target / "START_HERE.md").read_text(encoding="utf-8")
        self.assertIn("query Link for why Link helps agents", guide)
        self.assertIn('python3 link.py query "why does Link help agents?" . --budget small', guide)

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
        self.assertIn("memories need review", out.getvalue())

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

    def test_capture_session_is_not_pending_source_ingest(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-ingest-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        with redirect_stdout(StringIO()):
            link_cli.capture_session(
                target,
                "Remember that capture notes are proposal-only memory backlog.",
                title="Capture backlog",
                json_output=True,
            )

        ingest_out = StringIO()
        with redirect_stdout(ingest_out):
            ingest_code = link_cli.ingest_status(target, json_output=True)
        ingest = json.loads(ingest_out.getvalue())

        doctor_out = StringIO()
        with redirect_stdout(doctor_out):
            doctor_code = link_cli.doctor(target)

        self.assertEqual(ingest_code, 0)
        self.assertEqual(ingest["raw_count"], 3)
        self.assertEqual(ingest["pending_count"], 0)
        self.assertEqual(doctor_code, 0)
        self.assertIn("raw memory captures pending review: 1", doctor_out.getvalue())
        self.assertNotIn("raw files not referenced by wiki pages", doctor_out.getvalue())

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
        self.assertIn("Guidance: 1 raw file needs ingest.", out.getvalue())
        self.assertIn("Ask your agent: ingest raw/new-source.md into Link", out.getvalue())
        self.assertIn("Run: link validate", out.getvalue())
        self.assertIn("Suggested workflow: Ingest pending raw sources", out.getvalue())
        self.assertIn("Memory review: propose memories from raw/new-source.md", out.getvalue())
        self.assertIn("raw/new-source.md -> wiki/sources/new-source.md", out.getvalue())

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
        self.assertEqual(data["guidance"]["state"], "pending_raw")
        self.assertEqual(data["guidance"]["agent_prompt"], "ingest raw/new-source.md into Link")
        self.assertEqual(data["plan"]["batch"][0]["suggested_source_page"], "wiki/sources/new-source.md")

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
        self.assertIn("Guidance: Raw files are represented, but the graph index needs repair.", out.getvalue())
        self.assertIn("Run: link rebuild-backlinks", out.getvalue())

    def test_status_reports_demo_readiness(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-status-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.status(target, include_validation=True)

        self.assertEqual(code, 0)
        self.assertIn("Ready: yes", out.getvalue())
        self.assertIn("Schema: current", out.getvalue())
        self.assertIn("Search backend:", out.getvalue())
        self.assertIn("Validation: passed", out.getvalue())
        self.assertIn("query_link", out.getvalue())

    def test_backup_creates_local_archive_without_raw_by_default(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-backup-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        (target / "raw/private-note.md").write_text("secret source", encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.backup(target, label="cli test")

        self.assertEqual(code, 0)
        self.assertIn("Link backup created:", out.getvalue())
        archives = list((target / ".link-backups").glob("*.tar.gz"))
        self.assertEqual(len(archives), 1)
        with tarfile.open(archives[0], "r:gz") as tar:
            names = set(tar.getnames())
        self.assertIn("wiki/index.md", names)
        self.assertNotIn("raw/private-note.md", names)

    def test_backup_json_can_include_raw_and_list_archives(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-backup-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        (target / "raw/private-note.md").write_text("source", encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.backup(target, label="with raw", include_raw=True, json_output=True)
        payload = json.loads(out.getvalue())

        list_out = StringIO()
        with redirect_stdout(list_out):
            list_code = link_cli.backup(target, list_only=True, json_output=True)
        listing = json.loads(list_out.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(list_code, 0)
        self.assertIn("raw", payload["included"])
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["backups"][0]["name"], payload["name"])

    def test_migrate_repairs_schema_marker(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-migrate-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        (target / "wiki/_link_schema.json").unlink()

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.migrate(target)

        self.assertEqual(code, 0)
        self.assertTrue((target / "wiki/_link_schema.json").exists())
        self.assertIn("Previous schema: missing", out.getvalue())
        self.assertIn("Result: current", out.getvalue())

    def test_migrate_json_reports_current_schema(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-migrate-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.migrate(target, json_output=True)
        payload = json.loads(out.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["schema"]["status"], "current")
        self.assertFalse(payload["migrated"])

    def test_status_json_reports_missing_structure(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-status-test-"))
        target = tmp / "empty"

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.status(target, include_validation=True, json_output=True)
        payload = json.loads(out.getvalue())

        self.assertEqual(code, 1)
        self.assertFalse(payload["ready"])
        self.assertIn("wiki", payload["missing"])
        self.assertEqual(payload["search_backend"], "unavailable")

    def test_validate_accepts_demo_wiki(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-validate-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.validate(target)

        self.assertEqual(code, 0)
        self.assertIn("OK wiki pages satisfy the ingest validation gate", out.getvalue())
        self.assertIn("Result: passed", out.getvalue())

    def test_validate_reports_agent_format_errors_as_json(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-validate-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        page = target / "wiki/concepts/agent-memory.md"
        page.write_text(
            page.read_text(encoding="utf-8")
            .replace("type: concept", "type: source", 1)
            .replace("## Sources", "## References", 1),
            encoding="utf-8",
        )
        with redirect_stdout(StringIO()):
            link_cli.rebuild_backlinks(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.validate(target, json_output=True)
        payload = json.loads(out.getvalue())
        codes = {finding["code"] for finding in payload["findings"]}

        self.assertEqual(code, 1)
        self.assertFalse(payload["passed"])
        self.assertIn("type_directory_mismatch", codes)
        self.assertIn("missing_required_section", codes)
        self.assertNotIn("stale_backlinks", codes)

    def test_validate_strict_fails_on_warnings(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-validate-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        page = target / "wiki/concepts/agent-memory.md"
        page.write_text(
            page.read_text(encoding="utf-8").replace("> **TLDR:**", "> **Summary:**", 1),
            encoding="utf-8",
        )

        normal_out = StringIO()
        with redirect_stdout(normal_out):
            normal_code = link_cli.validate(target)

        strict_out = StringIO()
        with redirect_stdout(strict_out):
            strict_code = link_cli.validate(target, strict=True)

        self.assertEqual(normal_code, 0)
        self.assertEqual(strict_code, 1)
        self.assertIn("WARNING", strict_out.getvalue())
        self.assertIn("Result: failed (0 errors, 1 warnings)", strict_out.getvalue())

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

    def test_remember_blocks_strong_duplicate_by_default(self):
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

        duplicate_out = StringIO()
        with redirect_stdout(duplicate_out):
            duplicate_code = link_cli.remember(
                target,
                "User prefers release branches for Link work.",
                title="Prefer release branches",
                memory_type="preference",
                scope="project",
                json_output=True,
            )
        duplicate = json.loads(duplicate_out.getvalue())

        override_out = StringIO()
        with redirect_stdout(override_out):
            override_code = link_cli.remember(
                target,
                "User prefers release branches for Link work.",
                title="Prefer release branches",
                memory_type="preference",
                scope="project",
                allow_duplicate=True,
                json_output=True,
            )
        override = json.loads(override_out.getvalue())

        self.assertEqual(duplicate_code, 0)
        self.assertFalse(duplicate["created"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["candidates"][0]["name"], "prefer-release-branches")
        self.assertEqual(override_code, 0)
        self.assertTrue(override["created"])
        self.assertTrue(override["duplicate_override"])
        self.assertEqual(override["name"], "prefer-release-branches-2")

    def test_remember_blocks_conflict_by_default(self):
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

        conflict_out = StringIO()
        with redirect_stdout(conflict_out):
            conflict_code = link_cli.remember(
                target,
                "User prefers develop branches for Link work.",
                title="Prefer develop branches",
                memory_type="preference",
                scope="project",
            )

        self.assertEqual(conflict_code, 0)
        self.assertIn("Possible conflicting memory found", conflict_out.getvalue())
        self.assertIn("Prefer release branches", conflict_out.getvalue())
        self.assertFalse((target / "wiki/memories/prefer-develop-branches.md").exists())

    def test_update_memory_merges_text_and_resets_review(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        with redirect_stdout(StringIO()):
            link_cli.review_memory(target, "prefer-local-personal-memory", note="confirmed")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.update_memory(
                target,
                "prefer-local-personal-memory",
                "Also prefer updating existing memories instead of creating duplicates.",
                source="unit test",
                json_output=True,
            )
        payload = json.loads(out.getvalue())
        memory_text = (target / "wiki/memories/prefer-local-personal-memory.md").read_text(encoding="utf-8")
        log_text = (target / "wiki/log.md").read_text(encoding="utf-8")
        backlinks = json.loads((target / "wiki/_backlinks.json").read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertTrue(payload["updated"])
        self.assertEqual(payload["previous_review_status"], "reviewed")
        self.assertEqual(payload["review_status"], "pending")
        self.assertEqual(payload["update_count"], 1)
        self.assertIn("updated_at:", memory_text)
        self.assertIn("update_count: 1", memory_text)
        self.assertIn('last_update_source: "unit test"', memory_text)
        self.assertIn("review_status: pending", memory_text)
        self.assertNotIn("reviewed_at:", memory_text)
        self.assertIn("Update (", memory_text)
        self.assertIn("instead of creating duplicates", memory_text)
        self.assertIn("update-memory", log_text)
        self.assertIn("prefer-local-personal-memory", backlinks["backlinks"]["link"])

    def test_propose_memories_from_session_note_without_writing(self):
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
        session_note = tmp / "session.md"
        session_note.write_text(
            "\n".join([
                "- I prefer release branches for Link work.",
                "- We decided to keep Memory Mode local and source-backed.",
                "- Maybe we could add cloud sync later.",
            ]),
            encoding="utf-8",
        )

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.propose_memories(target, str(session_note), json_output=True)
        payload = json.loads(out.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["count"], 2)
        self.assertGreaterEqual(payload["skipped_count"], 1)
        self.assertEqual(payload["proposals"][0]["memory_type"], "preference")
        self.assertEqual(payload["proposals"][0]["suggested_action"], "update-memory")
        self.assertEqual(payload["proposals"][0]["primary_action"]["kind"], "update")
        self.assertEqual(payload["proposals"][0]["duplicate_candidates"][0]["name"], "prefer-release-branches")
        self.assertEqual(payload["proposals"][1]["memory_type"], "decision")
        self.assertEqual(payload["proposals"][1]["scope"], "project")
        self.assertEqual(payload["proposals"][1]["primary_action"]["kind"], "remember")
        self.assertFalse((target / "wiki/memories/decision-keep-memory-mode-local.md").exists())

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
        self.assertIn("Recall: needs_review", out.getvalue())

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
        self.assertEqual(payload["memories"][0]["recall"]["state"], "needs_review")
        self.assertEqual(payload["memories"][0]["review_issue_count"], 1)

    def test_recall_json_filters_project(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        with redirect_stdout(StringIO()):
            link_cli.remember(
                target,
                "Project uses alpha API for imports.",
                title="Alpha API imports",
                memory_type="project",
                scope="project",
                project="alpha",
            )
            link_cli.remember(
                target,
                "Project uses beta API for imports.",
                title="Beta API imports",
                memory_type="project",
                scope="project",
                project="beta",
            )

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.recall(target, "API imports", project="alpha", json_output=True)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["project"], "alpha")
        self.assertEqual([item["name"] for item in payload["memories"]], ["alpha-api-imports"])

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
        self.assertEqual(payload["review_count"], 1)

    def test_brief_primes_agent_memory(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.brief(target, "local personal memory")

        self.assertEqual(code, 0)
        self.assertIn("Link memory brief: local personal memory", out.getvalue())
        self.assertIn("Prefer local personal memory", out.getvalue())
        self.assertIn("Agent guidance", out.getvalue())

    def test_brief_json(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.brief(target, "local personal memory", json_output=True)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["selection"], "query")
        self.assertEqual(payload["profile"]["memory_count"], 1)
        self.assertEqual(payload["captures"]["count"], 0)
        self.assertEqual(payload["relevant_memories"][0]["name"], "prefer-local-personal-memory")
        self.assertNotIn("body", payload["relevant_memories"][0])

    def test_query_builds_context_packet(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-query-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.query(target, "agent memory", budget="small", json_output=True)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["found"])
        self.assertEqual(payload["budget"], "small")
        self.assertIn("memory", payload["strategy"]["mode"])
        self.assertEqual(payload["wiki"]["primary"], "agent-memory")
        self.assertEqual(payload["memory"]["items"][0]["name"], "prefer-local-personal-memory")
        self.assertIn("context_packet", payload)

    def test_benchmark_reports_local_query_timings(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-benchmark-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.benchmark(target, "agent memory", budget="small", json_output=True)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["query"], "agent memory")
        self.assertTrue(payload["found"])
        self.assertGreaterEqual(payload["pages"], 1)
        self.assertGreaterEqual(payload["memories"], 1)
        self.assertGreaterEqual(payload["edges"], 1)
        self.assertIn(payload["search_backend"], {"sqlite-fts", "token-index"})
        self.assertEqual(payload["budget"], "small")
        self.assertIn("cache", payload["timings"])
        self.assertIn("search", payload["timings"])
        self.assertIn("query", payload["timings"])
        self.assertIn("graph", payload["timings"])
        self.assertGreater(payload["budget_report"]["context_packet"]["estimated_chars"], 0)
        self.assertEqual(payload["health"]["status"], "pass")
        self.assertEqual(payload["health"]["label"], "interactive")
        self.assertIn("search", payload["health"]["thresholds_seconds"])

        text_out = StringIO()
        with redirect_stdout(text_out):
            text_code = link_cli.benchmark(target, "agent memory", budget="small")

        self.assertEqual(text_code, 0)
        self.assertIn("Verdict: interactive", text_out.getvalue())

    def test_brief_surfaces_saved_captures_without_secret_values(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        fake_key = "sk-" + ("F" * 24)
        with redirect_stdout(StringIO()):
            link_cli.capture_session(
                target,
                f"Remember that brief should surface capture review. Test key {fake_key}",
                title="Brief capture",
                project="alpha",
                json_output=True,
            )

        json_out = StringIO()
        with redirect_stdout(json_out):
            json_code = link_cli.brief(target, "capture review", project="alpha", json_output=True)
        payload = json.loads(json_out.getvalue())

        text_out = StringIO()
        with redirect_stdout(text_out):
            text_code = link_cli.brief(target, "capture review", project="alpha")

        self.assertEqual(json_code, 0)
        self.assertEqual(text_code, 0)
        self.assertEqual(payload["captures"]["project"], "alpha")
        self.assertEqual(payload["captures"]["count"], 1)
        self.assertEqual(payload["captures"]["warning_count"], 1)
        self.assertIn("[redacted-secret]", payload["captures"]["items"][0]["snippet"])
        self.assertIn("capture-inbox", payload["captures"]["next_action"])
        self.assertIn("Redact raw captures", "\n".join(payload["agent_guidance"]))
        self.assertNotIn(fake_key, json_out.getvalue())
        self.assertIn("Raw captures", text_out.getvalue())
        self.assertNotIn(fake_key, text_out.getvalue())

    def test_memory_audit_reports_backlog_without_secret_values(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        fake_key = "sk-" + ("G" * 24)
        with redirect_stdout(StringIO()):
            link_cli.capture_session(
                target,
                f"Remember that memory audit should show capture risk. Test key {fake_key}",
                title="Audit capture",
                project="alpha",
                json_output=True,
            )

        json_out = StringIO()
        with redirect_stdout(json_out):
            json_code = link_cli.memory_audit(target, project="alpha", json_output=True)
        payload = json.loads(json_out.getvalue())

        text_out = StringIO()
        with redirect_stdout(text_out):
            text_code = link_cli.memory_audit(target, project="alpha")

        self.assertEqual(json_code, 0)
        self.assertEqual(text_code, 0)
        self.assertEqual(payload["status"], "needs_attention")
        self.assertEqual(payload["project"], "alpha")
        self.assertEqual(payload["captures"]["warning_count"], 1)
        self.assertIn("capture_secret_warnings", [factor["code"] for factor in payload["risk_factors"]])
        self.assertIn("memory-inbox", payload["next_actions"][0]["command"])
        self.assertIn("capture-inbox", payload["next_actions"][1]["command"])
        self.assertNotIn(fake_key, json_out.getvalue())
        self.assertIn("Link memory audit", text_out.getvalue())
        self.assertIn("needs_attention", text_out.getvalue())
        self.assertNotIn(fake_key, text_out.getvalue())

    def test_capture_session_writes_raw_note_and_proposes_only(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        before_memories = list((target / "wiki/memories").glob("*.md"))

        out = StringIO()
        fake_key = "sk-" + ("A" * 24)
        with redirect_stdout(out):
            code = link_cli.capture_session(
                target,
                f"Remember that the user prefers release branches for Link work. Test key {fake_key}",
                title="Release workflow session",
                project="link",
                json_output=True,
            )

        payload = json.loads(out.getvalue())
        capture_path = target / payload["path"]
        after_memories = list((target / "wiki/memories").glob("*.md"))
        capture_text = capture_path.read_text(encoding="utf-8")
        log_text = (target / "wiki/log.md").read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertTrue(payload["captured"])
        self.assertEqual(payload["project"], "link")
        self.assertTrue(payload["path"].startswith("raw/memory-captures/"))
        self.assertIn('project: "link"', capture_text)
        self.assertIn("proposal-only", capture_text)
        self.assertEqual(payload["secret_warnings"], ["OpenAI API key"])
        self.assertGreaterEqual(payload["proposals"]["count"], 1)
        self.assertEqual(len(after_memories), len(before_memories))
        self.assertIn("capture-session", log_text)

    def test_capture_inbox_lists_captures_without_secret_values(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        fake_key = "sk-" + ("E" * 24)

        alpha_out = StringIO()
        with redirect_stdout(alpha_out):
            alpha_code = link_cli.capture_session(
                target,
                f"Remember that Alpha project captures need review. Test key {fake_key}",
                title="Alpha capture",
                project="alpha",
                json_output=True,
            )
        beta_out = StringIO()
        with redirect_stdout(beta_out):
            beta_code = link_cli.capture_session(
                target,
                "Remember that Beta project captures stay separate.",
                title="Beta capture",
                project="beta",
                json_output=True,
            )

        inbox_out = StringIO()
        with redirect_stdout(inbox_out):
            inbox_code = link_cli.capture_inbox(target, project="alpha", json_output=True)
        inbox = json.loads(inbox_out.getvalue())

        text_out = StringIO()
        with redirect_stdout(text_out):
            text_code = link_cli.capture_inbox(target, project="alpha")
        text = text_out.getvalue()

        self.assertEqual(alpha_code, 0)
        self.assertEqual(beta_code, 0)
        self.assertEqual(inbox_code, 0)
        self.assertEqual(text_code, 0)
        self.assertEqual(inbox["project"], "alpha")
        self.assertEqual(inbox["count"], 1)
        self.assertEqual(inbox["warning_count"], 1)
        self.assertEqual(inbox["captures"][0]["project"], "alpha")
        self.assertEqual(inbox["captures"][0]["secret_warnings"], ["OpenAI API key"])
        self.assertIn("[redacted-secret]", inbox["captures"][0]["snippet"])
        self.assertNotIn(fake_key, inbox_out.getvalue())
        self.assertIn("accept-capture", inbox["captures"][0]["commands"]["accept"])
        self.assertIn("redact-capture", text)
        self.assertIn("delete-capture", text)
        self.assertNotIn("Beta capture", inbox_out.getvalue())
        self.assertNotIn(fake_key, text)

    def test_accept_capture_writes_approved_proposal(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        capture_out = StringIO()
        with redirect_stdout(capture_out):
            capture_code = link_cli.capture_session(
                target,
                "We decided to keep session capture approval local and explicit.",
                title="Capture approval session",
                project="link",
                json_output=True,
            )
        capture = json.loads(capture_out.getvalue())

        accept_out = StringIO()
        with redirect_stdout(accept_out):
            accept_code = link_cli.accept_capture(
                target,
                capture["path"],
                index=1,
                json_output=True,
            )
        accepted = json.loads(accept_out.getvalue())
        memory_path = target / accepted["result"]["path"]
        memory_text = memory_path.read_text(encoding="utf-8")
        log_text = (target / "wiki/log.md").read_text(encoding="utf-8")

        self.assertEqual(capture_code, 0)
        self.assertEqual(accept_code, 0)
        self.assertTrue(accepted["accepted"])
        self.assertEqual(accepted["capture"], capture["path"])
        self.assertTrue(accepted["result"]["created"])
        self.assertIn(f'source: "{capture["path"]}"', memory_text)
        self.assertIn("session capture approval", memory_text)
        self.assertIn("accept-capture", log_text)

    def test_redact_capture_replaces_secret_like_values(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        fake_key = "sk-" + ("B" * 24)

        capture_out = StringIO()
        with redirect_stdout(capture_out):
            link_cli.capture_session(
                target,
                f"Remember that capture redaction stays local. Test key {fake_key}",
                title="Capture redaction session",
                json_output=True,
            )
        capture = json.loads(capture_out.getvalue())

        redact_out = StringIO()
        with redirect_stdout(redact_out):
            code = link_cli.redact_capture(target, capture["path"], json_output=True)
        redacted = json.loads(redact_out.getvalue())
        capture_text = (target / capture["path"]).read_text(encoding="utf-8")
        log_text = (target / "wiki/log.md").read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertTrue(redacted["redacted"])
        self.assertEqual(redacted["labels"], ["OpenAI API key"])
        self.assertNotIn(fake_key, capture_text)
        self.assertIn("[redacted-secret]", capture_text)
        self.assertIn("redact-capture", log_text)
        self.assertNotIn(fake_key, log_text)

    def test_delete_capture_requires_confirmation_and_removes_file(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        capture_out = StringIO()
        with redirect_stdout(capture_out):
            link_cli.capture_session(
                target,
                "Remember that raw capture deletion requires confirmation.",
                title="Capture deletion session",
                json_output=True,
            )
        capture = json.loads(capture_out.getvalue())
        capture_path = target / capture["path"]

        denied_out = StringIO()
        with redirect_stdout(denied_out):
            denied_code = link_cli.delete_capture(target, capture["path"], json_output=True)
        denied = json.loads(denied_out.getvalue())
        self.assertTrue(capture_path.exists())

        delete_out = StringIO()
        with redirect_stdout(delete_out):
            delete_code = link_cli.delete_capture(target, capture["path"], confirm=True, json_output=True)
        deleted = json.loads(delete_out.getvalue())
        log_text = (target / "wiki/log.md").read_text(encoding="utf-8")

        self.assertEqual(denied_code, 1)
        self.assertFalse(denied["deleted"])
        self.assertEqual(delete_code, 0)
        self.assertTrue(deleted["deleted"])
        self.assertFalse(capture_path.exists())
        self.assertIn("delete-capture", log_text)
        self.assertNotIn("raw capture deletion requires confirmation", log_text)

    def test_memory_inbox_and_review_memory(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        inbox_out = StringIO()
        with redirect_stdout(inbox_out):
            inbox_code = link_cli.memory_inbox(target, json_output=True)
        inbox = json.loads(inbox_out.getvalue())

        self.assertEqual(inbox_code, 0)
        self.assertEqual(inbox["review_count"], 1)
        self.assertEqual(inbox["items"][0]["name"], "prefer-local-personal-memory")
        self.assertEqual(inbox["items"][0]["issues"][0]["code"], "pending_review")
        self.assertEqual(inbox["items"][0]["primary_action"]["kind"], "review")

        text_out = StringIO()
        with redirect_stdout(text_out):
            text_code = link_cli.memory_inbox(target)
        self.assertEqual(text_code, 0)
        self.assertIn("Next: Review", text_out.getvalue())
        self.assertIn("Other actions:", text_out.getvalue())

        review_out = StringIO()
        with redirect_stdout(review_out):
            review_code = link_cli.review_memory(
                target,
                "prefer-local-personal-memory",
                note="confirmed in unit test",
                json_output=True,
            )
        review = json.loads(review_out.getvalue())
        memory_text = (target / "wiki/memories/prefer-local-personal-memory.md").read_text(encoding="utf-8")
        log_text = (target / "wiki/log.md").read_text(encoding="utf-8")

        self.assertEqual(review_code, 0)
        self.assertTrue(review["updated"])
        self.assertEqual(review["review_status"], "reviewed")
        self.assertEqual(review["remaining_issue_count"], 0)
        self.assertIn("review_status: reviewed", memory_text)
        self.assertIn("reviewed_at:", memory_text)
        self.assertIn('review_note: "confirmed in unit test"', memory_text)
        self.assertIn("review-memory", log_text)

        clear_out = StringIO()
        with redirect_stdout(clear_out):
            clear_code = link_cli.memory_inbox(target, json_output=True)
        clear = json.loads(clear_out.getvalue())
        self.assertEqual(clear_code, 0)
        self.assertEqual(clear["review_count"], 0)

    def test_memory_inbox_filters_by_project(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        with redirect_stdout(StringIO()):
            link_cli.review_memory(target, "prefer-local-personal-memory", json_output=True)
            alpha_code = link_cli.remember(
                target,
                "Alpha project stores deployment context in Link.",
                title="Alpha deployment context",
                memory_type="project",
                scope="project",
                project="alpha",
                json_output=True,
            )
            beta_code = link_cli.remember(
                target,
                "Beta project stores design context in Link.",
                title="Beta design context",
                memory_type="project",
                scope="project",
                project="beta",
                json_output=True,
            )

        inbox_out = StringIO()
        with redirect_stdout(inbox_out):
            inbox_code = link_cli.memory_inbox(target, project="alpha", json_output=True)
        inbox = json.loads(inbox_out.getvalue())

        text_out = StringIO()
        with redirect_stdout(text_out):
            text_code = link_cli.memory_inbox(target, project="alpha")

        self.assertEqual(alpha_code, 0)
        self.assertEqual(beta_code, 0)
        self.assertEqual(inbox_code, 0)
        self.assertEqual(text_code, 0)
        self.assertEqual(inbox["project"], "alpha")
        self.assertEqual([item["project"] for item in inbox["items"]], ["alpha"])
        self.assertIn("Project: alpha", text_out.getvalue())
        self.assertNotIn("Beta design context", inbox_out.getvalue())

    def test_explain_memory_reports_trust_state_and_graph(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.explain_memory(target, "prefer-local-personal-memory", json_output=True)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["found"])
        self.assertEqual(payload["memory"]["name"], "prefer-local-personal-memory")
        self.assertEqual(payload["provenance"]["source"], "demo")
        self.assertEqual(payload["recall"]["state"], "needs_review")
        self.assertTrue(payload["recall"]["default_enabled"])
        self.assertEqual(payload["review"]["issues"][0]["code"], "pending_review")
        self.assertIn("agent-memory", payload["graph"]["forward"])
        self.assertIn("link", payload["graph"]["forward"])
        self.assertIn("Prefer local personal memory", payload["body"])

    def test_explain_memory_ready_after_review_and_disabled_after_archive(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        with redirect_stdout(StringIO()):
            link_cli.review_memory(target, "prefer-local-personal-memory")

        reviewed_out = StringIO()
        with redirect_stdout(reviewed_out):
            link_cli.explain_memory(target, "prefer-local-personal-memory", json_output=True)
        reviewed = json.loads(reviewed_out.getvalue())

        with redirect_stdout(StringIO()):
            link_cli.archive_memory(target, "prefer-local-personal-memory", reason="unit test")
        archived_out = StringIO()
        with redirect_stdout(archived_out):
            link_cli.explain_memory(target, "prefer-local-personal-memory", json_output=True)
        archived = json.loads(archived_out.getvalue())

        self.assertEqual(reviewed["recall"]["state"], "ready")
        self.assertEqual(reviewed["review"]["issue_count"], 0)
        self.assertEqual(archived["recall"]["state"], "disabled")
        self.assertFalse(archived["recall"]["default_enabled"])
        self.assertEqual(archived["lifecycle"]["status"], "archived")

    def test_reviewed_memory_with_quality_issue_stays_in_inbox(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        memory_path = target / "wiki/memories/prefer-local-personal-memory.md"
        text = memory_path.read_text(encoding="utf-8")
        text = text.replace('source: "demo"\n', "")
        memory_path.write_text(text, encoding="utf-8")

        with redirect_stdout(StringIO()):
            code = link_cli.review_memory(target, "prefer-local-personal-memory")
        inbox_out = StringIO()
        with redirect_stdout(inbox_out):
            link_cli.memory_inbox(target, json_output=True)
        inbox = json.loads(inbox_out.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(inbox["review_count"], 1)
        self.assertEqual(inbox["items"][0]["issues"][0]["code"], "missing_source")

    def test_archive_memory_hides_from_default_recall_and_restore_reenables(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        with redirect_stdout(StringIO()):
            archive_code = link_cli.archive_memory(
                target,
                "prefer-local-personal-memory",
                reason="unit test stale memory",
            )

        memory_path = target / "wiki/memories/prefer-local-personal-memory.md"
        archived_text = memory_path.read_text(encoding="utf-8")
        log_text = (target / "wiki/log.md").read_text(encoding="utf-8")

        self.assertEqual(archive_code, 0)
        self.assertIn("status: archived", archived_text)
        self.assertIn("archived_at:", archived_text)
        self.assertIn('archive_reason: "unit test stale memory"', archived_text)
        self.assertIn("archive-memory", log_text)

        profile_out = StringIO()
        with redirect_stdout(profile_out):
            link_cli.profile(target, json_output=True)
        profile_payload = json.loads(profile_out.getvalue())
        self.assertEqual(profile_payload["active_count"], 0)
        self.assertEqual(profile_payload["by_status"]["archived"], 1)
        self.assertEqual(profile_payload["archived"][0]["name"], "prefer-local-personal-memory")

        out = StringIO()
        with redirect_stdout(out):
            recall_code = link_cli.recall(target, "local personal memory")
        self.assertEqual(recall_code, 0)
        self.assertIn("No matching memories found.", out.getvalue())

        out_json = StringIO()
        with redirect_stdout(out_json):
            include_code = link_cli.recall(target, "local personal memory", include_archived=True, json_output=True)
        include_payload = json.loads(out_json.getvalue())
        self.assertEqual(include_code, 0)
        self.assertTrue(include_payload["include_archived"])
        self.assertEqual(include_payload["memories"][0]["status"], "archived")

        with redirect_stdout(StringIO()):
            restore_code = link_cli.restore_memory(target, "Prefer local personal memory")
        restored_text = memory_path.read_text(encoding="utf-8")
        self.assertEqual(restore_code, 0)
        self.assertIn("status: active", restored_text)
        self.assertIn("restored_at:", restored_text)
        self.assertNotIn("archived_at:", restored_text)
        self.assertNotIn("archive_reason:", restored_text)

        out = StringIO()
        with redirect_stdout(out):
            link_cli.recall(target, "local personal memory")
        self.assertIn("Prefer local personal memory", out.getvalue())

    def test_forget_memory_requires_confirmation_and_deletes_page(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        memory_path = target / "wiki/memories/prefer-local-personal-memory.md"

        denied_out = StringIO()
        with redirect_stdout(denied_out):
            denied_code = link_cli.forget_memory(target, "prefer-local-personal-memory", json_output=True)
        denied = json.loads(denied_out.getvalue())
        self.assertEqual(denied_code, 1)
        self.assertFalse(denied["forgotten"])
        self.assertTrue(denied["confirmation_required"])
        self.assertTrue(memory_path.exists())

        forget_out = StringIO()
        with redirect_stdout(forget_out):
            forget_code = link_cli.forget_memory(target, "prefer-local-personal-memory", confirm=True, json_output=True)
        forgotten = json.loads(forget_out.getvalue())
        log_text = (target / "wiki/log.md").read_text(encoding="utf-8")
        index_text = (target / "wiki/index.md").read_text(encoding="utf-8")

        self.assertEqual(forget_code, 0)
        self.assertTrue(forgotten["forgotten"])
        self.assertTrue(forgotten["backlinks_rebuilt"])
        self.assertFalse(memory_path.exists())
        self.assertNotIn("[[prefer-local-personal-memory]]", index_text)
        self.assertIn("forget-memory", log_text)
        self.assertNotIn("local personal memory for agents", log_text)

    def test_archive_memory_json_not_found(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-memory-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)

        err = StringIO()
        with redirect_stdout(StringIO()), redirect_stderr(err):
            code = link_cli.archive_memory(target, "missing-memory", json_output=True)

        self.assertEqual(code, 1)
        self.assertIn("memory not found", err.getvalue())

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
        self.assertIn("python3 link.py init", out.getvalue())

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

    def test_rebuild_index_repairs_missing_catalog_entries(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-index-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        index_path = target / "wiki/index.md"
        index_path.write_text("# Broken Index\n", encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            rebuild_code = link_cli.rebuild_index(target)
            backlinks_code = link_cli.rebuild_backlinks(target)
            doctor_code = link_cli.doctor(target)

        index_text = index_path.read_text(encoding="utf-8")
        self.assertEqual(rebuild_code, 0)
        self.assertEqual(backlinks_code, 0)
        self.assertEqual(doctor_code, 0)
        self.assertIn("Rebuilt", out.getvalue())
        self.assertIn("rebuild-backlinks before validation", out.getvalue())
        self.assertIn("[[agent-memory]]", index_text)
        self.assertIn("[[prefer-local-personal-memory]]", index_text)

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

    def test_doctor_fix_repairs_index_drift(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-doctor-test-"))
        target = tmp / "demo"
        create_demo_quiet(target)
        index_path = target / "wiki/index.md"
        index_path.write_text("# Broken Index\n", encoding="utf-8")

        out = StringIO()
        with redirect_stdout(out):
            code = link_cli.doctor(target, fix=True)

        index_text = index_path.read_text(encoding="utf-8")
        backlinks = json.loads((target / "wiki/_backlinks.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertIn("rebuilt wiki/index.md", out.getvalue())
        self.assertIn("rebuilt wiki/_backlinks.json", out.getvalue())
        self.assertIn("[[agent-memory]]", index_text)
        self.assertIn("agent-memory", backlinks["backlinks"])

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
