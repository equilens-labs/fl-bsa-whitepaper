#!/usr/bin/env python3
"""Offline verifier for the FL-BSA public technical-whitepaper companion."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn


EXPECTED_SCHEMA = "flbsa.public_technical_whitepaper_companion.v1"
EXPECTED_PRODUCT_SHA = "97356e5f65e0032e8363190c47104c96294f8f2a"
EXPECTED_INTAKE_SHA256 = (
    "68246ce7aaeb571363cdc2bdbc25892ec3d3b438849661e06653fcd985c59e6c"
)
EXPECTED_RELEASE_TAG = "v5.0.8"
EXPECTED_PUBLIC_RELEASE_TAG = "v5.0.8-technical-whitepaper-20260930"
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_MEMBERS = 64
MAX_UNCOMPRESSED_BYTES = 25 * 1024 * 1024
# Assemble the sentinels so the distributable verifier does not match its own
# source text when the companion is scanned for private runner paths.
PRIVATE_PATH_RE = re.compile(
    rb"(?:/"
    + b"home"
    + rb"/|/"
    + b"Users"
    + rb"/|[A-Za-z]:\\\\|"
    + b"actions"
    + b"-runner)"
)


class VerificationError(ValueError):
    """Raised when a companion fails offline verification."""


def _fail(message: str) -> NoReturn:
    raise VerificationError(message)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(value, dict):
        _fail(f"{label} must contain a JSON object")
    return value


def _safe_name(name: str) -> None:
    path = PurePosixPath(name)
    raw_parts = name[:-1].split("/") if name.endswith("/") else name.split("/")
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or any(part in {"", ".", ".."} for part in raw_parts)
        or path.as_posix() != name.rstrip("/")
    ):
        _fail(f"unsafe companion member: {name!r}")


def _bounded_infos(
    infos: list[zipfile.ZipInfo], *, label: str
) -> list[zipfile.ZipInfo]:
    if len(infos) > MAX_MEMBERS:
        _fail(f"{label} has too many members")
    total = 0
    for item in infos:
        _safe_name(item.filename)
        if item.file_size < 0:
            _fail(f"{label} member has an invalid size: {item.filename}")
        total += item.file_size
        if total > MAX_UNCOMPRESSED_BYTES:
            _fail(f"{label} exceeds the uncompressed-size limit")
    return infos


def verify(path: Path) -> dict[str, Any]:
    try:
        archive_size = path.stat().st_size
    except OSError as exc:
        raise VerificationError(f"unable to inspect companion ZIP: {exc}") from exc
    if archive_size <= 0 or archive_size > MAX_ARCHIVE_BYTES:
        _fail(f"companion ZIP has an unsafe size: {archive_size}")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = _bounded_infos(archive.infolist(), label="companion")
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                _fail("companion contains duplicate member names")
            for item in infos:
                mode = (item.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    _fail(f"companion contains a symbolic link: {item.filename}")
            data = {name: archive.read(name) for name in names}
    except zipfile.BadZipFile as exc:
        raise VerificationError(f"invalid companion ZIP: {exc}") from exc

    manifest = _json(data.get("MANIFEST.json", b""), "MANIFEST.json")
    if manifest.get("schema_version") != EXPECTED_SCHEMA:
        _fail("unexpected companion schema")
    listed = manifest.get("files")
    if not isinstance(listed, dict):
        _fail("companion manifest files must be an object")
    expected_names = set(listed) | {"MANIFEST.json"}
    if set(data) != expected_names:
        _fail("companion membership differs from MANIFEST.json")
    for name, identity in listed.items():
        if not isinstance(identity, dict):
            _fail(f"invalid file identity for {name}")
        payload = data[name]
        if identity.get("sha256") != _sha256(payload):
            _fail(f"SHA-256 mismatch for {name}")
        if identity.get("size_bytes") != len(payload):
            _fail(f"size mismatch for {name}")
        if (
            name != "producer/WhitePaper_Intake_Bundle_v4.zip"
            and PRIVATE_PATH_RE.search(payload)
        ):
            _fail(f"private path leaked into public projection: {name}")

    claims = manifest.get("claims") or {}
    if claims.get("customer_evidence_eligible") is not False:
        _fail("companion must remain customer-evidence ineligible")
    if claims.get("customer_evidence_disposition") != "characterization_only":
        _fail("companion must retain characterization-only disposition")
    for denied_claim in (
        "claim_expansion_authorized",
        "legal_or_compliance_certification",
        "marketplace_or_ga_authorization",
        "production_utility_established",
        "promotion_evidence_eligible",
        "regulator_approval",
    ):
        if claims.get(denied_claim) is not False:
            _fail(f"companion must deny {denied_claim}")
    if claims.get("demo_evaluation_only") is not True:
        _fail("companion must retain the demo/evaluation-only boundary")

    build_decision = _json(
        data["authorization/build-source-decision-and-correction.json"],
        "build-source decision",
    )
    expected_decision = {
        "artifact_profile": "technical_whitepaper_v1",
        "decision": "approved_for_build_and_exact_byte_review",
        "product_sha": EXPECTED_PRODUCT_SHA,
        "proposed_public_release_tag": EXPECTED_PUBLIC_RELEASE_TAG,
        "public_distribution_authorized": False,
    }
    for field, expected in expected_decision.items():
        if build_decision.get(field) != expected:
            _fail(f"build-source decision has unexpected {field}")
    for field, expected in claims.items():
        if build_decision.get(field) != expected:
            _fail(f"build-source decision differs from claims: {field}")
    correction = build_decision.get("metadata_correction") or {}
    if (
        correction.get("field") != "whitepaper.customer_evidence_eligible"
        or correction.get("corrected_value") is not False
    ):
        _fail("build-source decision lacks the reviewed eligibility correction")

    identity = manifest.get("identity") or {}
    if identity.get("product_commit") != EXPECTED_PRODUCT_SHA:
        _fail("product commit mismatch")
    if identity.get("release_tag") != EXPECTED_RELEASE_TAG:
        _fail("release tag mismatch")
    if identity.get("release_evidence_run_id") != "36152873675":
        _fail("release-evidence run mismatch")
    if identity.get("source_attempt") != "1" or identity.get("current_attempt") != "2":
        _fail("retained-attempt lineage mismatch")
    if identity.get("source_attempt_conclusion") != "failure":
        _fail("source attempt conclusion was not disclosed")
    if identity.get("source_producer_job_conclusion") != "success":
        _fail("source producer job was not successful")
    if identity.get("current_attempt_conclusion") != "success":
        _fail("current release-evidence attempt was not successful")

    intake_bytes = data["producer/WhitePaper_Intake_Bundle_v4.zip"]
    if _sha256(intake_bytes) != EXPECTED_INTAKE_SHA256:
        _fail("producer intake ZIP does not match the exact retained source")
    try:
        with zipfile.ZipFile(io.BytesIO(intake_bytes)) as intake:
            intake_infos = _bounded_infos(intake.infolist(), label="producer intake")
            intake_names = [item.filename for item in intake_infos]
            if len(intake_names) != len(set(intake_names)):
                _fail("producer intake contains duplicate members")
            source_manifest = _json(
                intake.read("intake/manifest.json"), "producer intake manifest"
            )
    except (KeyError, zipfile.BadZipFile) as exc:
        raise VerificationError(f"invalid producer intake: {exc}") from exc
    if source_manifest.get("schema_version") != "wp-intake.v1":
        _fail("producer intake manifest schema mismatch")
    for field in ("commit_sha", "code_commit", "source_commit", "software_commit"):
        if source_manifest.get(field) != EXPECTED_PRODUCT_SHA:
            _fail(f"producer intake {field} mismatch")

    summary = _json(data["evidence/evidence-summary.json"], "evidence summary")
    if summary.get("claims") != claims or summary.get("identity") != identity:
        _fail("evidence summary claim or identity boundary differs from the manifest")
    expected_publication_model = {
        "artifact_class": "public_technical_characterization",
        "distribution_status": "exact_byte_review_pending",
        "proposed_public_release_tag": EXPECTED_PUBLIC_RELEASE_TAG,
        "source_build_decision": "approved_for_build_and_exact_byte_review",
        "public_artifact_evidence_disposition": "characterization_only",
        "source_public_distribution_authorized": False,
    }
    if summary.get("publication_model") != expected_publication_model:
        _fail("evidence summary publication model differs from the reviewed boundary")
    quality = summary.get("quality") or {}
    amp_quality = quality.get("amplification") or {}
    intrinsic_quality = quality.get("intrinsic") or {}
    if (amp_quality.get("component_dispositions") or {}).get(
        "demographic_rate_fidelity"
    ) != "evaluated":
        _fail("amplification demographic-rate fidelity must be evaluated")
    if (intrinsic_quality.get("component_dispositions") or {}).get(
        "demographic_rate_fidelity"
    ) != "not_evaluated_default_one_no_outcome":
        _fail("intrinsic demographic-rate fidelity default is not disclosed")
    if (intrinsic_quality.get("components") or {}).get(
        "bias_preservation_score"
    ) != 1.0:
        _fail("intrinsic demographic-rate fidelity default value differs")

    generation = summary.get("generation") or {}
    amplification_generation = generation.get("amplification") or {}
    intrinsic_generation = generation.get("intrinsic") or {}
    amp_wall = amplification_generation.get("exact_output_wall") or {}
    intrinsic_wall = intrinsic_generation.get("exact_output_wall") or {}
    alignment = amplification_generation.get("quantile_alignment") or {}
    if (
        amplification_generation.get("backend_id") != "first_party_evidence_native"
        or amplification_generation.get("backend_version") != "0.1.0"
        or amplification_generation.get("generated_rows") != 10_000
        or amplification_generation.get("seed") != 42
        or amp_wall.get("matching_row_instances") != 0
        or alignment.get("applied") is not True
        or alignment.get("reference_surface") != "original_training_data"
        or alignment.get("stratify_columns") != ["loan_approved"]
    ):
        _fail("amplification generation projection differs from reviewed evidence")
    if (
        intrinsic_generation.get("backend_id") != "first_party_evidence_native"
        or intrinsic_generation.get("backend_version") != "0.1.0"
        or intrinsic_generation.get("generated_rows") != 10_000
        or intrinsic_generation.get("seed") != 42
        or intrinsic_generation.get("sampling_strategy")
        != "intrinsic_anchor_profile_resampling"
        or intrinsic_generation.get("stratification_column") != "gender,race"
        or intrinsic_wall.get("matching_row_instances") != 0
    ):
        _fail("intrinsic generation projection differs from reviewed evidence")

    protected_scope = summary.get("protected_group_scope") or {}
    if (
        protected_scope.get("claim_scope") != "per_attribute"
        or protected_scope.get("covered_attributes") != ["gender", "race"]
        or protected_scope.get("excluded_claims")
        != [
            "absence_of_bias_for_uncovered_protected_bases",
            "absence_of_intersectional_bias",
            "multi_level_race_encoding_without_declared_schema_support",
        ]
        or protected_scope.get("uncovered_ecoa_reg_b_bases")
        != [
            "color",
            "religion",
            "national_origin",
            "marital_status",
            "age",
            "receipt_of_public_assistance",
            "exercise_of_consumer_credit_rights",
        ]
    ):
        _fail("protected-group scope differs from the reviewed LC11 boundary")
    robustness = summary.get("robustness") or {}
    if robustness.get("runs") != 40 or robustness.get("passes") != 40:
        _fail("robustness summary does not record 40/40 passing scenario runs")
    utility = robustness.get("advisory_utility") or {}
    if utility.get("runs") != 40 or utility.get("below_floor") != 36:
        _fail("advisory utility summary does not match the reviewed 40-run evidence")
    if utility.get("intrinsic_status") != "not_evaluated":
        _fail("intrinsic utility must remain not evaluated")
    if utility.get("accuracy_threshold_status") != "not_configured":
        _fail("advisory accuracy must not acquire an unreviewed threshold")

    csv_bytes = data["evidence/robustness-public.csv"]
    rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8"))))
    if len(rows) != 40:
        _fail(f"public robustness projection must contain 40 rows, got {len(rows)}")
    expected_columns = {
        "scenario",
        "seed",
        "status",
        "scenario_test_passed",
        "headline_gender_ratio",
        "selection_rate_gap",
        "maximum_demographic_parity_difference",
        "maximum_demographic_parity_attribute",
        "fairness_screen_within_threshold",
        "controlling_attribute",
        "controlling_tested_group",
        "controlling_reference_group",
        "controlling_ratio",
        "controlling_threshold",
        "controlling_within_threshold",
        "lowest_intersection",
        "lowest_intersection_reference",
        "lowest_intersection_ratio",
        "aod_status",
        "eod_status",
        "pdf_numeric_parity_passed",
        "certificate_chain_passed",
        "certificate_signatures_passed",
        "evidence_encryption_passed",
        "lc11_contract_certification_passed",
        "amplification_utility",
    }
    if set(rows[0]) != expected_columns:
        _fail("public robustness projection columns differ from the reviewed schema")
    scenarios = {row.get("scenario") for row in rows}
    if scenarios != {"01_balanced", "02_gender_bias", "03_outliers", "04_security"}:
        _fail("public robustness projection scenario set mismatch")
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
    utility_values: list[float] = []
    accuracy_values: list[float] = []
    utility_statuses: list[str] = []
    for scenario in scenarios:
        selected = [row for row in rows if row.get("scenario") == scenario]
        if {row.get("seed") for row in selected} != expected_seeds:
            _fail(f"{scenario} seed set mismatch")
        if any(row.get("status") != "pass" for row in selected):
            _fail(f"{scenario} contains a non-passing scenario run")
        if any(row.get("scenario_test_passed") != "True" for row in selected):
            _fail(f"{scenario} scenario status is internally inconsistent")
        if any(row.get("aod_status") != "unavailable" for row in selected):
            _fail(f"{scenario} incorrectly makes AOD available")
        if any(row.get("eod_status") != "unavailable" for row in selected):
            _fail(f"{scenario} incorrectly makes EOD available")
        for row in selected:
            if row.get("controlling_attribute") not in {
                "gender",
                "race",
                "intersectional",
            }:
                _fail(f"{scenario} controlling attribute is missing or wrong")
            if not row.get("controlling_tested_group") or not row.get(
                "controlling_reference_group"
            ):
                _fail(f"{scenario} controlling groups are missing")
            if (
                not row.get("lowest_intersection")
                or "|" not in row["lowest_intersection"]
                or row.get("lowest_intersection_reference") != "male|white"
            ):
                _fail(f"{scenario} lowest-intersection diagnostic is malformed")
            try:
                controlling_ratio = float(row["controlling_ratio"])
                controlling_threshold = float(row["controlling_threshold"])
                lowest_intersection_ratio = float(row["lowest_intersection_ratio"])
            except (TypeError, ValueError) as exc:
                raise VerificationError(
                    f"{scenario} comparison ratio or threshold is not numeric"
                ) from exc
            if (
                not math.isfinite(controlling_ratio)
                or controlling_ratio < 0
                or controlling_threshold != 0.8
                or not math.isfinite(lowest_intersection_ratio)
                or lowest_intersection_ratio < 0
            ):
                _fail(f"{scenario} comparison ratio or threshold is invalid")
            expected_within = "True" if controlling_ratio >= 0.8 else "False"
            if (
                row.get("controlling_within_threshold") != expected_within
                or row.get("fairness_screen_within_threshold") != expected_within
            ):
                _fail(f"{scenario} controlling ratio and review status disagree")
            for field in (
                "pdf_numeric_parity_passed",
                "certificate_chain_passed",
                "certificate_signatures_passed",
                "evidence_encryption_passed",
                "lc11_contract_certification_passed",
            ):
                if row.get(field) != "True":
                    _fail(f"{scenario} contains a failed integrity disposition")
            try:
                utility_value = json.loads(row["amplification_utility"])
            except json.JSONDecodeError as exc:
                raise VerificationError("invalid advisory utility JSON") from exc
            if not isinstance(utility_value, dict):
                _fail("invalid advisory utility shape")
            if set(utility_value) != {"accuracy", "auc", "floor", "status"}:
                _fail("invalid advisory utility shape")
            auc = utility_value.get("auc")
            accuracy = utility_value.get("accuracy")
            floor = utility_value.get("floor")
            status = utility_value.get("status")
            if (
                isinstance(auc, bool)
                or not isinstance(auc, (int, float))
                or not math.isfinite(auc)
                or not 0 <= auc <= 1
                or isinstance(accuracy, bool)
                or not isinstance(accuracy, (int, float))
                or not math.isfinite(accuracy)
                or not 0 <= accuracy <= 1
                or floor != 0.7
            ):
                _fail("invalid advisory utility value")
            if status not in {"pass", "warn"}:
                _fail("invalid advisory utility status")
            if status != ("pass" if auc >= floor else "warn"):
                _fail("advisory utility value and status disagree")
            utility_values.append(float(auc))
            accuracy_values.append(float(accuracy))
            utility_statuses.append(status)

    expected_scenario_worst = {
        "01_balanced": {
            "seed": 101,
            "attribute": "race",
            "tested_group": "other",
            "reference_group": "hispanic",
            "ratio": 0.8876387210196682,
            "within_configured_threshold": True,
        },
        "02_gender_bias": {
            "seed": 101,
            "attribute": "intersectional",
            "tested_group": "female|asian",
            "reference_group": "male|white",
            "ratio": 0.5326046511627907,
            "within_configured_threshold": False,
        },
        "03_outliers": {
            "seed": 1337,
            "attribute": "intersectional",
            "tested_group": "female|other",
            "reference_group": "male|white",
            "ratio": 0.8570195449781122,
            "within_configured_threshold": True,
        },
        "04_security": {
            "seed": 11,
            "attribute": "intersectional",
            "tested_group": "male|other",
            "reference_group": "male|white",
            "ratio": 0.8716203198253163,
            "within_configured_threshold": True,
        },
    }
    for scenario, expected in expected_scenario_worst.items():
        selected = [row for row in rows if row["scenario"] == scenario]
        observed_row = min(selected, key=lambda row: float(row["controlling_ratio"]))
        for field in ("attribute", "tested_group", "reference_group"):
            if observed_row[f"controlling_{field}"] != expected[field]:
                _fail(f"{scenario} controlling {field} differs from reviewed evidence")
        if (
            int(observed_row["seed"]) != expected["seed"]
            or not math.isclose(
                float(observed_row["controlling_ratio"]),
                expected["ratio"],
                rel_tol=0,
                abs_tol=1e-15,
            )
            or (observed_row["controlling_within_threshold"] == "True")
            is not expected["within_configured_threshold"]
        ):
            _fail(
                f"{scenario} decision-driving comparison differs from reviewed evidence"
            )
        summary_worst = ((robustness.get("scenarios") or {}).get(scenario) or {}).get(
            "worst_controlling_comparison"
        ) or {}
        if summary_worst != {**expected, "threshold": 0.8}:
            _fail(f"{scenario} summary decision driver differs from public rows")

    gender_rows = [row for row in rows if row["scenario"] == "02_gender_bias"]
    if any(row["fairness_screen_within_threshold"] != "False" for row in gender_rows):
        _fail("gender-bias positive-control review status is inconsistent")
    seed_42 = next(row for row in gender_rows if row["seed"] == "42")
    if (
        seed_42["controlling_attribute"] != "intersectional"
        or seed_42["controlling_tested_group"] != "female|white"
        or seed_42["controlling_reference_group"] != "male|white"
        or float(seed_42["controlling_ratio"]) != 0.6113118085346579
    ):
        _fail("seed-42 controlling comparison differs from the reviewed evidence")

    utility_passes = utility_statuses.count("pass")
    expected_utility = {
        "minimum_auc": min(utility_values),
        "mean_auc": math.fsum(utility_values) / len(utility_values),
        "maximum_auc": max(utility_values),
        "minimum_accuracy": min(accuracy_values),
        "mean_accuracy": math.fsum(accuracy_values) / len(accuracy_values),
        "maximum_accuracy": max(accuracy_values),
        "at_or_above_floor": utility_passes,
        "below_floor": len(utility_values) - utility_passes,
    }
    for field, expected in expected_utility.items():
        actual = utility.get(field)
        if isinstance(expected, float):
            if not isinstance(actual, (int, float)) or not math.isclose(
                actual, expected, rel_tol=0, abs_tol=1e-15
            ):
                _fail(f"advisory utility {field} differs from the public rows")
        elif actual != expected:
            _fail(f"advisory utility {field} differs from the public rows")

    return {
        "verified": True,
        "companion_sha256": _sha256(path.read_bytes()),
        "product_commit": EXPECTED_PRODUCT_SHA,
        "release_tag": EXPECTED_RELEASE_TAG,
        "robustness_runs": 40,
        "robustness_passes": 40,
        "customer_evidence_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("companion", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.companion)
    except (OSError, UnicodeDecodeError, VerificationError) as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
