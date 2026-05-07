import unittest

from mcp_package.link_core.security import clean_text_input, redact_secret_values, secret_value_warnings


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


if __name__ == "__main__":
    unittest.main()
