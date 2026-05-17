"""Shared doctor report helpers for Link health checks."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .files import atomic_write_text
from .frontmatter import parse_frontmatter
from .validation import validate_wiki
from .wiki import WIKILINK_RE, build_backlinks


DOCTOR_VALIDATION_CODES = {
    "invalid_directory",
    "missing_frontmatter",
    "missing_frontmatter_field",
    "missing_required_section",
    "type_directory_mismatch",
    "unreadable_page",
}


@dataclass
class DoctorReport:
    """Structured health-check report used by the CLI and future UI/API surfaces."""

    target: str
    fixes: list[str] = field(default_factory=list)
    ok: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    fix_requested: bool = False

    @property
    def healthy(self) -> bool:
        return not self.errors

    def add_ok(self, message: str) -> None:
        self.ok.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_error(self, message: str) -> None:
        self.errors.append(message)


def doctor_validation_errors(validation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return validation findings that should make doctor fail."""
    findings = validation.get("findings", [])
    if not isinstance(findings, list):
        return []
    return [
        finding
        for finding in findings
        if isinstance(finding, dict)
        and finding.get("severity") == "error"
        and str(finding.get("code") or "") in DOCTOR_VALIDATION_CODES
    ]


def format_validation_error_summary(findings: list[Mapping[str, Any]], limit: int = 8) -> str:
    details = [
        f"{finding.get('path')} [{finding.get('code')}] {finding.get('message')}"
        for finding in findings[:limit]
    ]
    return "validation errors: " + "; ".join(details)


def join_limited(prefix: str, values: list[str], limit: int = 8) -> str:
    return prefix + ", ".join(values[:limit])


def wiki_pages(wiki_dir: Path) -> list[Path]:
    return sorted(
        md for md in wiki_dir.rglob("*.md")
        if not md.name.startswith(".")
    )


def page_stems(wiki_dir: Path) -> set[str]:
    return {md.stem.lower() for md in wiki_pages(wiki_dir)}


def wiki_page_records(wiki_dir: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for md in wiki_pages(wiki_dir):
        text = md.read_text(encoding="utf-8", errors="replace")
        meta, body = parse_frontmatter(text)
        records.append({
            "path": md,
            "rel": str(md.relative_to(wiki_dir)),
            "stem": md.stem.lower(),
            "meta": meta,
            "body": body,
        })
    return records


def find_dead_links(wiki_dir: Path) -> list[str]:
    stems = page_stems(wiki_dir)
    dead: list[str] = []
    for md in wiki_pages(wiki_dir):
        source = md.stem.lower()
        text = md.read_text(encoding="utf-8", errors="replace")
        for match in WIKILINK_RE.finditer(text):
            target = match.group(1).strip().lower()
            if target and target not in stems:
                dead.append(f"{source} -> {target}")
    return sorted(set(dead))


def find_unindexed_pages(wiki_dir: Path) -> list[str]:
    index_path = wiki_dir / "index.md"
    if not index_path.exists():
        return []
    index_text = index_path.read_text(encoding="utf-8", errors="replace")
    indexed = {m.group(1).strip().lower() for m in WIKILINK_RE.finditer(index_text)}
    roots = {"index", "log"}
    return sorted(stem for stem in page_stems(wiki_dir) if stem not in indexed and stem not in roots)


def find_pages_missing_summaries(wiki_dir: Path) -> list[str]:
    missing: list[str] = []
    for record in wiki_page_records(wiki_dir):
        stem = str(record["stem"])
        if stem in {"index", "log"}:
            continue
        body = str(record["body"])
        if "> **TLDR:**" not in body and "> **Query:**" not in body:
            missing.append(str(record["rel"]))
    return sorted(missing)


def find_pages_missing_source_sections(wiki_dir: Path) -> list[str]:
    missing: list[str] = []
    source_backed_dirs = {"concepts", "entities", "comparisons", "explorations"}
    for record in wiki_page_records(wiki_dir):
        rel = str(record["rel"])
        top_dir = rel.split("/", 1)[0]
        if top_dir not in source_backed_dirs:
            continue
        body = str(record["body"])
        if not re.search(r"^## Sources\b", body, flags=re.MULTILINE):
            missing.append(rel)
    return sorted(missing)


def source_section_links(body: str) -> set[str]:
    match = re.search(r"^## Sources[^\n]*\n(?P<section>.*?)(?=^## |\Z)", body, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return set()
    return {m.group(1).strip().lower() for m in WIKILINK_RE.finditer(match.group("section"))}


def find_source_count_mismatches(wiki_dir: Path) -> list[str]:
    mismatches: list[str] = []
    for record in wiki_page_records(wiki_dir):
        rel = str(record["rel"])
        if rel.split("/", 1)[0] == "sources":
            continue
        meta = record["meta"]
        if not isinstance(meta, dict) or "source_count" not in meta:
            continue
        try:
            expected = int(str(meta["source_count"]))
        except ValueError:
            mismatches.append(f"{rel} has non-integer source_count")
            continue
        actual = len(source_section_links(str(record["body"])))
        if expected != actual:
            mismatches.append(f"{rel} source_count={expected}, sources section has {actual}")
    return sorted(mismatches)


def find_isolated_pages(wiki_dir: Path) -> list[str]:
    stems = page_stems(wiki_dir)
    records = wiki_page_records(wiki_dir)
    graph = build_backlinks(wiki_dir, body_only=False)
    isolated: list[str] = []
    for record in records:
        stem = str(record["stem"])
        if stem in {"index", "log"}:
            continue
        inbound = [name for name in graph["backlinks"].get(stem, []) if name in stems and name != stem]
        outgoing = [name for name in graph["forward"].get(stem, []) if name in stems and name != stem]
        if not inbound and not outgoing:
            isolated.append(str(record["rel"]))
    return sorted(isolated)


def raw_source_refs(text: str) -> list[str]:
    refs: list[str] = []
    for pattern in (r"`(raw/[^`\n]+)`", r"(?<![\w/])(raw/[^\s`<>()]+)"):
        for match in re.finditer(pattern, text):
            value = match.group(1).strip().rstrip(".,;:]")
            if value and value not in refs:
                refs.append(value)
    return refs


def body_with_tldr(body: str, title: str) -> str:
    if re.search(r">\s*\*\*(?:TLDR|Query):\*\*", body, flags=re.IGNORECASE):
        return body
    summary = f"> **TLDR:** {title} source notes.\n\n"
    heading = re.search(r"^#\s+.+\n", body, flags=re.MULTILINE)
    if heading:
        return body[: heading.end()] + "\n" + summary + body[heading.end():].lstrip("\n")
    return summary + body.lstrip("\n")


def append_section(body: str, title: str, content: str) -> str:
    return body.rstrip() + f"\n\n## {title}\n\n{content.strip()}\n"


def repair_source_page_validation_shape(page: Path, findings: list[dict[str, str]]) -> bool:
    text = page.read_text(encoding="utf-8", errors="replace")
    frontmatter_match = re.match(r"\A---\n.*?\n---\n?", text, flags=re.DOTALL)
    if not frontmatter_match:
        return False
    prefix = frontmatter_match.group(0).rstrip("\n") + "\n\n"
    meta, body = parse_frontmatter(text)
    if not isinstance(meta, dict) or str(meta.get("type") or "").strip() != "source":
        return False
    title = str(meta.get("title") or page.stem).strip() or page.stem
    messages = [str(finding.get("message") or "") for finding in findings]
    codes = {str(finding.get("code") or "") for finding in findings}
    changed = False

    if "missing_summary" in codes:
        updated = body_with_tldr(body, title)
        changed = changed or updated != body
        body = updated

    if any("## Summary" in message for message in messages):
        body = append_section(body, "Summary", f"{title} source notes.")
        changed = True

    if any("## Raw Source" in message for message in messages):
        refs = raw_source_refs(text)
        if refs:
            body = append_section(body, "Raw Source", f"`{refs[0]}`")
            changed = True

    if changed:
        atomic_write_text(page, prefix + body.rstrip() + "\n")
    return changed


def repair_validation_findings(wiki_dir: Path) -> list[str]:
    payload = validate_wiki(wiki_dir)
    findings_by_path: dict[str, list[dict[str, str]]] = {}
    for finding in payload.get("findings", []):
        if not isinstance(finding, dict):
            continue
        path = str(finding.get("path") or "")
        code = str(finding.get("code") or "")
        if not path.startswith("sources/"):
            continue
        if code != "missing_summary" and code != "missing_required_section":
            continue
        findings_by_path.setdefault(path, []).append(finding)

    fixes: list[str] = []
    for rel, findings in sorted(findings_by_path.items()):
        page = wiki_dir / rel
        try:
            repaired = repair_source_page_validation_shape(page, findings)
        except OSError:
            repaired = False
        if repaired:
            fixes.append(f"repaired validation shape for wiki/{rel}")
    return fixes


def render_doctor_report(report: DoctorReport) -> str:
    """Render a doctor report using the stable CLI text format."""
    lines = [f"Link doctor: {report.target}", ""]
    if report.fix_requested:
        if report.fixes:
            lines.append("Fixes applied:")
            lines.extend(f"- {item}" for item in report.fixes)
            lines.append("")
        else:
            lines.append("Fixes applied: none")
            lines.append("")

    lines.extend(report.ok)

    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in report.warnings)

    if report.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in report.errors)
        lines.append("")
        lines.append("Result: needs attention")
    else:
        lines.append("")
        lines.append("Result: healthy")

    return "\n".join(lines)
