"""Shared memory logic for Link CLI, HTTP, and MCP runtimes."""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from .frontmatter import meta_tags, parse_frontmatter


MEMORY_TYPES = ("preference", "decision", "project", "fact", "note")
MEMORY_SCOPES = ("user", "project", "global")
MEMORY_REVIEW_STATUSES = ("pending", "reviewed", "needs_update")
MEMORY_PROPOSAL_MIN_SCORE = 70


def slugify(value: str, fallback: str = "memory") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def memory_title(text: str, explicit_title: str | None = None) -> str:
    if explicit_title and explicit_title.strip():
        return explicit_title.strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "Memory")
    first_sentence = re.split(r"(?<=[.!?])\s+", first_line, maxsplit=1)[0].strip()
    if len(first_sentence) <= 70:
        return first_sentence.rstrip(".")
    return first_sentence[:67].rstrip() + "..."


def memory_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if len(token) >= 3
    }


def compact_memory_text(value: str) -> str:
    return " ".join(
        token
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if token
    )


def slim_memory(record: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in record.items() if key != "body"}


def is_active_memory(record: Mapping[str, object]) -> bool:
    return str(record.get("status") or "active").lower() not in {"archived", "stale"}


def extract_tldr(body: str) -> str:
    match = re.search(r">\s*\*\*TLDR:\*\*\s*(.+)", body)
    return match.group(1).strip() if match else ""


def first_body_snippet(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith(">"):
            return stripped[:200]
    return ""


def _heading_title(body: str) -> str:
    match = re.search(r"^#\s+(.+)", body, re.MULTILINE)
    return match.group(1).strip() if match else ""


def memory_records(wiki_dir: Path, include_body: bool = True) -> list[dict[str, object]]:
    memories_dir = wiki_dir / "memories"
    if not memories_dir.exists():
        return []
    records: list[dict[str, object]] = []
    for path in sorted(memories_dir.rglob("*.md")):
        if path.name.startswith("."):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        meta, body = parse_frontmatter(text)
        title = meta.get("title") or _heading_title(body) or memory_title(body) or path.stem
        record: dict[str, object] = {
            "name": path.stem,
            "path": f"wiki/{path.relative_to(wiki_dir).as_posix()}",
            "title": title,
            "memory_type": meta.get("memory_type") or "note",
            "scope": meta.get("scope") or "user",
            "status": meta.get("status") or "active",
            "date_captured": meta.get("date_captured", ""),
            "updated_at": meta.get("updated_at", ""),
            "update_count": meta.get("update_count", "0"),
            "last_update_source": meta.get("last_update_source", ""),
            "archived_at": meta.get("archived_at", ""),
            "archive_reason": meta.get("archive_reason", ""),
            "restored_at": meta.get("restored_at", ""),
            "source": meta.get("source", ""),
            "review_status": meta.get("review_status") or "pending",
            "reviewed_at": meta.get("reviewed_at", ""),
            "review_note": meta.get("review_note", ""),
            "tags": meta_tags(meta.get("tags", "")),
            "tldr": extract_tldr(body),
            "snippet": first_body_snippet(body),
        }
        if include_body:
            record["body"] = body
        records.append(record)
    return records


def memory_review_issues(
    record: Mapping[str, object],
    review_command: str = "review-memory",
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    status = str(record.get("status") or "active").lower()
    review_status = str(record.get("review_status") or "pending").lower()
    memory_type = str(record.get("memory_type") or "")
    scope = str(record.get("scope") or "")

    if review_status in {"pending", "needs_review"}:
        issues.append({
            "code": "pending_review",
            "severity": "medium",
            "message": "Memory has not been reviewed by the user.",
            "suggested_action": f"Confirm it is still accurate, then run {review_command}.",
        })
    elif review_status == "needs_update":
        issues.append({
            "code": "needs_update",
            "severity": "high",
            "message": "Memory is marked as needing an update.",
            "suggested_action": "Edit the memory page or archive it if it is no longer useful.",
        })
    elif review_status not in MEMORY_REVIEW_STATUSES:
        issues.append({
            "code": "invalid_review_status",
            "severity": "high",
            "message": f"Unknown review_status: {review_status}.",
            "suggested_action": "Use pending, reviewed, or needs_update.",
        })

    if status == "stale":
        issues.append({
            "code": "stale_status",
            "severity": "high",
            "message": "Memory is marked stale and is excluded from default recall.",
            "suggested_action": "Archive it, restore it, or update the memory text.",
        })
    if memory_type not in MEMORY_TYPES:
        issues.append({
            "code": "invalid_memory_type",
            "severity": "high",
            "message": f"Unknown memory_type: {memory_type or 'missing'}.",
            "suggested_action": f"Use one of: {', '.join(MEMORY_TYPES)}.",
        })
    if scope not in MEMORY_SCOPES:
        issues.append({
            "code": "invalid_scope",
            "severity": "high",
            "message": f"Unknown scope: {scope or 'missing'}.",
            "suggested_action": f"Use one of: {', '.join(MEMORY_SCOPES)}.",
        })
    if not str(record.get("source") or "").strip():
        issues.append({
            "code": "missing_source",
            "severity": "medium",
            "message": "Memory has no source metadata.",
            "suggested_action": "Add source metadata so future agents know why this memory exists.",
        })
    if not str(record.get("date_captured") or "").strip():
        issues.append({
            "code": "missing_date_captured",
            "severity": "medium",
            "message": "Memory has no date_captured metadata.",
            "suggested_action": "Add the capture timestamp or recreate the memory.",
        })
    if not (str(record.get("tldr") or "").strip() or str(record.get("snippet") or "").strip()):
        issues.append({
            "code": "missing_summary",
            "severity": "medium",
            "message": "Memory has no usable summary.",
            "suggested_action": "Add a TLDR line or a clear first paragraph.",
        })
    return issues


def memory_inbox(
    records: Iterable[Mapping[str, object]],
    limit: int = 20,
    include_archived: bool = False,
    review_command: str = "review-memory",
) -> dict[str, object]:
    limit = max(1, min(limit, 50))
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    items: list[dict[str, object]] = []
    for record in records:
        if not include_archived and str(record.get("status") or "").lower() == "archived":
            continue
        issues = memory_review_issues(record, review_command=review_command)
        if not issues:
            continue
        item = slim_memory(record)
        item["issues"] = issues
        item["issue_count"] = len(issues)
        item["highest_severity"] = min(
            (issue["severity"] for issue in issues),
            key=lambda severity: severity_rank.get(severity, 9),
        )
        items.append(item)
    items.sort(key=lambda item: (
        severity_rank.get(str(item["highest_severity"]), 9),
        -int(item["issue_count"]),
        str(item.get("date_captured") or ""),
        str(item.get("title") or "").lower(),
    ))
    counts_by_severity: dict[str, int] = {}
    for item in items:
        severity = str(item["highest_severity"])
        counts_by_severity[severity] = counts_by_severity.get(severity, 0) + 1
    return {
        "review_count": len(items),
        "counts_by_severity": counts_by_severity,
        "include_archived": include_archived,
        "items": items[:limit],
    }


def count_values(records: Iterable[Mapping[str, object]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(field) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def top_tags(records: Iterable[Mapping[str, object]], limit: int = 12) -> list[dict[str, object]]:
    counts: dict[str, int] = {}
    skip = {"memory", *MEMORY_TYPES}
    for record in records:
        for tag in record.get("tags", []):
            tag_text = str(tag).strip()
            if not tag_text or tag_text in skip:
                continue
            counts[tag_text] = counts.get(tag_text, 0) + 1
    return [
        {"tag": tag, "count": count}
        for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def recent_memories(records: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    return sorted(
        (dict(record) for record in records),
        key=lambda record: (
            str(record.get("date_captured") or ""),
            str(record.get("title") or "").lower(),
        ),
        reverse=True,
    )


def memory_profile(
    records: Iterable[Mapping[str, object]],
    limit: int = 10,
    review_command: str = "review-memory",
) -> dict[str, object]:
    limit = max(1, min(limit, 50))
    record_list = [dict(record) for record in records]
    active_records = [record for record in record_list if is_active_memory(record)]
    archived_records = [
        record for record in record_list
        if str(record.get("status") or "").lower() == "archived"
    ]
    recent = [slim_memory(record) for record in recent_memories(active_records)]

    def typed(memory_type: str) -> list[dict[str, object]]:
        return [
            slim_memory(record)
            for record in recent_memories(active_records)
            if str(record.get("memory_type") or "") == memory_type
        ][:limit]

    return {
        "memory_count": len(record_list),
        "active_count": len(active_records),
        "review_count": memory_inbox(record_list, limit=limit, review_command=review_command)["review_count"],
        "by_type": count_values(record_list, "memory_type"),
        "by_scope": count_values(record_list, "scope"),
        "by_status": count_values(record_list, "status"),
        "top_tags": top_tags(record_list),
        "recent": recent[:limit],
        "preferences": typed("preference"),
        "decisions": typed("decision"),
        "projects": typed("project"),
        "archived": [slim_memory(record) for record in recent_memories(archived_records)][:limit],
    }


def score_memory(record: Mapping[str, object], query: str) -> int:
    q = query.lower().strip()
    tokens = [token for token in re.split(r"\W+", q) if len(token) >= 3]
    title = str(record.get("title", "")).lower()
    tldr = str(record.get("tldr", "")).lower()
    body = str(record.get("body", "")).lower()
    tags = " ".join(str(tag).lower() for tag in record.get("tags", []))
    score = 0
    if q and q in title:
        score += 20
    if q and q in tldr:
        score += 12
    if q and q in tags:
        score += 8
    if q and q in body:
        score += 4
    for token in tokens:
        if token in title:
            score += 6
        if token in tldr:
            score += 4
        if token in tags:
            score += 3
        if token in body:
            score += 1
    return score


def recall_memories(
    records: Iterable[Mapping[str, object]],
    query: str,
    limit: int = 10,
    include_archived: bool = False,
) -> list[dict[str, object]]:
    q = query.strip()
    if not q:
        return []
    scored: list[tuple[int, dict[str, object]]] = []
    for record in records:
        if not include_archived and not is_active_memory(record):
            continue
        score = score_memory(record, q)
        if score > 0:
            slim = slim_memory(record)
            slim["score"] = score
            scored.append((score, slim))
    scored.sort(key=lambda item: (-item[0], str(item[1]["title"]).lower()))
    return [record for _, record in scored[:limit]]


def memory_duplicate_candidates(
    records: Iterable[Mapping[str, object]],
    text: str,
    title: str | None,
    memory_type: str,
    scope: str,
    limit: int = 3,
) -> list[dict[str, object]]:
    title_value = memory_title(text, title)
    new_slug = slugify(title_value)
    new_title = compact_memory_text(title_value)
    new_body = compact_memory_text(text)
    new_tokens = memory_tokens(f"{title_value} {text}")
    candidates: list[tuple[int, dict[str, object]]] = []

    for record in records:
        if not is_active_memory(record):
            continue
        reasons: list[str] = []
        score = 0
        record_title = compact_memory_text(str(record.get("title") or ""))
        record_text = compact_memory_text(
            " ".join(
                str(record.get(field) or "")
                for field in ("title", "tldr", "snippet", "body")
            )
        )
        record_tokens = memory_tokens(record_text)

        if str(record.get("name") or "") == new_slug:
            score = max(score, 100)
            reasons.append("same_slug")
        if new_title and record_title == new_title:
            score = max(score, 96)
            reasons.append("same_title")
        if len(new_body) >= 40 and new_body in record_text:
            score = max(score, 94)
            reasons.append("same_memory_text")

        overlap = sorted(new_tokens & record_tokens)
        union = new_tokens | record_tokens
        overlap_ratio = (len(overlap) / len(union)) if union else 0.0
        same_kind = (
            str(record.get("memory_type") or "") == memory_type
            and str(record.get("scope") or "") == scope
        )
        if same_kind and len(overlap) >= 5 and overlap_ratio >= 0.72:
            score = max(score, min(92, int(70 + overlap_ratio * 25)))
            reasons.append("high_token_overlap")

        if score < 85:
            continue
        candidate = slim_memory(record)
        candidate["duplicate_score"] = min(score, 100)
        candidate["duplicate_reasons"] = reasons
        candidate["matching_terms"] = overlap[:12]
        candidates.append((int(candidate["duplicate_score"]), candidate))

    candidates.sort(key=lambda item: (-item[0], str(item[1]["title"]).lower()))
    return [candidate for _, candidate in candidates[:limit]]


def memory_proposal_segments(text: str) -> list[str]:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    segments: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", line).strip()
        line = re.sub(r"^(?:user|human|me|assistant|codex|agent)\s*:\s*", "", line, flags=re.IGNORECASE)
        if not line:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            sentence = sentence.strip()
            if 18 <= len(sentence) <= 500:
                segments.append(sentence)
    return segments


def normalize_proposed_memory(text: str, memory_type: str) -> str:
    value = text.strip()
    value = re.sub(r"^please remember(?: that)?\s+", "", value, flags=re.IGNORECASE)
    replacements = [
        (r"^i prefer\b", "User prefers"),
        (r"^i like\b", "User likes"),
        (r"^i want\b", "User wants"),
        (r"^i need\b", "User needs"),
        (r"^i do not want\b", "User does not want"),
        (r"^i don't want\b", "User does not want"),
        (r"^i am\b", "User is"),
        (r"^i work\b", "User works"),
        (r"^my\b", "User's"),
        (r"^we decided\b", "Project decided"),
        (r"^we agreed\b", "Project agreed"),
        (r"^we chose\b", "Project chose"),
        (r"^we settled\b", "Project settled"),
    ]
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value, count=1, flags=re.IGNORECASE)
    if memory_type == "decision" and value.lower().startswith("decision:"):
        value = value.split(":", 1)[1].strip()
        value = "Project decided " + value[0].lower() + value[1:] if value else "Project decision"
    if value and value[-1] not in ".!?":
        value += "."
    return value


def proposal_title(memory: str, memory_type: str) -> str:
    title = memory.strip().rstrip(".")
    title = re.sub(r"^(?:User|Project|Team)\s+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^prefers\b", "Prefer", title, flags=re.IGNORECASE)
    title = re.sub(r"^wants\b", "Want", title, flags=re.IGNORECASE)
    title = re.sub(r"^needs\b", "Need", title, flags=re.IGNORECASE)
    title = re.sub(r"^decided(?: to)?\b", "Decision:", title, flags=re.IGNORECASE)
    title = re.sub(r"^agreed(?: to)?\b", "Decision:", title, flags=re.IGNORECASE)
    title = re.sub(r"^chose\b", "Decision:", title, flags=re.IGNORECASE)
    if memory_type == "project" and not title.lower().startswith("project"):
        title = f"Project {title[0].lower()}{title[1:]}" if title else "Project memory"
    if len(title) <= 70:
        return title or "Memory proposal"
    return title[:67].rstrip() + "..."


def classify_memory_segment(segment: str) -> dict[str, object] | None:
    text = segment.strip()
    lower = text.lower()
    if any(cue in lower for cue in ("maybe", "might", "not sure", "wondering", "considering", "could later")):
        return None

    checks: list[tuple[str, str, int, str, tuple[str, ...]]] = [
        (
            "preference",
            "user",
            90,
            "Matched an explicit user preference cue.",
            (
                r"\b(?:i|user|human)\s+(?:prefer|prefers|like|likes|want|wants|need|needs)\b",
                r"\b(?:please\s+)?(?:always|never|avoid|do not|don't)\b",
                r"\bagents?\s+should\s+(?:always|never|prefer|avoid|use)\b",
            ),
        ),
        (
            "decision",
            "project",
            88,
            "Matched an explicit decision cue.",
            (
                r"\b(?:we|project|team|user)\s+(?:decided|agreed|chose|settled)\b",
                r"\bdecision\s*:",
            ),
        ),
        (
            "project",
            "project",
            76,
            "Matched a project context cue.",
            (
                r"\b(?:project|repo|repository|link)\s+(?:uses|requires|runs|stores|keeps|ships|releases)\b",
                r"\b(?:this project|this repo)\s+(?:uses|requires|keeps|stores)\b",
            ),
        ),
        (
            "fact",
            "user",
            74,
            "Matched a stable user fact cue.",
            (
                r"\b(?:i am|i work|user is|user works|user has|my role|my timezone)\b",
            ),
        ),
    ]

    for memory_type, scope, score, reason, patterns in checks:
        if any(re.search(pattern, lower) for pattern in patterns):
            memory = normalize_proposed_memory(text, memory_type)
            return {
                "memory": memory,
                "memory_type": memory_type,
                "scope": scope,
                "confidence_score": score,
                "reason": reason,
            }
    return None


def confidence_label(score: int) -> str:
    if score >= 85:
        return "high"
    if score >= 70:
        return "medium"
    return "low"


def propose_memories_from_text(
    text: str,
    records: Iterable[Mapping[str, object]],
    source: str = "inline",
    limit: int = 10,
    writes_memory: bool = False,
) -> dict[str, object]:
    proposals: list[dict[str, object]] = []
    seen: set[str] = set()
    skipped = 0
    for segment in memory_proposal_segments(text):
        classified = classify_memory_segment(segment)
        if not classified:
            skipped += 1
            continue
        score = int(classified["confidence_score"])
        if score < MEMORY_PROPOSAL_MIN_SCORE:
            skipped += 1
            continue
        memory = str(classified["memory"])
        dedupe_key = compact_memory_text(memory)
        if dedupe_key in seen:
            skipped += 1
            continue
        seen.add(dedupe_key)
        memory_type = str(classified["memory_type"])
        scope = str(classified["scope"])
        title = proposal_title(memory, memory_type)
        duplicate_candidates = memory_duplicate_candidates(
            records,
            memory,
            title,
            memory_type,
            scope,
        )
        proposals.append({
            "title": title,
            "memory": memory,
            "memory_type": memory_type,
            "scope": scope,
            "confidence": confidence_label(score),
            "confidence_score": score,
            "reason": classified["reason"],
            "source": source,
            "duplicate_candidates": duplicate_candidates,
            "suggested_action": "update-memory" if duplicate_candidates else "remember",
        })
        if len(proposals) >= limit:
            break
    return {
        "proposed": True,
        "source": source,
        "count": len(proposals),
        "skipped_count": skipped,
        "proposals": proposals,
        "writes_memory": writes_memory,
    }
