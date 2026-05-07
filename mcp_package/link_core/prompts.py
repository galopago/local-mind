"""Shared first-run prompt helpers for Link."""
from __future__ import annotations

from pathlib import Path

from .memory import default_project_for_target


def starter_prompt_payload(target: Path, project: str | None = None) -> dict[str, object]:
    """Return natural agent prompts and local checks for a Link user."""
    target = target.expanduser().resolve()
    project_name = project if project is not None else default_project_for_target(target)
    remember_prompt = (
        "remember that this project uses Link for local agent memory"
        if project_name
        else "remember that I prefer local-first agent memory"
    )
    query_prompt = (
        "query Link for what this project remembers"
        if project_name
        else "query Link for what you know about me"
    )
    prompts = [
        {
            "label": "Check readiness",
            "prompt": "is Link ready?",
            "when": "right after install or before troubleshooting",
        },
        {
            "label": "Prime memory",
            "prompt": "brief me from Link before we continue",
            "when": "at the start of a session or task",
        },
        {
            "label": "Save explicit memory",
            "prompt": remember_prompt,
            "when": "when you want future agents to remember a preference, decision, or project fact",
        },
        {
            "label": "Ask with context",
            "prompt": query_prompt,
            "when": "when you want a compact answer-ready packet from memory and wiki context",
        },
        {
            "label": "Ingest a source",
            "prompt": "ingest raw/<file> into Link",
            "when": "after dropping a source file into raw/",
        },
        {
            "label": "Review memory proposals",
            "prompt": "propose memories from raw/<file>",
            "when": "when a source may contain preferences, decisions, or project context",
        },
    ]
    return {
        "target": str(target),
        "project": project_name,
        "prompts": prompts,
        "commands": [
            "link status --validate",
            "link ingest-status",
            "link memory-inbox",
            'link benchmark "agent memory"',
        ],
    }
