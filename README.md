<p align="center">
  <img src="logo.png" alt="Link" width="120">
</p>

# Link

A personal knowledge wiki maintained by LLMs. 

Based on [Andrej Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

[![GitHub](https://img.shields.io/github/stars/gowtham0992/link?style=flat)](https://github.com/gowtham0992/link)

## How it works

1. Drop sources (articles, papers, notes, images) into `raw/`
2. Tell your LLM agent: "ingest this" — it reads the source and compiles structured wiki pages
3. The wiki grows over time. Ask questions, get answers filed back. Knowledge compounds.

You never write the wiki yourself. The LLM writes and maintains all of it. You curate sources and ask questions.

## Setup

Run the install script for your tool — it wires Link into your agent's "always remember" mechanism:

```bash
bash integrations/claude-code/install.sh   # Claude Code → CLAUDE.md
bash integrations/codex/install.sh         # Codex → AGENTS.md
bash integrations/cursor/install.sh        # Cursor → .cursor/rules/link.mdc
bash integrations/kiro/install.sh          # Kiro → .kiro/steering/link.md
bash integrations/copilot/install.sh       # Copilot → .github/copilot-instructions.md
bash integrations/vscode/install.sh        # VS Code → .vscode/settings.json
```

That's it. Your agent will know about Link on every session. See [integrations/](integrations/) for details.

## Viewing the wiki

**Obsidian:** open the `wiki/` folder as a vault. Wikilinks, graph view, and tags all work natively.

**Web browser:**
```bash
python serve.py
# → http://localhost:3000
```

Wikipedia-style local viewer with search, navigation, dark mode. No dependencies beyond Python 3.10+.

## Structure

```
link/
├── LINK.md              ← schema (instructions for the LLM)
├── raw/                 ← your source documents (immutable)
├── wiki/                ← compiled knowledge (LLM-maintained)
│   ├── index.md         ← master catalog
│   ├── log.md           ← operation history
│   ├── sources/         ← one page per ingested source
│   ├── concepts/        ← topic articles
│   ├── entities/        ← people, orgs, projects
│   ├── comparisons/     ← side-by-side analyses
│   └── explorations/    ← filed query results
├── integrations/        ← one-step setup per AI tool
├── serve.py             ← local web viewer
└── .linkignore          ← files to skip
```

## Operations

| Command | What it does |
|---------|-------------|
| "ingest this" | Process a source from raw/ into wiki pages |
| "what is X?" | Query the wiki, optionally file the answer back |
| "lint the wiki" | Health check: orphans, contradictions, stale claims |

## Design principles

- Every claim links to its source. No orphan claims.
- Confidence tags on facts: high, medium, low.
- Pages mature over time: seed → growing → mature → established.
- The wiki is just markdown files in a git repo. Version history for free.
