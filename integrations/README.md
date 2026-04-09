# Integrations

One-step setup for your AI tool. Default is global — one central wiki at `~/link/` that works across all projects.

## Quick start

```bash
git clone https://github.com/gowtham0992/link.git
bash link/integrations/kiro/install.sh
```

That's it. Kiro now knows about Link in every project, and your wiki lives at `~/link/`.

## All integrations

| Tool | Command | Global location |
|------|---------|----------------|
| Kiro | `bash integrations/kiro/install.sh` | `~/.kiro/steering/link.md` |
| Claude Code | `bash integrations/claude-code/install.sh` | `~/.claude/CLAUDE.md` |
| Antigravity | `bash integrations/antigravity/install.sh` | `~/.gemini/GEMINI.md` |
| Codex | `bash integrations/codex/install.sh` | `~/AGENTS.md` |
| Cursor | `bash integrations/cursor/install.sh` | `~/.cursor/rules/link.mdc` |
| Copilot | `bash integrations/copilot/install.sh` | `.github/copilot-instructions.md` |
| VS Code | `bash integrations/vscode/install.sh` | `.vscode/settings.json` |

## Two modes

- **Default (global):** `bash install.sh` — installs tool instructions globally + scaffolds central wiki at `~/link/`. One wiki for everything. Knowledge compounds across all your projects.

- **Project-local:** `bash install.sh --project` — installs instructions in current project + scaffolds wiki here. Use this when a specific project needs its own isolated wiki (e.g. team projects).

## What the install does

1. Writes tool-specific instruction file (so the agent always knows about Link)
2. Scaffolds wiki structure at `~/link/` (or current dir with `--project`):
   - `LINK.md` — the schema
   - `serve.py` — web viewer
   - `raw/` — for your source documents
   - `wiki/` — where the LLM writes articles

## Uninstall

Each folder has an `uninstall.sh`. Same `--project` flag applies.

## Auto-ingest hooks

The Kiro and Claude Code integrations include auto-ingest hooks that trigger when new files land in `raw/`. The agent automatically runs the ingest protocol — no manual "ingest this" needed.

Note: file-trigger hooks only fire when the wiki folder is part of the open workspace. For the global wiki at `~/link/`, you can add it as a workspace folder in your IDE, or just use manual ingest from any project.
