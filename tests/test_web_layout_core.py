import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.web_layout import render_footer_html, render_header_html, render_layout  # noqa: E402


class WebLayoutCoreTests(unittest.TestCase):
    def test_header_has_primary_navigation_and_search(self):
        html = render_header_html()

        self.assertIn('<a href="/ingest">ingest</a>', html)
        self.assertIn('<a href="/brief">brief</a>', html)
        self.assertIn('<a href="/propose">propose</a>', html)
        self.assertIn('<a href="/graph">graph</a>', html)
        self.assertIn('id="search-input"', html)
        self.assertIn("data-theme-toggle", html)

    def test_footer_points_to_github(self):
        html = render_footer_html()

        self.assertIn("local agent memory", html)
        self.assertIn("https://github.com/gowtham0992/link", html)

    def test_layout_escapes_title_and_page_class(self):
        html = render_layout('<Title>', "<main>Body</main>", page_class='graph" onclick="bad')

        self.assertIn("<title>&lt;Title&gt; — Link</title>", html)
        self.assertIn('class="graph&quot; onclick=&quot;bad"', html)
        self.assertIn("<main>Body</main>", html)
        self.assertIn("document.activeElement.id === 'search-input'", html)
        self.assertIn("window.location.href = '/search?q=' + encodeURIComponent(q);", html)
        self.assertIn("localStorage.getItem('link-theme')", html)
        self.assertIn("navigator.clipboard.writeText", html)
        self.assertIn("/api/raw-source", html)


if __name__ == "__main__":
    unittest.main()
