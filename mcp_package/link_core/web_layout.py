"""Shared HTML shell for the local Link web UI."""
from __future__ import annotations

import html

from .web_assets import (
    COPY_BUTTON_JS,
    CSS,
    MEMORY_ACTION_JS,
    PROPOSAL_UI_JS,
    RAW_SOURCE_JS,
    THEME_CONTROL_JS,
    THEME_INIT_JS,
)


KEYBOARD_NAV_JS = """
// Keyboard navigation
document.addEventListener('keydown', function(e) {
  var tag = document.activeElement.tagName;
  var inInput = tag === 'INPUT' || tag === 'TEXTAREA';
  // / -> focus search
  if (e.key === '/' && !inInput) {
    e.preventDefault();
    var inp = document.getElementById('search-input');
    if (inp) { inp.focus(); inp.select(); }
  }
  // Escape -> blur search
  if (e.key === 'Escape' && inInput) {
    document.activeElement.blur();
  }
  if (e.key === 'Enter' && document.activeElement.id === 'search-input') {
    var q = document.activeElement.value.trim();
    if (q) {
      e.preventDefault();
      window.location.href = '/search?q=' + encodeURIComponent(q);
    }
  }
  // j/k -> navigate focusable links in page-list
  if ((e.key === 'j' || e.key === 'k') && !inInput) {
    var links = Array.from(document.querySelectorAll('.page-list a, .search-results a'));
    if (!links.length) return;
    var cur = document.activeElement;
    var idx = links.indexOf(cur);
    if (e.key === 'j') idx = idx < links.length - 1 ? idx + 1 : 0;
    else idx = idx > 0 ? idx - 1 : links.length - 1;
    links[idx].focus();
    e.preventDefault();
  }
});
"""


def render_header_html() -> str:
    return """<header>
  <div class="header-top">
    <div class="logo"><a href="/"><img src="/logo.svg" alt="">Link</a><small>agent memory</small></div>
    <div class="header-tools">
      <button type="button" class="theme-toggle" data-theme-toggle>
        <span class="theme-icon" aria-hidden="true"></span><span class="theme-text" data-theme-text>system</span>
      </button>
      <form action="/search" method="get">
        <input type="text" name="q" placeholder="search... (/)" autocomplete="off" id="search-input">
      </form>
    </div>
  </div>
  <nav>
    <a href="/">home</a>
    <a href="/prompts">prompts</a>
    <a href="/ingest">ingest</a>
    <a href="/brief">brief</a>
    <a href="/propose">propose</a>
    <a href="/memory">memory</a>
    <a href="/audit">audit</a>
    <a href="/inbox">inbox</a>
    <a href="/captures">captures</a>
    <a href="/profile">profile</a>
    <a href="/page/log">log</a>
    <a href="/all">all pages</a>
    <a href="/graph">graph</a>
  </nav>
</header>"""


def render_footer_html() -> str:
    return '<footer>Link — local agent memory · <a href="https://github.com/gowtham0992/link">github</a></footer>'


def render_layout(title: str, body: str, page_class: str = "") -> str:
    body_class = f' class="{html.escape(page_class, quote=True)}"' if page_class else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)} — Link</title>
<link rel="icon" href="/logo.svg" type="image/svg+xml">
<script>{THEME_INIT_JS}</script>
<style>{CSS}</style>
</head>
<body{body_class}>
{render_header_html()}
<div class="graph-tooltip" id="graph-tooltip"></div>
{body}
{render_footer_html()}
<script>{KEYBOARD_NAV_JS}</script>
<script>{THEME_CONTROL_JS}</script>
<script>{MEMORY_ACTION_JS}</script>
<script>{COPY_BUTTON_JS}</script>
<script>{RAW_SOURCE_JS}</script>
<script>{PROPOSAL_UI_JS}</script>
</body>
</html>"""
