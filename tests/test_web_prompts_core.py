import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.web_prompts import render_prompts_page  # noqa: E402


def _layout(title: str, body: str) -> str:
    return f"<title>{title}</title>{body}"


def test_render_prompts_page_shows_project_and_commands():
    payload = {
        "project": "client-launch",
        "prompts": [{"label": "Readiness", "prompt": "is Link ready?", "when": "Before work"}],
        "commands": ["link status --validate"],
    }

    html = render_prompts_page(payload, layout=_layout)

    assert "<title>Starter Prompts</title>" in html
    assert "Project examples are scoped to <code>client-launch</code>" in html
    assert "Ask Your Agent" in html
    assert "Local Checks" in html
    assert "is Link ready?" in html
    assert 'data-copy-text="is Link ready?"' in html
    assert "Before work" in html
    assert "link status --validate" in html
    assert 'data-copy-text="link status --validate"' in html


def test_render_prompts_page_escapes_payload_fields():
    payload = {
        "project": "<project>",
        "prompts": [{"label": "<label>", "prompt": "ingest raw/<file>", "when": "<when>"}],
        "commands": ["link query '<topic>'"],
    }

    html = render_prompts_page(payload, layout=_layout)

    assert "&lt;project&gt;" in html
    assert "&lt;label&gt;" in html
    assert "ingest raw/&lt;file&gt;" in html
    assert 'data-copy-text="ingest raw/&lt;file&gt;"' in html
    assert "&lt;when&gt;" in html
    assert "link query &#x27;&lt;topic&gt;&#x27;" in html
    assert "<project>" not in html


def test_render_prompts_page_uses_personal_copy_without_project():
    html = render_prompts_page({"prompts": [], "commands": []}, layout=_layout)

    assert "personal Link wiki" in html
    assert "?project=slug" in html
