#!/usr/bin/env python3
"""Verify visible identity and bounded claims in the public technical paper PDF."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

MAX_PDF_BYTES = 50 * 1024 * 1024


class TechnicalPdfError(ValueError):
    """Raised when visible PDF identity or claim text is incomplete or unsafe."""


def _fail(message: str) -> NoReturn:
    raise TechnicalPdfError(message)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TechnicalPdfError(f"unable to read summary JSON: {exc}") from exc
    if not isinstance(value, dict):
        _fail("summary JSON root must be an object")
    return value


def _extract(pdf: Path) -> str:
    try:
        size = pdf.stat().st_size
    except OSError as exc:
        raise TechnicalPdfError(f"unable to inspect PDF: {exc}") from exc
    if size <= 0 or size > MAX_PDF_BYTES:
        _fail(f"technical PDF has an unsafe size: {size}")
    try:
        completed = subprocess.run(
            ["pdftotext", "-layout", str(pdf), "-"],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise TechnicalPdfError(f"unable to extract technical PDF text: {exc}") from exc
    if not completed.stdout.strip():
        _fail("technical PDF has no extractable text")
    return completed.stdout


def _number(value: Any, places: int) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("summary contains a non-numeric result")
    return f"{value:.{places}f}"


def verify(pdf: Path, summary_path: Path) -> dict[str, Any]:
    """Require release identities, principal findings, and visible claim boundaries."""

    summary = _json(summary_path)
    if summary.get("schema_version") != "flbsa.public_technical_whitepaper.v1":
        _fail("technical summary schema mismatch")
    claims = summary.get("claims") or {}
    required_false = {
        "claim_expansion_authorized",
        "customer_evidence_eligible",
        "legal_or_compliance_certification",
        "marketplace_or_ga_authorization",
        "production_utility_established",
        "promotion_evidence_eligible",
        "regulator_approval",
    }
    if any(claims.get(field) is not False for field in required_false):
        _fail("technical summary widens a denied claim")
    if claims.get("customer_evidence_disposition") != "characterization_only":
        _fail("technical summary disposition mismatch")
    if claims.get("demo_evaluation_only") is not True:
        _fail("technical summary demo/evaluation marker mismatch")

    identity = summary.get("identity") or {}
    robustness = summary.get("robustness") or {}
    utility = robustness.get("advisory_utility") or {}
    quality = summary.get("quality") or {}
    companion = summary.get("companion") or {}
    text = _extract(pdf)
    compact = re.sub(r"\s+", " ", text).strip()
    lowered = compact.lower()
    dense = re.sub(r"\s+", "", text).lower()

    required_text = {
        "paper title": "FL-BSA v5.0.8 Technical Whitepaper",
        "publication status": "PUBLIC TECHNICAL CHARACTERIZATION",
        "demo marker": "DEMO / EVALUATION ONLY",
        "product tag": f"Product {identity.get('release_tag')} at",
        "evidence run": f"release-evidence run {identity.get('release_evidence_run_id')}",
        "attempt lineage": (
            f"retained source attempt {identity.get('source_attempt')}; "
            f"current successful attempt {identity.get('current_attempt')}"
        ),
        "backend": "first_party_evidence_native",
        "disposition": "characterization_only",
        "AOD/EOD availability": "AOD and EOD are unavailable",
        "customer boundary": "customer-evidence ineligible",
        "utility boundary": "Production utility is not established",
        "robustness result": f"{robustness.get('passes')}/{robustness.get('runs')}",
        "amplification quality": _number(
            (quality.get("amplification") or {}).get("overall_quality_score"), 6
        ),
        "intrinsic quality": _number(
            (quality.get("intrinsic") or {}).get("overall_quality_score"), 6
        ),
        "utility minimum": _number(utility.get("minimum_auc"), 6),
        "utility mean": _number(utility.get("mean_auc"), 6),
        "utility maximum": _number(utility.get("maximum_auc"), 6),
        "utility warnings": f"{utility.get('below_floor')} of 40",
        "accuracy minimum": _number(utility.get("minimum_accuracy"), 6),
        "accuracy mean": _number(utility.get("mean_accuracy"), 6),
        "accuracy maximum": _number(utility.get("maximum_accuracy"), 6),
        "accuracy threshold boundary": "no accuracy threshold is configured",
    }
    for label, expected in required_text.items():
        if expected not in compact:
            _fail(f"technical PDF is missing visible {label}: {expected!r}")

    dense_identities = {
        "product commit": identity.get("product_commit"),
        "product tag object": identity.get("product_tag_object"),
        "companion SHA-256": companion.get("sha256"),
        "intake SHA-256": (summary.get("source") or {}).get("intake_bundle_sha256"),
    }
    for label, expected in dense_identities.items():
        if not isinstance(expected, str) or expected.lower() not in dense:
            _fail(f"technical PDF is missing visible {label}")

    forbidden_patterns = {
        "numeric AOD regression": r"\baod\s*(?:is|=|:)\s*0\.0049\b",
        "customer eligibility widening": r"customer[- ]evidence\s+eligible\s*(?:=|:|is)\s*true",
        "production utility widening": r"production utility\s+(?:is\s+)?established",
    }
    for label, pattern in forbidden_patterns.items():
        if re.search(pattern, lowered):
            _fail(f"technical PDF contains forbidden {label}")

    return {
        "verified": True,
        "product_commit": identity.get("product_commit"),
        "release_evidence_run_id": identity.get("release_evidence_run_id"),
        "robustness_runs": robustness.get("runs"),
        "customer_evidence_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.pdf, args.summary)
    except (KeyError, OSError, TechnicalPdfError) as exc:
        print(f"technical PDF verification failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
