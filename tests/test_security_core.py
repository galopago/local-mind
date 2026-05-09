import unittest
import tempfile
from pathlib import Path

from mcp_package.link_core.security import (
    clean_text_input,
    redact_secret_values,
    secret_file_warnings,
    secret_value_warnings,
)


class SecurityCoreTests(unittest.TestCase):
    def test_clean_text_input_strips_bounds_and_handles_none(self):
        self.assertEqual(clean_text_input(None), "")
        self.assertEqual(clean_text_input("  hello  "), "hello")
        self.assertEqual(clean_text_input("  hello world  ", max_len=5), "hello")
        self.assertEqual(clean_text_input(123, max_len=2), "12")

    def test_secret_warnings_and_redaction(self):
        fake_key = "sk-" + "a" * 48

        warnings = secret_value_warnings(f"token {fake_key}")
        redacted, labels, count = redact_secret_values(f"token {fake_key}")

        self.assertEqual(warnings, ["OpenAI API key"])
        self.assertEqual(labels, ["OpenAI API key"])
        self.assertEqual(count, 1)
        self.assertNotIn(fake_key, redacted)
        self.assertIn("[redacted-secret]", redacted)

    def test_secret_file_warnings_streams_across_chunks(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-security-core-"))
        fake_key = "sk-" + "a" * 48
        path = tmp / "large-ish-source.md"
        path.write_text("safe text\n" + ("x" * 40) + " " + fake_key + "\n", encoding="utf-8")

        warnings = secret_file_warnings(path, chunk_size=16, tail_size=80)

        self.assertEqual(warnings, ["OpenAI API key"])

    def test_secret_file_warnings_handles_missing_file(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-security-core-"))

        warnings = secret_file_warnings(tmp / "missing.md")

        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
