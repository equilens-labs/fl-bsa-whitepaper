#!/usr/bin/env python3
"""Enforce the reviewed interpretation corrections in the generated release paper."""

from __future__ import annotations

import argparse
from pathlib import Path


class ReleaseClaimsLintError(ValueError):
    """Raised when a required claim boundary is absent or contradicted."""


CORRECTION_RULES: dict[str, tuple[str, tuple[str, ...]]] = {
    "srg-method": (
        "03_methods.tex",
        (
            "conservative difference of separate Wilson interval endpoints",
            "not itself a calibrated 95\\% confidence interval",
        ),
    ),
    "race-reference": (
        "01_executive_summary.tex",
        (
            "configured provenance reference",
            "effective pairwise screening reference",
        ),
    ),
    "intrinsic-estimand": (
        "04_model_algorithm.tex",
        ("policy-imposed rather than causal", "not a counterfactual estimate"),
    ),
    "internal-screen": (
        "01_executive_summary.tex",
        (
            "voluntarily selected internal characterization screen",
            "not an ECOA or Regulation B requirement",
        ),
    ),
    "single-run-inference": (
        "03_methods.tex",
        (
            "conditional on this single generated fixture",
            "policy-determined intrinsic interval and p-value fields are non-inferential",
        ),
    ),
    "race-multiplicity": (
        "03_methods.tex",
        (
            "Holm--Bonferroni",
            "Confidence intervals are pairwise and are not multiplicity-adjusted",
        ),
    ),
    "utility-skill-normalisation": (
        "10_limitations_monitoring.tex",
        (
            "Train-on-synthetic predictive utility is not evaluated or established",
            "skill-normalised AUC ratio",
        ),
    ),
    "integrity-language": (
        "09_reproducibility.tex",
        ("provide integrity linkage", "not standalone tamper proof"),
    ),
    "regulatory-current-state": (
        "07_compliance.tex",
        (
            "supersedes that producer narrative",
            "not adopted legal validation or compliance findings",
        ),
    ),
}

FORBIDDEN_RELEASE_CLAIMS = (
    "potential disparate-impact finding",
    "improvement opportunity",
    "auditability and tamper-evidence",
    "localizes the disparity to the decision labels",
)


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def lint_release_claims(sections_root: Path) -> None:
    """Require all nine reviewed corrections across the release-only TeX sources."""

    paths = sorted(sections_root.glob("*.tex"))
    if not paths:
        raise ReleaseClaimsLintError("release claim lint found no TeX sections")
    corpus = _normalized("\n".join(path.read_text(encoding="utf-8") for path in paths))

    for correction_id, (section_name, fragments) in CORRECTION_RULES.items():
        section_path = sections_root / section_name
        if not section_path.is_file():
            raise ReleaseClaimsLintError(
                f"release correction {correction_id!r} lost its owner section {section_name!r}"
            )
        section = _normalized(section_path.read_text(encoding="utf-8"))
        missing = [
            fragment for fragment in fragments if _normalized(fragment) not in section
        ]
        if missing:
            raise ReleaseClaimsLintError(
                f"release correction {correction_id!r} is not fully encoded"
            )

    for forbidden in FORBIDDEN_RELEASE_CLAIMS:
        if _normalized(forbidden) in corpus:
            raise ReleaseClaimsLintError(
                f"forbidden release claim remains: {forbidden!r}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sections-root", type=Path, default=Path("release/sections"))
    args = parser.parse_args()
    try:
        lint_release_claims(args.sections_root)
    except (OSError, UnicodeError, ReleaseClaimsLintError) as exc:
        parser.error(str(exc))
    print("Release interpretation corrections verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
