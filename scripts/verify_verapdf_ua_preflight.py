#!/usr/bin/env python3
"""Require veraPDF UA-1 preflight to fail only on the withheld declaration."""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


class PreflightError(RuntimeError):
    """Raised when the official validator reports an unexpected result."""


_EXPECTED_PROFILE = "PDF/UA-1 validation profile"
_EXPECTED_RULE = {
    "specification": "ISO 14289-1:2014",
    "clause": "5",
    "testNumber": "1",
    "status": "failed",
    "failedChecks": "1",
}
_EXPECTED_ERROR = (
    "The document metadata stream doesn't contain PDF/UA Identification Schema"
)


def _one(parent: ET.Element, path: str, label: str) -> ET.Element:
    values = parent.findall(path)
    if len(values) != 1:
        raise PreflightError(f"expected exactly one {label}; found {len(values)}")
    return values[0]


def verify(report_path: Path) -> dict[str, str | int]:
    try:
        root = ET.parse(report_path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise PreflightError(f"unable to parse veraPDF report: {exc}") from exc

    report = _one(root, "./jobs/job/validationReport", "validation report")
    expected_report = {
        "jobEndStatus": "normal",
        "profileName": _EXPECTED_PROFILE,
        "isCompliant": "false",
    }
    for name, expected in expected_report.items():
        if report.get(name) != expected:
            raise PreflightError(
                f"unexpected validationReport {name}: {report.get(name)!r}"
            )

    details = _one(report, "./details", "validation details")
    if details.get("failedRules") != "1" or details.get("failedChecks") != "1":
        raise PreflightError(
            "forced UA-1 profile must have exactly one rule and check failure"
        )

    rule = _one(details, "./rule", "failed rule")
    for name, expected in _EXPECTED_RULE.items():
        if rule.get(name) != expected:
            raise PreflightError(f"unexpected failed-rule {name}: {rule.get(name)!r}")

    failed_checks = rule.findall("./check[@status='failed']")
    if len(failed_checks) != 1:
        raise PreflightError(
            f"expected one failed declaration check; found {len(failed_checks)}"
        )
    error = _one(failed_checks[0], "./errorMessage", "failure message")
    if (error.text or "").strip() != _EXPECTED_ERROR:
        raise PreflightError("unexpected veraPDF failure message")

    batch = _one(root, "./batchSummary", "batch summary")
    if batch.get("totalJobs") != "1" or batch.get("failedToParse") != "0":
        raise PreflightError("veraPDF did not parse exactly one job successfully")
    reports = _one(batch, "./validationReports", "batch validation summary")
    expected_batch = {"compliant": "0", "nonCompliant": "1", "failedJobs": "0"}
    for name, expected in expected_batch.items():
        if reports.get(name) != expected:
            raise PreflightError(
                f"unexpected batch validation count {name}: {reports.get(name)!r}"
            )

    return {
        "status": "verified",
        "profile": _EXPECTED_PROFILE,
        "substantive_rule_failures": 0,
        "permitted_declaration_failures": 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.report)
    except PreflightError as exc:
        print(f"veraPDF UA preflight rejected: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
