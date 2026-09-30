#!/usr/bin/env python3
"""Validate the exact v5.0.8 public-technical-paper source lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

SCHEMA = "flbsa.public_technical_whitepaper_source_lock.v1"
PROFILE = "technical_whitepaper_v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
REVIEWED_FILES = {
    "gold/robustness_index.csv",
    "gold_robustness/evidence_manifest.json",
    "gold_robustness/robustness_gate_disposition.json",
    "gold_robustness/robustness_requirements.json",
    "gold_robustness/robustness_summary_merged.json",
}
DENIED_CLAIMS = {
    "claim_expansion_authorized",
    "customer_evidence_eligible",
    "legal_or_compliance_certification",
    "marketplace_or_ga_authorization",
    "production_utility_established",
    "promotion_evidence_eligible",
    "regulator_approval",
}


class SourceLockError(ValueError):
    """Raised when the checked-in technical-paper source lock is invalid."""


def _fail(message: str) -> NoReturn:
    raise SourceLockError(message)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceLockError(f"unable to read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        _fail(f"JSON root must be an object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail(f"{label} must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise SourceLockError(f"{label} must be an RFC3339 UTC timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        _fail(f"{label} must use UTC")
    return parsed


def _positive(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{label} must be a positive integer")
    return value


def _sha(value: Any, label: str, *, git: bool = False, digest: bool = False) -> str:
    pattern = GIT_SHA_RE if git else DIGEST_RE if digest else SHA256_RE
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        _fail(f"{label} has invalid digest syntax")
    return value


def _check_claims(claims: Any) -> dict[str, Any]:
    if not isinstance(claims, dict) or set(claims) != DENIED_CLAIMS | {
        "customer_evidence_disposition",
        "demo_evaluation_only",
    }:
        _fail("source-lock claim shape is invalid")
    if any(claims[field] is not False for field in DENIED_CLAIMS):
        _fail("source-lock denied claims must remain false")
    if claims["customer_evidence_disposition"] != "characterization_only":
        _fail("source-lock disposition must remain characterization_only")
    if claims["demo_evaluation_only"] is not True:
        _fail("source-lock must remain demo/evaluation only")
    return claims


def validate(
    *,
    lock_path: Path,
    product_source_map: Path | None = None,
    resolved_source: Path | None = None,
    intake_bundle: Path | None = None,
    robustness_root: Path | None = None,
    intake_actions_archive: Path | None = None,
    robustness_actions_archive: Path | None = None,
) -> dict[str, Any]:
    """Validate structure, chronology, hashes, and optional downloaded inputs."""

    lock = _json(lock_path)
    required = {
        "artifact_profile",
        "claims",
        "product_source_record",
        "product",
        "proposed_public_release_tag",
        "release_evidence",
        "schema_version",
        "signed_release",
        "sources",
    }
    if set(lock) != required or lock.get("schema_version") != SCHEMA:
        _fail("technical source-lock root shape or schema is invalid")
    if lock["artifact_profile"] != PROFILE:
        _fail("technical source-lock artifact profile is invalid")
    claims = _check_claims(lock["claims"])

    product = lock["product"]
    if not isinstance(product, dict) or set(product) != {"commit", "tag", "tag_object"}:
        _fail("source-lock product shape is invalid")
    _sha(product["commit"], "product commit", git=True)
    _sha(product["tag_object"], "product tag object", git=True)
    if product["tag"] != "v5.0.8":
        _fail("source-lock product tag must be v5.0.8")
    if lock["proposed_public_release_tag"] != "v5.0.8-technical-whitepaper-20260930":
        _fail("source-lock public tag is invalid")

    record = lock["product_source_record"]
    if not isinstance(record, dict) or set(record) != {
        "commit",
        "path",
        "repository",
        "sha256",
        "size_bytes",
    }:
        _fail("source-lock product record shape is invalid")
    _sha(record["commit"], "product source-record commit", git=True)
    _sha(record["sha256"], "product source-record SHA-256")
    _positive(record["size_bytes"], "product source-record size")
    if record["repository"] != "equilens-labs/fl-bsa":
        _fail("source-lock product source repository is invalid")
    if record["path"] != "config/public-technical-whitepaper-build-sources.v1.json":
        _fail("source-lock product source path is invalid")
    if product_source_map is not None:
        if product_source_map.stat().st_size != record["size_bytes"]:
            _fail("product source-map size mismatch")
        if _sha256(product_source_map) != record["sha256"]:
            _fail("product source-map SHA-256 mismatch")

    evidence = lock["release_evidence"]
    expected_evidence = {
        "branch": "main",
        "current_attempt": 2,
        "current_attempt_conclusion": "success",
        "event": "repository_dispatch",
        "run_id": 36152873675,
        "source_attempt": 1,
        "source_attempt_conclusion": "failure",
        "workflow_path": ".github/workflows/release-evidence.yml",
    }
    for field, expected in expected_evidence.items():
        if evidence.get(field) != expected:
            _fail(f"source-lock release-evidence {field} is invalid")
    source_start = _time(
        evidence.get("source_attempt_started_at"), "source attempt start"
    )
    source_end = _time(
        evidence.get("source_attempt_updated_at"), "source attempt update"
    )
    current_start = _time(
        evidence.get("current_attempt_started_at"), "current attempt start"
    )
    if not source_start < source_end < current_start:
        _fail("source-lock attempt chronology is invalid")

    signed = lock["signed_release"]
    if not isinstance(signed, dict) or set(signed) != {
        "release_artifact_manifest_sha256",
        "release_trust_root_record_sha256",
        "vendor_release_attestation_sha256",
    }:
        _fail("source-lock signed-release shape is invalid")
    for field, value in signed.items():
        _sha(value, f"signed release {field}")

    sources = lock["sources"]
    if not isinstance(sources, dict) or set(sources) != {"intake", "robustness"}:
        _fail("source-lock sources shape is invalid")
    for label in ("intake", "robustness"):
        source = sources[label]
        archive = source.get("actions_archive") or {}
        job = source.get("producer_job") or {}
        _positive(archive.get("id"), f"{label} artifact ID")
        _sha(archive.get("digest"), f"{label} artifact digest", digest=True)
        _positive(archive.get("size_bytes"), f"{label} artifact size")
        created = _time(archive.get("created_at"), f"{label} artifact creation")
        expires = _time(archive.get("expires_at"), f"{label} artifact expiry")
        started = _time(job.get("started_at"), f"{label} producer start")
        completed = _time(job.get("completed_at"), f"{label} producer completion")
        _positive(job.get("id"), f"{label} producer job ID")
        if job.get("conclusion") != "success":
            _fail(f"{label} producer job must have succeeded")
        if (
            not source_start
            <= started
            <= created
            <= completed
            <= source_end
            < current_start
            < expires
        ):
            _fail(f"{label} retained-attempt chronology is invalid")

        actions_archive = {
            "intake": intake_actions_archive,
            "robustness": robustness_actions_archive,
        }[label]
        if actions_archive is not None:
            if actions_archive.stat().st_size != archive["size_bytes"]:
                _fail(f"{label} Actions archive size mismatch")
            if _sha256(actions_archive) != archive["digest"].removeprefix("sha256:"):
                _fail(f"{label} Actions archive SHA-256 mismatch")

    intake = sources["intake"]
    inner = intake.get("inner_bundle") or {}
    if inner.get("filename") != "WhitePaper_Intake_Bundle_v4.zip":
        _fail("source-lock intake filename is invalid")
    _sha(inner.get("sha256"), "inner intake SHA-256")
    _positive(inner.get("size_bytes"), "inner intake size")
    _sha(intake.get("manifest_sha256"), "intake manifest SHA-256")
    if intake_bundle is not None:
        if intake_bundle.stat().st_size != inner["size_bytes"]:
            _fail("inner intake size mismatch")
        if _sha256(intake_bundle) != inner["sha256"]:
            _fail("inner intake SHA-256 mismatch")

    reviewed = sources["robustness"].get("reviewed_files")
    if not isinstance(reviewed, dict) or set(reviewed) != REVIEWED_FILES:
        _fail("source-lock reviewed robustness membership is invalid")
    for name, identity in reviewed.items():
        if not isinstance(identity, dict) or set(identity) != {"sha256", "size_bytes"}:
            _fail(f"source-lock robustness identity shape is invalid: {name}")
        _sha(identity["sha256"], f"robustness {name} SHA-256")
        _positive(identity["size_bytes"], f"robustness {name} size")
        if robustness_root is not None:
            path = robustness_root / name
            if not path.is_file() or path.stat().st_size != identity["size_bytes"]:
                _fail(f"robustness file size mismatch: {name}")
            if _sha256(path) != identity["sha256"]:
                _fail(f"robustness file SHA-256 mismatch: {name}")

    if resolved_source is not None:
        source = _json(resolved_source)
        comparisons = {
            "artifact_profile": PROFILE,
            "product_sha": product["commit"],
            "product_tag": product["tag"],
            "product_tag_object_sha": product["tag_object"],
            "proposed_public_release_tag": lock["proposed_public_release_tag"],
            "release_evidence_run_id": str(evidence["run_id"]),
            "release_evidence_current_attempt": str(evidence["current_attempt"]),
            "release_evidence_source_attempt_conclusion": evidence[
                "source_attempt_conclusion"
            ],
            "intake_source_attempt": str(evidence["source_attempt"]),
            "robustness_source_attempt": str(evidence["source_attempt"]),
            "intake_artifact_id": str(sources["intake"]["actions_archive"]["id"]),
            "intake_artifact_digest": sources["intake"]["actions_archive"]["digest"],
            "intake_artifact_archive_size": str(
                sources["intake"]["actions_archive"]["size_bytes"]
            ),
            "intake_bundle_sha256": inner["sha256"],
            "robustness_artifact_id": str(
                sources["robustness"]["actions_archive"]["id"]
            ),
            "robustness_artifact_digest": sources["robustness"]["actions_archive"][
                "digest"
            ],
            "robustness_artifact_archive_size": str(
                sources["robustness"]["actions_archive"]["size_bytes"]
            ),
            "release_manifest_sha256": signed["release_artifact_manifest_sha256"],
            "release_attestation_sha256": signed["vendor_release_attestation_sha256"],
            "release_trust_root_record_sha256": signed[
                "release_trust_root_record_sha256"
            ],
        }
        for field, expected in comparisons.items():
            if source.get(field) != expected:
                _fail(f"resolved product source differs from lock: {field}")
        for field, expected in claims.items():
            if source.get(field) != expected:
                _fail(f"resolved product claim differs from lock: {field}")
        correction = source.get("metadata_correction") or {}
        if correction.get("corrected_value") is not False:
            _fail("resolved product source lacks the reviewed eligibility correction")

    return {
        "validated": True,
        "schema_version": SCHEMA,
        "product_commit": product["commit"],
        "product_source_commit": record["commit"],
        "run_id": evidence["run_id"],
        "source_attempt": evidence["source_attempt"],
        "current_attempt": evidence["current_attempt"],
        "intake_artifact_id": sources["intake"]["actions_archive"]["id"],
        "robustness_artifact_id": sources["robustness"]["actions_archive"]["id"],
        "source_lock_sha256": _sha256(lock_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-lock", type=Path, required=True)
    parser.add_argument("--product-source-map", type=Path)
    parser.add_argument("--resolved-source", type=Path)
    parser.add_argument("--intake-bundle", type=Path)
    parser.add_argument("--robustness-root", type=Path)
    parser.add_argument("--intake-actions-archive", type=Path)
    parser.add_argument("--robustness-actions-archive", type=Path)
    args = parser.parse_args()
    try:
        result = validate(
            lock_path=args.source_lock,
            product_source_map=args.product_source_map,
            resolved_source=args.resolved_source,
            intake_bundle=args.intake_bundle,
            robustness_root=args.robustness_root,
            intake_actions_archive=args.intake_actions_archive,
            robustness_actions_archive=args.robustness_actions_archive,
        )
    except (OSError, SourceLockError) as exc:
        print(f"source-lock validation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
