import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.markdown import markdown_to_html  # noqa: E402


class MarkdownCoreTests(unittest.TestCase):
    def test_inline_markdown_sanitizes_html_and_links(self):
        rendered = markdown_to_html(
            "Hello <script>alert(1)</script> "
            "and [bad](javascript:alert%281%29) "
            "and [ok](https://example.com?a=1&b=2) "
            "and [[target|<b>label</b>]] "
            "and `<tag>`"
        )

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertIn('<a href="#">bad</a>', rendered)
        self.assertIn('<a href="https://example.com?a=1&amp;b=2">ok</a>', rendered)
        self.assertIn('<a href="/page/target">&lt;b&gt;label&lt;/b&gt;</a>', rendered)
        self.assertIn("<code>&lt;tag&gt;</code>", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("javascript:", rendered.lower())

    def test_wikilink_targets_encode_path_separators(self):
        rendered = markdown_to_html("[[../raw/private|private]]")

        self.assertIn('<a href="/page/..%2Fraw%2Fprivate">private</a>', rendered)
        self.assertNotIn("/page/../raw/private", rendered)

    def test_blocks_tables_lists_and_code_blocks(self):
        rendered = markdown_to_html(
            "# Title\n\n"
            "> quote **bold**\n\n"
            "- one\n"
            "- two\n\n"
            "| A | B |\n"
            "|---|---|\n"
            "| `x` | *y* |\n\n"
            "```python\n"
            "<raw>\n"
            "```"
        )

        self.assertIn("<h1>Title</h1>", rendered)
        self.assertIn("<blockquote>quote <strong>bold</strong></blockquote>", rendered)
        self.assertIn("<ul>", rendered)
        self.assertIn("<li>one</li>", rendered)
        self.assertIn("<table>", rendered)
        self.assertIn("<td><code>x</code></td>", rendered)
        self.assertIn('<pre><code class="language-python">', rendered)
        self.assertIn("&lt;raw&gt;", rendered)


if __name__ == "__main__":
    unittest.main()
