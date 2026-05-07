"""Smart query packet construction for Link agents.

This module keeps retrieval planning shared across CLI, HTTP, and MCP. It does
not answer the user directly; it returns a compact, source-backed packet an
agent can read before answering.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .memory import (
    memory_brief,
    normalize_project,
    recall_memories,
)
from .wiki import context_for_topic, search_pages


BUDGETS: dict[str, dict[str, int]] = {
    "small": {
        "memories": 3,
        "search_results": 4,
        "context_pages": 3,
        "primary_chars": 1200,
        "neighbor_chars": 450,
    },
    "medium": {
        "memories": 6,
        "search_results": 6,
        "context_pages": 5,
        "primary_chars": 2400,
        "neighbor_chars": 700,
    },
    "large": {
        "memories": 10,
        "search_results": 10,
        "context_pages": 8,
        "primary_chars": 5000,
        "neighbor_chars": 1200,
    },
}


def normalize_budget(value: str | None) -> str:
    budget = (value or "medium").strip().lower()
    return budget if budget in BUDGETS else "medium"


def _trim_text(value: object, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def _memory_reason(memory: Mapping[str, object]) -> str:
    parts = ["matched the query"]
    recall = memory.get("recall")
    if isinstance(recall, Mapping):
        state = str(recall.get("state") or "")
        if state and state != "ready":
            parts.append(f"recall state: {state}")
        elif state == "ready":
            parts.append("recall-ready")
    if str(memory.get("review_status") or "").lower() == "reviewed":
        parts.append("reviewed")
    if memory.get("project"):
        parts.append(f"project: {memory['project']}")
    return "; ".join(parts)


def _page_reason(page: Mapping[str, object]) -> str:
    relationship = str(page.get("relationship") or "")
    if relationship == "primary":
        return "best matching wiki page"
    if relationship == "inbound":
        return "links to the primary page"
    if relationship == "forward":
        return "linked from the primary page"
    return "related wiki page"


def _compact_memory(memory: Mapping[str, object]) -> dict[str, object]:
    item = {
        "kind": "memory",
        "name": memory.get("name", ""),
        "title": memory.get("title", ""),
        "memory_type": memory.get("memory_type", ""),
        "scope": memory.get("scope", ""),
        "project": memory.get("project", ""),
        "status": memory.get("status", ""),
        "review_status": memory.get("review_status", ""),
        "summary": memory.get("tldr") or memory.get("snippet") or "",
        "score": memory.get("score", 0),
        "rank_score": memory.get("rank_score", 0),
        "recall": memory.get("recall", {}),
        "review_issue_count": memory.get("review_issue_count", 0),
        "highest_review_severity": memory.get("highest_review_severity", "none"),
        "why_selected": _memory_reason(memory),
    }
    return {key: value for key, value in item.items() if value not in ("", [], {})}


def _compact_page(page: Mapping[str, object], primary_chars: int, neighbor_chars: int) -> dict[str, object]:
    relationship = str(page.get("relationship") or "")
    max_chars = primary_chars if relationship == "primary" else neighbor_chars
    return {
        "kind": "page",
        "name": page.get("name", ""),
        "title": page.get("title", ""),
        "type": page.get("type", ""),
        "relationship": relationship,
        "is_primary": bool(page.get("is_primary")),
        "content": _trim_text(page.get("content", ""), max_chars),
        "why_selected": _page_reason(page),
    }


def _compact_search_result(page: Mapping[str, object]) -> dict[str, object]:
    return {
        "name": page.get("name", ""),
        "title": page.get("title", ""),
        "type": page.get("type", ""),
        "category": page.get("category", ""),
        "score": page.get("score", 0),
        "snippet": page.get("snippet", ""),
    }


def _compact_review(review: object, limit: int) -> dict[str, object]:
    if not isinstance(review, Mapping):
        return {"count": 0, "counts_by_severity": {}, "items": []}
    items = []
    for item in list(review.get("items", []))[:limit]:
        if not isinstance(item, Mapping):
            continue
        primary_action = item.get("primary_action")
        action_kind = ""
        if isinstance(primary_action, Mapping):
            action_kind = str(primary_action.get("kind") or "")
        items.append({
            "name": item.get("name", ""),
            "title": item.get("title", ""),
            "memory_type": item.get("memory_type", ""),
            "scope": item.get("scope", ""),
            "issue_count": item.get("issue_count", 0),
            "highest_severity": item.get("highest_severity", "none"),
            "primary_action": action_kind,
        })
    return {
        "count": review.get("count", 0),
        "counts_by_severity": review.get("counts_by_severity", {}),
        "items": items,
    }


def _next_budget(current: str) -> str:
    order = ["small", "medium", "large"]
    try:
        index = order.index(current)
    except ValueError:
        return "medium"
    return order[min(index + 1, len(order) - 1)]


def _budget_item(selected: int, limit: int, has_more: bool) -> dict[str, object]:
    return {
        "selected": selected,
        "limit": limit,
        "has_more": has_more,
    }


def _estimated_json_chars(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _estimated_tokens(chars: int) -> int:
    # Practical rough count for agent budgeting; exact tokenizers vary by model.
    return max(1, (chars + 3) // 4) if chars else 0


def _context_packet_budget_item(packet: list[dict[str, object]], limit: int) -> dict[str, object]:
    chars = _estimated_json_chars(packet)
    item = _budget_item(len(packet), limit, False)
    item["estimated_chars"] = chars
    item["estimated_tokens"] = _estimated_tokens(chars)
    return item


def _follow_up_actions(
    query: str,
    budget_name: str,
    project: str,
    primary: object,
    budget_report: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    if any(bool(section.get("has_more")) for section in budget_report.values()):
        next_budget = _next_budget(budget_name)
        if next_budget != budget_name:
            args: dict[str, object] = {"query": query, "budget": next_budget}
            if project:
                args["project"] = project
            actions.append({
                "when": "packet is relevant but too thin",
                "tool": "query_link",
                "arguments": args,
            })
    if primary:
        actions.append({
            "when": "need the full source-backed topic neighborhood",
            "tool": "get_context",
            "arguments": {"topic": primary},
        })
    actions.append({
        "when": "need a different angle or exact page candidates",
        "tool": "search_wiki",
        "arguments": {"query": query, "limit": 10},
    })
    return actions


def query_link(
    wiki_dir: Path,
    query: str,
    cache: dict[str, Any],
    records: Iterable[Mapping[str, object]],
    *,
    budget: str = "medium",
    project: str | None = None,
    review_command: str = "review-memory",
) -> dict[str, object]:
    """Return a compact context packet for an agent query.

    The packet combines relevant local memory, ranked wiki search results, and
    graph-neighborhood context without forcing the agent to read the whole wiki.
    """
    q = str(query or "").strip()
    budget_name = normalize_budget(budget)
    limits = BUDGETS[budget_name]
    project_name = normalize_project(project)
    record_list = list(records)

    if not q:
        return {
            "query": "",
            "project": project_name,
            "budget": budget_name,
            "found": False,
            "error": "query required",
            "context_packet": [],
        }

    raw_memories = recall_memories(
        record_list,
        q,
        limit=limits["memories"] + 1,
        project=project_name,
    )
    memory_has_more = len(raw_memories) > limits["memories"]
    memories = [_compact_memory(memory) for memory in raw_memories[: limits["memories"]]]
    brief = memory_brief(
        record_list,
        query=q,
        limit=limits["memories"],
        review_command=review_command,
        project=project_name,
    )
    raw_search_results = search_pages(q, cache, limit=limits["search_results"] + 1)
    search_has_more = len(raw_search_results) > limits["search_results"]
    search_results = raw_search_results[: limits["search_results"]]
    context = context_for_topic(
        wiki_dir,
        q,
        cache,
        limit=limits["context_pages"] + 1,
    )
    raw_context_pages = [page for page in context.get("pages", []) if isinstance(page, Mapping)]
    context_has_more = len(raw_context_pages) > limits["context_pages"]
    pages = [
        _compact_page(page, limits["primary_chars"], limits["neighbor_chars"])
        for page in raw_context_pages[: limits["context_pages"]]
    ]
    packet = [*memories, *pages]
    mode_parts = []
    if memories:
        mode_parts.append("memory")
    if pages:
        mode_parts.append("wiki")
    mode = "+".join(mode_parts) if mode_parts else "none"

    guidance = [
        "Use this packet before answering; do not read the whole wiki unless this packet is insufficient.",
        "Prefer recall-ready reviewed memories for personalization and source-backed wiki pages for factual claims.",
        "If important context appears missing, rerun query_link with a larger budget or call get_context on the primary page.",
        "Do not create or update memory from this packet unless the user explicitly asks.",
    ]
    review = _compact_review(brief.get("review", {}), limit=limits["memories"])
    if review.get("count"):
        guidance.insert(2, "Some memories need review; treat provisional memories carefully.")
    budget_report = {
        "memories": _budget_item(len(memories), limits["memories"], memory_has_more),
        "wiki_search": _budget_item(len(search_results), limits["search_results"], search_has_more),
        "graph_context": _budget_item(len(pages), limits["context_pages"], context_has_more),
        "context_packet": _context_packet_budget_item(packet, limits["memories"] + limits["context_pages"]),
    }
    if any(bool(section.get("has_more")) for section in budget_report.values()):
        guidance.insert(1, "This packet is budget-limited; use follow_up instead of scanning files manually.")

    return {
        "query": q,
        "project": project_name,
        "budget": budget_name,
        "found": bool(packet or search_results),
        "strategy": {
            "mode": mode,
            "selection": "budgeted memory + ranked wiki + graph neighborhood",
            "limits": limits,
        },
        "budget_report": budget_report,
        "follow_up": _follow_up_actions(
            q,
            budget_name,
            project_name,
            context.get("primary", ""),
            budget_report,
        ),
        "memory": {
            "count": len(memories),
            "review": review,
            "items": memories,
        },
        "wiki": {
            "found": bool(context.get("found")),
            "primary": context.get("primary", ""),
            "inbound_count": context.get("inbound_count", 0),
            "forward_count": context.get("forward_count", 0),
            "search_count": len(search_results),
            "search_results": [_compact_search_result(page) for page in search_results],
            "pages": pages,
        },
        "context_packet": packet,
        "agent_guidance": guidance,
    }
