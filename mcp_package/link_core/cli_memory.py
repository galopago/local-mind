"""Text rendering helpers for Link memory CLI commands."""
from __future__ import annotations

from collections.abc import Mapping, Sequence


def _candidate_lines(candidates: object, *, include_reasons: bool = False) -> list[str]:
    lines: list[str] = []
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return lines
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        title = candidate.get("title", "Untitled memory")
        path = candidate.get("path", "")
        lines.append(f"- {title} ({path})")
        if include_reasons:
            reasons = candidate.get("conflict_reasons")
            if isinstance(reasons, Sequence) and not isinstance(reasons, (str, bytes)):
                reason_text = ", ".join(str(reason) for reason in reasons if reason)
                if reason_text:
                    lines.append(f"  Reasons: {reason_text}")
    return lines


def _first_candidate_name(candidates: object) -> str | None:
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return None
    for candidate in candidates:
        if isinstance(candidate, Mapping) and candidate.get("name"):
            return str(candidate["name"])
    return None


def render_remember_text(result: Mapping[str, object]) -> tuple[int, str]:
    if not result.get("created"):
        if result.get("conflict"):
            lines = [
                "Possible conflicting memory found",
                f"Title requested: {result['title']}",
                f"Type: {result['memory_type']}",
                f"Scope: {result['scope']}",
                "",
                "Conflict candidates:",
                *_candidate_lines(result.get("conflict_candidates", []), include_reasons=True),
                "",
                "Next:",
            ]
            first = _first_candidate_name(result.get("conflict_candidates", []))
            if first:
                lines.append(f"  python3 link.py explain-memory \"{first}\" .")
            lines.append("  Update/archive the old memory, or use --allow-conflict only if both should coexist.")
            return 0, "\n".join(lines)

        lines = [
            "Similar memory already exists",
            f"Title requested: {result['title']}",
            f"Type: {result['memory_type']}",
            f"Scope: {result['scope']}",
            "",
            "Existing candidates:",
            *_candidate_lines(result.get("candidates", [])),
            "",
            "Next:",
        ]
        first = _first_candidate_name(result.get("candidates", []))
        if first:
            lines.append(f"  python3 link.py explain-memory \"{first}\" .")
        lines.append("  Use --allow-duplicate only if this should be a separate memory.")
        return 0, "\n".join(lines)

    lines = [
        "Memory saved",
        f"Title: {result['title']}",
        f"Path: {result['path']}",
        f"Type: {result['memory_type']}",
        f"Scope: {result['scope']}",
    ]
    if result.get("project"):
        lines.append(f"Project: {result['project']}")
    lines.extend([
        "",
        "Next:",
        f"  python3 link.py recall \"{result['title']}\" .",
    ])
    return 0, "\n".join(lines)


def render_update_memory_text(result: Mapping[str, object]) -> tuple[int, str]:
    if not result.get("updated") and result.get("conflict"):
        lines = [
            "Possible conflicting memory found",
            f"Memory being updated: {result['title']} ({result['path']})",
            "",
            "Conflict candidates:",
            *_candidate_lines(result.get("conflict_candidates", []), include_reasons=True),
            "",
            "Next:",
        ]
        first = _first_candidate_name(result.get("conflict_candidates", []))
        if first:
            lines.append(f"  python3 link.py explain-memory \"{first}\" .")
        lines.append("  Update/archive the conflicting memory, or use --allow-conflict only if both should coexist.")
        return 0, "\n".join(lines)

    return 0, "\n".join([
        "Memory updated",
        f"Title: {result['title']}",
        f"Path: {result['path']}",
        f"Update count: {result['update_count']}",
        f"Review: {result['previous_review_status']} -> {result['review_status']}",
        "",
        "Next:",
        f"  python3 link.py explain-memory \"{result['name']}\" .",
        f"  python3 link.py review-memory \"{result['name']}\" .",
    ])


def render_recall_text(
    *,
    query: str,
    results: Sequence[Mapping[str, object]],
    include_archived: bool = False,
    project: str | None = None,
) -> tuple[int, str]:
    lines = [f"Link memory recall: {query}"]
    if project:
        lines.append(f"Project: {project}")
    if include_archived:
        lines.append("Including archived/stale memories")
    lines.append("")
    if not results:
        lines.extend([
            "No matching memories found.",
            "",
            "Next:",
            "  Add one: python3 link.py remember \"Memory to keep\" .",
        ])
        return 0, "\n".join(lines)

    lines.append(f"{len(results)} memor{'y' if len(results) == 1 else 'ies'}")
    for record in results:
        lines.append(f"- {record['title']} ({record['memory_type']} · {record['scope']})")
        lines.append(f"  {record['path']}")
        recall = record.get("recall") if isinstance(record.get("recall"), Mapping) else {}
        if recall.get("state"):
            lines.append(f"  Recall: {recall['state']}")
        summary = record.get("tldr") or record.get("snippet")
        if summary:
            lines.append(f"  {summary}")
    return 0, "\n".join(lines)
