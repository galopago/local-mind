import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from link_core.web_http import (  # noqa: E402
    HOST_HEADER_LOCAL_ONLY,
    HOST_HEADER_REQUIRED,
    parse_bounded_int,
    validate_local_host_header,
)


class WebHttpCoreTests(unittest.TestCase):
    def test_parse_bounded_int_clamps_and_reports_errors(self):
        self.assertEqual(parse_bounded_int("", "limit", 40, 1, 100), (40, None))
        self.assertEqual(parse_bounded_int("250", "limit", 40, 1, 100), (100, None))
        self.assertEqual(parse_bounded_int("0", "limit", 40, 1, 100), (None, "limit must be at least 1"))
        self.assertEqual(parse_bounded_int("bad", "limit", 40, 1, 100), (None, "limit must be an integer"))

    def test_validate_local_host_header_accepts_local_hosts_with_ports(self):
        for host in ("127.0.0.1", "127.0.0.1:3000", "localhost", "localhost:3000"):
            self.assertEqual(validate_local_host_header(host), (True, None))

    def test_validate_local_host_header_rejects_missing_or_remote_hosts(self):
        self.assertEqual(validate_local_host_header(""), (False, HOST_HEADER_REQUIRED))
        self.assertEqual(validate_local_host_header("attacker.example"), (False, HOST_HEADER_LOCAL_ONLY))
        self.assertEqual(validate_local_host_header("localhost.evil.test"), (False, HOST_HEADER_LOCAL_ONLY))
        self.assertEqual(validate_local_host_header("localhost:bad"), (False, HOST_HEADER_LOCAL_ONLY))
        self.assertEqual(validate_local_host_header("localhost attacker"), (False, HOST_HEADER_LOCAL_ONLY))


if __name__ == "__main__":
    unittest.main()
