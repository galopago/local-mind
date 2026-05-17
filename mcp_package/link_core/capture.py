"""Shared raw capture helpers for Link CLI and MCP runtimes."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from .frontmatter import parse_frontmatter
from .memory import normalize_project, slugify
from .security import redact_secret_values, secret_value_warnings


CaptureCommands = Callable[[str], dict[str, str]]


def capture_title(
    text: str,
    source: str = "",
    title: str | None = None,
    *,
    default_source: str = "inline",
    path_source: bool = False,
    max_source_len: int = 120,
) -> str:
    """Build a stable human-readable title for saved raw memory captures."""
    if title and title.strip():
        return " ".join(title.split())

    source_value = " ".join(str(source or "").split())
    if source_value and source_value != default_source:
        if path_source:
            stem = Path(source_value).stem.replace("-", " ").replace("_", " ").strip()
            if stem:
                return f"Memory capture: {stem.title()}"
        else:
            return f"Memory capture: {source_value[:max_source_len]}"

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "Session notes")
    short = " ".join(first_line.split()[:10]).strip(" .")
    return f"Memory capture: {short or 'Session notes'}"


def capture_filename(timestamp: str, title: str, raw_dir: Path) -> Path:
    """Return a unique capture path under raw_dir for the given timestamp/title."""
    safe_stamp = str(timestamp).replace("-", "").replace(":", "")
    title_slug = slugify(title.replace("Memory capture:", ""), fallback="session-notes")
    base = f"{safe_stamp}-{title_slug}"
    candidate = raw_dir / f"{base}.md"
    counter = 2
    while candidate.exists():
        candidate = raw_dir / f"{base}-{counter}.md"
        counter += 1
    return candidate


def resolve_capture_file(root: Path, capture: str, *, max_len: int | None = None) -> Path | None:
    """Resolve a user-provided raw capture path without escaping the Link root."""
    raw = str(capture or "").strip()
    if max_len is not None:
        raw = raw[:max_len]
    if not raw:
        return None

    root = root.expanduser().resolve()
    raw_path = Path(raw).expanduser()
    candidates = [raw_path]
    if not raw_path.is_absolute():
        candidates.extend([
            root / raw,
            root / "raw" / "memory-captures" / raw,
            root / "raw" / "memory-captures" / f"{raw}.md",
        ])

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.is_file():
            continue
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        return resolved
    return None


def capture_notes_from_markdown(text: str) -> tuple[dict[str, object], str]:
    """Return capture frontmatter and the `## Notes` body when present."""
    meta, body = parse_frontmatter(text)
    match = re.search(r"^## Notes\s*(.*?)(?=^## |\Z)", body, flags=re.MULTILINE | re.DOTALL)
    notes = match.group(1).strip() if match else body.strip()
    return meta, notes


def cli_capture_commands(rel_path: str) -> dict[str, str]:
    return {
        "accept": f'python3 link.py accept-capture "{rel_path}" . --index 1',
        "redact": f'python3 link.py redact-capture "{rel_path}" .',
        "delete": f'python3 link.py delete-capture "{rel_path}" . --confirm',
    }


def mcp_capture_commands(rel_path: str) -> dict[str, str]:
    return {
        "accept": f'accept_capture(capture="{rel_path}", index=1)',
        "redact": f'redact_capture(capture="{rel_path}")',
        "delete": f'delete_capture(capture="{rel_path}", confirm=true)',
    }


def capture_records(
    root: Path,
    limit: int = 20,
    project: str | None = None,
    commands_for: CaptureCommands | None = None,
    *,
    read_warnings: list[dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    root = root.expanduser().resolve()
    capture_dir = root / "raw" / "memory-captures"
    if not capture_dir.exists():
        return []
    project_name = normalize_project(project)
    command_builder = commands_for or cli_capture_commands
    records: list[dict[str, object]] = []
    for path in sorted(capture_dir.rglob("*.md")):
        if path.name.startswith("."):
            continue
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            stat = path.stat()
        except OSError as exc:
            if read_warnings is not None:
                read_warnings.append({
                    "capture": rel,
                    "error": str(exc) or exc.__class__.__name__,
                })
            continue
        meta, notes = capture_notes_from_markdown(text)
        capture_project = normalize_project(str(meta.get("project") or ""))
        if project_name and capture_project and capture_project != project_name:
            continue
        warnings = secret_value_warnings(text)
        safe_notes, _, _ = redact_secret_values(notes)
        records.append({
            "path": rel,
            "title": str(meta.get("title") or path.stem),
            "project": capture_project,
            "date_captured": str(meta.get("date_captured") or ""),
            "size_bytes": stat.st_size,
            "secret_warnings": warnings,
            "warning_count": len(warnings),
            "snippet": re.sub(r"\s+", " ", safe_notes).strip()[:180],
            "commands": command_builder(rel),
        })
    records.sort(key=lambda item: (str(item["date_captured"]), str(item["path"])), reverse=True)
    return records[:max(1, min(limit, 50))]


def capture_inbox(
    root: Path,
    limit: int = 20,
    project: str | None = None,
    commands_for: CaptureCommands | None = None,
) -> dict[str, object]:
    project_name = normalize_project(project)
    read_warnings: list[dict[str, str]] = []
    captures = capture_records(
        root,
        limit=limit,
        project=project_name,
        commands_for=commands_for,
        read_warnings=read_warnings,
    )
    return {
        "count": len(captures),
        "warning_count": sum(1 for capture in captures if capture["warning_count"]),
        "read_warning_count": len(read_warnings),
        "read_warnings": read_warnings,
        "project": project_name,
        "captures": captures,
    }


def render_capture_inbox_text(payload: dict[str, object]) -> str:
    """Render human-readable raw capture inbox output."""
    project_name = str(payload.get("project") or "")
    captures = payload.get("captures") if isinstance(payload.get("captures"), list) else []
    warning_count = int(payload.get("warning_count") or 0)
    read_warning_count = int(payload.get("read_warning_count") or 0)
    read_warnings = payload.get("read_warnings") if isinstance(payload.get("read_warnings"), list) else []

    lines = ["Raw capture inbox"]
    if project_name:
        lines.append(f"Project: {project_name}")
    lines.append(
        f"{len(captures)} readable capture{'s' if len(captures) != 1 else ''} · "
        f"{warning_count} with secret-looking warnings · {read_warning_count} read warnings"
    )
    if read_warnings:
        lines.extend(["", "Capture read warnings:"])
        for warning in read_warnings[:20]:
            if isinstance(warning, dict):
                lines.append(f"   {warning.get('capture')}: {warning.get('error')}")
    if not captures:
        lines.extend(["", "No readable saved raw captures."])
        return "\n".join(lines)
    for index, capture in enumerate(captures, start=1):
        if not isinstance(capture, dict):
            continue
        commands = capture.get("commands") if isinstance(capture.get("commands"), dict) else {}
        secret_warnings = capture.get("secret_warnings") if isinstance(capture.get("secret_warnings"), list) else []
        lines.extend(["", f"{index}. {capture.get('title')}"])
        lines.append(f"   Path: {capture.get('path')}")
        if capture.get("project"):
            lines.append(f"   Project: {capture.get('project')}")
        if secret_warnings:
            lines.append("   Secret-looking values: " + ", ".join(str(label) for label in secret_warnings))
        lines.append(f"   Accept: {commands.get('accept')}")
        if secret_warnings:
            lines.append(f"   Redact: {commands.get('redact')}")
        lines.append(f"   Delete: {commands.get('delete')}")
    return "\n".join(lines)


def render_accept_capture_text(payload: dict[str, object]) -> tuple[int, str]:
    """Render accept-capture text and return the corresponding exit code."""
    if not payload.get("accepted"):
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        duplicate_candidates = result.get("duplicate_candidates") or result.get("candidates")
        if isinstance(duplicate_candidates, list) and duplicate_candidates:
            first = duplicate_candidates[0]
            if isinstance(first, dict):
                return 1, f"Duplicate candidate: {first.get('title')} ({first.get('path')})"
        conflict_candidates = result.get("conflict_candidates")
        if isinstance(conflict_candidates, list) and conflict_candidates:
            first = conflict_candidates[0]
            if isinstance(first, dict):
                return 1, f"Conflict candidate: {first.get('title')} ({first.get('path')})"
        return 1, "Capture proposal was not accepted."

    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    lines = [
        "Capture proposal accepted",
        f"Capture: {payload.get('capture')}",
        f"Proposal: {payload.get('proposal_index')}",
        f"Memory: {result.get('path')}",
    ]
    if result.get("project"):
        lines.append(f"Project: {result.get('project')}")
    lines.extend(["", "Next:", f"  python3 link.py review-memory \"{result.get('name')}\" ."])
    return 0, "\n".join(lines)


def render_redact_capture_text(payload: dict[str, object]) -> str:
    """Render redact-capture CLI output."""
    if payload.get("redacted"):
        labels = payload.get("labels") if isinstance(payload.get("labels"), list) else []
        return "\n".join([
            "Capture redacted",
            f"Path: {payload.get('path')}",
            "Labels: " + ", ".join(str(label) for label in labels),
            f"Replacement count: {payload.get('replacement_count', 0)}",
        ])
    return "\n".join([
        "No secret-looking values found.",
        f"Path: {payload.get('path')}",
    ])


def render_delete_capture_text(payload: dict[str, object]) -> tuple[int, str]:
    """Render delete-capture CLI output and return the corresponding exit code."""
    path = str(payload.get("path") or "")
    if payload.get("confirmation_required"):
        return 1, "\n".join([
            "Confirmation required.",
            f"Run: python3 link.py delete-capture \"{path}\" . --confirm",
        ])
    if payload.get("deleted"):
        return 0, "\n".join([
            "Capture deleted",
            f"Path: {path}",
        ])
    return 1, "\n".join([
        "Capture was not deleted.",
        f"Path: {path}",
    ])


def render_capture_session_text(payload: dict[str, object]) -> str:
    """Render capture-session CLI output."""
    proposals = payload.get("proposals") if isinstance(payload.get("proposals"), dict) else {}
    proposal_items = proposals.get("proposals") if isinstance(proposals.get("proposals"), list) else []
    lines = [
        "Session captured",
        f"Path: {payload.get('path')}",
    ]
    if payload.get("project"):
        lines.append(f"Project: {payload.get('project')}")
    secret_warnings = payload.get("secret_warnings") if isinstance(payload.get("secret_warnings"), list) else []
    if secret_warnings:
        lines.append("Secret-looking content: " + ", ".join(str(label) for label in secret_warnings))
    lines.append(f"Proposals: {proposals.get('count', 0)}")
    if not proposal_items:
        lines.append("No durable memory candidates found.")
        return "\n".join(lines)
    for index, proposal in enumerate(proposal_items, start=1):
        if not isinstance(proposal, dict):
            continue
        lines.extend([
            "",
            f"{index}. {proposal.get('title')} [{proposal.get('confidence')}]",
            f"   Type: {proposal.get('memory_type')} | Scope: {proposal.get('scope')}",
        ])
        if proposal.get("project"):
            lines.append(f"   Project: {proposal.get('project')}")
        lines.append(f"   Action: {proposal.get('suggested_action')}")
        lines.append(f"   Memory: {proposal.get('memory')}")
    lines.extend(["", "Next:", "  Ask the user which proposals to remember, update, or discard."])
    return "\n".join(lines)


def capture_review_summary(
    root: Path,
    limit: int = 3,
    project: str | None = None,
    commands_for: CaptureCommands | None = None,
) -> dict[str, object]:
    """Return compact capture backlog context for briefs, audits, and dashboards."""
    payload = capture_inbox(
        root,
        limit=50,
        project=project,
        commands_for=commands_for,
    )
    captures = payload["captures"] if isinstance(payload.get("captures"), list) else []
    return {
        "count": len(captures),
        "warning_count": int(payload.get("warning_count") or 0),
        "read_warning_count": int(payload.get("read_warning_count") or 0),
        "read_warnings": payload.get("read_warnings") if isinstance(payload.get("read_warnings"), list) else [],
        "project": str(payload.get("project") or ""),
        "items": captures[:max(1, min(limit, 10))],
    }
