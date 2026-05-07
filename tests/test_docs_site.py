import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DocsSiteTests(unittest.TestCase):
    def test_github_pages_site_references_existing_local_assets(self):
        index = ROOT / "docs/index.html"
        html = index.read_text(encoding="utf-8")
        asset_refs = re.findall(r'(?:src|href)="(assets/[^"]+)"', html)

        self.assertIn("Link gives every agent the same memory.", html)
        self.assertIn("MCP Registry", html)
        self.assertTrue((ROOT / "docs/.nojekyll").exists())
        self.assertGreaterEqual(len(asset_refs), 4)
        for ref in asset_refs:
            self.assertTrue((ROOT / "docs" / ref).exists(), ref)

    def test_github_pages_site_has_no_external_runtime_dependencies(self):
        html = (ROOT / "docs/index.html").read_text(encoding="utf-8")

        self.assertNotIn("<script", html.lower())
        self.assertNotIn("fonts.googleapis.com", html)
        self.assertNotIn("../logo.svg", html)


if __name__ == "__main__":
    unittest.main()
