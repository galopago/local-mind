"""Shared local HTTP guard helpers for Link's web viewer."""
from __future__ import annotations

from typing import Iterable


ALLOWED_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})
HOST_HEADER_REQUIRED = "Host header required"
HOST_HEADER_LOCAL_ONLY = "Host header must be localhost or 127.0.0.1"


def parse_bounded_int(
    raw: object,
    label: str,
    default: int,
    min_value: int,
    max_value: int,
) -> tuple[int | None, str | None]:
    """Parse a bounded integer query parameter."""
    if raw == "" or raw is None:
        return default, None
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None, f"{label} must be an integer"
    if value < min_value:
        return None, f"{label} must be at least {min_value}"
    return min(value, max_value), None


def _host_without_port(host: str) -> str | None:
    if any(char.isspace() for char in host):
        return None
    if host.startswith("["):
        closing = host.find("]")
        if closing < 0:
            return None
        host_name = host[1:closing]
        remainder = host[closing + 1:]
        if remainder:
            if not remainder.startswith(":"):
                return None
            port = remainder[1:]
            if port and not port.isdigit():
                return None
        return host_name
    if host.count(":") == 1:
        host_name, port = host.rsplit(":", 1)
        if port and not port.isdigit():
            return None
        return host_name
    if ":" in host:
        return None
    return host


def validate_local_host_header(
    host_header: object,
    allowed_hosts: Iterable[str] = ALLOWED_LOCAL_HOSTS,
) -> tuple[bool, str | None]:
    """Validate a local-only Host header for the unauthenticated viewer."""
    host = str(host_header or "").strip().lower()
    if not host:
        return False, HOST_HEADER_REQUIRED
    host_name = _host_without_port(host)
    if host_name in set(allowed_hosts):
        return True, None
    return False, HOST_HEADER_LOCAL_ONLY
