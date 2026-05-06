## Link — Local Agent Memory

Local agent memory lives at `~/link/`. It has raw sources in `~/link/raw/`, compiled wiki pages in `~/link/wiki/`, and direct memories in `~/link/wiki/memories/`.

When answering a substantive question that may need local memory or wiki context, start with MCP `query_link` when available, or run `python3 ~/link/link.py query "<task or question>" ~/link`.

When starting personalized or project-specific work, prime yourself with Link first: use MCP `memory_brief` when available, or run `python3 ~/link/link.py brief "<task or question>" ~/link`.

After ingesting raw sources or making substantial wiki edits, use MCP `rebuild_backlinks` and `validate_wiki` when available, or run `python3 ~/link/link.py rebuild-backlinks ~/link` and `python3 ~/link/link.py validate ~/link`, before saying the wiki is updated.

When the user says **"remember"**, **"recall"**, **"ingest"**, **"query"**, **"lint"**, or **"research"**, read `~/link/LINK.md` for instructions and follow the protocol. Use terminal commands to access `~/link/` since it's outside the workspace.

Otherwise, don't interfere — just be a normal assistant.
