"""Local security hygiene helpers for Link."""
from __future__ import annotations

import re
from pathlib import Path


SECRET_VALUE_PATTERNS = (
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("OpenAI API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("AWS access key", re.compile(r"\bA[SK]IA[0-9A-Z]{16}\b")),
    ("PyPI token", re.compile(r"\bpypi-[A-Za-z0-9_-]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("Stripe live secret key", re.compile(r"\bsk_live_[A-Za-z0-9]{20,}\b")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)


def clean_text_input(value: object, max_len: int = 500) -> str:
    """Normalize optional user/tool text input to a stripped, bounded string."""
    if value is None:
        return ""
    return str(value).strip()[:max_len]


def secret_value_warnings(text: str) -> list[str]:
    """Return labels for secret-looking values found in text."""
    warnings: list[str] = []
    for label, pattern in SECRET_VALUE_PATTERNS:
        if pattern.search(text):
            warnings.append(label)
    return warnings


def secret_file_warnings(path: Path, chunk_size: int = 65536, tail_size: int = 512) -> list[str]:
    """Return secret-looking labels from a file without loading it all at once."""
    return list(secret_file_scan(path, chunk_size=chunk_size, tail_size=tail_size)["labels"])


def secret_file_scan(path: Path, chunk_size: int = 65536, tail_size: int = 512) -> dict[str, object]:
    """Scan a file for secret-looking values and report read failures explicitly."""
    found: set[str] = set()
    read_size = max(1, chunk_size)
    tail_len = max(0, tail_size)
    tail = ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            while True:
                chunk = handle.read(read_size)
                if not chunk:
                    break
                text = tail + chunk
                found.update(secret_value_warnings(text))
                if len(found) == len(SECRET_VALUE_PATTERNS):
                    break
                tail = text[-tail_len:] if tail_len else ""
    except OSError as exc:
        return {
            "labels": [],
            "readable": False,
            "error": str(exc),
        }
    return {
        "labels": [label for label, _pattern in SECRET_VALUE_PATTERNS if label in found],
        "readable": True,
        "error": "",
    }


def redact_secret_values(text: str, replacement: str = "[redacted-secret]") -> tuple[str, list[str], int]:
    """Replace secret-looking values and return redacted text, labels, and count."""
    labels: list[str] = []
    total = 0
    redacted = text
    for label, pattern in SECRET_VALUE_PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        if count:
            labels.append(label)
            total += count
    return redacted, labels, total
