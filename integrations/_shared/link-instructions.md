## Link — Personal Knowledge Wiki

This project uses Link, an LLM-maintained knowledge wiki.

**Wiki location: `~/link/`** — all wiki operations read/write there, not in the current project.

**Read `~/link/LINK.md` before performing any wiki operations.** It contains the full schema, page templates, and workflow instructions.

**Key rules:**
- When the user says "ingest", read the source from `~/link/raw/` and follow the ingest protocol in LINK.md
- When the user says "query" or asks about topics the wiki covers, search `~/link/wiki/index.md` first, then read relevant pages. Use terminal: `cat ~/link/wiki/index.md`
- When the user says "lint", run the health check protocol from LINK.md
- Do NOT check the wiki for coding questions, debugging, or tasks unrelated to the wiki's knowledge domain
- Every claim must link to its source. Use `[[wikilinks]]` for cross-references.
- Tag confidence on claims: `[confidence: high]`, `[confidence: medium]`, `[confidence: low]`
- Never modify files in `~/link/raw/` — they are immutable source documents
- The wiki is in `~/link/wiki/` — you own this directory entirely
- To view the wiki: `python ~/link/serve.py`
- At the start of each session, check ~/link/raw/ for any files not yet in wiki/sources/. If found, offer to ingest them.
- IMPORTANT: ~/link/ is outside the workspace. Always use terminal commands (ls, cat) to read files there, not workspace search.
