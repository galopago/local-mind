# Contributing To Link

Thanks for helping improve Link. The goal is simple: make local agent memory
easier to trust, inspect, and use.

Please open pull requests against `main` unless the maintainer asks for a
different target. The `develop` branch is a maintainer integration branch for
staging release work before it is proposed to `main`.

## Before Opening A PR

Run the local gate:

```bash
python3 -m pip install "ruff>=0.8,<1"
python3 -m ruff check .
python3 -m unittest discover -s tests
python3 scripts/check_release_hygiene.py
python3 scripts/check_runtime_duplication.py
python3 scripts/check_tool_contract.py
git diff --check
```

For UI changes, include a screenshot or GIF. For installer, MCP, memory-write,
HTTP API, or automation changes, call that out explicitly in the PR description.

## PR Description

Include:

- What changed.
- How you tested it.
- Whether it touches memory writes, installers, MCP behavior, HTTP endpoints, or
  automation.
- Screenshots or GIFs for UI changes.

Do not include personal wiki data, raw sources, registry tokens, `.env` files, or
local MCP credentials in a PR.

Full contributor guide:
https://gowtham0992.github.io/link/contributing.html
