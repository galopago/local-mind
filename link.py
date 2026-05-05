#!/usr/bin/env python3
"""Small Link command runner.

Usage:
  python link.py demo [target]
  python link.py doctor [target]
  python link.py ingest-status [target]
  python link.py remember "memory text" [target]
  python link.py propose-memories <file-or-text> [target]
  python link.py update-memory <name-or-title> "new memory text" [target]
  python link.py recall "query" [target]
  python link.py profile [target]
  python link.py archive-memory <name-or-title> [target]
  python link.py restore-memory <name-or-title> [target]
  python link.py memory-inbox [target]
  python link.py review-memory <name-or-title> [target]
  python link.py explain-memory <name-or-title> [target]
  python link.py rebuild-backlinks [target]
  python link.py verify-mcp [target]
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parent
DEFAULT_DEMO_DIR = "link-demo"
DEMO_MARKER = ".link-demo"
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
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
SECRET_VALUE_PATTERNS = (
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("OpenAI API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("AWS access key", re.compile(r"\bA[SK]IA[0-9A-Z]{16}\b")),
    ("PyPI token", re.compile(r"\bpypi-[A-Za-z0-9_-]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("Stripe live secret key", re.compile(r"\bsk_live_[A-Za-z0-9]{20,}\b")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)
SKIP_SCAN_DIRS = {
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
MEMORY_TYPES = ("preference", "decision", "project", "fact", "note")
MEMORY_SCOPES = ("user", "project", "global")
MEMORY_REVIEW_STATUSES = ("pending", "reviewed", "needs_update")

_BUNDLED_CORE = ROOT / "mcp_package"
if (_BUNDLED_CORE / "link_core").exists():
    sys.path.insert(0, str(_BUNDLED_CORE))

from link_core.memory import (
    memory_duplicate_candidates as _core_memory_duplicate_candidates,
    propose_memories_from_text as _core_propose_memories_from_text,
)
del _BUNDLED_CORE


DEMO_FILES: dict[str, str] = {
    "raw/agent-memory-session.md": """---
title: "Agent memory session"
source_type: demo-note
date_captured: 2026-05-02
author: Link demo
tags: [agents, memory, local-first]
---

# Agent memory session

An AI coding agent keeps losing project context between sessions. The team wants durable memory that is local, inspectable, and easy to cite.

Key decisions:

- Keep raw source notes immutable.
- Compile sources into durable wiki pages.
- Use [[agent-memory]] as the interface between past work and future agents.
- Prefer [[local-first-software]] so the knowledge base stays under user control.
- Expose context through MCP so agents can retrieve graph neighborhoods instead of reading every file.
""",
    "raw/transformer-reading-notes.md": """---
title: "Transformer reading notes"
source_type: demo-note
date_captured: 2026-05-02
author: Link demo
tags: [ai, transformers, retrieval]
---

# Transformer reading notes

Transformers made long-context sequence modeling practical by replacing recurrence with attention. Modern LLM systems often pair transformer models with external retrieval.

Connections:

- [[transformers]] provide the model architecture.
- [[retrieval-augmented-generation]] provides fresh or private context.
- [[agent-memory]] gives agents persistent project knowledge outside a single chat.
""",
    "raw/local-release-notes.md": """---
title: "Local release notes"
source_type: demo-note
date_captured: 2026-05-02
author: Link demo
tags: [release, graph, mcp]
---

# Local release notes

The product team ships a local wiki viewer, MCP server, and graph view. The release focuses on making agent memory visible and auditable.

Notable changes:

- [[link]] exposes search, context, backlinks, and graph tools.
- [[knowledge-graph]] shows concepts, sources, and entities as connected pages.
- [[local-first-software]] keeps the source material on disk.
""",
    "wiki/sources/agent-memory-session.md": """---
type: source
title: "Agent memory session"
author: "Link demo"
date_published: "2026-05-02"
date_ingested: "2026-05-02"
source_url: "local demo note"
tags: [agents, memory, local-first]
confidence: high
aliases: ["memory demo note"]
---

# Agent memory session

> **TLDR:** A demo note about turning local project sources into durable context for future agents.

## Summary

The source describes an AI coding workflow where an agent repeatedly loses project context between sessions. It proposes raw source notes, compiled wiki pages, and MCP retrieval as a durable memory layer. *Source: [[agent-memory-session]]* `[confidence: high]`

The note emphasizes local control and inspectability. Raw sources stay immutable, while generated wiki pages become the maintained knowledge layer. *Source: [[agent-memory-session]]* `[confidence: high]`

## Key Claims

- **Agent memory should be durable** so future sessions can recover project context. `[confidence: high]`
- **Raw notes should remain immutable** while wiki pages evolve. `[confidence: high]`
- **MCP makes memory agent-readable** through structured tools instead of ad hoc file scans. `[confidence: high]`

## Connections

- Defines a need for [[agent-memory]].
- Supports [[local-first-software]] as the storage model.
- Connects [[link]] to agent workflows through MCP.

## Raw Source

`raw/agent-memory-session.md`
""",
    "wiki/sources/transformer-reading-notes.md": """---
type: source
title: "Transformer reading notes"
author: "Link demo"
date_published: "2026-05-02"
date_ingested: "2026-05-02"
source_url: "local demo note"
tags: [ai, transformers, retrieval]
confidence: high
aliases: ["transformer demo note"]
---

# Transformer reading notes

> **TLDR:** A demo note linking transformers, retrieval, and persistent agent memory.

## Summary

The source frames [[transformers]] as the architecture behind modern LLM systems and connects them to external retrieval. It treats retrieval and memory as practical complements to model context. *Source: [[transformer-reading-notes]]* `[confidence: high]`

The note links [[retrieval-augmented-generation]] to [[agent-memory]] because both bring outside context into model workflows. *Source: [[transformer-reading-notes]]* `[confidence: high]`

## Key Claims

- **Transformers replaced recurrence with attention** for sequence modeling. `[confidence: high]`
- **External retrieval complements LLM context** when information is fresh, private, or project-specific. `[confidence: high]`
- **Persistent agent memory stores knowledge outside one chat session.** `[confidence: high]`

## Connections

- Explains why [[transformers]] matter to LLM systems.
- Connects [[retrieval-augmented-generation]] to persistent context.
- Supports [[agent-memory]] as a local retrieval layer.

## Raw Source

`raw/transformer-reading-notes.md`
""",
    "wiki/sources/local-release-notes.md": """---
type: source
title: "Local release notes"
author: "Link demo"
date_published: "2026-05-02"
date_ingested: "2026-05-02"
source_url: "local demo note"
tags: [release, graph, mcp]
confidence: high
aliases: ["demo release note"]
---

# Local release notes

> **TLDR:** A demo release note showing Link as a local wiki viewer, graph, and MCP memory server.

## Summary

The source describes a release centered on making agent memory visible and auditable. It identifies a local wiki viewer, MCP server, and graph view as the main product surfaces. *Source: [[local-release-notes]]* `[confidence: high]`

The note connects [[link]] with [[knowledge-graph]] and [[local-first-software]], showing how local markdown can become both a human-readable wiki and agent-readable memory. *Source: [[local-release-notes]]* `[confidence: high]`

## Key Claims

- **Link exposes search, context, backlinks, and graph tools.** `[confidence: high]`
- **Graph views make relationships inspectable.** `[confidence: high]`
- **Local-first storage keeps source material under user control.** `[confidence: high]`

## Connections

- Describes [[link]] product surfaces.
- Connects [[knowledge-graph]] to visible agent memory.
- Supports [[local-first-software]] as the privacy model.

## Raw Source

`raw/local-release-notes.md`
""",
    "wiki/concepts/agent-memory.md": """---
type: concept
title: "Agent memory"
aliases: ["AI memory", "agent context", "durable context"]
date_created: "2026-05-02"
date_updated: "2026-05-02"
source_count: 2
tags: [agents, memory, mcp]
maturity: growing
---

# Agent memory

> **TLDR:** Agent memory is durable, inspectable context that lets AI agents recover prior project knowledge across sessions.

## Overview

Agent memory addresses a common failure mode in AI workflows: each new session starts without the full project history. In Link, memory is stored as markdown wiki pages compiled from immutable raw sources. *Source: [[agent-memory-session]]* `[confidence: high]`

This memory is useful because agents can query a focused topic and receive the primary page plus related graph context. That is more efficient than reading every source file. *Source: [[transformer-reading-notes]]* `[confidence: high]`

## How It Works

1. A user drops source material into `raw/`.
2. An agent compiles durable pages into `wiki/`.
3. Link builds search indexes and backlinks.
4. MCP tools return focused graph context to future agents.

## Key Facts

- **Agent memory should be durable** so future sessions can recover project context. *Source: [[agent-memory-session]]* `[confidence: high]`
- **MCP makes memory agent-readable** through structured tools. *Source: [[agent-memory-session]]* `[confidence: high]`
- **Persistent memory complements LLM context windows** by storing knowledge outside a single chat. *Source: [[transformer-reading-notes]]* `[confidence: high]`

## Open Questions

- Which memories should be promoted from raw notes into stable wiki pages?
- How should agents detect stale project decisions?

## Related

- [[link]] - provides the local wiki and MCP layer.
- [[retrieval-augmented-generation]] - retrieves external context for model workflows.
- [[local-first-software]] - keeps memory under user control.

## Sources

- [[agent-memory-session]]
- [[transformer-reading-notes]]
""",
    "wiki/concepts/retrieval-augmented-generation.md": """---
type: concept
title: "Retrieval-augmented generation"
aliases: ["RAG", "retrieval augmented generation"]
date_created: "2026-05-02"
date_updated: "2026-05-02"
source_count: 1
tags: [ai, retrieval, context]
maturity: seed
---

# Retrieval-augmented generation

> **TLDR:** Retrieval-augmented generation brings external context into model workflows before generation.

## Overview

Retrieval-augmented generation pairs a model with a retrieval layer. Instead of relying only on model weights or the current chat, a system fetches relevant external context first. *Source: [[transformer-reading-notes]]* `[confidence: high]`

In Link, the retrieval layer is a local markdown wiki exposed through search, context, backlinks, and graph tools. This makes [[agent-memory]] inspectable instead of hidden in a proprietary store. *Source: [[transformer-reading-notes]]* `[confidence: high]`

## Key Facts

- **External retrieval complements LLM context** when information is fresh, private, or project-specific. *Source: [[transformer-reading-notes]]* `[confidence: high]`
- **Persistent memory can be modeled as retrieval** over durable local pages. *Source: [[transformer-reading-notes]]* `[confidence: high]`

## Related

- [[agent-memory]] - a local memory use case for retrieval.
- [[transformers]] - the model architecture that often consumes retrieved context.
- [[link]] - provides the local retrieval surface.

## Sources

- [[transformer-reading-notes]]
""",
    "wiki/concepts/transformers.md": """---
type: concept
title: "Transformers"
aliases: ["transformer architecture", "LLM architecture"]
date_created: "2026-05-02"
date_updated: "2026-05-02"
source_count: 1
tags: [ai, models, attention]
maturity: seed
---

# Transformers

> **TLDR:** Transformers are neural architectures that use attention to model relationships across sequences.

## Overview

Transformers are presented in the demo source as the architecture behind many modern LLM systems. They made long-context sequence modeling practical by replacing recurrence with attention. *Source: [[transformer-reading-notes]]* `[confidence: high]`

The source connects transformers to [[retrieval-augmented-generation]] because modern LLM workflows often combine model context with retrieved project or domain knowledge. *Source: [[transformer-reading-notes]]* `[confidence: high]`

## Key Facts

- **Transformers use attention for sequence modeling.** *Source: [[transformer-reading-notes]]* `[confidence: high]`
- **Transformer systems often benefit from retrieved context.** *Source: [[transformer-reading-notes]]* `[confidence: high]`

## Related

- [[retrieval-augmented-generation]] - supplies outside context to model workflows.
- [[agent-memory]] - stores project context for future sessions.

## Sources

- [[transformer-reading-notes]]
""",
    "wiki/concepts/local-first-software.md": """---
type: concept
title: "Local-first software"
aliases: ["local first", "local-first"]
date_created: "2026-05-02"
date_updated: "2026-05-02"
source_count: 2
tags: [privacy, storage, software]
maturity: growing
---

# Local-first software

> **TLDR:** Local-first software keeps user data on disk in formats the user can inspect, back up, and move.

## Overview

Local-first software is a product design choice where the user's data remains directly accessible on their machine. In the demo sources, this matters because [[agent-memory]] can contain project decisions and source notes. *Source: [[agent-memory-session]]* `[confidence: high]`

Link follows this model by storing raw sources and wiki pages as markdown files. The graph and MCP server read those files rather than sending them to a hosted backend. *Source: [[local-release-notes]]* `[confidence: high]`

## Key Facts

- **Raw notes stay immutable** while generated wiki pages evolve. *Source: [[agent-memory-session]]* `[confidence: high]`
- **Local markdown keeps memory inspectable.** *Source: [[local-release-notes]]* `[confidence: high]`

## Related

- [[link]] - implements local-first agent memory.
- [[agent-memory]] - benefits from local, inspectable storage.
- [[knowledge-graph]] - visualizes local wiki relationships.

## Sources

- [[agent-memory-session]]
- [[local-release-notes]]
""",
    "wiki/concepts/knowledge-graph.md": """---
type: concept
title: "Knowledge graph"
aliases: ["graph view", "wiki graph"]
date_created: "2026-05-02"
date_updated: "2026-05-02"
source_count: 1
tags: [graph, wiki, visualization]
maturity: seed
---

# Knowledge graph

> **TLDR:** A knowledge graph shows wiki pages as nodes and wikilinks as relationships.

## Overview

In Link, the knowledge graph makes relationships between sources, concepts, and entities visible. This helps users inspect what an agent has connected and where a claim came from. *Source: [[local-release-notes]]* `[confidence: high]`

The graph supports the same mental model as MCP context retrieval: a topic is not isolated, it lives in a neighborhood of related pages. *Source: [[local-release-notes]]* `[confidence: high]`

## Key Facts

- **Graph views make relationships inspectable.** *Source: [[local-release-notes]]* `[confidence: high]`
- **Wikilinks provide the graph edges.** *Source: [[local-release-notes]]* `[confidence: high]`

## Related

- [[link]] - renders the graph.
- [[agent-memory]] - uses graph context to recover related knowledge.
- [[local-first-software]] - keeps graph data in markdown files.

## Sources

- [[local-release-notes]]
""",
    "wiki/entities/link.md": """---
type: entity
title: "Link"
entity_type: project
aliases: ["Link wiki", "Link MCP"]
date_created: "2026-05-02"
date_updated: "2026-05-02"
tags: [wiki, mcp, agents, local-first]
source_count: 2
maturity: growing
---

# Link

> **TLDR:** Link is a local-first wiki and MCP server that turns source notes into durable memory for AI agents.

## Overview

Link stores source material in `raw/` and compiled wiki pages in `wiki/`. The web viewer makes the wiki readable by humans, while MCP tools make the same knowledge readable by agents. *Source: [[local-release-notes]]* `[confidence: high]`

The demo positions Link as a local [[agent-memory]] layer. It keeps knowledge inspectable through markdown and navigable through a [[knowledge-graph]]. *Source: [[agent-memory-session]]* `[confidence: high]`

## Key Contributions

- Provides search, context, backlinks, and graph tools. *Source: [[local-release-notes]]* `[confidence: high]`
- Keeps source material local and inspectable. *Source: [[local-release-notes]]* `[confidence: high]`
- Gives future agents durable project context. *Source: [[agent-memory-session]]* `[confidence: high]`

## Connections

- Implements [[agent-memory]].
- Uses [[local-first-software]] as the storage model.
- Exposes a [[knowledge-graph]] for human inspection.
- Supports [[retrieval-augmented-generation]] workflows through MCP.

## Sources

- [[agent-memory-session]]
- [[local-release-notes]]
""",
    "wiki/memories/prefer-local-personal-memory.md": """---
type: memory
title: "Prefer local personal memory"
memory_type: preference
scope: user
status: active
date_captured: "2026-05-04T00:00:00Z"
source: "demo"
review_status: pending
tags: [memory, agents, local-first]
aliases: ["local personal memory", "agent personal memory"]
---

# Prefer local personal memory

> **TLDR:** The user wants Link to be local personal memory for agents, with the wiki as the inspectable storage format.

## Memory

The user wants [[link]] to feel like local personal memory for agents rather than only a wiki. Agents should remember user preferences, project context, decisions, and why those memories exist.

## Use This When

- Positioning Link in product copy or onboarding.
- Deciding whether a feature should prioritize [[agent-memory]] workflows over generic note management.
- Explaining why [[local-first-software]] matters for personal agent memory.

## Source

Captured as demo product intent for the first-run wiki.
""",
    "wiki/explorations/why-link-helps-agents.md": """---
type: exploration
title: "Why Link helps agents"
date_created: "2026-05-02"
query: "Why does Link help AI agents?"
aliases: ["agent memory demo answer"]
tags: [agents, memory, demo]
---

# Why Link helps agents

> **Query:** Why does Link help AI agents?

## Answer

Link helps agents because it turns past project material into durable, queryable context. Instead of starting each session from a blank chat, an agent can ask for [[agent-memory]] and receive the main page plus related concepts, sources, and entities.

The important part is inspectability. The memory is just markdown, the relationships are just wikilinks, and the graph shows what the agent can retrieve. This fits [[local-first-software]] and makes the memory easier to audit.

## Reasoning

The answer combines [[agent-memory-session]], [[transformer-reading-notes]], and [[local-release-notes]]. Together they show Link as a local retrieval layer for AI workflows: sources become pages, pages form a [[knowledge-graph]], and MCP exposes that graph to agents.

## Sources Consulted

- [[agent-memory]]
- [[link]]
- [[knowledge-graph]]
- [[retrieval-augmented-generation]]
""",
    "wiki/index.md": """# Link Demo Wiki Index

> Last updated: 2026-05-02 | 11 pages | 3 sources

## Categories

### concepts
- [[agent-memory]] - Durable, inspectable context for AI agents. growing - 2 sources - also: AI memory, agent context
- [[retrieval-augmented-generation]] - Retrieves external context before generation. seed - 1 source - also: RAG
- [[transformers]] - Attention-based model architecture behind modern LLM systems. seed - 1 source
- [[local-first-software]] - Keeps user data on disk in inspectable formats. growing - 2 sources
- [[knowledge-graph]] - Shows pages as nodes and wikilinks as edges. seed - 1 source

### entities
- [[link]] - Local-first wiki and MCP memory server for agents. growing - 2 sources - also: Link MCP

### memories
- [[prefer-local-personal-memory]] - User preference that Link should behave as local personal memory for agents. preference · user

### sources
- [[agent-memory-session]] - Demo note on durable project context. high
- [[transformer-reading-notes]] - Demo note connecting transformers, retrieval, and memory. high
- [[local-release-notes]] - Demo note on Link surfaces and graph visibility. high

### explorations
- [[why-link-helps-agents]] - Filed answer explaining Link as durable agent memory.

## Recent

| Date | Operation | Pages Touched |
|------|-----------|---------------|
| 2026-05-02 | demo: create first-run sample wiki | 11 pages |
""",
    "wiki/log.md": """# Link Demo Wiki Log

*Append-only record of demo wiki operations.*

---

## [2026-05-02T00:00:00Z] demo | create first-run sample wiki

- Source: raw/agent-memory-session.md
- Source: raw/transformer-reading-notes.md
- Source: raw/local-release-notes.md
- Created: sources/agent-memory-session.md
- Created: sources/transformer-reading-notes.md
- Created: sources/local-release-notes.md
- Created: concepts/agent-memory.md
- Created: concepts/retrieval-augmented-generation.md
- Created: concepts/transformers.md
- Created: concepts/local-first-software.md
- Created: concepts/knowledge-graph.md
- Created: entities/link.md
- Created: memories/prefer-local-personal-memory.md
- Created: explorations/why-link-helps-agents.md
- Rebuilt: wiki/_backlinks.json
- Pages touched: 11

---
""",
}


def _build_backlinks(wiki_dir: Path) -> dict[str, dict[str, list[str]]]:
    backlinks: dict[str, list[str]] = {}
    forward: dict[str, list[str]] = {}
    for md in sorted(wiki_dir.rglob("*.md")):
        if md.name.startswith("."):
            continue
        source = md.stem.lower()
        text = md.read_text(encoding="utf-8", errors="replace")
        for match in WIKILINK_RE.finditer(text):
            target = match.group(1).strip().lower()
            if not target or target == source:
                continue
            backlinks.setdefault(target, [])
            if source not in backlinks[target]:
                backlinks[target].append(source)
            forward.setdefault(source, [])
            if target not in forward[source]:
                forward[source].append(target)
    return {"backlinks": backlinks, "forward": forward}


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    frontmatter = text[4:end]
    body = text[end + 4:].lstrip("\n")
    meta: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip("\"'")
    return meta, body


def _wiki_page_records(wiki_dir: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for md in _wiki_pages(wiki_dir):
        text = md.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(text)
        records.append({
            "path": md,
            "rel": str(md.relative_to(wiki_dir)),
            "stem": md.stem.lower(),
            "meta": meta,
            "body": body,
        })
    return records


def _wiki_pages(wiki_dir: Path) -> list[Path]:
    return sorted(
        md for md in wiki_dir.rglob("*.md")
        if not md.name.startswith(".")
    )


def _page_stems(wiki_dir: Path) -> set[str]:
    return {md.stem.lower() for md in _wiki_pages(wiki_dir)}


def _load_backlinks(path: Path) -> tuple[dict[str, dict[str, list[str]]] | None, str | None]:
    if not path.exists():
        return None, "missing wiki/_backlinks.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"invalid wiki/_backlinks.json: {exc}"
    if "backlinks" in raw or "forward" in raw:
        backlinks = raw.get("backlinks", {})
        forward = raw.get("forward", {})
    else:
        backlinks = raw
        forward = {}
    if not isinstance(backlinks, dict) or not isinstance(forward, dict):
        return None, "wiki/_backlinks.json must contain object maps"
    return {"backlinks": backlinks, "forward": forward}, None


def _resolve_wiki_dir(target: Path) -> Path:
    target = target.expanduser().resolve()
    if target.name == "wiki" and (target / "index.md").exists():
        return target
    return target / "wiki"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(value: str, fallback: str = "memory") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def _frontmatter_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _csv_values(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _meta_tags(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip().strip("\"'") for item in _csv_values(str(value).strip("[]"))]


def _yaml_list(values: list[str]) -> str:
    return "[" + ", ".join(values) + "]"


def _memory_title(text: str, explicit_title: str | None = None) -> str:
    if explicit_title and explicit_title.strip():
        return explicit_title.strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "Memory")
    first_sentence = re.split(r"(?<=[.!?])\s+", first_line, maxsplit=1)[0].strip()
    if len(first_sentence) <= 70:
        return first_sentence.rstrip(".")
    return first_sentence[:67].rstrip() + "..."


def _unique_page_path(directory: Path, slug: str) -> Path:
    candidate = directory / f"{slug}.md"
    index = 2
    while candidate.exists():
        candidate = directory / f"{slug}-{index}.md"
        index += 1
    return candidate


def _extract_tldr(body: str) -> str:
    match = re.search(r">\s*\*\*TLDR:\*\*\s*(.+)", body)
    return match.group(1).strip() if match else ""


def _first_body_snippet(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith(">"):
            return stripped[:200]
    return ""


def _memory_records(wiki_dir: Path) -> list[dict[str, object]]:
    memories_dir = wiki_dir / "memories"
    if not memories_dir.exists():
        return []
    records: list[dict[str, object]] = []
    for path in sorted(memories_dir.rglob("*.md")):
        if path.name.startswith("."):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(text)
        title = meta.get("title") or _memory_title(body)
        records.append({
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
            "tags": _meta_tags(meta.get("tags", "")),
            "tldr": _extract_tldr(body),
            "snippet": _first_body_snippet(body),
            "body": body,
        })
    return records


def _slim_memory(record: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in record.items() if key != "body"}


def _is_active_memory(record: dict[str, object]) -> bool:
    return str(record.get("status") or "active").lower() not in {"archived", "stale"}


def _memory_review_issues(record: dict[str, object]) -> list[dict[str, str]]:
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
            "suggested_action": "Confirm it is still accurate, then run review-memory.",
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


def _memory_inbox(wiki_dir: Path, limit: int = 20, include_archived: bool = False) -> dict[str, object]:
    limit = max(1, min(limit, 50))
    items: list[dict[str, object]] = []
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    for record in _memory_records(wiki_dir):
        if not include_archived and str(record.get("status") or "").lower() == "archived":
            continue
        issues = _memory_review_issues(record)
        if not issues:
            continue
        item = _slim_memory(record)
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


def _extract_wikilinks(text: str) -> list[str]:
    links: list[str] = []
    for match in re.finditer(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", text):
        target = match.group(1).strip()
        if target and target not in links:
            links.append(target)
    return links


def _memory_log_entries(wiki_dir: Path, record: dict[str, object], limit: int = 8) -> list[str]:
    log_path = wiki_dir / "log.md"
    if not log_path.exists():
        return []
    text = log_path.read_text(encoding="utf-8", errors="replace")
    needles = {
        str(record.get("name") or ""),
        str(record.get("title") or ""),
        f"memories/{record.get('name')}.md",
    }
    needles = {needle.lower() for needle in needles if needle}
    blocks = [block.strip() for block in re.split(r"\n---\n", text) if block.strip()]
    matches = [
        block for block in blocks
        if any(needle in block.lower() for needle in needles)
    ]
    return matches[-limit:]


def _recall_state(record: dict[str, object], issues: list[dict[str, str]]) -> dict[str, object]:
    default_enabled = _is_active_memory(record)
    high_issues = [issue for issue in issues if issue["severity"] == "high"]
    if not default_enabled:
        state = "disabled"
        reason = f"Memory status is {record.get('status')}; default recall excludes archived and stale memories."
    elif high_issues:
        state = "unsafe"
        reason = "Memory is active but has high-severity quality issues."
    elif issues:
        state = "needs_review"
        reason = "Memory is active but still needs review or stronger metadata."
    else:
        state = "ready"
        reason = "Memory is active, reviewed, and has no detected quality issues."
    return {
        "default_enabled": default_enabled,
        "state": state,
        "reason": reason,
    }


def _memory_explanation(wiki_dir: Path, identifier: str) -> dict[str, object]:
    page_path, resolved_record, error = _resolve_memory_page(wiki_dir, identifier)
    if error:
        raise ValueError(error)
    assert page_path is not None and resolved_record is not None

    record = next(
        (item for item in _memory_records(wiki_dir) if item["name"] == resolved_record["name"]),
        resolved_record,
    )
    body = str(record.get("body") or "")
    issues = _memory_review_issues(record)
    backlinks_data, backlinks_error = _load_backlinks(wiki_dir / "_backlinks.json")
    if backlinks_error:
        backlinks_data = _build_backlinks(wiki_dir)
    assert backlinks_data is not None
    name = str(record["name"])
    graph = {
        "forward": sorted(backlinks_data.get("forward", {}).get(name, [])),
        "inbound": sorted(backlinks_data.get("backlinks", {}).get(name, [])),
        "wikilinks": _extract_wikilinks(body),
    }
    return {
        "found": True,
        "memory": _slim_memory(record),
        "recall": _recall_state(record, issues),
        "review": {
            "status": record.get("review_status", "pending"),
            "reviewed_at": record.get("reviewed_at", ""),
            "review_note": record.get("review_note", ""),
            "issues": issues,
            "issue_count": len(issues),
        },
        "provenance": {
            "source": record.get("source", ""),
            "date_captured": record.get("date_captured", ""),
            "path": record.get("path", ""),
        },
        "lifecycle": {
            "status": record.get("status", "active"),
            "archived_at": record.get("archived_at", ""),
            "archive_reason": record.get("archive_reason", ""),
            "restored_at": record.get("restored_at", ""),
        },
        "graph": graph,
        "log_entries": _memory_log_entries(wiki_dir, record),
        "body": body,
    }


def _count_values(records: list[dict[str, object]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(field) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _top_tags(records: list[dict[str, object]], limit: int = 12) -> list[dict[str, object]]:
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


def _recent_memories(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        records,
        key=lambda record: (
            str(record.get("date_captured") or ""),
            str(record.get("title") or "").lower(),
        ),
        reverse=True,
    )


def _memory_profile(wiki_dir: Path, limit: int = 10) -> dict[str, object]:
    limit = max(1, min(limit, 50))
    records = _memory_records(wiki_dir)
    active_records = [record for record in records if _is_active_memory(record)]
    archived_records = [
        record for record in records
        if str(record.get("status") or "").lower() == "archived"
    ]
    recent = [_slim_memory(record) for record in _recent_memories(active_records)]

    def typed(memory_type: str) -> list[dict[str, object]]:
        return [
            _slim_memory(record)
            for record in _recent_memories(active_records)
            if str(record.get("memory_type") or "") == memory_type
        ][:limit]

    return {
        "memory_count": len(records),
        "active_count": len(active_records),
        "review_count": _memory_inbox(wiki_dir, limit=limit)["review_count"],
        "by_type": _count_values(records, "memory_type"),
        "by_scope": _count_values(records, "scope"),
        "by_status": _count_values(records, "status"),
        "top_tags": _top_tags(records),
        "recent": recent[:limit],
        "preferences": typed("preference"),
        "decisions": typed("decision"),
        "projects": typed("project"),
        "archived": [_slim_memory(record) for record in _recent_memories(archived_records)][:limit],
    }


def _score_memory(record: dict[str, object], query: str) -> int:
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


def _recall_memories(
    wiki_dir: Path,
    query: str,
    limit: int = 10,
    include_archived: bool = False,
) -> list[dict[str, object]]:
    q = query.strip()
    if not q:
        return []
    scored: list[tuple[int, dict[str, object]]] = []
    for record in _memory_records(wiki_dir):
        if not include_archived and not _is_active_memory(record):
            continue
        score = _score_memory(record, q)
        if score > 0:
            slim = _slim_memory(record)
            slim["score"] = score
            scored.append((score, slim))
    scored.sort(key=lambda item: (-item[0], str(item[1]["title"]).lower()))
    return [record for _, record in scored[:limit]]


def _memory_duplicate_candidates(
    wiki_dir: Path,
    text: str,
    title: str | None,
    memory_type: str,
    scope: str,
    limit: int = 3,
) -> list[dict[str, object]]:
    return _core_memory_duplicate_candidates(
        _memory_records(wiki_dir),
        text,
        title,
        memory_type,
        scope,
        limit=limit,
    )


def _propose_memories_from_text(
    wiki_dir: Path,
    text: str,
    source: str = "inline",
    limit: int = 10,
) -> dict[str, object]:
    return _core_propose_memories_from_text(
        text,
        _memory_records(wiki_dir),
        source=source,
        limit=limit,
        writes_memory=False,
    )


def _update_memory_index(index_path: Path, page_name: str, title: str, summary: str, memory_type: str, scope: str) -> None:
    if not index_path.exists():
        _write_default_index(index_path)
    text = index_path.read_text(encoding="utf-8", errors="replace")
    if f"[[{page_name}]]" in text:
        return
    entry = f"- [[{page_name}]] - {summary} {memory_type} · {scope}\n"
    if "### memories" in text:
        pattern = re.compile(r"(### memories\n)(.*?)(?=\n### |\n## Recent|\Z)", flags=re.DOTALL)
        text = pattern.sub(lambda m: m.group(1) + m.group(2).rstrip() + "\n" + entry, text, count=1)
    elif "\n## Recent" in text:
        text = text.replace("\n## Recent", f"\n### memories\n{entry}\n## Recent", 1)
    else:
        text = text.rstrip() + f"\n\n### memories\n{entry}"
    index_path.write_text(text, encoding="utf-8")


def _append_log(wiki_dir: Path, timestamp: str, operation: str, description: str, lines: list[str]) -> None:
    log_path = wiki_dir / "log.md"
    if not log_path.exists():
        _write_default_log(log_path)
    entry = [f"## [{timestamp}] {operation} | {description}", ""]
    entry.extend(f"- {line}" for line in lines)
    entry.extend(["", "---", ""])
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(entry))


def _update_frontmatter_fields(text: str, updates: dict[str, str], remove: set[str] | None = None) -> str:
    remove = remove or set()
    if not text.startswith("---\n"):
        frontmatter = [f"{key}: {value}" for key, value in updates.items()]
        return "---\n" + "\n".join(frontmatter) + "\n---\n\n" + text.lstrip("\n")

    end = text.find("\n---", 4)
    if end == -1:
        frontmatter = [f"{key}: {value}" for key, value in updates.items()]
        return "---\n" + "\n".join(frontmatter) + "\n---\n\n" + text

    seen: set[str] = set()
    lines: list[str] = []
    for line in text[4:end].splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            lines.append(line)
            continue
        key = line.split(":", 1)[0].strip()
        if key in remove:
            continue
        if key in updates:
            lines.append(f"{key}: {updates[key]}")
            seen.add(key)
        else:
            lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}: {value}")
    return "---\n" + "\n".join(lines) + "\n---" + text[end + 4:]


def _frontmatter_int(value: object) -> int:
    try:
        return int(str(value or "0").strip())
    except ValueError:
        return 0


def _replace_markdown_body(text: str, body: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            return text[:end + 4] + "\n\n" + body.strip() + "\n"
    return body.strip() + "\n"


def _append_memory_update(body: str, update_text: str, timestamp: str, source: str) -> str:
    source_label = source.strip() or "manual"
    update_block = f"Update ({timestamp}, {source_label}):\n\n{update_text.strip()}"
    pattern = re.compile(r"(## Memory\n)(.*?)(?=\n## |\Z)", flags=re.DOTALL)
    match = pattern.search(body)
    if not match:
        return body.rstrip() + f"\n\n## Memory\n\n{update_block}\n"
    existing = match.group(2).rstrip()
    merged = (existing + "\n\n" if existing else "") + update_block + "\n\n"
    return body[:match.start(2)] + merged + body[match.end(2):]


def _resolve_memory_page(wiki_dir: Path, identifier: str) -> tuple[Path | None, dict[str, object] | None, str | None]:
    needle = identifier.strip()
    if not needle:
        return None, None, "memory name or title is required"
    memories_dir = wiki_dir / "memories"
    direct_candidates = []
    raw_path = Path(needle)
    if raw_path.suffix == ".md" or "/" in needle:
        rel = Path(needle.removeprefix("wiki/"))
        direct_candidates.append((wiki_dir / rel).resolve())
        direct_candidates.append((memories_dir / raw_path.name).resolve())
    else:
        direct_candidates.append((memories_dir / f"{needle}.md").resolve())
        direct_candidates.append((memories_dir / f"{_slugify(needle)}.md").resolve())

    memories_root = memories_dir.resolve()
    for candidate in direct_candidates:
        try:
            candidate.relative_to(memories_root)
        except ValueError:
            continue
        if candidate.exists() and candidate.is_file():
            text = candidate.read_text(encoding="utf-8", errors="replace")
            meta, body = _parse_frontmatter(text)
            return candidate, {
                "name": candidate.stem,
                "path": f"wiki/{candidate.relative_to(wiki_dir).as_posix()}",
                "title": meta.get("title") or _memory_title(body),
                "memory_type": meta.get("memory_type") or "note",
                "scope": meta.get("scope") or "user",
                "status": meta.get("status") or "active",
                "date_captured": meta.get("date_captured", ""),
                "updated_at": meta.get("updated_at", ""),
                "update_count": meta.get("update_count", "0"),
                "last_update_source": meta.get("last_update_source", ""),
                "source": meta.get("source", ""),
                "review_status": meta.get("review_status") or "pending",
                "reviewed_at": meta.get("reviewed_at", ""),
                "review_note": meta.get("review_note", ""),
                "tldr": _extract_tldr(body),
                "snippet": _first_body_snippet(body),
            }, None

    lowered = needle.lower()
    slug = _slugify(needle)
    matches = [
        record for record in _memory_records(wiki_dir)
        if lowered in {str(record["name"]).lower(), str(record["title"]).lower()}
        or slug == str(record["name"]).lower()
    ]
    if len(matches) > 1:
        names = ", ".join(str(record["name"]) for record in matches[:5])
        return None, None, f"memory identifier is ambiguous: {names}"
    if not matches:
        return None, None, f"memory not found: {identifier}"
    record = matches[0]
    return wiki_dir / str(record["path"]).removeprefix("wiki/"), record, None


def _set_memory_status(
    target: Path,
    identifier: str,
    status: str,
    reason: str | None = None,
    timestamp: str | None = None,
) -> dict[str, object]:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        raise FileNotFoundError(f"missing wiki directory: {wiki_dir}")
    page_path, record, error = _resolve_memory_page(wiki_dir, identifier)
    if error:
        raise ValueError(error)
    assert page_path is not None and record is not None

    timestamp = timestamp or _utc_timestamp()
    current_status = str(record.get("status") or "active")
    if status == "archived":
        updates = {
            "status": "archived",
            "archived_at": f'"{timestamp}"',
        }
        if reason and reason.strip():
            updates["archive_reason"] = f'"{_frontmatter_string(reason.strip())}"'
        remove = {"restored_at"}
        operation = "archive-memory"
    elif status == "active":
        updates = {
            "status": "active",
            "restored_at": f'"{timestamp}"',
        }
        remove = {"archived_at", "archive_reason"}
        operation = "restore-memory"
    else:
        raise ValueError("unsupported memory status")

    changed = current_status != status
    if changed:
        text = page_path.read_text(encoding="utf-8", errors="replace")
        page_path.write_text(_update_frontmatter_fields(text, updates, remove=remove), encoding="utf-8")
        log_lines = [
            f"Updated: memories/{page_path.name}",
            f"Previous status: {current_status}",
            f"New status: {status}",
        ]
        if reason and reason.strip():
            log_lines.append(f"Reason: {reason.strip()}")
        _append_log(wiki_dir, timestamp, operation, str(record["title"]), log_lines)

    return {
        "updated": changed,
        "name": record["name"],
        "path": record["path"],
        "title": record["title"],
        "previous_status": current_status,
        "status": status,
    }


def _mark_memory_reviewed(
    target: Path,
    identifier: str,
    note: str | None = None,
    timestamp: str | None = None,
) -> dict[str, object]:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        raise FileNotFoundError(f"missing wiki directory: {wiki_dir}")
    page_path, record, error = _resolve_memory_page(wiki_dir, identifier)
    if error:
        raise ValueError(error)
    assert page_path is not None and record is not None

    timestamp = timestamp or _utc_timestamp()
    previous_review_status = str(record.get("review_status") or "pending")
    clean_note = note.strip() if note else ""
    updates = {
        "review_status": "reviewed",
        "reviewed_at": f'"{timestamp}"',
    }
    if clean_note:
        updates["review_note"] = f'"{_frontmatter_string(clean_note)}"'
    changed = previous_review_status != "reviewed" or bool(clean_note)
    if changed:
        text = page_path.read_text(encoding="utf-8", errors="replace")
        page_path.write_text(_update_frontmatter_fields(text, updates), encoding="utf-8")
        log_lines = [
            f"Reviewed: memories/{page_path.name}",
            f"Previous review status: {previous_review_status}",
            "New review status: reviewed",
        ]
        if clean_note:
            log_lines.append(f"Note: {clean_note}")
        _append_log(wiki_dir, timestamp, "review-memory", str(record["title"]), log_lines)

    _, updated_record, _ = _resolve_memory_page(wiki_dir, str(record["name"]))
    updated_record = updated_record or record
    issues = _memory_review_issues(updated_record)
    return {
        "updated": changed,
        "name": record["name"],
        "path": record["path"],
        "title": record["title"],
        "previous_review_status": previous_review_status,
        "review_status": "reviewed",
        "remaining_issue_count": len(issues),
        "remaining_issues": issues,
    }


def _update_memory_page(
    target: Path,
    identifier: str,
    text: str,
    source: str = "manual",
    timestamp: str | None = None,
) -> dict[str, object]:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        raise FileNotFoundError(f"missing wiki directory: {wiki_dir}")
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("memory update text required")
    clean_source = source.strip() if source else "manual"
    page_path, record, error = _resolve_memory_page(wiki_dir, identifier)
    if error:
        raise ValueError(error)
    assert page_path is not None and record is not None
    if not _is_active_memory(record):
        raise ValueError("cannot update archived or stale memory; restore it first")

    timestamp = timestamp or _utc_timestamp()
    previous_review_status = str(record.get("review_status") or "pending")
    previous_update_count = _frontmatter_int(record.get("update_count"))
    next_update_count = previous_update_count + 1
    original = page_path.read_text(encoding="utf-8", errors="replace")
    _, body = _parse_frontmatter(original)
    updated_body = _append_memory_update(body, clean_text, timestamp, clean_source)
    updates = {
        "updated_at": f'"{timestamp}"',
        "update_count": str(next_update_count),
        "last_update_source": f'"{_frontmatter_string(clean_source)}"',
        "review_status": "pending",
    }
    updated_text = _update_frontmatter_fields(original, updates, remove={"reviewed_at", "review_note"})
    page_path.write_text(_replace_markdown_body(updated_text, updated_body), encoding="utf-8")
    _append_log(
        wiki_dir,
        timestamp,
        "update-memory",
        str(record["title"]),
        [
            f"Updated: memories/{page_path.name}",
            f"Previous review status: {previous_review_status}",
            "New review status: pending",
            f"Update count: {next_update_count}",
            f"Source: {clean_source}",
        ],
    )
    backlinks = _build_backlinks(wiki_dir)
    (wiki_dir / "_backlinks.json").write_text(json.dumps(backlinks, indent=2) + "\n", encoding="utf-8")

    _, updated_record, _ = _resolve_memory_page(wiki_dir, str(record["name"]))
    updated_record = updated_record or record
    issues = _memory_review_issues(updated_record)
    return {
        "updated": True,
        "name": updated_record["name"],
        "path": updated_record["path"],
        "title": updated_record["title"],
        "previous_review_status": previous_review_status,
        "review_status": updated_record.get("review_status", "pending"),
        "updated_at": timestamp,
        "update_count": next_update_count,
        "source": clean_source,
        "remaining_issue_count": len(issues),
        "remaining_issues": issues,
        "backlinks_rebuilt": True,
    }


def _write_memory_page(
    target: Path,
    text: str,
    title: str | None = None,
    memory_type: str = "note",
    scope: str = "user",
    tags: str | None = None,
    source: str = "manual",
    timestamp: str | None = None,
    allow_duplicate: bool = False,
) -> dict[str, object]:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        raise FileNotFoundError(f"missing wiki directory: {wiki_dir}")
    if memory_type not in MEMORY_TYPES:
        raise ValueError(f"memory_type must be one of: {', '.join(MEMORY_TYPES)}")
    if scope not in MEMORY_SCOPES:
        raise ValueError(f"scope must be one of: {', '.join(MEMORY_SCOPES)}")

    timestamp = timestamp or _utc_timestamp()
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("memory text required")
    memory_title = _memory_title(clean_text, title)
    summary = clean_text.splitlines()[0].strip()
    if len(summary) > 180:
        summary = summary[:177].rstrip() + "..."
    duplicate_candidates = _memory_duplicate_candidates(
        wiki_dir,
        clean_text,
        title,
        memory_type,
        scope,
    )
    if duplicate_candidates and not allow_duplicate:
        return {
            "created": False,
            "duplicate": True,
            "message": "Similar active memory already exists. Review or update the existing memory, or pass allow_duplicate if this is intentional.",
            "title": memory_title,
            "memory_type": memory_type,
            "scope": scope,
            "candidates": duplicate_candidates,
        }
    memories_dir = wiki_dir / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)
    page_path = _unique_page_path(memories_dir, _slugify(memory_title))
    page_name = page_path.stem
    tag_values = ["memory", memory_type]
    for tag in _csv_values(tags):
        slug_tag = _slugify(tag, fallback="")
        if slug_tag and slug_tag not in tag_values:
            tag_values.append(slug_tag)

    page = f"""---
type: memory
title: "{_frontmatter_string(memory_title)}"
memory_type: {memory_type}
scope: {scope}
status: active
date_captured: "{timestamp}"
source: "{_frontmatter_string(source)}"
review_status: pending
tags: {_yaml_list(tag_values)}
---

# {memory_title}

> **TLDR:** {summary}

## Memory

{clean_text}

## Use This When

- An agent needs relevant {scope} context for future work.
- A future answer depends on this {memory_type}.

## Source

{source}
"""
    page_path.write_text(page, encoding="utf-8")
    _update_memory_index(wiki_dir / "index.md", page_name, memory_title, summary, memory_type, scope)
    _append_log(
        wiki_dir,
        timestamp,
        "remember",
        memory_title,
        [
            f"Created: memories/{page_path.name}",
            f"Type: {memory_type}",
            f"Scope: {scope}",
        ],
    )
    backlinks = _build_backlinks(wiki_dir)
    (wiki_dir / "_backlinks.json").write_text(json.dumps(backlinks, indent=2) + "\n", encoding="utf-8")
    return {
        "created": True,
        "name": page_name,
        "path": f"wiki/memories/{page_path.name}",
        "title": memory_title,
        "memory_type": memory_type,
        "scope": scope,
        "duplicate_override": bool(duplicate_candidates and allow_duplicate),
        "duplicate_candidates": duplicate_candidates,
    }


def _normalize_link_index(data: dict[str, dict[str, list[str]]]) -> dict[str, dict[str, list[str]]]:
    normalized: dict[str, dict[str, list[str]]] = {"backlinks": {}, "forward": {}}
    for section in ("backlinks", "forward"):
        for key, values in data.get(section, {}).items():
            if isinstance(values, list):
                normalized[section][key.lower()] = sorted({str(v).lower() for v in values})
    return normalized


def _find_dead_links(wiki_dir: Path) -> list[str]:
    stems = _page_stems(wiki_dir)
    dead: list[str] = []
    for md in _wiki_pages(wiki_dir):
        source = md.stem.lower()
        text = md.read_text(encoding="utf-8", errors="replace")
        for match in WIKILINK_RE.finditer(text):
            target = match.group(1).strip().lower()
            if target and target not in stems:
                dead.append(f"{source} -> {target}")
    return sorted(set(dead))


def _find_unindexed_pages(wiki_dir: Path) -> list[str]:
    index_path = wiki_dir / "index.md"
    if not index_path.exists():
        return []
    index_text = index_path.read_text(encoding="utf-8", errors="replace")
    indexed = {m.group(1).strip().lower() for m in WIKILINK_RE.finditer(index_text)}
    roots = {"index", "log"}
    return sorted(stem for stem in _page_stems(wiki_dir) if stem not in indexed and stem not in roots)


def _find_uningested_raw(target: Path) -> list[str]:
    target = target.expanduser().resolve()
    status = _collect_ingest_status(target)
    return [item["raw"].removeprefix("raw/") for item in status["pending_raw"]]


def _raw_source_files(raw_dir: Path) -> list[Path]:
    if not raw_dir.exists():
        return []
    files: list[Path] = []
    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if any(part in SKIP_SCAN_DIRS for part in path.relative_to(raw_dir).parts):
            continue
        files.append(path)
    return files


def _source_page_texts(wiki_dir: Path) -> dict[str, str]:
    sources_dir = wiki_dir / "sources"
    if not sources_dir.exists():
        return {}
    texts: dict[str, str] = {}
    for page in sorted(sources_dir.rglob("*.md")):
        if page.name.startswith("."):
            continue
        texts[page.stem.lower()] = page.read_text(encoding="utf-8", errors="replace")
    return texts


def _backlinks_health(wiki_dir: Path) -> tuple[str, str]:
    current, load_error = _load_backlinks(wiki_dir / "_backlinks.json")
    if load_error:
        return "missing" if "missing" in load_error else "invalid", load_error
    expected = _build_backlinks(wiki_dir)
    if current is not None and _normalize_link_index(current) == _normalize_link_index(expected):
        return "current", "wiki/_backlinks.json is current"
    return "stale", "wiki/_backlinks.json is stale"


def _collect_ingest_status(target: Path) -> dict[str, object]:
    target = target.expanduser().resolve()
    raw_dir = target / "raw"
    wiki_dir = target / "wiki"
    raw_files = _raw_source_files(raw_dir)
    source_texts = _source_page_texts(wiki_dir)

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
        _backlinks_health(wiki_dir)
        if wiki_dir.exists()
        else ("missing", "missing wiki directory")
    )

    return {
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


def _find_pages_missing_summaries(wiki_dir: Path) -> list[str]:
    missing: list[str] = []
    for record in _wiki_page_records(wiki_dir):
        stem = str(record["stem"])
        if stem in {"index", "log"}:
            continue
        body = str(record["body"])
        if "> **TLDR:**" not in body and "> **Query:**" not in body:
            missing.append(str(record["rel"]))
    return sorted(missing)


def _find_pages_missing_source_sections(wiki_dir: Path) -> list[str]:
    missing: list[str] = []
    source_backed_dirs = {"concepts", "entities", "comparisons", "explorations"}
    for record in _wiki_page_records(wiki_dir):
        rel = str(record["rel"])
        top_dir = rel.split("/", 1)[0]
        if top_dir not in source_backed_dirs:
            continue
        body = str(record["body"])
        if not re.search(r"^## Sources\b", body, flags=re.MULTILINE):
            missing.append(rel)
    return sorted(missing)


def _source_section_links(body: str) -> set[str]:
    match = re.search(r"^## Sources[^\n]*\n(?P<section>.*?)(?=^## |\Z)", body, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return set()
    return {m.group(1).strip().lower() for m in WIKILINK_RE.finditer(match.group("section"))}


def _find_source_count_mismatches(wiki_dir: Path) -> list[str]:
    mismatches: list[str] = []
    for record in _wiki_page_records(wiki_dir):
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
        actual = len(_source_section_links(str(record["body"])))
        if expected != actual:
            mismatches.append(f"{rel} source_count={expected}, sources section has {actual}")
    return sorted(mismatches)


def _find_isolated_pages(wiki_dir: Path) -> list[str]:
    stems = _page_stems(wiki_dir)
    records = _wiki_page_records(wiki_dir)
    graph = _build_backlinks(wiki_dir)
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


def _find_sensitive_filenames(target: Path) -> list[str]:
    matches: list[str] = []
    stack = [target]
    while stack:
        current = stack.pop()
        for path in current.iterdir():
            if path.is_dir():
                if path.name not in SKIP_SCAN_DIRS:
                    stack.append(path)
                continue
            if not path.is_file():
                continue
            name = path.name
            if any(fnmatch.fnmatch(name, pattern) for pattern in SECRET_NAME_PATTERNS):
                matches.append(str(path.relative_to(target)))
    return sorted(matches)


def _iter_scannable_files(target: Path) -> list[Path]:
    files: list[Path] = []
    stack = [target]
    while stack:
        current = stack.pop()
        for path in current.iterdir():
            if path.is_dir():
                if path.name not in SKIP_SCAN_DIRS:
                    stack.append(path)
                continue
            if not path.is_file() or path.suffix.lower() in SKIP_SCAN_SUFFIXES:
                continue
            files.append(path)
    return sorted(files)


def _find_sensitive_values(target: Path) -> list[str]:
    matches: list[str] = []
    for path in _iter_scannable_files(target):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for label, pattern in SECRET_VALUE_PATTERNS:
            if pattern.search(text):
                matches.append(f"{path.relative_to(target)} ({label})")
                break
    return sorted(matches)


def _required_paths(target: Path) -> list[Path]:
    wiki_dir = target / "wiki"
    raw_dir = target / "raw"
    return [
        raw_dir,
        wiki_dir,
        wiki_dir / "index.md",
        wiki_dir / "log.md",
        wiki_dir / "_backlinks.json",
        wiki_dir / "sources",
        wiki_dir / "concepts",
        wiki_dir / "entities",
        wiki_dir / "memories",
        wiki_dir / "comparisons",
        wiki_dir / "explorations",
    ]


def _write_default_index(path: Path) -> None:
    path.write_text(
        "# Link Wiki Index\n\n"
        "> Last updated: not yet ingested | 0 pages | 0 sources\n\n"
        "## Categories\n\n"
        "## Recent\n\n"
        "| Date | Operation | Pages Touched |\n"
        "|------|-----------|---------------|\n",
        encoding="utf-8",
    )


def _write_default_log(path: Path) -> None:
    path.write_text("# Link Wiki Log\n\n*Append-only record of wiki operations.*\n", encoding="utf-8")


def _apply_doctor_fixes(target: Path) -> list[str]:
    target = target.expanduser().resolve()
    wiki_dir = target / "wiki"
    fixes: list[str] = []

    for path in _required_paths(target):
        if path.suffix:
            continue
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            fixes.append(f"created {path.relative_to(target)}")

    index_path = wiki_dir / "index.md"
    if not index_path.exists():
        _write_default_index(index_path)
        fixes.append("created wiki/index.md")

    log_path = wiki_dir / "log.md"
    if not log_path.exists():
        _write_default_log(log_path)
        fixes.append("created wiki/log.md")

    if wiki_dir.exists():
        backlinks_path = wiki_dir / "_backlinks.json"
        current, load_error = _load_backlinks(backlinks_path)
        expected = _build_backlinks(wiki_dir)
        if load_error or current is None or _normalize_link_index(current) != _normalize_link_index(expected):
            backlinks_path.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
            fixes.append("rebuilt wiki/_backlinks.json")

    return fixes


def doctor(target: Path, fix: bool = False) -> int:
    target = target.expanduser().resolve()
    wiki_dir = target / "wiki"
    raw_dir = target / "raw"
    errors: list[str] = []
    warnings: list[str] = []

    print(f"Link doctor: {target}")
    print("")
    if fix:
        fixes = _apply_doctor_fixes(target)
        if fixes:
            print("Fixes applied:")
            for item in fixes:
                print(f"- {item}")
            print("")
        else:
            print("Fixes applied: none")
            print("")

    required = _required_paths(target)
    missing = [str(path.relative_to(target)) for path in required if not path.exists()]
    if missing:
        errors.append("missing required paths: " + ", ".join(missing))
    else:
        print("OK required wiki structure")

    if wiki_dir.exists():
        pages = _wiki_pages(wiki_dir)
        print(f"OK markdown pages: {len(pages)}")

        dead_links = _find_dead_links(wiki_dir)
        if dead_links:
            errors.append("dead wikilinks: " + ", ".join(dead_links[:8]))
        else:
            print("OK no dead wikilinks")

        unindexed = _find_unindexed_pages(wiki_dir)
        if unindexed:
            warnings.append("pages missing from index: " + ", ".join(unindexed[:8]))
        else:
            print("OK index lists wiki pages")

        current, load_error = _load_backlinks(wiki_dir / "_backlinks.json")
        if load_error:
            errors.append(load_error)
        elif current is not None:
            expected = _build_backlinks(wiki_dir)
            if _normalize_link_index(current) != _normalize_link_index(expected):
                errors.append("wiki/_backlinks.json is stale; run: python3 link.py rebuild-backlinks .")
            else:
                print("OK backlinks are current")

        missing_summaries = _find_pages_missing_summaries(wiki_dir)
        if missing_summaries:
            warnings.append("pages missing TLDR/query summary: " + ", ".join(missing_summaries[:8]))
        else:
            print("OK wiki pages have summaries")

        missing_sources = _find_pages_missing_source_sections(wiki_dir)
        if missing_sources:
            warnings.append("source-backed pages missing Sources section: " + ", ".join(missing_sources[:8]))
        else:
            print("OK source-backed pages cite sources")

        source_count_mismatches = _find_source_count_mismatches(wiki_dir)
        if source_count_mismatches:
            warnings.append("source_count metadata mismatch: " + ", ".join(source_count_mismatches[:8]))
        else:
            print("OK source_count metadata matches Sources sections")

        isolated = _find_isolated_pages(wiki_dir)
        if isolated:
            warnings.append("isolated wiki pages: " + ", ".join(isolated[:8]))
        else:
            print("OK graph has no isolated wiki pages")

    uningested = _find_uningested_raw(target)
    if uningested:
        warnings.append("raw files not referenced by wiki pages: " + ", ".join(uningested[:8]))
    elif raw_dir.exists():
        print("OK raw files are represented in wiki sources")

    sensitive_names = _find_sensitive_filenames(target)
    if sensitive_names:
        errors.append("sensitive-looking filenames present: " + ", ".join(sensitive_names[:8]))
    else:
        print("OK no sensitive-looking filenames")

    sensitive_values = _find_sensitive_values(target)
    if sensitive_values:
        errors.append("sensitive-looking file contents present: " + ", ".join(sensitive_values[:8]))
    else:
        print("OK no sensitive-looking file contents")

    if warnings:
        print("")
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")

    if errors:
        print("")
        print("Errors:")
        for error in errors:
            print(f"- {error}")
        print("")
        print("Result: needs attention")
        return 1

    print("")
    print("Result: healthy")
    return 0


def ingest_status(target: Path, json_output: bool = False) -> int:
    target = target.expanduser().resolve()
    status = _collect_ingest_status(target)

    if json_output:
        print(json.dumps(status, indent=2))
        return 0 if status["has_raw_dir"] and status["has_wiki_dir"] else 1

    print(f"Link ingest status: {target}")
    print("")
    if not status["has_raw_dir"]:
        print("Missing raw/ directory")
    if not status["has_wiki_dir"]:
        print("Missing wiki/ directory")
    if not status["has_raw_dir"] or not status["has_wiki_dir"]:
        print("")
        print("Next:")
        print("  Run an installer or create a demo: python3 link.py demo")
        return 1

    print(f"Raw files: {status['raw_count']}")
    print(f"Source pages: {status['source_page_count']}")
    print(f"Represented in wiki/sources: {status['represented_count']}")
    print(f"Pending ingest: {status['pending_count']}")
    print(f"Backlinks: {status['backlinks_status']} ({status['backlinks_message']})")

    pending_raw = status["pending_raw"]
    if pending_raw:
        print("")
        print("Pending raw files:")
        for item in pending_raw[:20]:
            print(f"- {item['raw']}")
        if len(pending_raw) > 20:
            print(f"- ... {len(pending_raw) - 20} more")

    print("")
    print("Next:")
    if pending_raw:
        first_pending = pending_raw[0]["raw"]
        print(f"  Ask your agent: ingest {first_pending}")
        print("  After ingest: python3 link.py rebuild-backlinks .")
        print("  Then check:  python3 link.py doctor .")
    elif status["backlinks_status"] != "current":
        print("  Repair graph index: python3 link.py rebuild-backlinks .")
        print("  Then check:          python3 link.py doctor .")
    else:
        print("  No pending raw files. Run: python3 link.py doctor .")

    return 0


def rebuild_backlinks(target: Path) -> int:
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    backlinks = _build_backlinks(wiki_dir)
    out_path = wiki_dir / "_backlinks.json"
    out_path.write_text(json.dumps(backlinks, indent=2) + "\n", encoding="utf-8")
    page_count = len(_wiki_pages(wiki_dir))
    edge_count = sum(len(targets) for targets in backlinks["forward"].values())
    print(f"Rebuilt {out_path}")
    print(f"Pages: {page_count}")
    print(f"Edges: {edge_count}")
    return 0


def remember(
    target: Path,
    text: str,
    title: str | None = None,
    memory_type: str = "note",
    scope: str = "user",
    tags: str | None = None,
    source: str = "manual",
    allow_duplicate: bool = False,
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
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not remember: {exc}", file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(result, indent=2))
        return 0

    if not result.get("created"):
        print("Similar memory already exists")
        print(f"Title requested: {result['title']}")
        print(f"Type: {result['memory_type']}")
        print(f"Scope: {result['scope']}")
        print("")
        print("Existing candidates:")
        for candidate in result.get("candidates", []):
            print(f"- {candidate['title']} ({candidate['path']})")
        print("")
        print("Next:")
        first = next(iter(result.get("candidates", [])), None)
        if first:
            print(f"  python3 link.py explain-memory \"{first['name']}\" .")
        print("  Use --allow-duplicate only if this should be a separate memory.")
        return 0

    print("Memory saved")
    print(f"Title: {result['title']}")
    print(f"Path: {result['path']}")
    print(f"Type: {result['memory_type']}")
    print(f"Scope: {result['scope']}")
    print("")
    print("Next:")
    print(f"  python3 link.py recall \"{result['title']}\" .")
    return 0


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
    )

    if json_output:
        print(json.dumps(result, indent=2))
        return 0

    print("Memory proposals")
    print(f"Source: {result['source']}")
    print(f"Count: {result['count']}")
    if not result["proposals"]:
        print("No durable memory candidates found.")
        return 0
    for index, proposal in enumerate(result["proposals"], start=1):
        print("")
        print(f"{index}. {proposal['title']} [{proposal['confidence']}]")
        print(f"   Type: {proposal['memory_type']} | Scope: {proposal['scope']}")
        print(f"   Action: {proposal['suggested_action']}")
        print(f"   Memory: {proposal['memory']}")
        if proposal["duplicate_candidates"]:
            first = proposal["duplicate_candidates"][0]
            print(f"   Duplicate candidate: {first['title']} ({first['path']})")
    print("")
    print("Next:")
    print("  Use remember for new memories, or update-memory for duplicate candidates.")
    return 0


def update_memory(
    target: Path,
    identifier: str,
    text: str,
    source: str = "manual",
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
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not update memory: {exc}", file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(result, indent=2))
        return 0

    print("Memory updated")
    print(f"Title: {result['title']}")
    print(f"Path: {result['path']}")
    print(f"Update count: {result['update_count']}")
    print(f"Review: {result['previous_review_status']} -> {result['review_status']}")
    print("")
    print("Next:")
    print(f"  python3 link.py explain-memory \"{result['name']}\" .")
    print(f"  python3 link.py review-memory \"{result['name']}\" .")
    return 0


def recall(
    target: Path,
    query: str,
    limit: int = 10,
    json_output: bool = False,
    include_archived: bool = False,
) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    results = _recall_memories(wiki_dir, query, limit=limit, include_archived=include_archived)

    if json_output:
        print(json.dumps({
            "query": query,
            "count": len(results),
            "include_archived": include_archived,
            "memories": results,
        }, indent=2))
        return 0

    print(f"Link memory recall: {query}")
    if include_archived:
        print("Including archived/stale memories")
    print("")
    if not results:
        print("No matching memories found.")
        print("")
        print("Next:")
        print("  Add one: python3 link.py remember \"Memory to keep\" .")
        return 0

    print(f"{len(results)} memor{'y' if len(results) == 1 else 'ies'}")
    for record in results:
        print(f"- {record['title']} ({record['memory_type']} · {record['scope']})")
        print(f"  {record['path']}")
        summary = record.get("tldr") or record.get("snippet")
        if summary:
            print(f"  {summary}")
    return 0


def archive_memory(target: Path, identifier: str, reason: str | None = None, json_output: bool = False) -> int:
    try:
        result = _set_memory_status(target, identifier, "archived", reason=reason)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not archive memory: {exc}", file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(result, indent=2))
        return 0

    if result["updated"]:
        print("Memory archived")
    else:
        print("Memory already archived")
    print(f"Title: {result['title']}")
    print(f"Path: {result['path']}")
    print(f"Previous status: {result['previous_status']}")
    print(f"Status: {result['status']}")
    print("")
    print("Next:")
    print(f"  Restore: python3 link.py restore-memory \"{result['name']}\" .")
    return 0


def restore_memory(target: Path, identifier: str, json_output: bool = False) -> int:
    try:
        result = _set_memory_status(target, identifier, "active")
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not restore memory: {exc}", file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(result, indent=2))
        return 0

    if result["updated"]:
        print("Memory restored")
    else:
        print("Memory already active")
    print(f"Title: {result['title']}")
    print(f"Path: {result['path']}")
    print(f"Previous status: {result['previous_status']}")
    print(f"Status: {result['status']}")
    return 0


def memory_inbox(
    target: Path,
    limit: int = 20,
    include_archived: bool = False,
    json_output: bool = False,
) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    inbox = _memory_inbox(wiki_dir, limit=limit, include_archived=include_archived)

    if json_output:
        print(json.dumps(inbox, indent=2))
        return 0

    print(f"Link memory inbox: {target}")
    if include_archived:
        print("Including archived memories")
    print("")
    review_count = inbox["review_count"]
    print(f"{review_count} memor{'y' if review_count == 1 else 'ies'} need review")
    if inbox["counts_by_severity"]:
        print(f"Severity: {_format_counts(inbox['counts_by_severity'])}")
    print("")
    if not inbox["items"]:
        print("Inbox is clear.")
        return 0

    for item in inbox["items"]:
        print(f"- {item['title']} ({item['memory_type']} · {item['scope']} · {item['status']})")
        print(f"  {item['path']}")
        for issue in item["issues"]:
            print(f"  [{issue['severity']}] {issue['code']}: {issue['message']}")
        print(f"  Review: python3 link.py review-memory \"{item['name']}\" .")
    return 0


def review_memory(target: Path, identifier: str, note: str | None = None, json_output: bool = False) -> int:
    try:
        result = _mark_memory_reviewed(target, identifier, note=note)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not review memory: {exc}", file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(result, indent=2))
        return 0

    if result["updated"]:
        print("Memory reviewed")
    else:
        print("Memory was already reviewed")
    print(f"Title: {result['title']}")
    print(f"Path: {result['path']}")
    print(f"Previous review status: {result['previous_review_status']}")
    print(f"Review status: {result['review_status']}")
    if result["remaining_issue_count"]:
        print("")
        print(f"{result['remaining_issue_count']} issue{'s' if result['remaining_issue_count'] != 1 else ''} still need attention:")
        for issue in result["remaining_issues"]:
            print(f"- [{issue['severity']}] {issue['code']}: {issue['message']}")
    return 0


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

    memory = explanation["memory"]
    recall_info = explanation["recall"]
    review = explanation["review"]
    provenance = explanation["provenance"]
    lifecycle = explanation["lifecycle"]
    graph = explanation["graph"]

    print(f"Link memory explanation: {memory['title']}")
    print("")
    print(f"Path: {memory['path']}")
    print(f"Type: {memory['memory_type']} · Scope: {memory['scope']} · Status: {lifecycle['status']}")
    print(f"Source: {provenance['source'] or 'missing'}")
    print(f"Captured: {provenance['date_captured'] or 'missing'}")
    print(f"Review: {review['status']} · Issues: {review['issue_count']}")
    print(f"Recall: {recall_info['state']} ({'enabled' if recall_info['default_enabled'] else 'disabled'} by default)")
    print(f"Reason: {recall_info['reason']}")
    summary = memory.get("tldr") or memory.get("snippet")
    if summary:
        print("")
        print(f"Summary: {summary}")
    if review["issues"]:
        print("")
        print("Review issues:")
        for issue in review["issues"]:
            print(f"- [{issue['severity']}] {issue['code']}: {issue['message']}")
            print(f"  Action: {issue['suggested_action']}")
    print("")
    print("Graph:")
    print(f"- Forward links: {', '.join(graph['forward']) if graph['forward'] else 'none'}")
    print(f"- Inbound links: {', '.join(graph['inbound']) if graph['inbound'] else 'none'}")
    if explanation["log_entries"]:
        print("")
        print("Recent lifecycle log:")
        for entry in explanation["log_entries"][-3:]:
            first_line = next((line for line in entry.splitlines() if line.strip().startswith("## ")), "")
            print(f"- {first_line[3:] if first_line.startswith('## ') else first_line or 'log entry'}")
    return 0


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{name}: {count}" for name, count in counts.items())


def _print_memory_list(title: str, records: list[dict[str, object]], empty: str = "none") -> None:
    print(title)
    if not records:
        print(f"- {empty}")
        return
    for record in records:
        print(f"- {record['title']} ({record['memory_type']} · {record['scope']})")
        print(f"  {record['path']}")
        summary = record.get("tldr") or record.get("snippet")
        if summary:
            print(f"  {summary}")


def profile(target: Path, limit: int = 10, json_output: bool = False) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    if not wiki_dir.exists():
        print(f"Missing wiki directory: {wiki_dir}", file=sys.stderr)
        return 1
    profile_data = _memory_profile(wiki_dir, limit=limit)

    if json_output:
        print(json.dumps(profile_data, indent=2))
        return 0

    print(f"Link memory profile: {target}")
    print("")
    memory_count = profile_data["memory_count"]
    active_count = profile_data["active_count"]
    review_count = profile_data["review_count"]
    print(f"{memory_count} memor{'y' if memory_count == 1 else 'ies'} · {active_count} active · {review_count} need review")
    print(f"Types: {_format_counts(profile_data['by_type'])}")
    print(f"Scopes: {_format_counts(profile_data['by_scope'])}")
    print(f"Status: {_format_counts(profile_data['by_status'])}")
    tags = ", ".join(
        f"{item['tag']} ({item['count']})"
        for item in profile_data["top_tags"]
    )
    if tags:
        print(f"Tags: {tags}")
    print("")

    if memory_count == 0:
        print("No memories found.")
        print("")
        print("Next:")
        print("  Add one: python3 link.py remember \"Memory to keep\" .")
        return 0

    _print_memory_list("Recent memories", profile_data["recent"])
    print("")
    _print_memory_list("Preferences", profile_data["preferences"])
    print("")
    _print_memory_list("Decisions", profile_data["decisions"])
    print("")
    _print_memory_list("Project context", profile_data["projects"])
    if profile_data["archived"]:
        print("")
        _print_memory_list("Archived memories", profile_data["archived"])
    return 0


def _check_link_mcp_import(python_cmd: str) -> dict[str, object]:
    code = (
        "import json, link_mcp; "
        "print(json.dumps({'installed': True, 'version': getattr(link_mcp, '__version__', 'unknown')}))"
    )
    try:
        result = subprocess.run(
            [python_cmd, "-c", code],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        return {"installed": False, "version": None, "error": str(exc)}
    if result.returncode != 0:
        error = (result.stderr or result.stdout).strip()
        return {"installed": False, "version": None, "error": error}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"installed": False, "version": None, "error": "could not parse link_mcp import output"}
    return {
        "installed": bool(data.get("installed")),
        "version": data.get("version") or "unknown",
        "error": None,
    }


def _mcp_config(python_cmd: str, wiki_dir: Path) -> dict[str, object]:
    return {
        "mcpServers": {
            "link": {
                "command": python_cmd,
                "args": ["-m", "link_mcp", "--wiki", str(wiki_dir)],
            }
        }
    }


def _resolve_mcp_python(target: Path, wiki_dir: Path, python_cmd: str | None) -> str:
    if python_cmd:
        return str(Path(python_cmd).expanduser())

    root = wiki_dir.parent if wiki_dir.name == "wiki" else target
    marker = root / ".link-mcp-python"
    if marker.exists():
        configured = marker.read_text(encoding="utf-8", errors="replace").strip()
        if configured:
            return str(Path(configured).expanduser())

    return sys.executable


def verify_mcp(
    target: Path,
    json_output: bool = False,
    python_cmd: str | None = None,
    import_check: Callable[[str], dict[str, object]] = _check_link_mcp_import,
) -> int:
    target = target.expanduser().resolve()
    wiki_dir = _resolve_wiki_dir(target)
    python_cmd = _resolve_mcp_python(target, wiki_dir, python_cmd)
    import_status = import_check(python_cmd)
    wiki_exists = wiki_dir.exists() and wiki_dir.is_dir()
    config = _mcp_config(python_cmd, wiki_dir)
    ready = bool(import_status.get("installed")) and wiki_exists
    status = {
        "ready": ready,
        "python": python_cmd,
        "link_mcp": import_status,
        "wiki": {
            "path": str(wiki_dir),
            "exists": wiki_exists,
        },
        "config": config,
    }

    if json_output:
        print(json.dumps(status, indent=2))
        return 0 if ready else 1

    print(f"Link MCP verification: {target}")
    print("")
    print(f"Python: {python_cmd}")
    if import_status.get("installed"):
        print(f"link-mcp: installed ({import_status.get('version')})")
    else:
        print("link-mcp: missing")
        error = import_status.get("error")
        if error:
            print(f"Import error: {error}")
    print(f"Wiki: {'found' if wiki_exists else 'missing'} ({wiki_dir})")

    print("")
    print("MCP config:")
    print(json.dumps(config, indent=2))

    if ready:
        print("")
        print("Result: ready")
        return 0

    print("")
    print("Next:")
    if not import_status.get("installed"):
        print("  Install: python3 -m pip install --upgrade link-mcp")
        print("  macOS/Homebrew fallback:")
        print("    python3 -m venv ~/.link-mcp-venv")
        print("    ~/.link-mcp-venv/bin/python -m pip install --upgrade pip link-mcp")
        print("    Then rerun with: python3 link.py verify-mcp . --python ~/.link-mcp-venv/bin/python")
    if not wiki_exists:
        print("  Create a wiki with an installer, or try: python3 link.py demo")
    print("")
    print("Result: needs attention")
    return 1


def _copy_runtime_files(target: Path) -> None:
    for name in ("serve.py", "link.py", "LINK.md", ".linkignore"):
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, target / name)
    core_src = ROOT / "mcp_package" / "link_core"
    if core_src.exists():
        core_target = target / "link_core"
        core_target.mkdir(exist_ok=True)
        for src in core_src.glob("*.py"):
            shutil.copy2(src, core_target / src.name)
    for name in ("logo.png", "logo.svg"):
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, target / name)


def create_demo(target: Path, force: bool = False) -> None:
    target = target.expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        marker = target / DEMO_MARKER
        if not force:
            raise SystemExit(
                f"{target} already exists. Re-run with --force to replace a Link demo directory."
            )
        if not marker.exists():
            raise SystemExit(
                f"{target} does not look like a Link demo directory; refusing to overwrite it."
            )
        shutil.rmtree(target)

    target.mkdir(parents=True, exist_ok=True)
    (target / DEMO_MARKER).write_text("Link demo directory\n", encoding="utf-8")
    _copy_runtime_files(target)

    for directory in (
        "raw",
        "wiki/sources",
        "wiki/concepts",
        "wiki/entities",
        "wiki/memories",
        "wiki/comparisons",
        "wiki/explorations",
    ):
        path = target / directory
        path.mkdir(parents=True, exist_ok=True)
        (path / ".gitkeep").touch()

    for rel, content in DEMO_FILES.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")

    backlinks = _build_backlinks(target / "wiki")
    (target / "wiki/_backlinks.json").write_text(
        json.dumps(backlinks, indent=2), encoding="utf-8"
    )

    print(f"Link demo created at {target}")
    print("")
    print("View it:")
    print(f"  cd {target}")
    print("  python3 serve.py")
    print("")
    print("Then open:")
    print("  http://localhost:3000")
    print("  http://localhost:3000/graph")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="link.py", description="Link command runner")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="create a pre-ingested sample Link wiki")
    demo.add_argument("target", nargs="?", default=DEFAULT_DEMO_DIR)
    demo.add_argument("--force", action="store_true", help="replace an existing Link demo directory")

    doctor_cmd = sub.add_parser("doctor", help="check a Link wiki for common health issues")
    doctor_cmd.add_argument("target", nargs="?", default=".")
    doctor_cmd.add_argument("--fix", action="store_true", help="repair safe structural and backlink issues")

    ingest_status_cmd = sub.add_parser("ingest-status", help="show raw files pending wiki ingestion")
    ingest_status_cmd.add_argument("target", nargs="?", default=".")
    ingest_status_cmd.add_argument("--json", action="store_true", help="print machine-readable status")

    remember_cmd = sub.add_parser("remember", help="save a local agent memory")
    remember_cmd.add_argument("text", help="memory text to save")
    remember_cmd.add_argument("target", nargs="?", default=".")
    remember_cmd.add_argument("--title", default=None, help="memory page title")
    remember_cmd.add_argument("--type", choices=MEMORY_TYPES, default="note", dest="memory_type")
    remember_cmd.add_argument("--scope", choices=MEMORY_SCOPES, default="user")
    remember_cmd.add_argument("--tags", default=None, help="comma-separated tags")
    remember_cmd.add_argument("--source", default="manual", help="where this memory came from")
    remember_cmd.add_argument("--allow-duplicate", action="store_true", help="create a new memory even if a strong duplicate exists")
    remember_cmd.add_argument("--json", action="store_true", help="print machine-readable status")

    propose_cmd = sub.add_parser("propose-memories", help="propose durable memories from chat or session notes without writing them")
    propose_cmd.add_argument("source_input", help="text or path to a note/session file")
    propose_cmd.add_argument("target", nargs="?", default=".")
    propose_cmd.add_argument("--limit", type=int, default=10)
    propose_cmd.add_argument("--json", action="store_true", help="print machine-readable proposals")

    update_memory_cmd = sub.add_parser("update-memory", help="merge new text into an existing memory")
    update_memory_cmd.add_argument("identifier", help="memory page name, title, or path")
    update_memory_cmd.add_argument("text", help="new memory text to merge")
    update_memory_cmd.add_argument("target", nargs="?", default=".")
    update_memory_cmd.add_argument("--source", default="manual", help="where this update came from")
    update_memory_cmd.add_argument("--json", action="store_true", help="print machine-readable status")

    recall_cmd = sub.add_parser("recall", help="search local agent memories")
    recall_cmd.add_argument("query", help="memory query")
    recall_cmd.add_argument("target", nargs="?", default=".")
    recall_cmd.add_argument("--limit", type=int, default=10)
    recall_cmd.add_argument("--include-archived", action="store_true", help="include archived and stale memories")
    recall_cmd.add_argument("--json", action="store_true", help="print machine-readable results")

    profile_cmd = sub.add_parser("profile", help="show what Link remembers")
    profile_cmd.add_argument("target", nargs="?", default=".")
    profile_cmd.add_argument("--limit", type=int, default=10)
    profile_cmd.add_argument("--json", action="store_true", help="print machine-readable profile")

    archive_cmd = sub.add_parser("archive-memory", help="archive a stale or unwanted memory")
    archive_cmd.add_argument("identifier", help="memory page name, title, or path")
    archive_cmd.add_argument("target", nargs="?", default=".")
    archive_cmd.add_argument("--reason", default=None, help="why this memory is being archived")
    archive_cmd.add_argument("--json", action="store_true", help="print machine-readable status")

    restore_cmd = sub.add_parser("restore-memory", help="restore an archived memory to active status")
    restore_cmd.add_argument("identifier", help="memory page name, title, or path")
    restore_cmd.add_argument("target", nargs="?", default=".")
    restore_cmd.add_argument("--json", action="store_true", help="print machine-readable status")

    inbox_cmd = sub.add_parser("memory-inbox", help="show memories that need review")
    inbox_cmd.add_argument("target", nargs="?", default=".")
    inbox_cmd.add_argument("--limit", type=int, default=20)
    inbox_cmd.add_argument("--include-archived", action="store_true", help="include archived memories")
    inbox_cmd.add_argument("--json", action="store_true", help="print machine-readable inbox")

    review_cmd = sub.add_parser("review-memory", help="mark a memory as reviewed")
    review_cmd.add_argument("identifier", help="memory page name, title, or path")
    review_cmd.add_argument("target", nargs="?", default=".")
    review_cmd.add_argument("--note", default=None, help="optional review note")
    review_cmd.add_argument("--json", action="store_true", help="print machine-readable status")

    explain_cmd = sub.add_parser("explain-memory", help="explain why a memory exists and whether it is recall-ready")
    explain_cmd.add_argument("identifier", help="memory page name, title, or path")
    explain_cmd.add_argument("target", nargs="?", default=".")
    explain_cmd.add_argument("--json", action="store_true", help="print machine-readable explanation")

    rebuild_cmd = sub.add_parser("rebuild-backlinks", help="rebuild wiki/_backlinks.json")
    rebuild_cmd.add_argument("target", nargs="?", default=".")

    verify_mcp_cmd = sub.add_parser("verify-mcp", help="verify link-mcp import and print MCP config")
    verify_mcp_cmd.add_argument("target", nargs="?", default=".")
    verify_mcp_cmd.add_argument("--json", action="store_true", help="print machine-readable status")
    verify_mcp_cmd.add_argument("--python", default=None, help="Python executable to verify")

    args = parser.parse_args(argv)
    if args.command == "demo":
        create_demo(Path(args.target), force=args.force)
        return 0
    if args.command == "doctor":
        return doctor(Path(args.target), fix=args.fix)
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
            allow_duplicate=args.allow_duplicate,
            json_output=args.json,
        )
    if args.command == "propose-memories":
        return propose_memories(
            Path(args.target),
            args.source_input,
            limit=args.limit,
            json_output=args.json,
        )
    if args.command == "update-memory":
        return update_memory(
            Path(args.target),
            args.identifier,
            args.text,
            source=args.source,
            json_output=args.json,
        )
    if args.command == "recall":
        return recall(
            Path(args.target),
            args.query,
            limit=args.limit,
            json_output=args.json,
            include_archived=args.include_archived,
        )
    if args.command == "profile":
        return profile(Path(args.target), limit=args.limit, json_output=args.json)
    if args.command == "archive-memory":
        return archive_memory(Path(args.target), args.identifier, reason=args.reason, json_output=args.json)
    if args.command == "restore-memory":
        return restore_memory(Path(args.target), args.identifier, json_output=args.json)
    if args.command == "memory-inbox":
        return memory_inbox(
            Path(args.target),
            limit=args.limit,
            include_archived=args.include_archived,
            json_output=args.json,
        )
    if args.command == "review-memory":
        return review_memory(Path(args.target), args.identifier, note=args.note, json_output=args.json)
    if args.command == "explain-memory":
        return explain_memory(Path(args.target), args.identifier, json_output=args.json)
    if args.command == "rebuild-backlinks":
        return rebuild_backlinks(Path(args.target))
    if args.command == "verify-mcp":
        return verify_mcp(Path(args.target), json_output=args.json, python_cmd=args.python)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
