import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DocsSiteTests(unittest.TestCase):
    def docs_pages(self):
        return sorted((ROOT / "docs").glob("*.html"))

    def test_github_pages_site_references_existing_local_assets(self):
        pages = self.docs_pages()
        self.assertGreaterEqual(len(pages), 6)
        self.assertTrue((ROOT / "docs/.nojekyll").exists())

        all_refs = []
        for page in pages:
            html = page.read_text(encoding="utf-8")
            all_refs.extend(re.findall(r'(?:src|href)="(assets/[^"]+)"', html))
            for local_page in re.findall(r'href="([^":#]+\.html)"', html):
                self.assertTrue((ROOT / "docs" / local_page).exists(), f"{page.name} -> {local_page}")

        index_html = (ROOT / "docs/index.html").read_text(encoding="utf-8")
        self.assertIn("Link gives every agent the same memory.", index_html)
        self.assertIn("MCP Registry", index_html)
        self.assertGreaterEqual(len(all_refs), 10)
        for ref in all_refs:
            self.assertTrue((ROOT / "docs" / ref).exists(), ref)

    def test_github_pages_site_has_no_external_runtime_dependencies(self):
        for page in self.docs_pages():
            html = page.read_text(encoding="utf-8")

            self.assertNotIn("<script", html.lower())
            self.assertNotIn("fonts.googleapis.com", html)
            self.assertNotIn("../logo.svg", html)


if __name__ == "__main__":
    unittest.main()
