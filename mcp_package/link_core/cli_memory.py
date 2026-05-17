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


def format_counts(counts: Mapping[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{name}: {count}" for name, count in counts.items())


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


def render_memory_status_text(result: Mapping[str, object], *, action: str) -> tuple[int, str]:
    if action == "archive":
        headline = "Memory archived" if result["updated"] else "Memory already archived"
        next_lines = [
            "",
            "Next:",
            f"  Restore: python3 link.py restore-memory \"{result['name']}\" .",
        ]
    elif action == "restore":
        headline = "Memory restored" if result["updated"] else "Memory already active"
        next_lines = []
    else:
        raise ValueError(f"Unsupported memory status action: {action}")

    return 0, "\n".join([
        headline,
        f"Title: {result['title']}",
        f"Path: {result['path']}",
        f"Previous status: {result['previous_status']}",
        f"Status: {result['status']}",
        *next_lines,
    ])


def render_forget_memory_text(result: Mapping[str, object], *, identifier: str) -> tuple[int, str]:
    if not result.get("found"):
        return 1, f"Memory not found: {identifier}"
    if result.get("confirmation_required"):
        return 1, "\n".join([
            "Confirmation required.",
            f"Run: python3 link.py forget-memory \"{result['name']}\" . --confirm",
        ])
    return 0, "\n".join([
        "Memory forgotten",
        f"Title: {result['title']}",
        f"Deleted: {result['path']}",
        f"Backlinks rebuilt: {'yes' if result.get('backlinks_rebuilt') else 'no'}",
    ])


def render_review_memory_text(result: Mapping[str, object]) -> tuple[int, str]:
    lines = [
        "Memory reviewed" if result["updated"] else "Memory was already reviewed",
        f"Title: {result['title']}",
        f"Path: {result['path']}",
        f"Previous review status: {result['previous_review_status']}",
        f"Review status: {result['review_status']}",
    ]
    if result["remaining_issue_count"]:
        lines.extend([
            "",
            f"{result['remaining_issue_count']} issue{'s' if result['remaining_issue_count'] != 1 else ''} still need attention:",
        ])
        remaining = result.get("remaining_issues", [])
        if isinstance(remaining, Sequence) and not isinstance(remaining, (str, bytes)):
            for issue in remaining:
                if isinstance(issue, Mapping):
                    lines.append(f"- [{issue['severity']}] {issue['code']}: {issue['message']}")
    return 0, "\n".join(lines)


def render_memory_inbox_text(
    inbox: Mapping[str, object],
    *,
    target: object,
    include_archived: bool = False,
) -> tuple[int, str]:
    lines = [f"Link memory inbox: {target}"]
    if inbox.get("project"):
        lines.append(f"Project: {inbox['project']}")
    if include_archived:
        lines.append("Including archived memories")
    lines.append("")
    review_count = int(inbox.get("review_count") or 0)
    lines.append(f"{review_count} memor{'y' if review_count == 1 else 'ies'} need review")
    counts = inbox.get("counts_by_severity")
    if isinstance(counts, Mapping) and counts:
        lines.append(f"Severity: {format_counts(counts)}")
    lines.append("")
    items = inbox.get("items", [])
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)) or not items:
        lines.append("Inbox is clear.")
        return 0, "\n".join(lines)

    for item in items:
        if not isinstance(item, Mapping):
            continue
        lines.append(f"- {item['title']} ({item['memory_type']} · {item['scope']} · {item['status']})")
        lines.append(f"  {item['path']}")
        issues = item.get("issues", [])
        if isinstance(issues, Sequence) and not isinstance(issues, (str, bytes)):
            for issue in issues:
                if isinstance(issue, Mapping):
                    lines.append(f"  [{issue['severity']}] {issue['code']}: {issue['message']}")
        primary = item.get("primary_action") if isinstance(item.get("primary_action"), Mapping) else {}
        if primary:
            lines.append(f"  Next: {primary['label']} - {primary['description']}")
            lines.append(f"  Command: {primary['command']}")
        actions = []
        raw_actions = item.get("actions", [])
        if isinstance(raw_actions, Sequence) and not isinstance(raw_actions, (str, bytes)):
            primary_kind = primary.get("kind") if primary else None
            actions = [
                action
                for action in raw_actions
                if isinstance(action, Mapping) and action.get("kind") != primary_kind
            ][:3]
        if actions:
            labels = ", ".join(str(action.get("label") or "") for action in actions)
            lines.append(f"  Other actions: {labels}")
    return 0, "\n".join(lines)


def render_explain_memory_text(explanation: Mapping[str, object]) -> tuple[int, str]:
    memory = explanation["memory"]
    recall_info = explanation["recall"]
    review = explanation["review"]
    provenance = explanation["provenance"]
    lifecycle = explanation["lifecycle"]
    graph = explanation["graph"]
    if not all(isinstance(value, Mapping) for value in (memory, recall_info, review, provenance, lifecycle, graph)):
        raise ValueError("Invalid memory explanation payload")

    lines = [
        f"Link memory explanation: {memory['title']}",
        "",
        f"Path: {memory['path']}",
        f"Type: {memory['memory_type']} · Scope: {memory['scope']} · Status: {lifecycle['status']}",
        f"Source: {provenance['source'] or 'missing'}",
        f"Captured: {provenance['date_captured'] or 'missing'}",
        f"Review: {review['status']} · Issues: {review['issue_count']}",
        f"Recall: {recall_info['state']} ({'enabled' if recall_info['default_enabled'] else 'disabled'} by default)",
        f"Reason: {recall_info['reason']}",
    ]
    summary = memory.get("tldr") or memory.get("snippet")
    if summary:
        lines.extend(["", f"Summary: {summary}"])
    issues = review.get("issues", [])
    if isinstance(issues, Sequence) and not isinstance(issues, (str, bytes)) and issues:
        lines.extend(["", "Review issues:"])
        for issue in issues:
            if isinstance(issue, Mapping):
                lines.append(f"- [{issue['severity']}] {issue['code']}: {issue['message']}")
                lines.append(f"  Action: {issue['suggested_action']}")
    forward = graph.get("forward") if isinstance(graph.get("forward"), Sequence) else []
    inbound = graph.get("inbound") if isinstance(graph.get("inbound"), Sequence) else []
    lines.extend([
        "",
        "Graph:",
        f"- Forward links: {', '.join(str(item) for item in forward) if forward else 'none'}",
        f"- Inbound links: {', '.join(str(item) for item in inbound) if inbound else 'none'}",
    ])
    log_entries = explanation.get("log_entries", [])
    if isinstance(log_entries, Sequence) and not isinstance(log_entries, (str, bytes)) and log_entries:
        lines.extend(["", "Recent lifecycle log:"])
        for entry in log_entries[-3:]:
            first_line = next((line for line in str(entry).splitlines() if line.strip().startswith("## ")), "")
            lines.append(f"- {first_line[3:] if first_line.startswith('## ') else first_line or 'log entry'}")
    return 0, "\n".join(lines)
