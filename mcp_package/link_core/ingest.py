"""Shared Link ingest status helpers."""
from __future__ import annotations

import re
from pathlib import Path

from .wiki import build_backlinks, load_backlinks_index


DEFAULT_SKIP_DIRS = {
    ".git",
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


def raw_source_files(raw_dir: Path, skip_dirs: set[str] | None = None) -> list[Path]:
    if not raw_dir.exists():
        return []
    skipped = skip_dirs or DEFAULT_SKIP_DIRS
    files: list[Path] = []
    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        rel_parts = path.relative_to(raw_dir).parts
        if rel_parts and rel_parts[0] == "memory-captures":
            continue
        if any(part in skipped for part in rel_parts):
            continue
        files.append(path)
    return files


def source_page_texts(wiki_dir: Path) -> dict[str, str]:
    sources_dir = wiki_dir / "sources"
    if not sources_dir.exists():
        return {}
    texts: dict[str, str] = {}
    for page in sorted(sources_dir.rglob("*.md")):
        if page.name.startswith("."):
            continue
        texts[page.stem.lower()] = page.read_text(encoding="utf-8", errors="replace")
    return texts


def normalize_link_index(data: dict[str, dict[str, list[str]]]) -> dict[str, dict[str, list[str]]]:
    normalized: dict[str, dict[str, list[str]]] = {"backlinks": {}, "forward": {}}
    for section in ("backlinks", "forward"):
        for key, values in data.get(section, {}).items():
            if isinstance(values, list):
                normalized[section][key.lower()] = sorted({str(value).lower() for value in values})
    return normalized


def backlinks_health(wiki_dir: Path) -> tuple[str, str]:
    current, load_error = load_backlinks_index(
        wiki_dir / "_backlinks.json",
        missing_error="missing wiki/_backlinks.json",
    )
    if load_error:
        return "missing" if "missing" in load_error else "invalid", load_error
    expected = build_backlinks(wiki_dir)
    if current is not None and normalize_link_index(current) == normalize_link_index(expected):
        return "current", "wiki/_backlinks.json is current"
    return "stale", "wiki/_backlinks.json is stale"


def _source_page_suggestion(raw_rel: str) -> str:
    stem = Path(raw_rel).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-") or "source"
    return f"wiki/sources/{slug}.md"


def build_ingest_plan(status: dict[str, object], limit: int = 5) -> dict[str, object]:
    """Build a short, actionable ingest workflow for agents and humans."""
    guidance = status.get("guidance") if isinstance(status.get("guidance"), dict) else {}
    state = str(guidance.get("state") or "unknown")
    pending_raw = status.get("pending_raw") if isinstance(status.get("pending_raw"), list) else []
    batch: list[dict[str, object]] = []
    for item in pending_raw[: max(limit, 1)]:
        raw_rel = str(item.get("raw") or "")
        if not raw_rel:
            continue
        batch.append({
            "raw": raw_rel,
            "size_bytes": int(item.get("size_bytes") or 0),
            "suggested_source_page": _source_page_suggestion(raw_rel),
        })

    if state == "pending_raw" and batch:
        first = batch[0]
        batch_count = len(batch)
        file_label = "file" if batch_count == 1 else "files"
        return {
            "state": state,
            "title": "Ingest pending raw sources",
            "summary": f"Start with {first['raw']} and process at most {batch_count} {file_label} in this pass.",
            "batch": batch,
            "steps": [
                "Read each raw file completely before writing wiki pages.",
                "Create or update one source page per raw file and include the exact raw path.",
                "Update existing concept/entity/memory pages before creating new thin pages.",
                "Keep durable memories proposal-only until the human approves them.",
                "Rebuild index and backlinks, then validate before reporting ingest complete.",
            ],
            "agent_prompt": guidance.get("agent_prompt"),
            "post_checks": [
                "link rebuild-index",
                "link rebuild-backlinks",
                "link validate",
                "link status --validate",
            ],
        }

    if state == "stale_graph":
        return {
            "state": state,
            "title": "Repair graph index",
            "summary": "Raw sources are represented, but the graph index is stale.",
            "batch": [],
            "steps": [
                "Run the graph repair before relying on search, context, or graph views.",
                "Validate the wiki after rebuilding backlinks.",
            ],
            "agent_prompt": guidance.get("agent_prompt"),
            "post_checks": ["link rebuild-backlinks", "link validate", "link status --validate"],
        }

    if state == "empty":
        return {
            "state": state,
            "title": "Add first sources",
            "summary": "Drop notes, articles, transcripts, screenshots, or project files into raw/.",
            "batch": [],
            "steps": [
                "Add one or more source files to raw/.",
                "Ask your agent to ingest the specific raw file.",
                "Review generated pages before relying on them as memory.",
            ],
            "agent_prompt": None,
            "post_checks": ["link ingest-status", "link status --validate"],
        }

    if state == "ready":
        return {
            "state": state,
            "title": "Ready for new sources",
            "summary": "All current raw sources are represented and the graph index is current.",
            "batch": [],
            "steps": [
                "Use query or brief for retrieval.",
                "Add new files to raw/ when Link should learn new source-backed context.",
            ],
            "agent_prompt": None,
            "post_checks": ["link doctor", "link status --validate"],
        }

    return {
        "state": state,
        "title": "Initialize Link",
        "summary": "Link needs its raw/ and wiki/ structure before ingest can start.",
        "batch": [],
        "steps": [
            "Run link init or rerun an installer.",
            "Check readiness before adding sources.",
        ],
        "agent_prompt": None,
        "post_checks": ["link init", "link status --validate"],
    }


def build_ingest_guidance(status: dict[str, object]) -> dict[str, object]:
    has_raw_dir = bool(status.get("has_raw_dir"))
    has_wiki_dir = bool(status.get("has_wiki_dir"))
    pending_raw = status.get("pending_raw")
    pending_items = pending_raw if isinstance(pending_raw, list) else []
    pending_count = int(status.get("pending_count") or 0)
    raw_count = int(status.get("raw_count") or 0)
    backlinks_status = str(status.get("backlinks_status") or "unknown")

    if not has_raw_dir or not has_wiki_dir:
        return {
            "state": "missing_structure",
            "summary": "Link is not initialized here yet.",
            "agent_prompt": None,
            "commands": ["link init", "link status --validate"],
            "notes": ["Run the installer or initialize this directory before ingesting sources."],
        }

    if pending_items:
        first = str(pending_items[0].get("raw", "raw/<file>"))
        more = pending_count - 1
        summary = f"{pending_count} raw file needs ingest."
        if pending_count != 1:
            summary = f"{pending_count} raw files need ingest."
        if more > 0:
            summary += f" Start with {first}; {more} more remain."
        return {
            "state": "pending_raw",
            "summary": summary,
            "agent_prompt": f"ingest {first} into Link",
            "commands": ["link rebuild-index", "link rebuild-backlinks", "link validate", "link status --validate"],
            "notes": [
                "If the source contains user preferences, decisions, or project context, ask for memory proposals before saving durable memories.",
                "After ingest, rebuild index/backlinks if your agent did not already do it.",
            ],
        }

    if backlinks_status != "current":
        return {
            "state": "stale_graph",
            "summary": "Raw files are represented, but the graph index needs repair.",
            "agent_prompt": "rebuild Link backlinks and validate the wiki",
            "commands": ["link rebuild-backlinks", "link validate", "link doctor"],
            "notes": ["Run the graph repair before relying on context or graph views."],
        }

    if raw_count == 0:
        return {
            "state": "empty",
            "summary": "Link is ready, but raw/ has no source files yet.",
            "agent_prompt": None,
            "commands": ["link status --validate", "link serve"],
            "notes": ["Drop notes, articles, transcripts, or project files into raw/, then ask your agent to ingest them into Link."],
        }

    return {
        "state": "ready",
        "summary": "All raw files are represented in wiki/sources and the graph index is current.",
        "agent_prompt": None,
        "commands": ["link doctor", "link status --validate"],
        "notes": ["Add new files to raw/ when you want Link to learn new source-backed knowledge."],
    }


def collect_ingest_status(target: Path, skip_dirs: set[str] | None = None) -> dict[str, object]:
    target = target.expanduser().resolve()
    raw_dir = target / "raw"
    wiki_dir = target / "wiki"
    raw_files = raw_source_files(raw_dir, skip_dirs=skip_dirs)
    source_texts = source_page_texts(wiki_dir)

    represented_raw: list[dict[str, object]] = []
    pending_raw: list[dict[str, object]] = []
    for raw_path in raw_files:
        rel = raw_path.relative_to(target).as_posix()
        matches = [
            source_name
            for source_name, source_text in source_texts.items()
            if rel in source_text
        ]
        item = {
            "raw": rel,
            "size_bytes": raw_path.stat().st_size,
            "source_pages": matches,
        }
        if matches:
            represented_raw.append(item)
        else:
            pending_raw.append(item)

    backlinks_status, backlinks_message = (
        backlinks_health(wiki_dir)
        if wiki_dir.exists()
        else ("missing", "missing wiki directory")
    )

    payload: dict[str, object] = {
        "target": str(target),
        "raw_count": len(raw_files),
        "source_page_count": len(source_texts),
        "represented_count": len(represented_raw),
        "pending_count": len(pending_raw),
        "represented_raw": represented_raw,
        "pending_raw": pending_raw,
        "backlinks_status": backlinks_status,
        "backlinks_message": backlinks_message,
        "has_raw_dir": raw_dir.exists(),
        "has_wiki_dir": wiki_dir.exists(),
    }
    payload["guidance"] = build_ingest_guidance(payload)
    payload["plan"] = build_ingest_plan(payload)
    return payload
