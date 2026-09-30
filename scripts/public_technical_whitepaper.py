#!/usr/bin/env python3
"""Build and verify the v5.0.8 public technical-whitepaper evidence set."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import time
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn


SCHEMA_VERSION = "flbsa.public_technical_whitepaper.v1"
COMPANION_SCHEMA = "flbsa.public_technical_whitepaper_companion.v1"
SIDECAR_SCHEMA = "flbsa.public_technical_whitepaper_release.v1"
PRODUCT_REPO = "equilens-labs/fl-bsa"
WHITEPAPER_REPO = "equilens-labs/fl-bsa-whitepaper"
INTAKE_NAME = "WhitePaper_Intake_Bundle_v4.zip"
REQUIRED_ROBUSTNESS_FILES = (
    "gold/robustness_index.csv",
    "gold_robustness/evidence_manifest.json",
    "gold_robustness/robustness_gate_disposition.json",
    "gold_robustness/robustness_requirements.json",
    "gold_robustness/robustness_summary_merged.json",
)
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class TechnicalPaperError(ValueError):
    """Raised when technical-paper evidence is incomplete or inconsistent."""


def _fail(message: str) -> NoReturn:
    raise TechnicalPaperError(message)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TechnicalPaperError(f"unable to read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        _fail(f"JSON root must be an object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _require_equal(actual: Any, expected: Any, label: str) -> None:
    if type(actual) is not type(expected) or actual != expected:
        _fail(f"{label} must be {expected!r}, got {actual!r}")


def _require_sha(value: str, label: str, *, full_git: bool = False) -> str:
    matcher = FULL_SHA_RE if full_git else SHA_RE
    if matcher.fullmatch(value) is None:
        _fail(f"{label} must be lowercase hexadecimal ({matcher.pattern})")
    return value


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        _fail(f"{label} must be finite")
    return result


def _safe_member(name: str) -> None:
    path = PurePosixPath(name)
    raw_parts = name[:-1].split("/") if name.endswith("/") else name.split("/")
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or any(part in {"", ".", ".."} for part in raw_parts)
    ):
        _fail(f"unsafe ZIP member path: {name!r}")
    if path.as_posix() != name.rstrip("/"):
        _fail(f"non-canonical ZIP member path: {name!r}")


def _extract_intake(bundle: Path, destination: Path) -> None:
    if bundle.name != INTAKE_NAME:
        _fail(f"intake bundle filename must be {INTAKE_NAME}")
    try:
        with zipfile.ZipFile(bundle) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                _fail("intake bundle contains duplicate member names")
            for info in archive.infolist():
                _safe_member(info.filename)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    _fail(f"intake bundle contains a symbolic link: {info.filename}")
                target = destination / PurePosixPath(info.filename)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
    except zipfile.BadZipFile as exc:
        raise TechnicalPaperError(f"invalid intake ZIP: {exc}") from exc


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        _fail(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def _tex(value: Any) -> str:
    text = str(value)
    replacements = {
        "\\": "\\textbackslash{}",
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def _macro(name: str, value: Any) -> str:
    return f"\\newcommand{{\\{name}}}{{{_tex(value)}}}"


def _quality_projection(certificate: dict[str, Any]) -> dict[str, Any]:
    statistical = certificate.get("statistical_comparison") or {}
    correlation = certificate.get("correlation_analysis") or {}
    bias = certificate.get("bias_analysis") or {}
    privacy = certificate.get("privacy_metrics") or {}
    demographic = certificate.get("demographic_alignment") or {}
    branch = certificate.get("branch_mode")
    bias_surfaces = (
        bias.get("demographic_parity_real"),
        bias.get("demographic_parity_synthetic"),
        bias.get("demographic_parity_difference"),
    )
    if all(isinstance(surface, dict) and surface for surface in bias_surfaces):
        demographic_rate_fidelity_disposition = "evaluated"
    elif (
        branch == "intrinsic"
        and all(surface == {} for surface in bias_surfaces)
        and bias.get("bias_preservation_score") == 1.0
    ):
        demographic_rate_fidelity_disposition = "not_evaluated_default_one_no_outcome"
    else:
        _fail("demographic-rate-fidelity surface has an unexpected disposition")
    projection = {
        "branch": branch,
        "overall_quality_score": certificate.get("overall_quality_score"),
        "quality_threshold_used": certificate.get("quality_threshold_used"),
        "quality_threshold_met": certificate.get("quality_threshold_met"),
        "components": {
            "overall_distribution_score": statistical.get("overall_distribution_score"),
            "correlation_preservation_score": correlation.get(
                "correlation_preservation_score"
            ),
            "bias_preservation_score": bias.get("bias_preservation_score"),
            "privacy_quality_heuristic": privacy.get("privacy_preservation_score"),
        },
        "component_dispositions": {
            "demographic_rate_fidelity": demographic_rate_fidelity_disposition,
        },
        "demographic_alignment": {
            "max_abs_pp_drift": demographic.get("max_abs_pp_drift"),
            "threshold_pp": demographic.get("threshold_pp"),
            "within_threshold": demographic.get("within_threshold"),
        },
        "privacy_boundaries": {
            "exact_duplicate_score_count": privacy.get("exact_duplicate_score_count"),
            "near_duplicate_count_status": privacy.get("near_duplicate_count_status"),
            "near_duplicate_privacy_claimed": privacy.get(
                "near_duplicate_privacy_claimed"
            ),
            "differential_privacy_claimed": privacy.get("differential_privacy_claimed"),
            "score_scope": privacy.get("privacy_preservation_score_scope"),
        },
        "utility": {
            "evaluated": False,
            "certificate_value": certificate.get("utility_metrics"),
            "quality_ok": certificate.get("quality_ok"),
        },
    }
    components = projection["components"]
    component_values = [
        _finite_number(value, f"quality component {name}")
        for name, value in components.items()
    ]
    if any(not 0 <= value <= 1 for value in component_values):
        _fail("quality components must be within [0, 1]")
    overall = _finite_number(
        projection["overall_quality_score"], "overall quality score"
    )
    threshold = _finite_number(
        projection["quality_threshold_used"], "quality threshold"
    )
    if not 0 <= overall <= 1 or threshold != 0.8:
        _fail("quality score or threshold is outside the reviewed contract")
    if not math.isclose(
        overall, statistics.fmean(component_values), rel_tol=0, abs_tol=1e-12
    ):
        _fail("overall quality score does not equal the four-component mean")
    if projection["quality_threshold_met"] is not True or overall < threshold:
        _fail("quality threshold disposition is inconsistent")
    alignment = projection["demographic_alignment"]
    drift = _finite_number(alignment["max_abs_pp_drift"], "demographic drift")
    drift_threshold = _finite_number(
        alignment["threshold_pp"], "demographic drift threshold"
    )
    if (
        drift < 0
        or drift_threshold != 5.0
        or alignment["within_threshold"] is not True
        or drift > drift_threshold
    ):
        _fail("demographic-alignment disposition is inconsistent")
    boundaries = projection["privacy_boundaries"]
    if (
        isinstance(boundaries["exact_duplicate_score_count"], bool)
        or not isinstance(boundaries["exact_duplicate_score_count"], int)
        or boundaries["exact_duplicate_score_count"] != 0
        or boundaries["near_duplicate_count_status"] != "not_computed"
        or boundaries["near_duplicate_privacy_claimed"] is not False
        or boundaries["differential_privacy_claimed"] is not False
        or boundaries["score_scope"] != "quality_heuristic_not_formal_privacy_guarantee"
    ):
        _fail("privacy quality boundaries differ from the reviewed contract")
    return projection


def _generation_projection(
    amplification: dict[str, Any], intrinsic: dict[str, Any]
) -> dict[str, Any]:
    """Project and validate generation facts used in the public methods section."""

    projected: dict[str, Any] = {}
    for branch, certificate in (
        ("amplification", amplification),
        ("intrinsic", intrinsic),
    ):
        backend = certificate.get("generator_backend") or {}
        parameters = certificate.get("generation_parameters") or {}
        validation = certificate.get("validation_results") or {}
        wall = (certificate.get("post_processing") or {}).get(
            "native_final_exact_output_wall"
        ) or {}
        _require_equal(
            certificate.get("branch_mode"), branch, f"{branch} generation branch"
        )
        _require_equal(
            backend.get("backend_id"),
            "first_party_evidence_native",
            f"{branch} generation backend",
        )
        _require_equal(
            backend.get("backend_version"), "0.1.0", f"{branch} backend version"
        )
        _require_equal(parameters.get("n_samples"), 10_000, f"{branch} generated rows")
        _require_equal(parameters.get("random_seed"), 42, f"{branch} generation seed")
        _require_equal(
            validation.get("samples_generated"), 10_000, f"{branch} generated count"
        )
        _require_equal(
            validation.get("output_schema_matches"), True, f"{branch} output schema"
        )
        _require_equal(wall.get("applied"), True, f"{branch} final exact-output wall")
        _require_equal(
            wall.get("matching_row_instances"), 0, f"{branch} exact-row matches"
        )
        projected[branch] = {
            "backend_id": backend["backend_id"],
            "backend_version": backend["backend_version"],
            "claim_limits": backend.get("claim_limits"),
            "generated_rows": parameters["n_samples"],
            "seed": parameters["random_seed"],
            "sampling_strategy": parameters.get("sampling_strategy"),
            "stratification_column": parameters.get("stratification_column"),
            "exact_output_wall": {
                "checked_rows": wall.get("checked_rows"),
                "matching_row_instances": wall.get("matching_row_instances"),
                "claim_scope": wall.get("claim_scope"),
                "near_duplicate_privacy_not_claimed": wall.get(
                    "near_duplicate_privacy_not_claimed"
                ),
            },
        }

    alignment = (amplification.get("post_processing") or {}).get(
        "quantile_alignment"
    ) or {}
    expected_columns = [
        "credit_score",
        "income",
        "debt_to_income",
        "loan_amount",
        "age",
    ]
    _require_equal(alignment.get("applied"), True, "amplification quantile alignment")
    _require_equal(
        alignment.get("reference_surface"),
        "original_training_data",
        "amplification alignment reference",
    )
    _require_equal(
        alignment.get("numeric_columns"),
        expected_columns,
        "amplification alignment columns",
    )
    _require_equal(
        alignment.get("stratify_cols"),
        ["loan_approved"],
        "amplification alignment strata",
    )
    projected["amplification"]["quantile_alignment"] = {
        "applied": True,
        "reference_surface": alignment["reference_surface"],
        "numeric_columns": alignment["numeric_columns"],
        "stratify_columns": alignment["stratify_cols"],
        "stage": alignment.get("stage"),
        "ks_delta_by_column": alignment.get("ks_delta_by_column"),
    }
    _require_equal(
        projected["intrinsic"]["sampling_strategy"],
        "intrinsic_anchor_profile_resampling",
        "intrinsic sampling strategy",
    )
    _require_equal(
        projected["intrinsic"]["stratification_column"],
        "gender,race",
        "intrinsic protected strata",
    )
    return projected


def _protected_scope_projection(certificate: dict[str, Any]) -> dict[str, Any]:
    scope = certificate.get("protected_group_scope") or {}
    expected_uncovered = [
        "color",
        "religion",
        "national_origin",
        "marital_status",
        "age",
        "receipt_of_public_assistance",
        "exercise_of_consumer_credit_rights",
    ]
    _require_equal(
        scope.get("claim_scope"), "per_attribute", "protected-group claim scope"
    )
    _require_equal(
        scope.get("covered_attributes"), ["gender", "race"], "covered attributes"
    )
    _require_equal(
        scope.get("excluded_claims"),
        [
            "absence_of_bias_for_uncovered_protected_bases",
            "absence_of_intersectional_bias",
            "multi_level_race_encoding_without_declared_schema_support",
        ],
        "protected-group excluded claims",
    )
    uncovered = scope.get("uncovered_ecoa_reg_b_bases") or []
    _require_equal(
        [item.get("basis") for item in uncovered if isinstance(item, dict)],
        expected_uncovered,
        "uncovered protected bases",
    )
    return {
        "claim_scope": scope["claim_scope"],
        "covered_attributes": scope["covered_attributes"],
        "excluded_claims": scope["excluded_claims"],
        "uncovered_ecoa_reg_b_bases": expected_uncovered,
        "human_readable": scope.get("human_readable"),
    }


def _decision_driver(
    worst_case: dict[str, Any],
    intersectional: dict[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    """Project the comparison that actually controls the configured review decision."""
    attribute = worst_case.get("attribute")
    if attribute not in {"gender", "race", "intersectional"}:
        _fail(f"unexpected controlling attribute in {label}")
    ratio = _finite_number(worst_case.get("ratio"), f"controlling ratio in {label}")
    threshold = _finite_number(
        worst_case.get("threshold"), f"controlling threshold in {label}"
    )
    if threshold != 0.8 or worst_case.get("metric") != "air":
        _fail(f"unexpected controlling metric or threshold in {label}")
    within = worst_case.get("within_configured_threshold")
    if not isinstance(within, bool) or within != (ratio >= threshold):
        _fail(f"controlling ratio and review status disagree in {label}")
    if attribute == "intersectional":
        tested_group = worst_case.get("pair")
        reference_group = intersectional["reference_intersection"]
        expected_ratio = intersectional["pair_ratios"].get(tested_group)
        if expected_ratio is None or not math.isclose(
            expected_ratio, ratio, rel_tol=0, abs_tol=1e-15
        ):
            _fail(f"controlling intersection differs from source evidence in {label}")
    else:
        tested_group = worst_case.get("protected_group")
        reference_group = worst_case.get("reference_group")
        if not isinstance(tested_group, str) or not isinstance(reference_group, str):
            _fail(f"controlling protected/reference group is missing in {label}")
    return {
        "attribute": attribute,
        "tested_group": tested_group,
        "reference_group": reference_group,
        "ratio": ratio,
        "threshold": threshold,
        "within_configured_threshold": within,
        "source": worst_case.get("source"),
    }


def _robustness_projection(root: Path, product_sha: str) -> dict[str, Any]:
    paths = {name: root / name for name in REQUIRED_ROBUSTNESS_FILES}
    for name, path in paths.items():
        if not path.is_file():
            _fail(f"required robustness file is missing: {name}")
    disposition = _read_json(paths["gold_robustness/robustness_gate_disposition.json"])
    evidence_manifest = _read_json(paths["gold_robustness/evidence_manifest.json"])
    requirements = _read_json(paths["gold_robustness/robustness_requirements.json"])
    merged = _read_json(paths["gold_robustness/robustness_summary_merged.json"])
    for label, payload in (
        ("robustness disposition", disposition),
        ("robustness evidence manifest", evidence_manifest),
    ):
        _require_equal(payload.get("git_sha"), product_sha, f"{label} product SHA")
        _require_equal(payload.get("github_run_id"), "36152873675", f"{label} run ID")
        _require_equal(payload.get("release_tag"), "v5.0.8", f"{label} release tag")
    _require_equal(
        disposition.get("requirements_outcome"), "success", "requirements outcome"
    )
    _require_equal(
        disposition.get("strict_robustness_requirements_passed"),
        True,
        "strict robustness disposition",
    )

    with paths["gold/robustness_index.csv"].open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 40:
        _fail(f"robustness index must contain 40 runs, got {len(rows)}")
    scenarios = ("01_balanced", "02_gender_bias", "03_outliers", "04_security")
    expected_seeds = {
        "7",
        "11",
        "23",
        "42",
        "101",
        "1337",
        "2025",
        "4096",
        "8191",
        "314159",
    }
    intersectional_evidence: dict[tuple[str, int], dict[str, Any]] = {}
    intersectional_paths = sorted(
        root.glob(
            "robustness-seeds/gold-robustness-seed-*/artifacts/gold/*/"
            "0[1-4]_*/validation/intersectional_fairness.json"
        )
    )
    if len(intersectional_paths) != 40:
        _fail(
            "expected 40 canonical intersectional-fairness evidence files, "
            f"got {len(intersectional_paths)}"
        )
    for path in intersectional_paths:
        try:
            scenario = path.parents[1].name
            seed_part = next(
                part for part in path.parts if part.startswith("gold-robustness-seed-")
            )
            seed = int(seed_part.removeprefix("gold-robustness-seed-"))
        except (StopIteration, ValueError) as exc:
            raise TechnicalPaperError(
                f"unable to identify intersectional-fairness source: {path}"
            ) from exc
        payload = _read_json(path).get("intersectional_fairness") or {}
        reference = payload.get("reference_group") or {}
        if reference != {"gender": "male", "race": "white"}:
            _fail(f"unexpected intersectional reference group in {path}")
        pairs = payload.get("pairs") or {}
        worst_pair = payload.get("worst_case_pair")
        pair_evidence = pairs.get(worst_pair) or {}
        air = pair_evidence.get("air") or {}
        key = (scenario, seed)
        if key in intersectional_evidence:
            _fail(
                f"duplicate intersectional-fairness evidence for {scenario} seed {seed}"
            )
        pair_ratios = {
            pair: _finite_number(
                (evidence.get("air") or {}).get("point"),
                f"intersectional AIR for {pair} in {path}",
            )
            for pair, evidence in pairs.items()
            if isinstance(evidence, dict)
        }
        intersectional_evidence[key] = {
            "reference_intersection": "male|white",
            "worst_case_pair": worst_pair,
            "ratio": _finite_number(air.get("point"), f"intersectional AIR in {path}"),
            "pair_ratios": pair_ratios,
        }
    expected_run_keys = {
        (scenario, int(seed)) for scenario in scenarios for seed in expected_seeds
    }
    if set(intersectional_evidence) != expected_run_keys:
        _fail(
            "canonical intersectional-fairness evidence differs from the ten-seed plan"
        )

    decision_evidence: dict[tuple[str, int], dict[str, Any]] = {}
    decision_paths = sorted(
        root.glob(
            "robustness-seeds/gold-robustness-seed-*/artifacts/gold/*/"
            "0[1-4]_*/validation/compliance_decision.json"
        )
    )
    if len(decision_paths) != 40:
        _fail(f"expected 40 canonical compliance decisions, got {len(decision_paths)}")
    for path in decision_paths:
        try:
            scenario = path.parents[1].name
            seed_part = next(
                part for part in path.parts if part.startswith("gold-robustness-seed-")
            )
            seed = int(seed_part.removeprefix("gold-robustness-seed-"))
        except (StopIteration, ValueError) as exc:
            raise TechnicalPaperError(
                f"unable to identify compliance-decision source: {path}"
            ) from exc
        decision = _read_json(path)
        _require_equal(
            decision.get("schema_version"), "compliance.v1", "compliance schema"
        )
        _require_equal(
            decision.get("screening_only"), True, "screening-only disposition"
        )
        _require_equal(decision.get("legal_attestation"), False, "legal attestation")
        basis = decision.get("basis") or {}
        _require_equal(
            basis.get("screening_policy"),
            "worst_across_configured_attributes_and_intersections",
            "compliance screening policy",
        )
        worst_case = basis.get("worst_case") or {}
        if worst_case not in (basis.get("observations") or []):
            _fail(f"controlling comparison is not in the decision observations: {path}")
        intersectional = intersectional_evidence[(scenario, seed)]
        driver = _decision_driver(worst_case, intersectional, label=str(path))
        key = (scenario, seed)
        if key in decision_evidence:
            _fail(f"duplicate compliance decision for {scenario} seed {seed}")
        decision_within = decision.get("within_configured_threshold")
        if (
            decision_within is not driver["within_configured_threshold"]
            or decision.get("compliant") is not driver["within_configured_threshold"]
            or decision.get("screening_status")
            != (
                "within_configured_threshold"
                if driver["within_configured_threshold"]
                else "outside_configured_threshold"
            )
        ):
            _fail(f"compliance decision status is internally inconsistent in {path}")
        decision_evidence[key] = driver
    if set(decision_evidence) != expected_run_keys:
        _fail("canonical compliance decisions differ from the ten-seed plan")

    summary: dict[str, Any] = {}
    public_rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        selected = [row for row in rows if row.get("scenario") == scenario]
        if (
            len(selected) != 10
            or {row.get("seed") for row in selected} != expected_seeds
        ):
            _fail(f"{scenario} must contain the exact ten-seed plan")
        if {row.get("status") for row in selected} != {"pass"}:
            _fail(f"{scenario} contains a non-passing run")
        headline_gender_ratios = [
            _finite_number(float(row["di"]), f"{scenario} disparity ratio")
            for row in selected
        ]
        gaps = [
            _finite_number(float(row["spd"]), f"{scenario} selection-rate gap")
            for row in selected
        ]
        summary[scenario] = {
            "runs": len(selected),
            "passes": len(selected),
            "headline_gender_ratio": {
                "protected_group": "female",
                "reference_group": "male",
                "minimum": min(headline_gender_ratios),
                "mean": statistics.fmean(headline_gender_ratios),
                "maximum": max(headline_gender_ratios),
            },
            "selection_rate_gap": {
                "minimum": min(gaps),
                "mean": statistics.fmean(gaps),
                "maximum": max(gaps),
            },
        }
        scenario_public_rows: list[dict[str, Any]] = []
        for row in selected:
            if row.get("aod") not in {None, ""} or row.get("eod") not in {None, ""}:
                _fail(f"{scenario} unexpectedly reports AOD/EOD as available")
            boolean_fields = {
                field: row[field].lower()
                for field in (
                    "compliance_compliant",
                    "pdf_parity_pass",
                    "chain_pass",
                    "signatures_pass",
                    "evidence_encryption_pass",
                    "lc11_contract_certification_pass",
                )
            }
            if any(value not in {"true", "false"} for value in boolean_fields.values()):
                _fail(f"{scenario} contains a malformed boolean disposition")
            for field in (
                "pdf_parity_pass",
                "chain_pass",
                "signatures_pass",
                "evidence_encryption_pass",
                "lc11_contract_certification_pass",
            ):
                if boolean_fields[field] != "true":
                    _fail(
                        f"{scenario} contains a failed integrity disposition: {field}"
                    )
            lowest_intersection = row["intersectional_worst_case_pair"].strip()
            if not lowest_intersection or "|" not in lowest_intersection:
                _fail(f"{scenario} lowest intersection is malformed")
            intersectional = intersectional_evidence[(scenario, int(row["seed"]))]
            if intersectional["worst_case_pair"] != lowest_intersection:
                _fail(f"{scenario} lowest intersection differs from source evidence")
            lowest_intersection_ratio = _finite_number(
                float(row["intersectional_worst_case_air"]),
                f"{scenario} lowest intersection ratio",
            )
            if not math.isclose(
                intersectional["ratio"],
                lowest_intersection_ratio,
                rel_tol=0,
                abs_tol=1e-15,
            ):
                _fail(
                    f"{scenario} lowest intersection ratio differs from source evidence"
                )
            decision = decision_evidence[(scenario, int(row["seed"]))]
            if (boolean_fields["compliance_compliant"] == "true") is not decision[
                "within_configured_threshold"
            ]:
                _fail(f"{scenario} index and compliance-decision status disagree")
            projected_row = {
                "scenario": scenario,
                "seed": int(row["seed"]),
                "status": row["status"],
                "scenario_test_passed": row["status"] == "pass",
                "headline_gender_ratio": float(row["di"]),
                "selection_rate_gap": float(row["spd"]),
                "maximum_demographic_parity_difference": _finite_number(
                    float(row["max_demographic_parity_difference"]),
                    f"{scenario} maximum demographic-parity difference",
                ),
                "maximum_demographic_parity_attribute": row[
                    "max_demographic_parity_attribute"
                ],
                "fairness_screen_within_threshold": decision[
                    "within_configured_threshold"
                ],
                "controlling_attribute": decision["attribute"],
                "controlling_tested_group": decision["tested_group"],
                "controlling_reference_group": decision["reference_group"],
                "controlling_ratio": decision["ratio"],
                "controlling_threshold": decision["threshold"],
                "controlling_within_threshold": decision["within_configured_threshold"],
                "lowest_intersection": lowest_intersection,
                "lowest_intersection_reference": intersectional[
                    "reference_intersection"
                ],
                "lowest_intersection_ratio": lowest_intersection_ratio,
                "aod_status": "unavailable",
                "eod_status": "unavailable",
                "pdf_numeric_parity_passed": True,
                "certificate_chain_passed": True,
                "certificate_signatures_passed": True,
                "evidence_encryption_passed": True,
                "lc11_contract_certification_passed": True,
            }
            public_rows.append(projected_row)
            scenario_public_rows.append(projected_row)
        fairness_within = sum(
            item["fairness_screen_within_threshold"] for item in scenario_public_rows
        )
        controlling = min(
            scenario_public_rows,
            key=lambda item: item["controlling_ratio"],
        )
        seed_42 = next(item for item in scenario_public_rows if item["seed"] == 42)
        summary[scenario]["fairness_screen"] = {
            "within_threshold": fairness_within,
            "outside_threshold": len(scenario_public_rows) - fairness_within,
        }
        summary[scenario]["worst_controlling_comparison"] = {
            "seed": controlling["seed"],
            "attribute": controlling["controlling_attribute"],
            "tested_group": controlling["controlling_tested_group"],
            "reference_group": controlling["controlling_reference_group"],
            "ratio": controlling["controlling_ratio"],
            "threshold": controlling["controlling_threshold"],
            "within_configured_threshold": controlling["controlling_within_threshold"],
        }
        summary[scenario]["seed_42_controlling_comparison"] = {
            "attribute": seed_42["controlling_attribute"],
            "tested_group": seed_42["controlling_tested_group"],
            "reference_group": seed_42["controlling_reference_group"],
            "ratio": seed_42["controlling_ratio"],
            "threshold": seed_42["controlling_threshold"],
            "fairness_screen_within_threshold": seed_42[
                "fairness_screen_within_threshold"
            ],
        }

    utility_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    certificate_paths = sorted(
        root.glob(
            "robustness-seeds/gold-robustness-seed-*/artifacts/gold/*/"
            "0[1-4]_*/certificates/synthetic_quality_certificate.json"
        )
    )
    for path in certificate_paths:
        certificate = _read_json(path)
        try:
            scenario = path.parents[1].name
            seed_part = next(
                part for part in path.parts if part.startswith("gold-robustness-seed-")
            )
            seed = int(seed_part.removeprefix("gold-robustness-seed-"))
        except (StopIteration, ValueError) as exc:
            raise TechnicalPaperError(
                f"unable to identify robustness utility source: {path}"
            ) from exc
        utility = certificate.get("utility_metrics") or {}
        auc = utility.get("auc_overall")
        accuracy = utility.get("accuracy_overall")
        floor = certificate.get("synthetic_utility_floor")
        check = certificate.get("synthetic_utility_check")
        auc_value = _finite_number(auc, f"advisory utility AUC in {path}")
        accuracy_value = _finite_number(
            accuracy, f"advisory utility accuracy in {path}"
        )
        floor_value = _finite_number(floor, f"advisory utility floor in {path}")
        if (
            not 0 <= auc_value <= 1
            or not 0 <= accuracy_value <= 1
            or floor_value != 0.7
        ):
            _fail(f"unexpected advisory utility AUC/accuracy/floor in {path}")
        if check not in {"pass", "warn"}:
            _fail(f"unexpected advisory utility disposition in {path}: {check!r}")
        if check != ("pass" if auc_value >= floor_value else "warn"):
            _fail(f"inconsistent advisory utility disposition in {path}")
        key = (scenario, seed)
        if key in utility_by_key:
            _fail(
                f"duplicate robustness utility certificate for {scenario} seed {seed}"
            )
        utility_by_key[key] = {
            "auc": auc_value,
            "accuracy": accuracy_value,
            "floor": floor_value,
            "status": check,
        }
    if len(utility_by_key) != 40:
        _fail(f"expected 40 advisory utility certificates, got {len(utility_by_key)}")
    for row in public_rows:
        key = (str(row["scenario"]), int(row["seed"]))
        row["amplification_utility"] = utility_by_key[key]

    utility_values = [item["auc"] for item in utility_by_key.values()]
    accuracy_values = [item["accuracy"] for item in utility_by_key.values()]
    utility_passes = sum(item["status"] == "pass" for item in utility_by_key.values())
    return {
        "runs": 40,
        "passes": 40,
        "seeds": sorted(int(seed) for seed in expected_seeds),
        "scenarios": summary,
        "public_rows": sorted(
            public_rows, key=lambda item: (item["scenario"], item["seed"])
        ),
        "advisory_utility": {
            "branch": "amplification",
            "intrinsic_status": "not_evaluated",
            "minimum_auc": min(utility_values),
            "mean_auc": statistics.fmean(utility_values),
            "maximum_auc": max(utility_values),
            "minimum_accuracy": min(accuracy_values),
            "mean_accuracy": statistics.fmean(accuracy_values),
            "maximum_accuracy": max(accuracy_values),
            "accuracy_threshold_status": "not_configured",
            "at_or_above_floor": utility_passes,
            "below_floor": 40 - utility_passes,
            "runs": 40,
            "interpretation": "advisory_diagnostic_generally_below_configured_floor",
        },
        "requirements_sha256": _sha256_file(
            paths["gold_robustness/robustness_requirements.json"]
        ),
        "merged_summary_sha256": _sha256_file(
            paths["gold_robustness/robustness_summary_merged.json"]
        ),
        "index_sha256": _sha256_file(paths["gold/robustness_index.csv"]),
        "requirements_schema": requirements.get("schema_version"),
        "merged_schema": merged.get("schema_version"),
        "source_files": {
            name: {
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for name, path in paths.items()
        },
    }


def _write_technical_includes(build: Path, summary: dict[str, Any]) -> None:
    (build / "includes").mkdir(parents=True, exist_ok=True)
    identity = summary["identity"]
    companion = summary["companion"]
    source = summary["source"]
    lines = ["% Generated from exact v5.0.8 evidence; do not edit."]
    values = {
        "TechnicalDocumentVersion": "WP-5.0.8-public.1",
        "PaperPublicationStatus": "PUBLIC TECHNICAL CHARACTERIZATION",
        "PublicationAsOf": "30 September 2026",
        "ProductReleaseTag": "v5.0.8",
        "ProductCommitRaw": identity["product_commit"],
        "ProductTagObjectRaw": identity["product_tag_object"],
        "WhitepaperCommitRaw": identity["whitepaper_commit"],
        "EvidenceRunRaw": identity["release_evidence_run_id"],
        "EvidenceSourceAttemptRaw": identity["source_attempt"],
        "EvidenceCurrentAttemptRaw": identity["current_attempt"],
        "IntakeArtifactIdRaw": source["intake_artifact_id"],
        "IntakeArtifactDigestRaw": source["intake_artifact_digest"],
        "IntakeBundleShaRaw": source["intake_bundle_sha256"],
        "IntakeManifestShaRaw": source["intake_manifest_sha256"],
        "CompanionFilenameRaw": companion["filename"],
        "CompanionShaRaw": companion["sha256"],
        "CompanionSizeRaw": companion["size_bytes"],
        "AuthorizationShaRaw": source["authorization_sha256"],
        "CorrectionIndexShaRaw": source["immutable_release_index_sha256"],
        "ReleaseManifestShaRaw": source["release_manifest_sha256"],
        "ReleaseAttestationShaRaw": source["release_attestation_sha256"],
        "ReleaseTrustRootShaRaw": source["release_trust_root_record_sha256"],
        "RuntimeImageDigestRaw": summary["runtime"]["image_digest"],
        "GeneratorBackendRaw": summary["runtime"]["generator_backend"],
        "RunUuidRaw": summary["runtime"]["run_uuid"],
        "DatasetHashRaw": summary["runtime"]["dataset_hash"],
    }
    lines.extend(_macro(name, value) for name, value in values.items())
    (build / "includes/technical_identity.tex").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    quality_lines = ["% Generated quality values and components."]
    for prefix, branch in (("Amp", "amplification"), ("Int", "intrinsic")):
        quality = summary["quality"][branch]
        components = quality["components"]
        qvalues = {
            f"{prefix}Quality": f"{quality['overall_quality_score']:.6f}",
            f"{prefix}Distribution": f"{components['overall_distribution_score']:.6f}",
            f"{prefix}Correlation": f"{components['correlation_preservation_score']:.6f}",
            f"{prefix}Bias": f"{components['bias_preservation_score']:.6f}",
            f"{prefix}PrivacyHeuristic": f"{components['privacy_quality_heuristic']:.6f}",
        }
        quality_lines.extend(_macro(name, value) for name, value in qvalues.items())
    (build / "includes/technical_quality.tex").write_text(
        "\n".join(quality_lines) + "\n", encoding="utf-8"
    )

    robust_lines = ["% Generated forty-run robustness values."]
    robust_lines.extend(
        [
            _macro("RobustnessRuns", summary["robustness"]["runs"]),
            _macro("RobustnessPasses", summary["robustness"]["passes"]),
            _macro(
                "UtilityMinAUC",
                f"{summary['robustness']['advisory_utility']['minimum_auc']:.6f}",
            ),
            _macro(
                "UtilityMeanAUC",
                f"{summary['robustness']['advisory_utility']['mean_auc']:.6f}",
            ),
            _macro(
                "UtilityMaxAUC",
                f"{summary['robustness']['advisory_utility']['maximum_auc']:.6f}",
            ),
            _macro(
                "UtilityMinAccuracy",
                f"{summary['robustness']['advisory_utility']['minimum_accuracy']:.6f}",
            ),
            _macro(
                "UtilityMeanAccuracy",
                f"{summary['robustness']['advisory_utility']['mean_accuracy']:.6f}",
            ),
            _macro(
                "UtilityMaxAccuracy",
                f"{summary['robustness']['advisory_utility']['maximum_accuracy']:.6f}",
            ),
            _macro(
                "UtilityAtOrAboveFloor",
                summary["robustness"]["advisory_utility"]["at_or_above_floor"],
            ),
            _macro(
                "UtilityBelowFloor",
                summary["robustness"]["advisory_utility"]["below_floor"],
            ),
        ]
    )
    scenario_names = {
        "01_balanced": ("Balanced", "Balanced"),
        "02_gender_bias": ("GenderBias", "Gender-bias positive control"),
        "03_outliers": ("Outliers", "Outliers"),
        "04_security": ("Security", "Security"),
    }
    rows: list[str] = []
    for scenario, (prefix, label) in scenario_names.items():
        values = summary["robustness"]["scenarios"][scenario]
        ratio = values["headline_gender_ratio"]
        robust_lines.extend(
            [
                _macro(f"{prefix}RatioMin", f"{ratio['minimum']:.6f}"),
                _macro(f"{prefix}RatioMean", f"{ratio['mean']:.6f}"),
                _macro(f"{prefix}RatioMax", f"{ratio['maximum']:.6f}"),
            ]
        )
        fairness = values["fairness_screen"]
        controlling = values["worst_controlling_comparison"]
        fairness_text = (
            f"{fairness['within_threshold']}/{values['runs']} within"
            if fairness["outside_threshold"] == 0
            else f"{fairness['outside_threshold']}/{values['runs']} outside; review"
        )
        tested_group = controlling["tested_group"].replace("|", "--").title()
        reference_group = controlling["reference_group"].replace("|", "--").title()
        status = (
            "within"
            if controlling["within_configured_threshold"]
            else "outside; review"
        )
        rows.append(
            f"{label} & {values['passes']}/{values['runs']} pass & "
            f"{fairness_text} & {ratio['minimum']:.6f}--{ratio['maximum']:.6f} & "
            f"{controlling['attribute'].title()}: {tested_group} vs {reference_group} / "
            f"{controlling['ratio']:.6f} / {status} at "
            f"{controlling['threshold']:.3f} (seed {controlling['seed']})\\\\"
        )
    (build / "includes/technical_robustness.tex").write_text(
        "\n".join(robust_lines) + "\n", encoding="utf-8"
    )
    (build / "includes/table_technical_robustness.tex").write_text(
        "\\AccessibleTableHeaderRow\n"
        "\\begin{tabular}{@{}>{\\RaggedRight\\arraybackslash}p{0.14\\linewidth}"
        ">{\\RaggedRight\\arraybackslash}p{0.13\\linewidth}"
        ">{\\RaggedRight\\arraybackslash}p{0.17\\linewidth}"
        ">{\\RaggedRight\\arraybackslash}p{0.18\\linewidth}"
        ">{\\RaggedRight\\arraybackslash}p{0.28\\linewidth}@{}}\n"
        "\\toprule\n"
        "Scenario & Technical contract & Fairness review & Gender female/male ratio range & "
        "Lowest decision driver / ratio / status\\\\\n"
        "\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n",
        encoding="utf-8",
    )


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = args.repo_root.resolve()
    build = args.build_dir.resolve()
    build.mkdir(parents=True, exist_ok=True)
    intake_dir = build / "intake-source"
    intake_dir.mkdir(parents=True, exist_ok=False)
    expected_bundle_sha = _require_sha(args.intake_sha256, "intake SHA-256")
    actual_bundle_sha = _sha256_file(args.intake_bundle)
    _require_equal(actual_bundle_sha, expected_bundle_sha, "intake bundle SHA-256")
    copied_bundle = build / "source" / INTAKE_NAME
    copied_bundle.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.intake_bundle, copied_bundle)
    _extract_intake(copied_bundle, intake_dir)

    manifest_path = intake_dir / "intake/manifest.json"
    manifest = _read_json(manifest_path)
    pack_intent = _read_json(intake_dir / "intake/pack_intent.json")
    product_sha = _require_sha(args.product_sha, "product commit", full_git=True)
    _require_equal(manifest.get("schema_version"), "wp-intake.v1", "intake schema")
    for field in ("commit_sha", "code_commit", "source_commit", "software_commit"):
        _require_equal(manifest.get(field), product_sha, f"intake manifest {field}")
    _require_equal(manifest.get("build_ref"), "v5.0.8", "intake build reference")

    authorization = _read_json(args.authorization)
    _require_equal(
        authorization.get("artifact_profile"),
        "technical_whitepaper_v1",
        "build-source artifact profile",
    )
    _require_equal(
        authorization.get("decision"),
        "approved_for_build_and_exact_byte_review",
        "build-source decision",
    )
    _require_equal(
        authorization.get("public_distribution_authorized"),
        False,
        "pre-review public-distribution boundary",
    )
    _require_equal(
        authorization.get("customer_evidence_eligible"),
        False,
        "whitepaper customer-evidence boundary",
    )
    _require_equal(
        authorization.get("production_utility_established"),
        False,
        "whitepaper production-utility boundary",
    )
    _require_equal(
        authorization.get("product_sha"), product_sha, "build-source product commit"
    )
    _require_equal(
        authorization["intake_artifact_digest"],
        args.intake_artifact_digest,
        "authorized intake artifact digest",
    )
    _require_equal(
        authorization["robustness_artifact_digest"],
        args.robustness_artifact_digest,
        "authorized robustness artifact digest",
    )

    amp_cert_path = (
        intake_dir
        / "certificates/branch_amplification__synthetic_quality_certificate.json"
    )
    int_cert_path = (
        intake_dir / "certificates/branch_intrinsic__synthetic_quality_certificate.json"
    )
    qualities = {
        "amplification": _quality_projection(_read_json(amp_cert_path)),
        "intrinsic": _quality_projection(_read_json(int_cert_path)),
    }
    for branch, projection in qualities.items():
        _require_equal(
            projection["branch"], branch, f"{branch} quality certificate branch"
        )
        _require_equal(
            projection["quality_threshold_met"], True, f"{branch} quality gate"
        )
        _require_equal(
            projection["utility"]["evaluated"], False, f"{branch} utility disposition"
        )

    amp_generation = _read_json(
        intake_dir
        / "certificates/branch_amplification__generation_process_certificate.json"
    )
    intrinsic_generation = _read_json(
        intake_dir
        / "certificates/branch_intrinsic__generation_process_certificate.json"
    )
    generation = _generation_projection(amp_generation, intrinsic_generation)
    amplification_lc11 = _read_json(
        intake_dir / "certificates/lc11_contract_certificate_amplification.json"
    )
    intrinsic_lc11 = _read_json(
        intake_dir / "certificates/lc11_contract_certificate_intrinsic.json"
    )
    protected_scope = _protected_scope_projection(amplification_lc11)
    _require_equal(
        _protected_scope_projection(intrinsic_lc11),
        protected_scope,
        "branch protected-group scopes",
    )

    robustness = _robustness_projection(args.robustness_root.resolve(), product_sha)
    backend = manifest.get("generator_backend") or {}
    _require_equal(
        backend.get("backend_id"),
        "first_party_evidence_native",
        "generator backend",
    )
    whitepaper_commit = _git(repo_root, "rev-parse", "HEAD")
    _require_sha(whitepaper_commit, "whitepaper commit", full_git=True)
    claims = {
        "claim_expansion_authorized": authorization["claim_expansion_authorized"],
        "customer_evidence_disposition": authorization["customer_evidence_disposition"],
        "customer_evidence_eligible": authorization["customer_evidence_eligible"],
        "demo_evaluation_only": authorization["demo_evaluation_only"],
        "legal_or_compliance_certification": authorization[
            "legal_or_compliance_certification"
        ],
        "marketplace_or_ga_authorization": authorization[
            "marketplace_or_ga_authorization"
        ],
        "production_utility_established": authorization[
            "production_utility_established"
        ],
        "promotion_evidence_eligible": authorization["promotion_evidence_eligible"],
        "regulator_approval": authorization["regulator_approval"],
    }
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "claims": claims,
        "publication_model": {
            "artifact_class": "public_technical_characterization",
            "distribution_status": "exact_byte_review_pending",
            "proposed_public_release_tag": authorization["proposed_public_release_tag"],
            "source_build_decision": authorization["decision"],
            "public_artifact_evidence_disposition": "characterization_only",
            "source_public_distribution_authorized": authorization[
                "public_distribution_authorized"
            ],
        },
        "identity": {
            "product_repo": PRODUCT_REPO,
            "product_commit": product_sha,
            "product_tag_object": authorization["product_tag_object_sha"],
            "release_tag": "v5.0.8",
            "whitepaper_repo": WHITEPAPER_REPO,
            "whitepaper_commit": whitepaper_commit,
            "release_evidence_run_id": authorization["release_evidence_run_id"],
            "source_attempt": authorization["intake_source_attempt"],
            "source_attempt_conclusion": "failure",
            "source_producer_job_id": authorization["intake_producer_job_id"],
            "source_producer_job_conclusion": authorization[
                "intake_producer_job_conclusion"
            ],
            "current_attempt": authorization["release_evidence_current_attempt"],
            "current_attempt_conclusion": authorization[
                "release_evidence_current_attempt_conclusion"
            ],
        },
        "runtime": {
            "generator_backend": backend["backend_id"],
            "generator_claim_limits": backend.get("claim_limits"),
            "image_digest": manifest["ci_runtime_provenance"]["runtime_image"][
                "digest"
            ],
            "run_uuid": manifest["run_id"],
            "dataset_hash": manifest["dataset_hash"],
            "rng_seed": manifest["seeds"]["rng_seed"],
            "bootstrap_seed": manifest["seeds"]["bootstrap_seed"],
        },
        "source": {
            "intake_artifact_id": args.intake_artifact_id,
            "intake_artifact_digest": args.intake_artifact_digest,
            "intake_bundle_filename": INTAKE_NAME,
            "intake_bundle_sha256": actual_bundle_sha,
            "intake_manifest_sha256": _sha256_file(manifest_path),
            "pack_intent_sha256": _sha256_file(intake_dir / "intake/pack_intent.json"),
            "authorization_sha256": _sha256_file(args.authorization),
            "immutable_release_index_sha256": authorization[
                "historical_release_index_sha256"
            ],
            "release_manifest_sha256": authorization["release_manifest_sha256"],
            "release_attestation_sha256": authorization["release_attestation_sha256"],
            "release_trust_root_record_sha256": authorization[
                "release_trust_root_record_sha256"
            ],
            "robustness_artifact_id": args.robustness_artifact_id,
            "robustness_artifact_digest": args.robustness_artifact_digest,
        },
        "quality": qualities,
        "generation": generation,
        "protected_group_scope": protected_scope,
        "robustness": robustness,
        "source_intake_claims": {
            "purpose": pack_intent.get("purpose"),
            "row_level_customer_data": False,
            "single_run_utility_evaluated": False,
            "robustness_amplification_utility_evaluated": True,
            "robustness_intrinsic_utility_evaluated": False,
        },
        "companion": {
            "filename": args.companion_output.name,
            "sha256": "pending",
            "size_bytes": 0,
        },
    }
    _write_json(build / "evidence-summary.json", summary)
    shutil.copyfile(args.authorization, build / "authorization.json")
    public_csv = build / "robustness-public.csv"
    with public_csv.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = list(robustness["public_rows"][0])
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in robustness["public_rows"]:
            encoded = dict(row)
            encoded["amplification_utility"] = json.dumps(
                encoded["amplification_utility"], sort_keys=True, separators=(",", ":")
            )
            writer.writerow(encoded)
    _write_json(
        build / "consumer-source-record.json",
        {
            "schema_version": "flbsa.public_technical_whitepaper_source.v1",
            "producer_bundle": {
                "filename": INTAKE_NAME,
                "sha256": actual_bundle_sha,
                "manifest_sha256": _sha256_file(manifest_path),
                "unchanged": True,
            },
            "consumer": {
                "repo": WHITEPAPER_REPO,
                "commit": whitepaper_commit,
                "authorization_sha256": _sha256_file(args.authorization),
            },
            "retained_attempt": summary["identity"],
        },
    )
    return summary


def _zip_info(name: str, epoch: int, *, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, time.gmtime(max(epoch, 315532800))[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = ((0o100755 if executable else 0o100644) & 0xFFFF) << 16
    return info


def companion(args: argparse.Namespace) -> dict[str, Any]:
    build = args.build_dir.resolve()
    summary_path = build / "evidence-summary.json"
    summary = _read_json(summary_path)
    public_summary = dict(summary)
    public_summary.pop("companion", None)
    members: dict[str, bytes] = {
        f"producer/{INTAKE_NAME}": (build / "source" / INTAKE_NAME).read_bytes(),
        "consumer/source-record.json": (
            build / "consumer-source-record.json"
        ).read_bytes(),
        "authorization/build-source-decision-and-correction.json": (
            build / "authorization.json"
        ).read_bytes(),
        "evidence/evidence-summary.json": (
            json.dumps(public_summary, indent=2, sort_keys=True) + "\n"
        ).encode(),
        "verify_public_technical_companion.py": args.verifier.read_bytes(),
    }
    members["evidence/robustness-public.csv"] = (
        build / "robustness-public.csv"
    ).read_bytes()
    manifest = {
        "schema_version": COMPANION_SCHEMA,
        "claims": summary["claims"],
        "identity": summary["identity"],
        "files": {
            name: {"sha256": _sha256_bytes(data), "size_bytes": len(data)}
            for name, data in sorted(members.items())
        },
    }
    members["MANIFEST.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode()
    epoch_raw = os.environ.get("SOURCE_DATE_EPOCH") or _git(
        args.repo_root, "show", "-s", "--format=%ct", "HEAD"
    )
    try:
        epoch = int(epoch_raw)
    except ValueError as exc:
        raise TechnicalPaperError("SOURCE_DATE_EPOCH must be an integer") from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w") as archive:
        for name, data in sorted(members.items()):
            archive.writestr(
                _zip_info(name, epoch, executable=name.endswith(".py")), data
            )
    summary["companion"] = {
        "filename": args.output.name,
        "sha256": _sha256_file(args.output),
        "size_bytes": args.output.stat().st_size,
    }
    _write_json(summary_path, summary)
    _write_technical_includes(build, summary)
    return summary


def finalize(args: argparse.Namespace) -> dict[str, Any]:
    summary = _read_json(args.build_dir / "evidence-summary.json")
    if summary["companion"]["sha256"] == "pending":
        _fail("companion must be built before finalizing the PDF")
    pdf_bytes = args.pdf.read_bytes()
    if not pdf_bytes.startswith(b"%PDF-"):
        _fail("technical whitepaper is not a PDF")
    for label, value in (
        ("whitepaper build run ID", args.whitepaper_run_id),
        ("whitepaper build run attempt", args.whitepaper_run_attempt),
    ):
        if not value.isdigit() or int(value) <= 0:
            _fail(f"{label} must be a positive integer")
    identity = dict(summary["identity"])
    identity.update(
        {
            "whitepaper_build_run_id": args.whitepaper_run_id,
            "whitepaper_build_run_attempt": args.whitepaper_run_attempt,
        }
    )
    sidecar = {
        "schema_version": SIDECAR_SCHEMA,
        "publication_model": summary["publication_model"],
        "claims": summary["claims"],
        "identity": identity,
        "source": summary["source"],
        "pdf": {
            "filename": args.pdf.name,
            "sha256": _sha256_bytes(pdf_bytes),
            "size_bytes": len(pdf_bytes),
        },
        "companion": summary["companion"],
    }
    _write_json(args.output, sidecar)
    return sidecar


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    prepare_parser.add_argument("--build-dir", type=Path, required=True)
    prepare_parser.add_argument("--intake-bundle", type=Path, required=True)
    prepare_parser.add_argument("--intake-sha256", required=True)
    prepare_parser.add_argument("--intake-artifact-id", required=True)
    prepare_parser.add_argument("--intake-artifact-digest", required=True)
    prepare_parser.add_argument("--robustness-root", type=Path, required=True)
    prepare_parser.add_argument("--robustness-artifact-id", required=True)
    prepare_parser.add_argument("--robustness-artifact-digest", required=True)
    prepare_parser.add_argument("--product-sha", required=True)
    prepare_parser.add_argument("--authorization", type=Path, required=True)
    prepare_parser.add_argument("--companion-output", type=Path, required=True)

    companion_parser = subparsers.add_parser("companion")
    companion_parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    companion_parser.add_argument("--build-dir", type=Path, required=True)
    companion_parser.add_argument("--verifier", type=Path, required=True)
    companion_parser.add_argument("--output", type=Path, required=True)

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--build-dir", type=Path, required=True)
    finalize_parser.add_argument("--pdf", type=Path, required=True)
    finalize_parser.add_argument("--output", type=Path, required=True)
    finalize_parser.add_argument("--whitepaper-run-id", required=True)
    finalize_parser.add_argument("--whitepaper-run-attempt", required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args)
        elif args.command == "companion":
            result = companion(args)
        else:
            result = finalize(args)
    except (OSError, KeyError, TechnicalPaperError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
