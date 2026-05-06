# Changelog

All notable changes to Link are tracked here.

Release sections use `MAJOR.MINOR.PATCH` versions that match `link-mcp` on PyPI and the MCP Registry. Keep `Unreleased` for work merged after the latest published version.

## [Unreleased]

### Added

- Added Memory Mode foundation with `wiki/memories/`, `link.py remember`, `link.py recall`, and MCP `remember_memory`/`recall_memory` tools.
- Added a first-run demo memory page so Link presents as local agent memory, not only a wiki.
- Added Memory Profile views through `link.py profile`, MCP `memory_profile`, `/profile`, and `/api/memory-profile`.
- Added reversible memory lifecycle controls with `archive-memory`/`restore-memory` and MCP `archive_memory`/`restore_memory`; archived memories are hidden from recall by default.
- Added Memory Review Inbox with `memory-inbox`, `review-memory`, MCP `memory_inbox`/`review_memory`, `/inbox`, and `/api/memory-inbox`.
- Added Explain Memory views with `explain-memory`, MCP `explain_memory`, `/explain-memory`, and `/api/explain-memory` for provenance, review state, lifecycle, graph links, and recall readiness.
- Added duplicate protection for `remember`/`remember_memory`; strong duplicate memories are refused unless explicitly allowed.
- Added memory merge/update workflow with `update-memory` and MCP `update_memory`, including update counts, audit logs, backlink rebuilds, and review reset.
- Added proposal-only memory extraction with `propose-memories` and MCP `propose_memories` for chat/session notes.
- Added agent memory briefs with `link.py brief` and MCP `memory_brief` so agents can prime themselves with relevant local memory before a task.
- Added conflict detection for memory writes, updates, and proposals; contradictory active memories are surfaced before saving unless explicitly allowed.
- Added shared memory review action plans so inbox and explanation payloads tell agents whether to review, update, archive, restore, or edit metadata next.
- Added read-only web Memory Dashboard at `/memory` and `/api/memory-dashboard` for active memories, review queue, recent updates, archived memories, and next-action commands.
- Added secure proposal-only HTTP endpoint `POST /api/propose-memories`; memory write operations remain CLI/MCP-only.
- Added a graph node inspector so moving nodes no longer accidentally opens pages; double-click or Open page still navigates.
- Added an explicit `system`/`dark`/`light` theme toggle for the local web UI; dark mode now uses a black page background.
- Added a real MCP stdio smoke test for the built `link-mcp` wheel in CI.
- Added Memory Dashboard next actions so the web UI and API surface the most important memory maintenance step.
- Extracted shared memory proposal logic into `link_core` so CLI, HTTP, and MCP proposal behavior stays aligned.
- Extracted shared frontmatter parsing and typed update helpers into `link_core` for safer memory metadata writes.
- Extracted shared memory record loading, review inbox, profile, and recall helpers into `link_core`.
- Extracted shared memory resolution, log lookup, and recall-state helpers into `link_core`.
- Extracted shared memory lifecycle mutations for archive, restore, review, and update workflows into `link_core`.
- Extracted shared memory creation for `remember` and `remember_memory` into `link_core`.
- Extracted shared wiki indexing, search, context, graph, and backlink helpers into `link_core`.
- Extracted shared memory explanation/audit payloads into `link_core`.

### Fixed

- Tightened README onboarding and release examples around Link's local memory product value.
- Fixed installer MCP setup reporting so failed upgrades no longer masquerade as success by reusing an unrelated older global `link-mcp`.
- Fixed project-mode installer output so MCP wiki paths are absolute and next-step hints point at the project wiki instead of `~/link`.
- Fixed search/context matching for natural queries against hyphenated page slugs, e.g. `local first software` now finds `local-first-software`.
- Hardened backlink rebuild over HTTP so local web rebuilds require JSON POST instead of a mutating GET.
- Hardened `/raw/` static serving so the local web viewer only serves supported media/PDF source assets.
- Refreshed the checked-in demo backlink index so `link.py doctor .` reports a healthy graph.

## [1.0.7] - 2026-05-04

### Fixed

- Fixed Codex MCP auto-registration after the venv installer fallback so existing `~/.codex/config.toml` files are updated without a regex crash.
- Fixed `link.py verify-mcp` to use the installer-recorded MCP Python when present.
- Fixed dashboard polish and search keyboard submission in the local web viewer.

## [1.0.6] - 2026-05-04

### Added

- Added `scripts/prepare_release.py` to bump MCP release versions, cut changelog notes, and print publish commands without uploading anything automatically.
- Added versioned changelog tracking for repo, PyPI, and MCP Registry releases.
- Added `link.py ingest-status` to show pending raw sources and stale graph indexes.
- Added `link.py doctor --fix` for safe structure creation and backlink repair.
- Added `link.py verify-mcp` to validate local MCP readiness and print client config.
- Added first 10 minutes onboarding docs.
- Added golden demo snapshot tests and direct MCP contract tests.

### Changed

- Polished the graph view with reset, label, and motion controls, keyboard focus, empty-state handling, cursor-centered zoom, and sticky dragged node placement.
- Restructured README.md into a product-doc flow: promise, quick start, first 10 minutes, install paths, then reference and release details.
- Switched release guidance to `release/*` branches and made changelog updates part of the release checklist.
- Refreshed the Link logo.
- Improved first-run and Homebrew/PEP 668 install documentation.
- Narrowed CI trigger noise to pull requests, `main` pushes, and manual dispatch.

### Fixed

- Hardened installers to avoid silently using `--break-system-packages`; they now fall back to `~/.link-mcp-venv` and register MCP with the resolved Python.
- Hardened the local viewer against unsafe graph JSON embedding, path-like wikilink targets, malformed static paths, and local path leakage from static file errors.
- Hardened `link-mcp` tool inputs for empty queries/topics and invalid search limits.
- Expanded `doctor` and release hygiene checks for common credential filenames, private keys, and token patterns.

## [1.0.5] - 2026-05-02

### Added

- Added `link.py demo` for a pre-ingested sample wiki.
- Added `link.py doctor` health checks for structure, backlinks, source hygiene, graph integrity, and secret-looking files.
- Added CI release gates for tests, demo health, installer syntax, package build, version consistency, and release hygiene.

### Changed

- Published `link-mcp` 1.0.5 package metadata for PyPI and the MCP Registry.

### Fixed

- Fixed `/api/context` and MCP context handling for the current backlink index shape.
- Fixed markdown rendering so raw HTML and unsafe markdown links cannot execute in the browser.
- Fixed installers so reruns preserve existing user instructions and project installs point MCP at the project wiki.
- Fixed wiki cache invalidation so edits to existing pages refresh search and context.
- Fixed MCP package reinstall behavior so rerunning installers upgrades `link-mcp`.
- Fixed invalid HTTP search limits to return controlled JSON errors.

## Earlier

- `1.0.2` through `1.0.4` were early public MCP packaging and hardening releases. Use `1.0.5` or newer for public installs.
