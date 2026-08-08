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
_RUN_ID_RE = re.compile(r"^[1-9][0-9]*$")
_TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
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
) -> None:
    """Validate the three independent identities rendered into the PDF text layer."""

    if not _TAG_RE.fullmatch(product_tag):
        raise PdfIdentityError("expected product tag must be a semantic v-prefixed version")
    if not _SHA_RE.fullmatch(product_sha):
        raise PdfIdentityError("expected product SHA must be 40 lowercase hex characters")
    if not _SHA_RE.fullmatch(whitepaper_sha):
        raise PdfIdentityError("expected whitepaper SHA must be 40 lowercase hex characters")
    if not _RUN_ID_RE.fullmatch(evidence_run_id):
        raise PdfIdentityError("expected evidence run ID must be a positive decimal")

    for marker in _FALLBACK_MARKERS:
        if marker in text:
            raise PdfIdentityError(f"PDF contains unresolved identity marker {marker!r}")

    normalized = re.sub(r"\s+", " ", text)
    labelled_patterns = {
        "product identity": (
            rf"\bProduct {re.escape(product_tag)} at {re.escape(product_sha)}(?![0-9A-Za-z])"
        ),
        "evidence run identity": (
            rf"\bEvidence release workflow run {re.escape(evidence_run_id)}(?![0-9A-Za-z])"
        ),
        "whitepaper identity": (
            rf"\bWhitepaper source {re.escape(whitepaper_sha)}(?![0-9A-Za-z])"
        ),
    }
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
    args = parser.parse_args()

    try:
        verify_text(
            extract_text(args.pdf),
            product_tag=args.product_tag,
            product_sha=args.product_sha,
            evidence_run_id=args.evidence_run_id,
            whitepaper_sha=args.whitepaper_sha,
        )
    except PdfIdentityError as exc:
        parser.error(str(exc))
    print("PDF release identity verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
