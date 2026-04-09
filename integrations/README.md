# Integrations

One-step setup for your AI tool. Two modes:

- `--global` — install once, Link is available in every project you open
- `--project` — install into the current project + scaffold the wiki structure

## Quick start

```bash
# Clone Link
git clone https://github.com/gowtham0992/link.git

# Global install (every project gets Link context automatically)
bash link/integrations/kiro/install.sh --global

# Then in any project, scaffold the wiki
cd my-project
bash /path/to/link/integrations/kiro/install.sh --project
```

## All integrations

| Tool | Global | Project | What it writes |
|------|--------|---------|----------------|
| Claude Code | `--global` → `~/.claude/CLAUDE.md` | `--project` → `./CLAUDE.md` + wiki | Persistent instructions |
| Codex | `--global` → `~/AGENTS.md` | `--project` → `./AGENTS.md` + wiki | Persistent instructions |
| Cursor | `--global` → `~/.cursor/rules/link.mdc` | `--project` → `.cursor/rules/link.mdc` + wiki | Always-apply rule |
| Kiro | `--global` → `~/.kiro/steering/link.md` | `--project` → `.kiro/steering/link.md` + wiki | Always-on steering |
| Copilot | — | `--project` → `.github/copilot-instructions.md` + wiki | Project instructions |
| VS Code | — | `--project` → `.vscode/settings.json` + wiki | Copilot chat instructions |

`--project` is the default if you don't specify a mode.

Every script is idempotent — safe to re-run. Each folder has an `uninstall.sh` too.

## What `--project` does

1. Writes the tool-specific instruction file
2. Copies `LINK.md` (the schema) into your project
3. Copies `serve.py` (the web viewer)
4. Creates `raw/`, `wiki/sources/`, `wiki/concepts/`, `wiki/entities/`, etc.
5. Creates empty `wiki/index.md` and `wiki/log.md`

After that, drop sources into `raw/` and tell your agent to ingest them.
