#!/usr/bin/env python3
"""Fail closed unless an extractable PDF carries its reviewed release identity."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


class PdfIdentityError(ValueError):
    """Raised when the rendered PDF identity is absent or ambiguous."""


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID_RE = re.compile(r"^[1-9][0-9]*$")
_TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_BACKEND_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_FALLBACK_MARKERS = (
    "SOURCE-COMMIT-NOT-GENERATED",
    "COMPANION-DIGEST-NOT-GENERATED",
    "identity-include-missing",
)


def verify_text(
    text: str,
    *,
    product_tag: str,
    product_sha: str,
    evidence_run_id: str,
    whitepaper_sha: str,
    evidence_run_attempt: str | None = None,
    generator_backend_id: str | None = None,
    whitepaper_run_id: str | None = None,
    whitepaper_run_attempt: str | None = None,
    intake_snapshot_id: str | None = None,
    intake_bundle_sha256: str | None = None,
) -> None:
    """Validate each supplied identity in the PDF's labelled text layer."""

    if not _TAG_RE.fullmatch(product_tag):
        raise PdfIdentityError(
            "expected product tag must be a semantic v-prefixed version"
        )
    if not _SHA_RE.fullmatch(product_sha):
        raise PdfIdentityError(
            "expected product SHA must be 40 lowercase hex characters"
        )
    if not _SHA_RE.fullmatch(whitepaper_sha):
        raise PdfIdentityError(
            "expected whitepaper SHA must be 40 lowercase hex characters"
        )
    if not _RUN_ID_RE.fullmatch(evidence_run_id):
        raise PdfIdentityError("expected evidence run ID must be a positive decimal")
    for label, value in (
        ("evidence run attempt", evidence_run_attempt),
        ("whitepaper run ID", whitepaper_run_id),
        ("whitepaper run attempt", whitepaper_run_attempt),
    ):
        if value is not None and not _RUN_ID_RE.fullmatch(value):
            raise PdfIdentityError(f"expected {label} must be a positive decimal")
    if (whitepaper_run_id is None) != (whitepaper_run_attempt is None):
        raise PdfIdentityError(
            "expected whitepaper run ID and attempt must be supplied together"
        )
    if generator_backend_id is not None and not _BACKEND_RE.fullmatch(
        generator_backend_id
    ):
        raise PdfIdentityError("expected generator backend ID is invalid")
    for label, value in (
        ("intake snapshot ID", intake_snapshot_id),
        ("intake bundle SHA-256", intake_bundle_sha256),
    ):
        if value is not None and not _SHA256_RE.fullmatch(value):
            raise PdfIdentityError(
                f"expected {label} must be 64 lowercase hex characters"
            )

    for marker in _FALLBACK_MARKERS:
        if marker in text:
            raise PdfIdentityError(
                f"PDF contains unresolved identity marker {marker!r}"
            )

    normalized = re.sub(r"\s+", " ", text)
    evidence_pattern = rf"\bEvidence release workflow run {re.escape(evidence_run_id)}"
    if evidence_run_attempt is not None:
        evidence_pattern += rf" \(attempt {re.escape(evidence_run_attempt)}\)"
    evidence_pattern += r"(?![0-9A-Za-z])"
    labelled_patterns: dict[str, str] = {
        "product identity": (
            rf"\bProduct {re.escape(product_tag)} at {re.escape(product_sha)}(?![0-9A-Za-z])"
        ),
        "evidence run identity": evidence_pattern,
        "whitepaper identity": (
            rf"\bWhitepaper source {re.escape(whitepaper_sha)}(?![0-9A-Za-z])"
        ),
    }
    if generator_backend_id is not None:
        labelled_patterns["generator backend identity"] = (
            rf"\bGenerator backend {re.escape(generator_backend_id)}(?![0-9A-Za-z._-])"
        )
    if whitepaper_run_id is not None and whitepaper_run_attempt is not None:
        labelled_patterns["whitepaper workflow run identity"] = (
            rf"\bWhitepaper workflow run {re.escape(whitepaper_run_id)} "
            rf"\(attempt {re.escape(whitepaper_run_attempt)}\)(?![0-9A-Za-z])"
        )
    if intake_snapshot_id is not None:
        labelled_patterns["intake snapshot identity"] = (
            rf"\bIntake snapshot {re.escape(intake_snapshot_id)}(?![0-9A-Za-z])"
        )
    if intake_bundle_sha256 is not None:
        labelled_patterns["intake bundle identity"] = (
            rf"\bIntake bundle SHA-256 {re.escape(intake_bundle_sha256)}(?![0-9A-Za-z])"
        )
    for label, pattern in labelled_patterns.items():
        if re.search(pattern, normalized) is None:
            raise PdfIdentityError(f"PDF does not contain the exact labelled {label}")


def extract_text(pdf: Path) -> str:
    """Return the PDF text layer using the system Poppler binary."""

    if not pdf.is_file():
        raise PdfIdentityError(f"PDF does not exist: {pdf}")
    completed = subprocess.run(
        ["pdftotext", str(pdf), "-"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or "pdftotext failed"
        raise PdfIdentityError(detail)
    if not completed.stdout.strip():
        raise PdfIdentityError("PDF has no extractable text layer")
    return completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--product-tag", required=True)
    parser.add_argument("--product-sha", required=True)
    parser.add_argument("--evidence-run-id", required=True)
    parser.add_argument("--whitepaper-sha", required=True)
    parser.add_argument("--evidence-run-attempt")
    parser.add_argument("--generator-backend-id")
    parser.add_argument("--whitepaper-run-id")
    parser.add_argument("--whitepaper-run-attempt")
    parser.add_argument("--intake-snapshot-id")
    parser.add_argument("--intake-bundle-sha256")
    args = parser.parse_args()

    try:
        verify_text(
            extract_text(args.pdf),
            product_tag=args.product_tag,
            product_sha=args.product_sha,
            evidence_run_id=args.evidence_run_id,
            whitepaper_sha=args.whitepaper_sha,
            evidence_run_attempt=args.evidence_run_attempt,
            generator_backend_id=args.generator_backend_id,
            whitepaper_run_id=args.whitepaper_run_id,
            whitepaper_run_attempt=args.whitepaper_run_attempt,
            intake_snapshot_id=args.intake_snapshot_id,
            intake_bundle_sha256=args.intake_bundle_sha256,
        )
    except PdfIdentityError as exc:
        parser.error(str(exc))
    print("PDF release identity verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
