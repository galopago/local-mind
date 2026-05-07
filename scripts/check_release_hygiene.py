#!/usr/bin/env python3
"""Check tracked files for release-blocking credential leaks."""
from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path


SECRET_NAME_PATTERNS = (
    ".env",
    ".env.*",
    ".envrc",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "*.token",
    ".mcpregistry_*",
    "*.key",
    "*.pem",
    "*.p8",
    "*.p12",
    "*.jks",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "service-account*.json",
)

BUILD_ARTIFACT_PATTERNS = (
    "dist/*",
    "*/dist/*",
    "*.whl",
    "*.tar.gz",
    "*.egg-info",
    "*.egg-info/*",
)

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

BINARY_SUFFIXES = {
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".pyc",
    ".tar",
    ".webp",
    ".whl",
    ".zip",
}

CHANGELOG_VERSION_RE = re.compile(r"^## \[([^\]]+)\](?: - \d{4}-\d{2}-\d{2})?\s*$", re.MULTILINE)

AGENT_CONTRACT_REQUIREMENTS = {
    Path("LINK.md"): ("link_status", "query_link", "validate_wiki", "memory_brief"),
    Path("README.md"): ("link_status", "query_link", "validate_wiki", "memory_brief"),
    Path("mcp_package/README.md"): ("link_status", "query_link", "validate_wiki", "memory_brief"),
    Path("integrations/_shared/link-instructions.md"): ("link_status", "query_link", "validate_wiki", "memory_brief"),
    Path("integrations/_shared/link-instructions-project.md"): ("link_status", "query_link", "validate_wiki", "memory_brief"),
}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        stdout=subprocess.PIPE,
    )
    names = result.stdout.decode("utf-8").split("\0")
    return [Path(name) for name in names if name]


def read_pyproject_version(path: Path) -> str | None:
    match = re.search(r'^version\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8"), flags=re.MULTILINE)
    return match.group(1) if match else None


def read_init_version(path: Path) -> str | None:
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8"), flags=re.MULTILINE)
    return match.group(1) if match else None


def check_version_consistency(findings: list[str]) -> str | None:
    pyproject_version = read_pyproject_version(Path("mcp_package/pyproject.toml"))
    init_version = read_init_version(Path("mcp_package/link_mcp/__init__.py"))
    server = json.loads(Path("mcp_package/server.json").read_text(encoding="utf-8"))
    server_version = server.get("version")
    package_versions = {
        package.get("version")
        for package in server.get("packages", [])
        if package.get("identifier") == "link-mcp"
    }
    versions = {
        "mcp_package/pyproject.toml": pyproject_version,
        "mcp_package/link_mcp/__init__.py": init_version,
        "mcp_package/server.json": server_version,
    }
    if len(set(versions.values()) | package_versions) != 1:
        for label, version in versions.items():
            findings.append(f"version mismatch: {label} is {version!r}")
        findings.append(f"version mismatch: server.json package versions are {sorted(package_versions)!r}")
    return pyproject_version


def read_changelog_versions(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    return CHANGELOG_VERSION_RE.findall(text)


def check_changelog(findings: list[str], current_version: str | None, path: Path = Path("CHANGELOG.md")) -> None:
    versions = read_changelog_versions(path)
    if not versions:
        findings.append("missing or empty CHANGELOG.md version sections")
        return
    if "Unreleased" not in versions:
        findings.append("CHANGELOG.md missing ## [Unreleased] section")
    if not current_version:
        findings.append("could not determine current package version for CHANGELOG.md check")
    elif current_version not in versions:
        findings.append(f"CHANGELOG.md missing current package version: {current_version}")


def check_agent_contract(
    findings: list[str],
    requirements: dict[Path, tuple[str, ...]] = AGENT_CONTRACT_REQUIREMENTS,
) -> None:
    for path, required_terms in requirements.items():
        if not path.exists():
            findings.append(f"agent contract file missing: {path}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for term in required_terms:
            if term not in text:
                findings.append(f"agent contract missing {term!r} in {path}")


def check_tracked_path_hygiene(findings: list[str], path: Path) -> bool:
    """Check release-blocking tracked path patterns. Return true when caller should skip content scan."""
    rel = path.as_posix()
    if any(fnmatch.fnmatch(rel, pattern) for pattern in BUILD_ARTIFACT_PATTERNS):
        findings.append(f"build artifact should not be tracked: {path}")
        return True

    name = path.name
    if any(fnmatch.fnmatch(name, pattern) for pattern in SECRET_NAME_PATTERNS):
        findings.append(f"sensitive-looking tracked filename: {path}")
        return True

    return False


def main() -> int:
    findings: list[str] = []
    current_version = check_version_consistency(findings)
    check_changelog(findings, current_version)
    check_agent_contract(findings)

    for path in tracked_files():
        if check_tracked_path_hygiene(findings, path):
            continue

        if path.suffix.lower() in BINARY_SUFFIXES:
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(f"could not read tracked file {path}: {exc}")
            continue

        for label, pattern in SECRET_VALUE_PATTERNS:
            if pattern.search(text):
                findings.append(f"sensitive-looking content in {path}: {label}")
                break

    if findings:
        print("Release hygiene check failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("Release hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
