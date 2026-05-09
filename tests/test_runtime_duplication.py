import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "runtime_duplication", ROOT / "scripts/check_runtime_duplication.py"
)
runtime_duplication = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = runtime_duplication
SPEC.loader.exec_module(runtime_duplication)


class RuntimeDuplicationTests(unittest.TestCase):
    def test_current_runtime_duplication_guard_passes(self):
        functions = runtime_duplication.runtime_functions()

        findings = [
            *runtime_duplication.check_exact_duplicate_bodies(functions),
            *runtime_duplication.check_large_duplicate_private_names(functions),
        ]

        self.assertEqual(findings, [])

    def test_large_duplicate_private_helper_is_reported(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-runtime-dup-test-"))
        a = tmp / "a.py"
        b = tmp / "b.py"
        body = "\n".join(f"    value += {i}" for i in range(22))
        a.write_text(f"def _copied():\n    value = 0\n{body}\n    return value\n", encoding="utf-8")
        b.write_text(f"def _copied():\n    value = 1\n{body}\n    return value\n", encoding="utf-8")

        functions = runtime_duplication.runtime_functions((a, b))

        findings = runtime_duplication.check_large_duplicate_private_names(functions)

        self.assertTrue(any("_copied" in finding for finding in findings))

    def test_exact_duplicate_body_is_reported_even_with_different_names(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-runtime-dup-test-"))
        a = tmp / "a.py"
        b = tmp / "b.py"
        body = "\n".join(f"    value += {i}" for i in range(12))
        a.write_text(f"def first():\n    value = 0\n{body}\n    return value\n", encoding="utf-8")
        b.write_text(f"def second():\n    value = 0\n{body}\n    return value\n", encoding="utf-8")

        functions = runtime_duplication.runtime_functions((a, b))

        findings = runtime_duplication.check_exact_duplicate_bodies(functions)

        self.assertTrue(any("exact duplicate" in finding for finding in findings))

    def test_report_tracks_thin_duplicate_private_helpers_without_failing(self):
        tmp = Path(tempfile.mkdtemp(prefix="link-runtime-dup-test-"))
        a = tmp / "a.py"
        b = tmp / "b.py"
        a.write_text("def _adapter():\n    return 1\n", encoding="utf-8")
        b.write_text("def _adapter():\n    return 2\n", encoding="utf-8")

        functions = runtime_duplication.runtime_functions((a, b))

        report = runtime_duplication.format_private_name_report(functions)
        findings = runtime_duplication.check_large_duplicate_private_names(functions)

        self.assertIn("_adapter", report)
        self.assertIn("thin", report)
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
