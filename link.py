#!/usr/bin/env python3
"""Small Link command runner.

Usage:
  python link.py init [target]
  python link.py serve [target]
  python link.py demo [target]
  python link.py prompts [target]
  python link.py status [target]
  python link.py backup [target]
  python link.py doctor [target]
  python link.py migrate [target]
  python link.py validate [target]
  python link.py ingest-status [target]
  python link.py remember "memory text" [target]
  python link.py propose-memories <file-or-text> [target]
  python link.py capture-inbox [target]
  python link.py update-memory <name-or-title> "new memory text" [target]
  python link.py query "task or question" [target]
  python link.py graph-summary ["topic"] [target]
  python link.py benchmark ["query"] [target]
  python link.py brief ["task or question"] [target]
  python link.py recall "query" [target]
  python link.py profile [target]
  python link.py memory-audit [target]
  python link.py archive-memory <name-or-title> [target]
  python link.py restore-memory <name-or-title> [target]
  python link.py forget-memory <name-or-title> [target] --confirm
  python link.py memory-inbox [target]
  python link.py review-memory <name-or-title> [target]
  python link.py explain-memory <name-or-title> [target]
  python link.py rebuild-index [target]
  python link.py rebuild-backlinks [target]
  python link.py verify-mcp [target]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parent
DEFAULT_DEMO_DIR = "link-demo"
SECRET_NAME_PATTERNS = (
    ".env",
    ".env.*",
    ".envrc",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "*.token",
    ".mcpregistry_*",
    "*.key",
    "*.pem",
    "*.p8",
    "*.p12",
    "*.jks",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "service-account*.json",
)
SKIP_SCAN_DIRS = {
    ".git",
    ".link-backups",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "dist",
    "build",
    ".venv",
    "venv",
    "node_modules",
}
SKIP_SCAN_SUFFIXES = {
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".pyc",
    ".tar",
    ".webp",
    ".whl",
    ".zip",
}
_BUNDLED_CORE = ROOT / "mcp_package"
if (_BUNDLED_CORE / "link_core").exists():
    sys.path.insert(0, str(_BUNDLED_CORE))

from link_core.memory import (
    add_capture_review_to_brief as _core_add_capture_review_to_brief,
    count_values as _core_count_values,
    default_project_for_target as _core_default_project_for_target,
    forget_memory_page as _core_forget_memory_page,
    mark_memory_reviewed as _core_mark_memory_reviewed,
    memory_brief as _core_memory_brief,
    memory_explanation as _core_memory_explanation,
    memory_inbox as _core_memory_inbox,
    memory_profile as _core_memory_profile,
    memory_audit_report as _core_memory_audit_report,
    memory_audit_next_actions as _core_memory_audit_next_actions,
    memory_records as _core_memory_records,
    memory_review_issues as _core_memory_review_issues,
    propose_memories_from_text as _core_propose_memories_from_text,
    recall_memories as _core_recall_memories,
    recent_memories as _core_recent_memories,
    resolve_memory_page as _core_resolve_memory_page,
    set_memory_status as _core_set_memory_status,
    top_tags as _core_top_tags,
    update_memory_page as _core_update_memory_page,
    write_memory_page as _core_write_memory_page,
)
from link_core.backup import (
    BackupError as _CoreBackupError,
    create_backup as _core_create_backup,
    list_backups as _core_list_backups,
)
from link_core.benchmark import (
    build_benchmark_payload as _core_build_benchmark_payload,
    render_benchmark_text as _core_render_benchmark_text,
)
from link_core.demo import (
    DemoError as _CoreDemoError,
    copy_runtime_files as _core_copy_runtime_files,
    create_demo_workspace as _core_create_demo_workspace,
)
from link_core.doctor import (
    apply_doctor_fixes as _core_apply_doctor_fixes,
    build_doctor_report as _core_build_doctor_report,
    required_paths as _core_required_paths,
    render_doctor_report as _core_render_doctor_report,
)
from link_core.cli_parser import (
    build_cli_parser as _core_build_cli_parser,
)
from link_core.cli_admin import (
    render_backup_created_text as _core_render_backup_created_text,
    render_backup_list_text as _core_render_backup_list_text,
    render_migrate_text as _core_render_migrate_text,
    render_rebuild_backlinks_text as _core_render_rebuild_backlinks_text,
    render_rebuild_index_text as _core_render_rebuild_index_text,
    render_status_text as _core_render_status_text,
    render_validate_text as _core_render_validate_text,
)
from link_core.cli_memory import (
    render_brief_text as _core_render_brief_text,
    render_explain_memory_text as _core_render_explain_memory_text,
    render_forget_memory_text as _core_render_forget_memory_text,
    render_memory_audit_text as _core_render_memory_audit_text,
    render_memory_inbox_text as _core_render_memory_inbox_text,
    render_memory_status_text as _core_render_memory_status_text,
    render_profile_text as _core_render_profile_text,
    render_recall_text as _core_render_recall_text,
    render_review_memory_text as _core_render_review_memory_text,
    render_remember_text as _core_render_remember_text,
    render_update_memory_text as _core_render_update_memory_text,
)
from link_core.capture import (
    capture_filename as _core_capture_filename,
    capture_inbox as _core_capture_inbox,
    capture_notes_from_markdown as _core_capture_notes_from_markdown,
    capture_records as _core_capture_records,
    capture_review_summary as _core_capture_review_summary,
    capture_title as _core_capture_title,
    cli_capture_commands as _core_cli_capture_commands,
    render_accept_capture_text as _core_render_accept_capture_text,
    render_capture_session_text as _core_render_capture_session_text,
    render_capture_inbox_text as _core_render_capture_inbox_text,
    render_delete_capture_text as _core_render_delete_capture_text,
    render_redact_capture_text as _core_render_redact_capture_text,
    resolve_capture_file as _core_resolve_capture_file,
)
from link_core.files import (
    atomic_write_json as _core_atomic_write_json,
    atomic_write_text as _core_atomic_write_text,
)
from link_core.frontmatter import (
    frontmatter_string as _frontmatter_string,
)
from link_core.ingest import (
    collect_ingest_status as _core_collect_ingest_status,
    render_ingest_status_text as _core_render_ingest_status_text,
)
from link_core.log import (
    append_log as _core_append_log,
    utc_timestamp as _core_utc_timestamp,
)
from link_core.mcp_verify import (
    build_mcp_verify_status as _core_build_mcp_verify_status,
    check_link_mcp_import as _core_check_link_mcp_import,
    display_command as _core_display_command,
    render_mcp_verify_text as _core_render_mcp_verify_text,
)
from link_core.schema import (
    migrate_wiki as _core_migrate_wiki,
    schema_status as _core_schema_status,
)
from link_core.security import (
    clean_text_input as _clean_text_input,
    redact_secret_values as _redact_secret_values,
    secret_value_warnings as _secret_value_warnings,
)
from link_core.query import (
    query_link as _core_query_link,
)
from link_core.cli_query import (
    render_graph_summary_text as _core_render_graph_summary_text,
    render_query_text as _core_render_query_text,
)
from link_core.cli_runtime import (
    render_demo_text as _core_render_demo_text,
    render_init_text as _core_render_init_text,
    render_starter_prompts_text as _core_render_starter_prompts_text,
)
from link_core.prompts import (
    starter_prompt_payload as _core_starter_prompt_payload,
)
from link_core.validation import (
    validate_wiki as _core_validate_wiki,
)
from link_core.version import (
    LINK_VERSION,
)
from link_core.status import (
    link_status as _core_link_status,
)
from link_core.wiki import (
    build_backlinks as _core_build_backlinks,
    build_wiki_cache as _core_build_wiki_cache,
    close_wiki_cache as _core_close_wiki_cache,
    graph_summary as _core_graph_summary,
    rebuild_index as _core_rebuild_index,
)
del _BUNDLED_CORE



def _build_backlinks(wiki_dir: Path) -> dict[str, dict[str, list[str]]]:
    return _core_build_backlinks(wiki_dir, body_only=False)


def _wiki_pages(wiki_dir: Path) -> list[Path]:
    return sorted(
        md for md in wiki_dir.rglob("*.md")
        if not md.name.startswith(".")
    )


def _resolve_wiki_dir(target: Path) -> Path:
    target = target.expanduser().resolve()
    if target.name == "wiki" and (target / "index.md").exists():
        return target
    return target / "wiki"


def _resolve_link_root(target: Path) -> Path:
    target = target.expanduser().resolve()
    if target.name == "wiki" and (target / "index.md").exists():
        return target.parent
    return target


def _default_project(target: Path) -> str:
    return _core_default_project_for_target(target)


def _utc_timestamp() -> str:
    return _core_utc_timestamp()


def _memory_records(wiki_dir: Path) -> list[dict[str, object]]:
    return _core_memory_records(wiki_dir)


def _memory_review_issues(record: dict[str, object]) -> list[dict[str, str]]:
    return _core_memory_review_issues(record, review_command="review-memory")


def _memory_inbox(
    wiki_dir: Path,
    limit: int = 20,
    include_archived: bool = False,
    project: str | None = None,
) -> dict[str, object]:
    return _core_memory_inbox(
        _memory_records(wiki_dir),
        limit=limit,
        include_archived=include_archived,
        review_command="review-memory",
        project=project,
    )


def _memory_explanation(wiki_dir: Path, identifier: str) -> dict[str, object]:
    return _core_memory_explanation(
        wiki_dir,
        identifier,
        records=_memory_records(wiki_dir),
        review_command="review-memory",
        backlinks_body_only=False,
    )


def _count_values(records: list[dict[str, object]], field: str) -> dict[str, int]:
    return _core_count_values(records, field)


def _top_tags(records: list[dict[str, object]], limit: int = 12) -> list[dict[str, object]]:
    return _core_top_tags(records, limit=limit)


def _recent_memories(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return _core_recent_memories(records)


def _memory_profile(wiki_dir: Path, limit: int = 10, project: str | None = None) -> dict[str, object]:
    return _core_memory_profile(
        _memory_records(wiki_dir),
        limit=limit,
        review_command="review-memory",
        project=project,
    )


def _memory_brief(wiki_dir: Path, query: str = "", limit: int = 6, project: str | None = None) -> dict[str, object]:
    return _core_memory_brief(
        _memory_records(wiki_dir),
        query=query,
        limit=limit,
        review_command="review-memory",
        project=project,
    )


def _query_link(wiki_dir: Path, query: str, budget: str = "medium", project: str | None = None) -> dict[str, object]:
    cache = _core_build_wiki_cache(wiki_dir)
    try:
        return _core_query_link(
            wiki_dir,
            query,
            cache,
            _memory_records(wiki_dir),
            budget=budget,
            project=project,
            review_command="review-memory",
        )
    finally:
        _core_close_wiki_cache(cache)


def _recall_memories(
    wiki_dir: Path,
    query: str,
    limit: int = 10,
    include_archived: bool = False,
    project: str | None = None,
) -> list[dict[str, object]]:
    return _core_recall_memories(
        _memory_records(wiki_dir),
        query,
        limit=limit,
        include_archived=include_archived,
        project=project,
    )


def _propose_memories_from_text(
    wiki_dir: Path,
    text: str,
    source: str = "inline",
    limit: int = 10,
    project: str | None = None,
) -> dict[str, object]:
    return _core_propose_memories_from_text(
        text,
        _memory_records(wiki_dir),
        source=source,
        limit=limit,
        writes_memory=False,
        project=project,
    )


def _append_log(wiki_dir: Path, timestamp: str, operation: str, description: str, lines: list[str]) -> None:
    _core_append_log(wiki_dir, timestamp, operation, description, lines)


def _resolve_memory_page(wiki_dir: Path, identifier: str) -> tuple[Path | None, dict[str, object] | None, str | None]:
    return _core_resolve_memory_page(wiki_dir, identifier, records=_memory_records(wiki_dir))


def _memory_runtime(target: Path) -> tuple[Path, list[dict[str, object]]]:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        raise FileNotFoundError(f"missing wiki directory: {wiki_dir}")
    return wiki_dir, _memory_records(wiki_dir)


def _log_writer_for(wiki_dir: Path) -> Callable[[str, str, str, list[str]], None]:
    return lambda ts, operation, description, lines: _append_log(
        wiki_dir,
        ts,
        operation,
        description,
        lines,
    )


def _rebuild_memory_backlinks(wiki_dir: Path) -> bool:
    try:
        backlinks = _build_backlinks(wiki_dir)
    except OSError as exc:
        print(f"Could not rebuild backlinks: {exc}", file=sys.stderr)
        return False
    _core_atomic_write_json(wiki_dir / "_backlinks.json", backlinks)
    return True


def _memory_mutation_options(
    wiki_dir: Path,
    records: list[dict[str, object]],
    timestamp: str | None,
    project: str | None = None,
) -> dict[str, object]:
    return {
        "timestamp": timestamp or _utc_timestamp(),
        "records": records,
        "project": project,
        "log_writer": _log_writer_for(wiki_dir),
        "rebuild_backlinks": lambda: _rebuild_memory_backlinks(wiki_dir),
    }


def _required_memory_text(text: str, message: str) -> str:
    clean_text = text.strip()
    if not clean_text:
        raise ValueError(message)
    return clean_text


def _set_memory_status(
    target: Path,
    identifier: str,
    status: str,
    reason: str | None = None,
    timestamp: str | None = None,
) -> dict[str, object]:
    wiki_dir, records = _memory_runtime(target)
    return _core_set_memory_status(
        wiki_dir,
        identifier,
        status,
        reason=reason,
        timestamp=timestamp or _utc_timestamp(),
        records=records,
        log_writer=_log_writer_for(wiki_dir),
    )


def _mark_memory_reviewed(
    target: Path,
    identifier: str,
    note: str | None = None,
    timestamp: str | None = None,
) -> dict[str, object]:
    wiki_dir, records = _memory_runtime(target)
    return _core_mark_memory_reviewed(
        wiki_dir,
        identifier,
        note=note,
        timestamp=timestamp or _utc_timestamp(),
        records=records,
        review_command="review-memory",
        log_writer=_log_writer_for(wiki_dir),
    )


def _update_memory_page(
    target: Path,
    identifier: str,
    text: str,
    source: str = "manual",
    timestamp: str | None = None,
    allow_conflict: bool = False,
    project: str | None = None,
) -> dict[str, object]:
    wiki_dir, records = _memory_runtime(target)
    clean_text = _required_memory_text(text, "memory update text required")
    options = _memory_mutation_options(wiki_dir, records, timestamp, project)

    return _core_update_memory_page(
        wiki_dir, identifier, clean_text, source=source,
        review_command="review-memory", allow_conflict=allow_conflict,
        **options,
    )


def _write_memory_page(
    target: Path, text: str, title: str | None = None,
    memory_type: str = "note", scope: str = "user",
    tags: str | None = None, source: str = "manual",
    timestamp: str | None = None, allow_duplicate: bool = False,
    allow_conflict: bool = False, project: str | None = None,
) -> dict[str, object]:
    wiki_dir, records = _memory_runtime(target)
    clean_text = _required_memory_text(text, "memory text required")
    options = _memory_mutation_options(wiki_dir, records, timestamp, project)

    return _core_write_memory_page(
        wiki_dir, clean_text, title=title, memory_type=memory_type,
        scope=scope, tags=tags, source=source,
        allow_duplicate=allow_duplicate, allow_conflict=allow_conflict,
        **options,
    )


def _collect_ingest_status(target: Path) -> dict[str, object]:
    return _core_collect_ingest_status(target, skip_dirs=SKIP_SCAN_DIRS)


def _required_paths(target: Path) -> list[Path]:
    return _core_required_paths(target)


def _apply_doctor_fixes(target: Path) -> list[str]:
    return _core_apply_doctor_fixes(target)


def doctor(target: Path, fix: bool = False) -> int:
    report = _core_build_doctor_report(
        target,
        fix=fix,
        skip_dirs=SKIP_SCAN_DIRS,
        secret_name_patterns=SECRET_NAME_PATTERNS,
        skip_suffixes=SKIP_SCAN_SUFFIXES,
    )
    print(_core_render_doctor_report(report))
    return 0 if report.healthy else 1


def validate(target: Path, strict: bool = False, json_output: bool = False) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    payload = _core_validate_wiki(wiki_dir, strict=strict)
    if json_output:
        print(json.dumps(payload, indent=2))
        return 0 if payload["passed"] else 1

    code, text = _core_render_validate_text(payload, wiki_dir=wiki_dir)
    print(text)
    return code


def migrate(target: Path, json_output: bool = False) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    payload = _core_migrate_wiki(wiki_dir)
    if json_output:
        print(json.dumps(payload, indent=2))
        return 0 if payload["ok"] else 1

    code, text = _core_render_migrate_text(payload, wiki_dir=wiki_dir)
    print(text)
    return code


def status(target: Path, include_validation: bool = False, json_output: bool = False) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    payload = _core_link_status(wiki_dir, version=LINK_VERSION, include_validation=include_validation)
    if json_output:
        print(json.dumps(payload, indent=2))
        return 0 if payload["ready"] else 1

    code, text = _core_render_status_text(payload, wiki_dir=wiki_dir, version=LINK_VERSION)
    print(text)
    return code


def backup(
    target: Path,
    *,
    label: str = "manual",
    include_raw: bool = False,
    list_only: bool = False,
    json_output: bool = False,
) -> int:
    target = _resolve_link_root(target)
    if list_only:
        payload = _core_list_backups(target)
        if json_output:
            print(json.dumps(payload, indent=2))
            return 0
        code, text = _core_render_backup_list_text(payload)
        print(text)
        return code

    try:
        payload = _core_create_backup(target, label=label, include_raw=include_raw)
    except (FileNotFoundError, _CoreBackupError) as exc:
        if json_output:
            print(json.dumps({"created": False, "error": str(exc)}, indent=2))
        else:
            print(str(exc), file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(payload, indent=2))
        return 0

    code, text = _core_render_backup_created_text(payload, include_raw=include_raw)
    print(text)
    return code


def ingest_status(target: Path, json_output: bool = False) -> int:
    target = target.expanduser().resolve()
    status = _collect_ingest_status(target)

    if json_output:
        print(json.dumps(status, indent=2))
        return 0 if status["has_raw_dir"] and status["has_wiki_dir"] else 1

    print(_core_render_ingest_status_text(str(target), status))
    return 0 if status["has_raw_dir"] and status["has_wiki_dir"] else 1


def rebuild_backlinks(target: Path) -> int:
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    try:
        backlinks = _build_backlinks(wiki_dir)
    except OSError as exc:
        print(f"Could not rebuild backlinks: {exc}", file=sys.stderr)
        return 1
    out_path = wiki_dir / "_backlinks.json"
    _core_atomic_write_json(out_path, backlinks)
    page_count = len(_wiki_pages(wiki_dir))
    edge_count = sum(len(targets) for targets in backlinks["forward"].values())
    code, text = _core_render_rebuild_backlinks_text(
        out_path=out_path,
        page_count=page_count,
        edge_count=edge_count,
    )
    print(text)
    return code


def rebuild_index(target: Path) -> int:
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    try:
        result = _core_rebuild_index(wiki_dir)
    except OSError as exc:
        print(f"Could not rebuild index: {exc}", file=sys.stderr)
        return 1
    code, text = _core_render_rebuild_index_text(result, index_path=wiki_dir / "index.md")
    print(text)
    return code


def remember(
    target: Path,
    text: str,
    title: str | None = None,
    memory_type: str = "note",
    scope: str = "user",
    tags: str | None = None,
    source: str = "manual",
    allow_duplicate: bool = False,
    allow_conflict: bool = False,
    project: str | None = None,
    json_output: bool = False,
) -> int:
    if not text or not text.strip():
        print("Memory text is required", file=sys.stderr)
        return 1
    try:
        result = _write_memory_page(
            target,
            text,
            title=title,
            memory_type=memory_type,
            scope=scope,
            tags=tags,
            source=source,
            allow_duplicate=allow_duplicate,
            allow_conflict=allow_conflict,
            project=project or _default_project(target),
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not remember: {exc}", file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(result, indent=2))
        return 0

    code, text = _core_render_remember_text(result)
    print(text)
    return code


def _read_proposal_input(target: Path, value: str) -> tuple[str, str]:
    raw = value.strip()
    candidates = [Path(raw).expanduser()]
    target_path = target.expanduser()
    if not Path(raw).is_absolute():
        candidates.append((target_path / raw).expanduser())
    for candidate in candidates:
        try:
            is_file = candidate.exists() and candidate.is_file()
        except OSError:
            is_file = False
        if is_file:
            return candidate.read_text(encoding="utf-8", errors="replace"), str(candidate)
    return value, "inline"


def propose_memories(
    target: Path,
    source_input: str,
    limit: int = 10,
    project: str | None = None,
    json_output: bool = False,
) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    text, source = _read_proposal_input(target, source_input)
    if not text.strip():
        print("Memory proposal input is required", file=sys.stderr)
        return 1
    result = _propose_memories_from_text(
        wiki_dir,
        text,
        source=source,
        limit=max(1, min(limit, 20)),
        project=project or _default_project(target),
    )

    if json_output:
        print(json.dumps(result, indent=2))
        return 0

    print("Memory proposals")
    print(f"Source: {result['source']}")
    if result.get("project"):
        print(f"Project: {result['project']}")
    print(f"Count: {result['count']}")
    if not result["proposals"]:
        print("No durable memory candidates found.")
        return 0
    for index, proposal in enumerate(result["proposals"], start=1):
        print("")
        print(f"{index}. {proposal['title']} [{proposal['confidence']}]")
        print(f"   Type: {proposal['memory_type']} | Scope: {proposal['scope']}")
        if proposal.get("project"):
            print(f"   Project: {proposal['project']}")
        print(f"   Action: {proposal['suggested_action']}")
        print(f"   Memory: {proposal['memory']}")
        primary_action = proposal.get("primary_action") if isinstance(proposal.get("primary_action"), dict) else {}
        if primary_action.get("command"):
            print(f"   Command: {primary_action['command']}")
        if proposal["duplicate_candidates"]:
            first = proposal["duplicate_candidates"][0]
            print(f"   Duplicate candidate: {first['title']} ({first['path']})")
    print("")
    print("Next:")
    print("  Use remember for new memories, or update-memory for duplicate candidates.")
    return 0


def capture_session(
    target: Path,
    source_input: str,
    title: str | None = None,
    limit: int = 10,
    project: str | None = None,
    json_output: bool = False,
) -> int:
    target = target.expanduser().resolve()
    root = _resolve_link_root(target)
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1

    text, source = _read_proposal_input(root, source_input)
    if not text.strip():
        print("Session capture input is required", file=sys.stderr)
        return 1

    timestamp = _utc_timestamp()
    project_name = project or _default_project(root)
    capture_title = _core_capture_title(text, source, title, default_source="inline", path_source=True)
    secret_warnings = _secret_value_warnings(text)
    capture_dir = root / "raw" / "memory-captures"
    capture_dir.mkdir(parents=True, exist_ok=True)
    capture_path = _core_capture_filename(timestamp, capture_title, capture_dir)
    project_line = f'project: "{_frontmatter_string(project_name)}"\n' if project_name else ""
    _core_atomic_write_text(
        capture_path,
        f"""---
title: "{_frontmatter_string(capture_title)}"
source_type: conversation
date_captured: "{timestamp}"
{project_line}---

# {capture_title}

Captured locally for Link memory review. This raw note is proposal-only until the user approves durable memories.

## Source Input

{source}

## Notes

{text.strip()}
""",
    )
    rel_path = capture_path.relative_to(root).as_posix()
    result = _propose_memories_from_text(
        wiki_dir,
        text,
        source=rel_path,
        limit=max(1, min(limit, 20)),
        project=project_name,
    )
    payload = {
        "captured": True,
        "path": rel_path,
        "source_input": source,
        "title": capture_title,
        "project": project_name,
        "secret_warnings": secret_warnings,
        "proposals": result,
    }
    _append_log(
        wiki_dir,
        timestamp,
        "capture-session",
        f"Captured proposal-only session notes at {rel_path}",
        [
            f"Source input: {source}",
            f"Project: {project_name or 'none'}",
            f"Secret warnings: {', '.join(secret_warnings) if secret_warnings else 'none'}",
            f"Proposals: {result['count']}",
        ],
    )

    if json_output:
        print(json.dumps(payload, indent=2))
        return 0

    print(_core_render_capture_session_text(payload))
    return 0


def _resolve_capture_file(root: Path, capture: str) -> Path | None:
    return _core_resolve_capture_file(root, capture)


def _capture_records(target: Path, limit: int = 20, project: str | None = None) -> list[dict[str, object]]:
    root = _resolve_link_root(target)
    return _core_capture_records(
        root,
        limit=limit,
        project=project,
        commands_for=_core_cli_capture_commands,
    )


def capture_inbox(
    target: Path,
    limit: int = 20,
    project: str | None = None,
    json_output: bool = False,
) -> int:
    target = target.expanduser().resolve()
    root = _resolve_link_root(target)
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    payload = _core_capture_inbox(
        root,
        limit=limit,
        project=project,
        commands_for=_core_cli_capture_commands,
    )
    if json_output:
        print(json.dumps(payload, indent=2))
        return 0

    print(_core_render_capture_inbox_text(payload))
    return 0


def _capture_review_summary(target: Path, project: str | None = None, limit: int = 3) -> dict[str, object]:
    root = _resolve_link_root(target)
    summary = _core_capture_review_summary(
        root,
        limit=limit,
        project=project,
        commands_for=_core_cli_capture_commands,
    )
    summary["next_action"] = f'python3 link.py capture-inbox "{root}"'
    if summary["project"]:
        summary["next_action"] = f'python3 link.py capture-inbox "{root}" --project "{summary["project"]}"'
    return summary


def accept_capture(
    target: Path,
    capture: str,
    index: int = 1,
    title: str | None = None,
    memory_type: str | None = None,
    scope: str | None = None,
    tags: str | None = None,
    project: str | None = None,
    allow_duplicate: bool = False,
    allow_conflict: bool = False,
    json_output: bool = False,
) -> int:
    target = target.expanduser().resolve()
    root = _resolve_link_root(target)
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    capture_path = _resolve_capture_file(root, capture)
    if capture_path is None:
        print(f"Capture not found under {root}: {capture}", file=sys.stderr)
        return 1
    if index < 1:
        print("Proposal index must be 1 or greater", file=sys.stderr)
        return 1

    raw_text = capture_path.read_text(encoding="utf-8", errors="replace")
    meta, notes = _core_capture_notes_from_markdown(raw_text)
    if not notes:
        print(f"Capture has no notes: {capture_path}", file=sys.stderr)
        return 1

    rel_path = capture_path.relative_to(root).as_posix()
    project_name = project or str(meta.get("project") or "") or _default_project(root)
    proposals = _propose_memories_from_text(
        wiki_dir,
        notes,
        source=rel_path,
        limit=max(1, min(max(index, 10), 50)),
        project=project_name,
    )
    if index > len(proposals["proposals"]):
        print(f"Capture has {len(proposals['proposals'])} proposal(s); index {index} is unavailable", file=sys.stderr)
        return 1
    proposal = proposals["proposals"][index - 1]
    chosen_scope = scope or str(proposal["scope"])
    chosen_project = project_name if chosen_scope == "project" else ""
    result = _write_memory_page(
        target,
        str(proposal["memory"]),
        title=title or str(proposal["title"]),
        memory_type=memory_type or str(proposal["memory_type"]),
        scope=chosen_scope,
        tags=tags,
        source=rel_path,
        allow_duplicate=allow_duplicate,
        allow_conflict=allow_conflict,
        project=chosen_project,
    )
    payload = {
        "accepted": bool(result.get("created")),
        "capture": rel_path,
        "proposal_index": index,
        "project": str(result.get("project") or proposal.get("project") or ""),
        "proposal": proposal,
        "result": result,
    }
    if result.get("created"):
        _append_log(
            wiki_dir,
            _utc_timestamp(),
            "accept-capture",
            f"Accepted proposal {index} from {rel_path}",
            [
                f"Memory: {result['path']}",
                f"Project: {result.get('project') or 'none'}",
            ],
        )

    if json_output:
        print(json.dumps(payload, indent=2))
        return 0 if payload["accepted"] else 1

    code, text = _core_render_accept_capture_text(payload)
    print(text)
    return code


def redact_capture(
    target: Path,
    capture: str,
    replacement: str = "[redacted-secret]",
    json_output: bool = False,
) -> int:
    target = target.expanduser().resolve()
    root = _resolve_link_root(target)
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    capture_path = _resolve_capture_file(root, capture)
    if capture_path is None:
        print(f"Capture not found under {root}: {capture}", file=sys.stderr)
        return 1

    original = capture_path.read_text(encoding="utf-8", errors="replace")
    redacted, labels, replacement_count = _redact_secret_values(original, replacement=replacement)
    rel_path = capture_path.relative_to(root).as_posix()
    if replacement_count:
        _core_atomic_write_text(capture_path, redacted)
        _append_log(
            wiki_dir,
            _utc_timestamp(),
            "redact-capture",
            f"Redacted secret-looking values from {rel_path}",
            [
                f"Labels: {', '.join(labels)}",
                f"Replacement count: {replacement_count}",
            ],
        )
    payload = {
        "redacted": bool(replacement_count),
        "path": rel_path,
        "labels": labels,
        "replacement_count": replacement_count,
    }
    if json_output:
        print(json.dumps(payload, indent=2))
        return 0

    print(_core_render_redact_capture_text(payload))
    return 0


def delete_capture(
    target: Path,
    capture: str,
    confirm: bool = False,
    json_output: bool = False,
) -> int:
    target = target.expanduser().resolve()
    root = _resolve_link_root(target)
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    capture_path = _resolve_capture_file(root, capture)
    if capture_path is None:
        print(f"Capture not found under {root}: {capture}", file=sys.stderr)
        return 1
    rel_path = capture_path.relative_to(root).as_posix()
    payload = {
        "deleted": False,
        "path": rel_path,
        "confirmation_required": not confirm,
    }
    if not confirm:
        if json_output:
            print(json.dumps(payload, indent=2))
        else:
            _, text = _core_render_delete_capture_text(payload)
            print(text)
        return 1

    capture_path.unlink()
    _append_log(
        wiki_dir,
        _utc_timestamp(),
        "delete-capture",
        f"Deleted raw capture {rel_path}",
        ["Deleted file only; capture contents were not logged."],
    )
    payload["deleted"] = True
    payload["confirmation_required"] = False
    if json_output:
        print(json.dumps(payload, indent=2))
        return 0
    code, text = _core_render_delete_capture_text(payload)
    print(text)
    return code


def update_memory(
    target: Path,
    identifier: str,
    text: str,
    source: str = "manual",
    allow_conflict: bool = False,
    project: str | None = None,
    json_output: bool = False,
) -> int:
    if not text or not text.strip():
        print("Memory update text is required", file=sys.stderr)
        return 1
    try:
        result = _update_memory_page(
            target,
            identifier,
            text,
            source=source,
            allow_conflict=allow_conflict,
            project=project or _default_project(target),
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not update memory: {exc}", file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(result, indent=2))
        return 0

    code, text = _core_render_update_memory_text(result)
    print(text)
    return code


def recall(
    target: Path,
    query: str,
    limit: int = 10,
    json_output: bool = False,
    include_archived: bool = False,
    project: str | None = None,
) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    project_name = project or _default_project(target)
    results = _recall_memories(
        wiki_dir,
        query,
        limit=limit,
        include_archived=include_archived,
        project=project_name,
    )

    if json_output:
        print(json.dumps({
            "query": query,
            "count": len(results),
            "include_archived": include_archived,
            "project": project_name,
            "memories": results,
        }, indent=2))
        return 0

    code, text = _core_render_recall_text(
        query=query,
        results=results,
        include_archived=include_archived,
        project=project_name,
    )
    print(text)
    return code


def archive_memory(target: Path, identifier: str, reason: str | None = None, json_output: bool = False) -> int:
    try:
        result = _set_memory_status(target, identifier, "archived", reason=reason)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not archive memory: {exc}", file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(result, indent=2))
        return 0

    code, text = _core_render_memory_status_text(result, action="archive")
    print(text)
    return code


def restore_memory(target: Path, identifier: str, json_output: bool = False) -> int:
    try:
        result = _set_memory_status(target, identifier, "active")
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not restore memory: {exc}", file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(result, indent=2))
        return 0

    code, text = _core_render_memory_status_text(result, action="restore")
    print(text)
    return code


def forget_memory(target: Path, identifier: str, confirm: bool = False, json_output: bool = False) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1

    def rebuild_memory_backlinks() -> bool:
        backlinks = _build_backlinks(wiki_dir)
        _core_atomic_write_json(wiki_dir / "_backlinks.json", backlinks)
        return True

    result = _core_forget_memory_page(
        wiki_dir,
        identifier,
        confirm=confirm,
        records=_memory_records(wiki_dir),
        timestamp=_utc_timestamp(),
        log_writer=lambda ts, operation, description, lines: _append_log(
            wiki_dir,
            ts,
            operation,
            description,
            lines,
        ),
        rebuild_backlinks=rebuild_memory_backlinks,
    )
    if json_output:
        print(json.dumps(result, indent=2))
        return 0 if result.get("forgotten") else 1

    code, text = _core_render_forget_memory_text(result, identifier=identifier)
    if not result.get("found"):
        print(text, file=sys.stderr)
    else:
        print(text)
    return code


def memory_inbox(
    target: Path,
    limit: int = 20,
    include_archived: bool = False,
    project: str | None = None,
    json_output: bool = False,
) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    inbox = _memory_inbox(wiki_dir, limit=limit, include_archived=include_archived, project=project)

    if json_output:
        print(json.dumps(inbox, indent=2))
        return 0

    code, text = _core_render_memory_inbox_text(inbox, target=target, include_archived=include_archived)
    print(text)
    return code


def review_memory(target: Path, identifier: str, note: str | None = None, json_output: bool = False) -> int:
    try:
        result = _mark_memory_reviewed(target, identifier, note=note)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not review memory: {exc}", file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(result, indent=2))
        return 0

    code, text = _core_render_review_memory_text(result)
    print(text)
    return code


def explain_memory(target: Path, identifier: str, json_output: bool = False) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    try:
        explanation = _memory_explanation(wiki_dir, identifier)
    except ValueError as exc:
        print(f"Could not explain memory: {exc}", file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(explanation, indent=2))
        return 0

    code, text = _core_render_explain_memory_text(explanation)
    print(text)
    return code


def query(
    target: Path,
    query_text: str,
    budget: str = "medium",
    project: str | None = None,
    json_output: bool = False,
) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    query_text = _clean_text_input(query_text, max_len=500)
    project_name = project or _default_project(target)
    payload = _query_link(wiki_dir, query_text, budget=budget, project=project_name)
    if json_output:
        print(json.dumps(payload, indent=2))
        return 0
    code, text = _core_render_query_text(payload, query_text=query_text)
    print(text)
    return code


def graph_summary(
    target: Path,
    topic: str = "",
    limit: int = 40,
    depth: int = 1,
    max_edges: int = 120,
    json_output: bool = False,
) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    topic = _clean_text_input(topic, max_len=500)
    cache = _core_build_wiki_cache(wiki_dir)
    payload = _core_graph_summary(
        cache,
        topic=topic,
        limit=limit,
        depth=depth,
        max_edges=max_edges,
    )
    _core_close_wiki_cache(cache)
    if json_output:
        print(json.dumps(payload, indent=2))
        return 0

    code, text = _core_render_graph_summary_text(payload, topic=topic)
    print(text)
    return code


def benchmark(
    target: Path,
    query_text: str = "agent memory",
    budget: str = "small",
    project: str | None = None,
    json_output: bool = False,
) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    query_text = _clean_text_input(query_text, max_len=500)
    project_name = project or _default_project(target)
    payload = _core_build_benchmark_payload(
        target,
        wiki_dir,
        query_text=query_text,
        budget=budget,
        project=project_name,
        review_command="review-memory",
    )
    if json_output:
        print(json.dumps(payload, indent=2))
        return 0

    print(_core_render_benchmark_text(payload))
    return 0


def brief(
    target: Path,
    query: str = "",
    limit: int = 6,
    project: str | None = None,
    json_output: bool = False,
) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    query = _clean_text_input(query, max_len=500)
    project_name = project or _default_project(target)
    payload = _memory_brief(wiki_dir, query=query, limit=limit, project=project_name)
    payload = _core_add_capture_review_to_brief(
        payload,
        _capture_review_summary(target, project=project_name),
    )

    if json_output:
        print(json.dumps(payload, indent=2))
        return 0

    code, text = _core_render_brief_text(payload, query=query, project=project_name)
    print(text)
    return code


def profile(target: Path, limit: int = 10, project: str | None = None, json_output: bool = False) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    project_name = project or _default_project(target)
    profile_data = _memory_profile(wiki_dir, limit=limit, project=project_name)

    if json_output:
        print(json.dumps(profile_data, indent=2))
        return 0

    code, text = _core_render_profile_text(profile_data, target=target, project=project_name)
    print(text)
    return code


def _memory_audit_payload(target: Path, wiki_dir: Path, limit: int = 10, project: str | None = None) -> dict[str, object]:
    project_name = project or _default_project(target)
    profile_data = _memory_profile(wiki_dir, limit=limit, project=project_name)
    inbox = _memory_inbox(wiki_dir, limit=limit, include_archived=True, project=project_name)
    captures = _capture_review_summary(target, project=project_name, limit=min(limit, 10))
    payload = _core_memory_audit_report(profile_data, inbox, captures, [], project=project_name)
    payload["next_actions"] = _core_memory_audit_next_actions(
        mode="cli",
        inbox=inbox,
        captures=captures,
        risk_factors=payload["risk_factors"],
        project=str(payload["project"]),
        root=_resolve_link_root(target),
    )
    return payload


def memory_audit(target: Path, limit: int = 10, project: str | None = None, json_output: bool = False) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    payload = _memory_audit_payload(target, wiki_dir, limit=limit, project=project)

    if json_output:
        print(json.dumps(payload, indent=2))
        return 0

    code, text = _core_render_memory_audit_text(payload, target=target)
    print(text)
    return code


def _display_command(parts: list[str]) -> str:
    return _core_display_command(parts)


def verify_mcp(
    target: Path,
    json_output: bool = False,
    python_cmd: str | None = None,
    import_check: Callable[[str], dict[str, object]] = _core_check_link_mcp_import,
) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    status = _core_build_mcp_verify_status(
        target=target,
        wiki_dir=wiki_dir,
        init_command=[sys.executable, str(ROOT / "link.py"), "init", str(target)],
        expected_version=LINK_VERSION,
        python_cmd=python_cmd,
        default_python=sys.executable,
        import_check=import_check,
    )

    if json_output:
        print(json.dumps(status, indent=2))
        return 0 if status["ready"] else 1

    code, text = _core_render_mcp_verify_text(status)
    print(text)
    return code


def _copy_runtime_files(target: Path) -> None:
    _core_copy_runtime_files(ROOT, target)


def init_wiki(target: Path) -> int:
    target = target.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    _copy_runtime_files(target)
    fixes = _apply_doctor_fixes(target)

    code, text = _core_render_init_text(target=target, fixes=fixes)
    print(text)
    return code


def starter_prompts(target: Path, project: str | None = None, json_output: bool = False) -> int:
    payload = _core_starter_prompt_payload(target, project=project)
    if json_output:
        print(json.dumps(payload, indent=2))
        return 0

    code, text = _core_render_starter_prompts_text(payload)
    print(text)
    return code


def serve_wiki(target: Path, port: int = 3000) -> int:
    target = target.expanduser().resolve()
    if port < 1 or port > 65535:
        print("--port must be between 1 and 65535")
        return 1
    serve_path = ROOT / "serve.py"
    if not serve_path.exists():
        serve_path = target / "serve.py"
    if not serve_path.exists():
        print(f"Link viewer missing: {serve_path}")
        print("")
        print("Next:")
        print(f"  {_display_command(['link', 'init', str(target)])}")
        return 1
    if not (target / "wiki").exists():
        print(f"Link wiki missing: {target / 'wiki'}")
        print("")
        print("Next:")
        print(f"  {_display_command(['link', 'init', str(target)])}")
        return 1
    try:
        return subprocess.run(
            [sys.executable, str(serve_path), "--root", str(target), "--port", str(port)]
        ).returncode
    except KeyboardInterrupt:
        return 130


def create_demo(target: Path, force: bool = False) -> int:
    target = target.expanduser().resolve()
    try:
        _core_create_demo_workspace(target, source_root=ROOT, force=force)
    except _CoreDemoError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    code, text = _core_render_demo_text(
        target=target,
        guide_path=target / "START_HERE.md",
        serve_command=_display_command(["python3", "link.py", "serve", str(target)]),
        query_command=_display_command([
            "python3",
            "link.py",
            "query",
            "why does Link help agents?",
            str(target),
            "--budget",
            "small",
        ]),
        brief_command=_display_command(["python3", "link.py", "brief", "working on agent memory", str(target)]),
        audit_command=_display_command(["python3", "link.py", "memory-audit", str(target)]),
    )
    print(text)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = _core_build_cli_parser(default_demo_dir=DEFAULT_DEMO_DIR)
    args = parser.parse_args(argv)
    if args.command == "init":
        return init_wiki(Path(args.target))
    if args.command == "serve":
        return serve_wiki(Path(args.target), port=args.port)
    if args.command == "demo":
        return create_demo(Path(args.target), force=args.force)
    if args.command == "prompts":
        return starter_prompts(Path(args.target), project=args.project, json_output=args.json)
    if args.command == "status":
        return status(Path(args.target), include_validation=args.validate, json_output=args.json)
    if args.command == "backup":
        return backup(
            Path(args.target),
            label=args.label,
            include_raw=args.include_raw,
            list_only=args.list_only,
            json_output=args.json,
        )
    if args.command == "doctor":
        return doctor(Path(args.target), fix=args.fix)
    if args.command == "migrate":
        return migrate(Path(args.target), json_output=args.json)
    if args.command == "validate":
        return validate(Path(args.target), strict=args.strict, json_output=args.json)
    if args.command == "ingest-status":
        return ingest_status(Path(args.target), json_output=args.json)
    if args.command == "remember":
        return remember(
            Path(args.target),
            args.text,
            title=args.title,
            memory_type=args.memory_type,
            scope=args.scope,
            tags=args.tags,
            source=args.source,
            project=args.project,
            allow_duplicate=args.allow_duplicate,
            allow_conflict=args.allow_conflict,
            json_output=args.json,
        )
    if args.command == "propose-memories":
        return propose_memories(
            Path(args.target),
            args.source_input,
            limit=args.limit,
            project=args.project,
            json_output=args.json,
        )
    if args.command == "capture-session":
        return capture_session(
            Path(args.target),
            args.source_input,
            title=args.title,
            limit=args.limit,
            project=args.project,
            json_output=args.json,
        )
    if args.command == "capture-inbox":
        return capture_inbox(
            Path(args.target),
            limit=args.limit,
            project=args.project,
            json_output=args.json,
        )
    if args.command == "accept-capture":
        return accept_capture(
            Path(args.target),
            args.capture,
            index=args.index,
            title=args.title,
            memory_type=args.memory_type,
            scope=args.scope,
            tags=args.tags,
            project=args.project,
            allow_duplicate=args.allow_duplicate,
            allow_conflict=args.allow_conflict,
            json_output=args.json,
        )
    if args.command == "redact-capture":
        return redact_capture(
            Path(args.target),
            args.capture,
            replacement=args.replacement,
            json_output=args.json,
        )
    if args.command == "delete-capture":
        return delete_capture(
            Path(args.target),
            args.capture,
            confirm=args.confirm,
            json_output=args.json,
        )
    if args.command == "update-memory":
        return update_memory(
            Path(args.target),
            args.identifier,
            args.text,
            source=args.source,
            allow_conflict=args.allow_conflict,
            project=args.project,
            json_output=args.json,
        )
    if args.command == "recall":
        return recall(
            Path(args.target),
            args.query,
            limit=args.limit,
            json_output=args.json,
            include_archived=args.include_archived,
            project=args.project,
        )
    if args.command in {"query", "query-link"}:
        return query(
            Path(args.target),
            args.query,
            budget=args.budget,
            project=args.project,
            json_output=args.json,
        )
    if args.command == "graph-summary":
        return graph_summary(
            Path(args.target),
            topic=args.topic,
            limit=args.limit,
            depth=args.depth,
            max_edges=args.max_edges,
            json_output=args.json,
        )
    if args.command == "benchmark":
        return benchmark(
            Path(args.target),
            query_text=args.query,
            budget=args.budget,
            project=args.project,
            json_output=args.json,
        )
    if args.command == "brief":
        return brief(Path(args.target), query=args.query, limit=args.limit, project=args.project, json_output=args.json)
    if args.command == "profile":
        return profile(Path(args.target), limit=args.limit, project=args.project, json_output=args.json)
    if args.command == "memory-audit":
        return memory_audit(Path(args.target), limit=args.limit, project=args.project, json_output=args.json)
    if args.command == "archive-memory":
        return archive_memory(Path(args.target), args.identifier, reason=args.reason, json_output=args.json)
    if args.command == "restore-memory":
        return restore_memory(Path(args.target), args.identifier, json_output=args.json)
    if args.command == "forget-memory":
        return forget_memory(Path(args.target), args.identifier, confirm=args.confirm, json_output=args.json)
    if args.command == "memory-inbox":
        return memory_inbox(
            Path(args.target),
            limit=args.limit,
            include_archived=args.include_archived,
            project=args.project,
            json_output=args.json,
        )
    if args.command == "review-memory":
        return review_memory(Path(args.target), args.identifier, note=args.note, json_output=args.json)
    if args.command == "explain-memory":
        return explain_memory(Path(args.target), args.identifier, json_output=args.json)
    if args.command == "rebuild-index":
        return rebuild_index(Path(args.target))
    if args.command == "rebuild-backlinks":
        return rebuild_backlinks(Path(args.target))
    if args.command == "verify-mcp":
        return verify_mcp(Path(args.target), json_output=args.json, python_cmd=args.python)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
