"""Shared memory proposal logic for Link CLI, HTTP, and MCP runtimes."""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping


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
