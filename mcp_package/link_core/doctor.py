"""Shared doctor report helpers for Link health checks."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


DOCTOR_VALIDATION_CODES = {
    "invalid_directory",
    "missing_frontmatter",
    "missing_frontmatter_field",
    "missing_required_section",
    "type_directory_mismatch",
    "unreadable_page",
}


@dataclass
class DoctorReport:
    """Structured health-check report used by the CLI and future UI/API surfaces."""

    target: str
    fixes: list[str] = field(default_factory=list)
    ok: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    fix_requested: bool = False

    @property
    def healthy(self) -> bool:
        return not self.errors

    def add_ok(self, message: str) -> None:
        self.ok.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_error(self, message: str) -> None:
        self.errors.append(message)


def doctor_validation_errors(validation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return validation findings that should make doctor fail."""
    findings = validation.get("findings", [])
    if not isinstance(findings, list):
        return []
    return [
        finding
        for finding in findings
        if isinstance(finding, dict)
        and finding.get("severity") == "error"
        and str(finding.get("code") or "") in DOCTOR_VALIDATION_CODES
    ]


def format_validation_error_summary(findings: list[Mapping[str, Any]], limit: int = 8) -> str:
    details = [
        f"{finding.get('path')} [{finding.get('code')}] {finding.get('message')}"
        for finding in findings[:limit]
    ]
    return "validation errors: " + "; ".join(details)


def join_limited(prefix: str, values: list[str], limit: int = 8) -> str:
    return prefix + ", ".join(values[:limit])


def render_doctor_report(report: DoctorReport) -> str:
    """Render a doctor report using the stable CLI text format."""
    lines = [f"Link doctor: {report.target}", ""]
    if report.fix_requested:
        if report.fixes:
            lines.append("Fixes applied:")
            lines.extend(f"- {item}" for item in report.fixes)
            lines.append("")
        else:
            lines.append("Fixes applied: none")
            lines.append("")

    lines.extend(report.ok)

    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in report.warnings)

    if report.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in report.errors)
        lines.append("")
        lines.append("Result: needs attention")
    else:
        lines.append("")
        lines.append("Result: healthy")

    return "\n".join(lines)
