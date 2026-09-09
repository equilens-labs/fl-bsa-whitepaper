#!/usr/bin/env python3
"""Verify the standalone FL-BSA v5.0.1 whitepaper companion bundle."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import re
import stat
import statistics
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from characterization_contract import (
    GOLD_SOURCE_SUMMARY_SHA256,
    GOLD_SUMMARY_PROJECTION,
    INTERNAL_AIR_SCREEN,
    UTILITY_SUMMARY_PATH,
)


PRODUCT_COMMIT = "cc32b3a8d13cb75419b0dec1d4b9bdf5a3eb90c2"
PRODUCT_TAG = "v5.0.1"
PRODUCT_TAG_OBJECT = "3a0ea6e4faea9d61aabcedebab2a838624fb587d"
PRODUCT_RUN_ID = "30765888408"
PRIMARY_BUNDLE_SHA256 = (
    "f6a0bd9390565f7bd852b451e11b7384b1628c24caba02865b1ec94c1e263026"
)
PRIMARY_ARTIFACT_ID = 8838967644
PRIMARY_ARTIFACT_API_DIGEST = (
    "sha256:7241da6013653e96337c540d3670bed69c04454002f3e7d315a95e9c8e197615"
)
UTILITY_ARTIFACT_ID = 8839094646
UTILITY_ARTIFACT_NAME = "gold-full-artifacts"
UTILITY_ARTIFACT_API_DIGEST = (
    "sha256:1ea221c8bb77313ac0fddfe7703496d191d666c0555fdb5d9b5d1d9f3e94e2f4"
)
UTILITY_FIXTURE_SHA256 = (
    "b04f721d789226723066b3d6ae70e4ab2a3fa17c825ef1d0e04d7d779571982b"
)
GOLD_ARTIFACT_ID = 8839160190
GOLD_ARTIFACT_API_DIGEST = (
    "sha256:4fc12773c6410df3e6b4a1b1ded43c14a4ef2c84d013f09ec42d3ba7df1c7988"
)
GOLD_EVIDENCE_MANIFEST_PATH = (
    "evidence/v5.0.1/robustness/evidence_manifest.json"
)
GOLD_INDEX_PATH = "evidence/v5.0.1/robustness/robustness_index.csv"
GOLD_SUMMARY_PATH = (
    "evidence/v5.0.1/robustness/robustness_summary_merged.json"
)
SRG_METHOD = "conservative_wilson_endpoint_difference"
PRODUCER_BUNDLE_MEMBER = "producer/WhitePaper_Intake_Bundle_v4.zip"
EXPECTED_SEEDS = (7, 11, 23, 42, 101, 1337, 2025, 4096, 8191, 314159)
MAX_ARCHIVE_MEMBERS = 256
MAX_MEMBER_BYTES = 20 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
WILSON_Z = 1.96
DELTA_Z = 1.959963984540054
PRODUCER_CERTIFICATE_NAMES = (
    "branch_amplification__generation_process_certificate.json",
    "branch_amplification__synthetic_quality_certificate.json",
    "branch_amplification__synthetic_validation_certificate.json",
    "branch_intrinsic__generation_process_certificate.json",
    "branch_intrinsic__synthetic_quality_certificate.json",
    "branch_intrinsic__synthetic_validation_certificate.json",
    "data_profiling_certificate_amplification.json",
    "data_profiling_certificate_intrinsic.json",
    "generation_process_certificate.json",
    "hyperparameter_tuning_certificate_amplification.json",
    "hyperparameter_tuning_certificate_intrinsic.json",
    "input_validation_certificate.json",
    "lc11_contract_certificate_amplification.json",
    "lc11_contract_certificate_intrinsic.json",
    "model_certificate_amplification.json",
    "model_certificate_intrinsic.json",
    "regulatory_alignment_certificate.json",
    "synthetic_quality_certificate.json",
    "synthetic_validation_certificate.json",
    "training_convergence_certificate_amplification.json",
    "training_convergence_certificate_intrinsic.json",
)
PRODUCER_INTAKE_FILES = (
    "air_status.json",
    "ece_status.json",
    "eo_status.json",
    "fairness_slices.json",
    "group_confusion.csv",
    "manifest.json",
    "metrics_long.csv",
    "metrics_uncertainty.json",
    "pack_intent.json",
    "regulatory_matrix.csv",
    "run_summary.json",
    "selection_rates.csv",
)
HEX_16 = re.compile(r"^[0-9a-f]{16}$")
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
HEX_128 = re.compile(r"^[0-9a-f]{128}$")
CERT_HASH_EXCLUDED_FIELDS = {
    "certificate_hash",
    "certificate_signature",
    "public_key_fingerprint",
    "signature_algorithm",
    "signed_at",
    "visual_proofs",
}


class VerificationError(ValueError):
    """Raised when companion evidence or identity validation fails."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or name.startswith("/")
        or name.endswith("/")
        or path.is_absolute()
        or "." in path.parts
        or ".." in path.parts
        or "\\" in name
    ):
        raise VerificationError(f"unsafe archive member: {name!r}")
    return name


def _validate_zip_infos(
    infos: list[zipfile.ZipInfo], *, label: str
) -> list[str]:
    _require(
        len(infos) <= MAX_ARCHIVE_MEMBERS,
        f"{label} exceeds {MAX_ARCHIVE_MEMBERS} archive members",
    )
    names: list[str] = []
    total = 0
    for info in infos:
        name = _safe_name(info.filename)
        mode = info.external_attr >> 16
        _require(not stat.S_ISLNK(mode), f"symlink archive member is forbidden: {name}")
        _require(not info.is_dir(), f"directory archive entries are forbidden: {name}")
        _require(
            info.file_size <= MAX_MEMBER_BYTES,
            f"archive member exceeds size limit: {name}",
        )
        total += info.file_size
        _require(
            total <= MAX_TOTAL_UNCOMPRESSED_BYTES,
            f"{label} exceeds total uncompressed size limit",
        )
        if info.file_size:
            _require(info.compress_size > 0, f"invalid compressed size for {name}")
            _require(
                info.file_size / info.compress_size <= MAX_COMPRESSION_RATIO,
                f"archive member exceeds compression-ratio limit: {name}",
            )
        names.append(name)
    _require(len(names) == len(set(names)), f"duplicate {label} archive member")
    return names


class Bundle:
    def __init__(self, path: Path):
        self.path = path
        self._zip: zipfile.ZipFile | None = None
        if path.is_file():
            try:
                self._zip = zipfile.ZipFile(path)
            except (OSError, zipfile.BadZipFile) as exc:
                raise VerificationError(f"invalid companion ZIP: {exc}") from exc
            names = _validate_zip_infos(
                self._zip.infolist(), label="companion"
            )
            self.names = sorted(names)
        elif path.is_dir():
            names = []
            total = 0
            for child in path.rglob("*"):
                if child.is_symlink():
                    raise VerificationError(f"symlink bundle member is forbidden: {child}")
                if child.is_file():
                    size = child.stat().st_size
                    _require(
                        size <= MAX_MEMBER_BYTES,
                        f"bundle member exceeds size limit: {child}",
                    )
                    total += size
                    _require(
                        total <= MAX_TOTAL_UNCOMPRESSED_BYTES,
                        "bundle exceeds total size limit",
                    )
                    names.append(_safe_name(child.relative_to(path).as_posix()))
            _require(
                len(names) <= MAX_ARCHIVE_MEMBERS,
                f"bundle exceeds {MAX_ARCHIVE_MEMBERS} members",
            )
            self.names = sorted(names)
        else:
            raise VerificationError(f"bundle path does not exist: {path}")

    def read(self, name: str) -> bytes:
        _safe_name(name)
        if name not in self.names:
            raise VerificationError(f"missing bundle member: {name}")
        if self._zip is not None:
            return self._zip.read(name)
        return (self.path / name).read_bytes()

    def json(self, name: str) -> dict[str, Any]:
        try:
            value = json.loads(self.read(name).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VerificationError(f"invalid JSON in {name}: {exc}") from exc
        if not isinstance(value, dict):
            raise VerificationError(f"{name} must contain a JSON object")
        return value


def _require(value: bool, message: str) -> None:
    if not value:
        raise VerificationError(message)


def _digest_anchored_bytes(
    bundle: Bundle, name: str, expected_sha256: str
) -> bytes:
    data = bundle.read(name)
    _require(
        _sha256(data) == expected_sha256,
        f"{name} does not match PDF-disclosed SHA-256",
    )
    return data


def _digest_anchored_json(
    bundle: Bundle, name: str, expected_sha256: str
) -> dict[str, Any]:
    data = _digest_anchored_bytes(bundle, name, expected_sha256)
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"invalid JSON in {name}: {exc}") from exc
    _require(isinstance(value, dict), f"{name} must contain a JSON object")
    return value


def _verify_gold_anchors(
    bundle: Bundle,
    *,
    expected_gold_manifest_sha256: str,
    expected_gold_index_sha256: str,
    expected_gold_summary_sha256: str,
) -> dict[str, str]:
    for name, expected in (
        (GOLD_EVIDENCE_MANIFEST_PATH, expected_gold_manifest_sha256),
        (GOLD_INDEX_PATH, expected_gold_index_sha256),
        (GOLD_SUMMARY_PATH, expected_gold_summary_sha256),
    ):
        _digest_anchored_bytes(bundle, name, expected)
    return {
        "gold_evidence_manifest_sha256_expected": (
            expected_gold_manifest_sha256
        ),
        "gold_index_sha256_expected": expected_gold_index_sha256,
        "gold_summary_sha256_expected": expected_gold_summary_sha256,
    }


def _certificate_content(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in CERT_HASH_EXCLUDED_FIELDS
    }


def _certificate_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        _certificate_content(payload), sort_keys=True, separators=(",", ":")
    )
    return _sha256(canonical.encode("utf-8"))


def _verify_file_manifest(bundle: Bundle, manifest: dict[str, Any]) -> None:
    entries = manifest.get("files")
    _require(isinstance(entries, list) and bool(entries), "manifest files list is missing")
    expected_names = {"MANIFEST.json"}
    previous = ""
    for entry in entries:
        _require(isinstance(entry, dict), "manifest file entry must be an object")
        name = str(entry.get("path") or "")
        _safe_name(name)
        _require(name > previous, "manifest file paths must be unique and sorted")
        previous = name
        data = bundle.read(name)
        _require(entry.get("size") == len(data), f"size mismatch for {name}")
        _require(entry.get("sha256") == _sha256(data), f"SHA-256 mismatch for {name}")
        expected_names.add(name)
    _require(set(bundle.names) == expected_names, "bundle members differ from MANIFEST.json")


def _producer_expected_names() -> set[str]:
    names = {f"certificates/{name}" for name in PRODUCER_CERTIFICATE_NAMES}
    names.update(
        {"config/fairness_config.yaml", "config/sap.yaml", "provenance/manifest.json"}
    )
    names.update({f"intake/{name}" for name in PRODUCER_INTAKE_FILES})
    return names


def _verify_original_producer_bundle(bundle: Bundle) -> dict[str, Any]:
    raw = bundle.read(PRODUCER_BUNDLE_MEMBER)
    _require(
        _sha256(raw) == PRIMARY_BUNDLE_SHA256,
        "original producer ZIP digest mismatch",
    )
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise VerificationError(f"invalid original producer ZIP: {exc}") from exc
    with archive:
        names = set(
            _validate_zip_infos(archive.infolist(), label="original producer")
        )
        _require(
            names == _producer_expected_names(),
            "original producer ZIP member inventory mismatch",
        )
        original_manifest = archive.read("intake/manifest.json")
        _require(
            archive.read("provenance/manifest.json") == original_manifest,
            "producer provenance manifest differs from intake manifest",
        )
        try:
            producer_identity = json.loads(original_manifest.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VerificationError(f"invalid original producer manifest: {exc}") from exc
        _require(
            producer_identity.get("source_commit") == PRODUCT_COMMIT,
            "original producer source commit mismatch",
        )
        _require(
            producer_identity.get("commit_sha") == PRODUCT_COMMIT,
            "original producer commit mismatch",
        )

        for name in PRODUCER_CERTIFICATE_NAMES:
            _require(
                archive.read(f"certificates/{name}")
                == bundle.read(f"intake/certificates/{name}"),
                f"consumer certificate differs from producer bytes: {name}",
            )
        for name in ("fairness_config.yaml", "sap.yaml"):
            _require(
                archive.read(f"config/{name}") == bundle.read(f"config/{name}"),
                f"consumer configuration differs from producer bytes: {name}",
            )
        for name in PRODUCER_INTAKE_FILES:
            original = archive.read(f"intake/{name}")
            consumer = bundle.read(f"intake/{name}")
            if name == "manifest.json":
                try:
                    payload = json.loads(consumer.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise VerificationError(f"invalid consumer intake manifest: {exc}") from exc
                stamp = payload.pop("whitepaper_consumer", None)
                _require(isinstance(stamp, dict), "whitepaper consumer stamp is missing")
                consumer = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
            _require(
                original == consumer,
                f"consumer intake differs from producer bytes: {name}",
            )
    return {
        "producer_bundle_sha256": PRIMARY_BUNDLE_SHA256,
        "producer_bundle_files": len(names),
    }


def _verify_identity(bundle: Bundle, manifest: dict[str, Any]) -> None:
    _require(
        manifest.get("schema_version") == "flbsa.whitepaper_companion.v1",
        "unsupported companion manifest schema",
    )
    product = manifest.get("product") or {}
    _require(product.get("tag") == PRODUCT_TAG, "wrong product tag")
    _require(product.get("commit") == PRODUCT_COMMIT, "wrong product commit")
    _require(product.get("tag_object") == PRODUCT_TAG_OBJECT, "wrong product tag object")
    paper = manifest.get("whitepaper") or {}
    _require(HEX_40.fullmatch(str(paper.get("commit") or "")) is not None, "bad paper commit")
    _require(paper.get("document_version") == "WP-5.0.1-candidate.3", "bad document version")
    _require(paper.get("publication_status") == "candidate_not_published", "bad publication status")
    evidence = manifest.get("evidence") or {}
    _require(
        evidence.get("primary_bundle_member") == PRODUCER_BUNDLE_MEMBER,
        "producer bundle member mismatch",
    )
    _require(
        evidence.get("primary_bundle_sha256") == PRIMARY_BUNDLE_SHA256,
        "producer bundle manifest digest mismatch",
    )

    identity = bundle.json(
        "evidence/v5.0.1/publication/evidence_identity.json"
    )
    _require(
        identity.get("schema_version")
        == "flbsa.whitepaper_evidence_identity.v1",
        "unsupported evidence identity schema",
    )
    identity_product = identity.get("product") or {}
    for field, expected in (
        ("tag", PRODUCT_TAG),
        ("tag_object", PRODUCT_TAG_OBJECT),
        ("commit", PRODUCT_COMMIT),
        ("repository", "equilens-labs/fl-bsa"),
    ):
        _require(
            identity_product.get(field) == expected,
            f"evidence identity product {field} mismatch",
        )
    workflow = identity.get("producer_workflow") or {}
    for field, expected in (
        ("repository", "equilens-labs/fl-bsa"),
        ("name", "release-evidence.yml"),
        ("run_id", int(PRODUCT_RUN_ID)),
        ("attempt", 1),
        ("head_commit", PRODUCT_COMMIT),
    ):
        _require(
            workflow.get(field) == expected,
            f"evidence identity workflow {field} mismatch",
        )
    primary_identity = identity.get("primary_intake") or {}
    for field, expected in (
        ("artifact_id", PRIMARY_ARTIFACT_ID),
        ("artifact_name", "wp-intake-bundle-v4-1"),
        ("artifact_api_digest", PRIMARY_ARTIFACT_API_DIGEST),
        ("bundle_sha256", PRIMARY_BUNDLE_SHA256),
    ):
        _require(
            primary_identity.get(field) == expected,
            f"primary intake identity {field} mismatch",
        )
    utility_identity = identity.get("utility_source") or {}
    for field, expected in (
        ("artifact_id", UTILITY_ARTIFACT_ID),
        ("artifact_name", UTILITY_ARTIFACT_NAME),
        ("artifact_api_digest", UTILITY_ARTIFACT_API_DIGEST),
        ("fixture_sha256", UTILITY_FIXTURE_SHA256),
    ):
        _require(
            utility_identity.get(field) == expected,
            f"utility artifact identity {field} mismatch",
        )
    gold_identity = identity.get("gold_robustness") or {}
    for field, expected in (
        ("artifact_id", GOLD_ARTIFACT_ID),
        (
            "artifact_name",
            f"gold-robustness-{PRODUCT_COMMIT}-{PRODUCT_RUN_ID}",
        ),
        ("artifact_api_digest", GOLD_ARTIFACT_API_DIGEST),
    ):
        _require(
            gold_identity.get(field) == expected,
            f"Gold artifact identity {field} mismatch",
        )
    for field, path in (
        (
            "evidence_manifest_sha256",
            "evidence/v5.0.1/robustness/evidence_manifest.json",
        ),
        (
            "index_sha256",
            "evidence/v5.0.1/robustness/robustness_index.csv",
        ),
        (
            "summary_sha256",
            "evidence/v5.0.1/robustness/robustness_summary_merged.json",
        ),
    ):
        _require(
            gold_identity.get(field) == _sha256(bundle.read(path)),
            f"Gold artifact identity {field} mismatch",
        )
    _require(
        gold_identity.get("source_summary_sha256")
        == GOLD_SOURCE_SUMMARY_SHA256,
        "Gold source summary identity mismatch",
    )
    _require(
        gold_identity.get("summary_projection") == GOLD_SUMMARY_PROJECTION,
        "Gold summary projection identity mismatch",
    )
    identity_claims = identity.get("claim_boundary") or {}
    _require(
        identity_claims
        == {
            "customer_evidence_disposition": "characterization_only",
            "customer_evidence_eligible": False,
            "publication_status": "candidate_not_published",
        },
        "evidence identity claim boundary mismatch",
    )

    intake = bundle.json("intake/manifest.json")
    _require(intake.get("source_commit") == PRODUCT_COMMIT, "intake source commit mismatch")
    _require(intake.get("commit_sha") == PRODUCT_COMMIT, "intake commit mismatch")
    consumer = intake.get("whitepaper_consumer") or {}
    producer = consumer.get("producer") or {}
    _require(producer.get("run_id") == PRODUCT_RUN_ID, "producer run mismatch")
    _require(producer.get("head_sha") == PRODUCT_COMMIT, "producer head mismatch")
    _require(producer.get("bundle_sha256") == PRIMARY_BUNDLE_SHA256, "intake bundle mismatch")
    _require(producer.get("workflow") == "release-evidence.yml", "producer workflow mismatch")

    pack = bundle.json("intake/pack_intent.json")
    _require(pack.get("evidence_grade") is False, "pack evidence grade must be false")
    _require(pack.get("certificate_signing_expected") is False, "pack signing expectation must be false")
    snapshot = bundle.json("intake/archive/v5.0.1-release-30765888408.json")
    claims = snapshot.get("claims") or {}
    _require(claims.get("customer_evidence_eligible") is False, "customer evidence flag must be false")
    _require(
        claims.get("customer_evidence_disposition") == "characterization_only",
        "customer evidence disposition mismatch",
    )
    _require(claims.get("publication_status") == "candidate_not_published", "snapshot publication status mismatch")
    release_disposition = bundle.json(
        "evidence/v5.0.1/robustness/robustness_gate_disposition.json"
    )
    _require(
        release_disposition.get("customer_evidence_eligible") is False,
        "release customer-evidence flag must be false",
    )
    _require(
        release_disposition.get("promotion_evidence_eligible") is False,
        "release promotion flag must be false",
    )


def _number(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{label} must be numeric",
    )
    result = float(value)
    _require(math.isfinite(result), f"{label} must be finite")
    return result


def _close(actual: Any, expected: float, label: str) -> None:
    value = _number(actual, label)
    _require(
        math.isclose(value, expected, rel_tol=1e-10, abs_tol=1e-300),
        f"{label} mismatch: expected {expected!r}, got {value!r}",
    )


def _wilson(approved: int, count: int) -> tuple[float, float]:
    proportion = approved / count
    denominator = 1 + WILSON_Z**2 / count
    center = (proportion + WILSON_Z**2 / (2 * count)) / denominator
    half_width = (
        WILSON_Z
        * math.sqrt(
            proportion * (1 - proportion) / count
            + WILSON_Z**2 / (4 * count**2)
        )
        / denominator
    )
    return center - half_width, center + half_width


def _two_proportion_p_value(
    protected_approved: int,
    protected_n: int,
    reference_approved: int,
    reference_n: int,
) -> float:
    protected_rate = protected_approved / protected_n
    reference_rate = reference_approved / reference_n
    pooled = (protected_approved + reference_approved) / (
        protected_n + reference_n
    )
    standard_error = math.sqrt(
        pooled * (1 - pooled) * (1 / protected_n + 1 / reference_n)
    )
    _require(standard_error > 0, "two-proportion test has zero standard error")
    z_score = (protected_rate - reference_rate) / standard_error
    return math.erfc(abs(z_score) / math.sqrt(2))


def _verify_fairness_row(row: dict[str, Any], label: str) -> tuple[float, float]:
    counts = row.get("counts") or {}
    try:
        reference_n = int(counts["ref_n"])
        protected_n = int(counts["prot_n"])
        reference_approved = int(counts["ref_approved"])
        protected_approved = int(counts["prot_approved"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VerificationError(f"invalid fairness counts in {label}") from exc
    _require(
        0 <= reference_approved <= reference_n and reference_n > 0,
        f"invalid reference counts in {label}",
    )
    _require(
        0 <= protected_approved <= protected_n and protected_n > 0,
        f"invalid protected counts in {label}",
    )
    reference_rate = reference_approved / reference_n
    protected_rate = protected_approved / protected_n
    selection_rates = row.get("selection_rates") or {}
    reference = selection_rates.get("ref") or {}
    protected = selection_rates.get("prot") or {}
    _close(reference.get("p"), reference_rate, f"{label} reference rate")
    _close(protected.get("p"), protected_rate, f"{label} protected rate")
    reference_interval = _wilson(reference_approved, reference_n)
    protected_interval = _wilson(protected_approved, protected_n)
    for index, expected in enumerate(reference_interval):
        _close(
            (reference.get("ci95") or [None, None])[index],
            expected,
            f"{label} reference Wilson endpoint {index}",
        )
    for index, expected in enumerate(protected_interval):
        _close(
            (protected.get("ci95") or [None, None])[index],
            expected,
            f"{label} protected Wilson endpoint {index}",
        )

    _require(reference_rate > 0 and protected_rate > 0, f"AIR undefined in {label}")
    air_point = protected_rate / reference_rate
    log_variance = (1 - protected_rate) / (
        protected_n * protected_rate
    ) + (1 - reference_rate) / (reference_n * reference_rate)
    air_interval = (
        air_point * math.exp(-DELTA_Z * math.sqrt(log_variance)),
        air_point * math.exp(DELTA_Z * math.sqrt(log_variance)),
    )
    p_value = _two_proportion_p_value(
        protected_approved, protected_n, reference_approved, reference_n
    )
    air = row.get("air") or {}
    _require(air.get("method") == "wilson+delta", f"wrong AIR method in {label}")
    _close(air.get("point"), air_point, f"{label} AIR point")
    for index, expected in enumerate(air_interval):
        _close(
            (air.get("ci95") or [None, None])[index],
            expected,
            f"{label} AIR endpoint {index}",
        )
    _close(air.get("p_value"), p_value, f"{label} AIR p-value")

    srg_point = protected_rate - reference_rate
    srg_interval = (
        protected_interval[0] - reference_interval[1],
        protected_interval[1] - reference_interval[0],
    )
    srg = row.get("srg") or {}
    _require(srg.get("method") == SRG_METHOD, f"wrong SRG method in {label}")
    _close(srg.get("point"), srg_point, f"{label} SRG point")
    for index, expected in enumerate(srg_interval):
        _close(
            (srg.get("ci95") or [None, None])[index],
            expected,
            f"{label} SRG endpoint {index}",
        )
    _close(srg.get("p_value"), p_value, f"{label} SRG p-value")
    _close(srg.get("p_value_adjusted"), p_value, f"{label} SRG adjusted p-value")
    _require(
        srg.get("p_value_adjustment") == "none",
        f"wrong SRG p-value adjustment in {label}",
    )
    _require(
        row.get("p_value_method") == "two_proportion_z_test",
        f"wrong p-value method in {label}",
    )
    _close(row.get("confidence_level"), 0.95, f"{label} confidence level")
    return air_point, p_value


def _selection_rate_rows(bundle: Bundle) -> dict[tuple[str, str], tuple[int, int]]:
    text = bundle.read("intake/selection_rates.csv").decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    _require(len(rows) == 7, "selection-rate row count mismatch")
    result: dict[tuple[str, str], tuple[int, int]] = {}
    run_ids: set[str] = set()
    for row in rows:
        key = (str(row.get("attribute") or ""), str(row.get("group") or ""))
        _require(key not in result, f"duplicate selection-rate row: {key}")
        try:
            selected = int(str(row.get("selected") or ""))
            count = int(str(row.get("n") or ""))
        except ValueError as exc:
            raise VerificationError(f"invalid selection-rate counts for {key}") from exc
        _require(0 <= selected <= count and count > 0, f"invalid counts for {key}")
        result[key] = (selected, count)
        run_ids.add(str(row.get("run_id") or ""))
    _require(len(run_ids) == 1, "selection-rate rows span multiple runs")
    return result


def _verify_fairness(bundle: Bundle) -> dict[str, int]:
    slices = bundle.json("intake/fairness_slices.json")
    _require(slices.get("attribute") == "gender", "gender slices missing")
    _close(
        slices.get("air_threshold"),
        INTERNAL_AIR_SCREEN,
        "AIR screening threshold",
    )
    slice_rows = slices.get("slices") or {}
    _require(
        set(slice_rows) == {"historical", "amplification", "intrinsic"},
        "fairness slice inventory mismatch",
    )
    for name, row in slice_rows.items():
        _, p_value = _verify_fairness_row(row, f"gender {name}")
        air = row.get("air") or {}
        _close(
            air.get("p_value_adjusted"),
            p_value,
            f"gender {name} adjusted p-value",
        )
        _require(
            air.get("p_value_adjustment") == "none",
            f"wrong gender p-value adjustment in {name}",
        )

    uncertainty = bundle.json("intake/metrics_uncertainty.json")
    fairness = uncertainty.get("fairness_uncertainty") or {}
    _require(set(fairness) == {"gender", "race"}, "uncertainty attribute inventory mismatch")
    gender = fairness.get("gender") or {}
    _, gender_p = _verify_fairness_row(gender, "gender uncertainty")
    _close(
        (gender.get("air") or {}).get("p_value_adjusted"),
        gender_p,
        "gender uncertainty adjusted p-value",
    )

    observed = _selection_rate_rows(bundle)
    gender_counts = gender.get("counts") or {}
    _require(
        observed.get(("gender", "male"))
        == (gender_counts.get("ref_approved"), gender_counts.get("ref_n")),
        "male selection-rate counts mismatch",
    )
    _require(
        observed.get(("gender", "female"))
        == (gender_counts.get("prot_approved"), gender_counts.get("prot_n")),
        "female selection-rate counts mismatch",
    )

    race = fairness.get("race") or {}
    _require(race.get("configured_reference_group") == "white", "wrong configured race reference")
    _require(race.get("reference_group") == "black", "wrong effective race reference")
    _require(
        race.get("reference_group_selection_policy") == "highest_selection_rate_four_fifths",
        "wrong race reference policy",
    )
    race_observed = {
        group: values for (attribute, group), values in observed.items() if attribute == "race"
    }
    _require(
        set(race_observed) == {"asian", "black", "hispanic", "other", "white"},
        "race selection-rate group inventory mismatch",
    )
    rates = {
        group: selected / count for group, (selected, count) in race_observed.items()
    }
    effective_reference = max(rates, key=rates.get)
    minimum_rate_group = min(rates, key=rates.get)
    _require(effective_reference == "black", "race reference is not the highest-rate group")
    rate_range = race.get("selection_rate_range") or {}
    _require(rate_range.get("max_group") == effective_reference, "race maximum-rate group mismatch")
    _require(rate_range.get("min_group") == minimum_rate_group, "race minimum-rate group mismatch")
    _close(rate_range.get("max_rate"), rates[effective_reference], "race maximum rate")
    _close(rate_range.get("min_rate"), rates[minimum_rate_group], "race minimum rate")

    pairs = race.get("pairs") or {}
    _require(set(pairs) == set(race_observed) - {effective_reference}, "race pair inventory mismatch")
    raw_p_values: dict[str, float] = {}
    air_points: dict[str, float] = {}
    reference_counts = race_observed[effective_reference]
    for name, row in pairs.items():
        counts = row.get("counts") or {}
        _require(
            (counts.get("ref_approved"), counts.get("ref_n")) == reference_counts,
            f"race reference counts mismatch for {name}",
        )
        _require(
            (counts.get("prot_approved"), counts.get("prot_n")) == race_observed[name],
            f"race protected counts mismatch for {name}",
        )
        air_points[name], raw_p_values[name] = _verify_fairness_row(
            row, f"race {name}"
        )

    adjusted: dict[str, float] = {}
    running = 0.0
    ordered = sorted(raw_p_values.items(), key=lambda item: (item[1], item[0]))
    for index, (name, p_value) in enumerate(ordered):
        running = max(running, (len(ordered) - index) * p_value)
        adjusted[name] = min(1.0, running)
    for name, expected in adjusted.items():
        air = pairs[name].get("air") or {}
        _close(air.get("p_value_adjusted"), expected, f"race {name} Holm p-value")
        _require(
            air.get("p_value_adjustment") == "holm_bonferroni",
            f"wrong race AIR p-value adjustment for {name}",
        )
    _require(
        race.get("worst_case_pair") == min(air_points, key=air_points.get),
        "race worst-case pair mismatch",
    )
    counts = [count for _, count in race_observed.values()]
    observed_policy = race.get("observed") or {}
    _require(observed_policy.get("total_n") == sum(counts), "race total count mismatch")
    _require(observed_policy.get("min_group_n") == min(counts), "race minimum count mismatch")
    _close(
        observed_policy.get("min_group_pct"),
        min(counts) / sum(counts),
        "race minimum group share",
    )
    display_policy = ((race.get("policy") or {}).get("display_race_in_main_pdf") or {})
    display_expected = (
        min(counts) >= int(display_policy.get("min_group_n") or 0)
        and min(counts) / sum(counts) >= float(display_policy.get("min_group_pct") or 0)
    )
    _require(
        race.get("display_in_main_pdf") is display_expected,
        "race display policy mismatch",
    )
    return {"fairness_surfaces_recomputed": 3 + 1 + len(pairs)}


def _assert_single_rooted_graph(predecessors: dict[str, str]) -> tuple[str, int]:
    roots = [node for node, previous in predecessors.items() if not previous]
    _require(len(roots) == 1, "certificate graph must have exactly one root")
    root = roots[0]
    links = 0
    for start in predecessors:
        current = start
        visited: set[str] = set()
        while True:
            _require(
                current in predecessors,
                f"unresolved predecessor hash for certificate {start}",
            )
            previous = predecessors[current]
            if not previous:
                break
            _require(current not in visited, "certificate graph contains a cycle")
            visited.add(current)
            current = previous
        _require(current == root, "certificate does not resolve to the common root")
        if start != root:
            links += 1
    return root, links


def _verify_certificates(bundle: Bundle) -> dict[str, int]:
    names = [
        name
        for name in bundle.names
        if name.startswith("intake/certificates/") and name.endswith(".json")
    ]
    _require(len(names) == 21, f"expected 21 certificates, found {len(names)}")
    node_payloads: dict[str, dict[str, Any]] = {}
    alias_files = 0
    file_links = 0
    for name in names:
        payload = bundle.json(name)
        stored = str(payload.get("certificate_hash") or "")
        _require(HEX_64.fullmatch(stored) is not None, f"invalid stored certificate hash in {name}")
        _require(_certificate_hash(payload) == stored, f"certificate hash mismatch in {name}")
        _require(payload.get("signature_algorithm") == "ECDSA-P256-SHA256", f"signature metadata missing in {name}")
        _require(HEX_16.fullmatch(str(payload.get("public_key_fingerprint") or "")) is not None, f"bad key fingerprint in {name}")
        _require(HEX_128.fullmatch(str(payload.get("certificate_signature") or "")) is not None, f"bad signature encoding in {name}")
        if payload.get("previous_certificate_hash"):
            file_links += 1
        if stored in node_payloads:
            _require(
                _certificate_content(payload)
                == _certificate_content(node_payloads[stored]),
                f"canonical-content alias mismatch in {name}",
            )
            alias_files += 1
        else:
            node_payloads[stored] = payload
    predecessors = {
        str(payload["certificate_hash"]): str(
            payload.get("previous_certificate_hash") or ""
        )
        for payload in node_payloads.values()
    }
    _, traversed = _assert_single_rooted_graph(predecessors)
    _require(
        traversed == len(predecessors) - 1,
        "certificate graph traversal did not cover every non-root certificate",
    )
    return {
        "certificate_files": len(names),
        "certificate_unique_nodes": len(predecessors),
        "certificate_alias_files": alias_files,
        "internal_links": file_links,
        "certificate_graph_edges": len(predecessors) - 1,
        "roots": 1,
        "graph_nodes_traversed": len(predecessors),
    }


def _computed_band(
    values: list[float], *, sample_stdev: bool
) -> dict[str, float | int]:
    _require(bool(values), "cannot aggregate an empty numeric series")
    return {
        "count": len(values),
        "min": min(values),
        "mean": statistics.mean(values),
        "max": max(values),
        "stdev": (
            statistics.stdev(values)
            if sample_stdev and len(values) > 1
            else statistics.pstdev(values)
            if len(values) > 1
            else 0.0
        ),
    }


def _verify_band(
    stored: dict[str, Any],
    values: list[float],
    label: str,
    *,
    sample_stdev: bool,
) -> None:
    computed = _computed_band(values, sample_stdev=sample_stdev)
    _require(stored.get("count") == computed["count"], f"{label} count mismatch")
    for field in ("min", "mean", "max", "stdev"):
        _close(stored.get(field), float(computed[field]), f"{label} {field}")


def _dotted(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for component in path.split("."):
        if not isinstance(current, dict) or component not in current:
            return None
        current = current[component]
    return current


def _verify_robustness(bundle: Bundle) -> dict[str, int]:
    robustness = bundle.json("evidence/v5.0.1/robustness/robustness_summary_merged.json")
    _require(robustness.get("schema_version") == "gold.robustness.v1", "bad robustness schema")
    _require(robustness.get("complete") is True, "robustness evidence is incomplete")
    _require(
        tuple(robustness.get("planned_seeds") or ()) == EXPECTED_SEEDS,
        "robustness planned seed set mismatch",
    )
    _require(
        tuple(robustness.get("completed_seeds") or ()) == EXPECTED_SEEDS,
        "robustness completed seed set mismatch",
    )
    release_gate = robustness.get("release_gate") or {}
    _require(release_gate.get("git_sha") == PRODUCT_COMMIT, "robustness product mismatch")
    _require(release_gate.get("release_tag") == PRODUCT_TAG, "robustness tag mismatch")
    _require(str(release_gate.get("github_run_id")) == PRODUCT_RUN_ID, "robustness run mismatch")
    _require(release_gate.get("customer_evidence_eligible") is False, "robustness customer flag mismatch")
    _require(release_gate.get("promotion_evidence_eligible") is False, "robustness promotion flag mismatch")

    scenarios = robustness.get("scenarios") or {}
    expected_scenarios = {"balanced", "gender_bias", "outliers", "security"}
    _require(set(scenarios) == expected_scenarios, "wrong robustness scenarios")
    prefix_to_name = {
        "01_balanced": "balanced",
        "02_gender_bias": "gender_bias",
        "03_outliers": "outliers",
        "04_security": "security",
    }
    index_text = bundle.read(
        "evidence/v5.0.1/robustness/robustness_index.csv"
    ).decode("utf-8")
    index_rows = list(csv.DictReader(io.StringIO(index_text)))
    _require(len(index_rows) == 40, "robustness index row count mismatch")
    index: dict[tuple[str, int], dict[str, str]] = {}
    evidence_hashes: set[str] = set()
    for row in index_rows:
        scenario = prefix_to_name.get(str(row.get("scenario") or ""))
        _require(scenario is not None, "unknown robustness index scenario")
        try:
            seed = int(str(row.get("seed") or ""))
        except ValueError as exc:
            raise VerificationError("invalid robustness index seed") from exc
        key = (scenario, seed)
        _require(key not in index, f"duplicate robustness index row: {key}")
        digest = str(row.get("evidence_sha256") or "")
        _require(HEX_64.fullmatch(digest) is not None, f"bad robustness evidence hash: {key}")
        _require(digest not in evidence_hashes, f"duplicate robustness evidence hash: {key}")
        evidence_hashes.add(digest)
        index[key] = row

    aggregate_bands = 0
    for name, scenario in scenarios.items():
        seeds = scenario.get("seeds") or {}
        _require(
            {int(seed) for seed in seeds} == set(EXPECTED_SEEDS),
            f"robustness seed inventory mismatch for {name}",
        )
        for seed in EXPECTED_SEEDS:
            result = seeds.get(str(seed)) or {}
            _require(result.get("seed") == seed, f"robustness seed label mismatch for {name}/{seed}")
            _require(result.get("status") == "pass", f"robustness non-pass for {name}/{seed}")
            expected_compliance = name != "gender_bias"
            _require(
                result.get("compliant") is expected_compliance,
                f"robustness scenario compliance mismatch for {name}/{seed}",
            )
            _require(result.get("metrics_partial") is False, f"robustness metrics partial for {name}/{seed}")
            indexed = index.get((name, seed)) or {}
            _require(indexed.get("status") == "pass", f"robustness index non-pass for {name}/{seed}")
            _require(
                indexed.get("compliance_compliant")
                == ("True" if expected_compliance else "False"),
                f"robustness index compliance mismatch for {name}/{seed}",
            )
            for field in ("di", "spd", "max_demographic_parity_difference"):
                try:
                    indexed_value = float(str(indexed.get(field) or ""))
                except ValueError as exc:
                    raise VerificationError(
                        f"invalid robustness index number for {name}/{seed}/{field}"
                    ) from exc
                _close(indexed_value, _number(result.get(field), f"{name}/{seed} {field}"), f"index {name}/{seed} {field}")
            _require(
                indexed.get("max_demographic_parity_attribute")
                == result.get("max_demographic_parity_attribute"),
                f"index attribute mismatch for {name}/{seed}",
            )

        aggregates = scenario.get("aggregates") or {}
        _require(aggregates.get("planned_seed_count") == 10, f"wrong planned seed count for {name}")
        _require(aggregates.get("observed_seed_count") == 10, f"wrong seed count for {name}")
        _require(aggregates.get("missing_seed_count") == 0, f"missing robustness seeds for {name}")
        _require(aggregates.get("pass_count") == 10, f"robustness failures in {name}")
        _require(aggregates.get("fail_count") == 0, f"robustness failures in {name}")
        _require(aggregates.get("other_status_count") == 0, f"unexpected robustness status in {name}")
        numeric_bands = aggregates.get("numeric_bands") or {}
        _require("di" in numeric_bands, f"DI band missing for {name}")
        for path, stored in numeric_bands.items():
            _require(isinstance(stored, dict), f"invalid aggregate band {name}/{path}")
            values = []
            for seed in EXPECTED_SEEDS:
                value = _dotted(seeds[str(seed)], path)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    finite = float(value)
                    _require(math.isfinite(finite), f"non-finite robustness metric {name}/{seed}/{path}")
                    values.append(finite)
            _verify_band(
                stored,
                values,
                f"robustness {name}/{path}",
                sample_stdev=False,
            )
            aggregate_bands += 1
    _require(set(index) == {(name, seed) for name in expected_scenarios for seed in EXPECTED_SEEDS}, "robustness index coverage mismatch")
    return {
        "robustness_scenarios": len(scenarios),
        "robustness_runs": len(index),
        "robustness_aggregate_bands_recomputed": aggregate_bands,
    }


def _verify_utility(
    bundle: Bundle, expected_utility_sha256: str
) -> dict[str, int]:
    utility = _digest_anchored_json(
        bundle, UTILITY_SUMMARY_PATH, expected_utility_sha256
    )
    _require(
        utility.get("schema_version") == "flbsa.whitepaper_fixture_utility.v2",
        "unsupported utility schema",
    )
    product = utility.get("product") or {}
    _require(product.get("commit") == PRODUCT_COMMIT, "utility product mismatch")
    _require(product.get("tag") == PRODUCT_TAG, "utility tag mismatch")
    _require(utility.get("claim_scope") == "synthetic_fixture_tstr_characterization_only", "utility claim scope mismatch")
    _require(utility.get("utility_established") is False, "utility claim boundary mismatch")
    source = utility.get("source") or {}
    compressed = bundle.read(str(source.get("fixture") or ""))
    _require(_sha256(compressed) == source.get("fixture_sha256_gzip"), "utility fixture gzip hash mismatch")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as handle:
            uncompressed = handle.read(MAX_MEMBER_BYTES + 1)
    except OSError as exc:
        raise VerificationError(f"invalid utility fixture gzip: {exc}") from exc
    _require(len(uncompressed) <= MAX_MEMBER_BYTES, "utility fixture exceeds decompression limit")
    _require(_sha256(uncompressed) == source.get("fixture_sha256_uncompressed"), "utility fixture raw hash mismatch")
    try:
        fixture_rows = sum(
            1
            for _ in csv.DictReader(
                io.StringIO(uncompressed.decode("utf-8"))
            )
        )
    except UnicodeDecodeError as exc:
        raise VerificationError(f"invalid utility fixture text: {exc}") from exc
    _require(fixture_rows == source.get("rows") == 5000, "utility fixture row count mismatch")
    _require(source.get("synthetic_fixture_only") is True, "utility fixture scope mismatch")

    source_manifest = bundle.json("evidence/v5.0.1/utility/source_manifest.json")
    _require(
        source_manifest.get("schema_version")
        == "flbsa.whitepaper_utility_source.v1",
        "unsupported utility source schema",
    )
    manifest_product = source_manifest.get("product") or {}
    _require(manifest_product.get("commit") == PRODUCT_COMMIT, "utility source product mismatch")
    _require(manifest_product.get("tag") == PRODUCT_TAG, "utility source tag mismatch")
    _require(manifest_product.get("tag_object") == PRODUCT_TAG_OBJECT, "utility source tag object mismatch")
    artifact = source_manifest.get("artifact") or {}
    for field, expected in (
        ("repository", "equilens-labs/fl-bsa"),
        ("workflow", "release-evidence.yml"),
        ("run_id", int(PRODUCT_RUN_ID)),
        ("run_attempt", 1),
        ("artifact_id", str(UTILITY_ARTIFACT_ID)),
        ("name", UTILITY_ARTIFACT_NAME),
        ("api_digest", UTILITY_ARTIFACT_API_DIGEST),
    ):
        _require(
            artifact.get(field) == expected,
            f"utility source artifact {field} mismatch",
        )
    fixture_manifest = source_manifest.get("fixture") or {}
    _require(
        fixture_manifest.get("path_in_artifact")
        == "artifacts/gold/20260802T203945Z/01_balanced/original_data.csv",
        "utility source fixture path mismatch",
    )
    _require(
        fixture_manifest.get("rows") == source.get("rows") == 5000,
        "utility source fixture row count mismatch",
    )
    _require(
        fixture_manifest.get("synthetic_fixture_only") is True,
        "utility source fixture scope mismatch",
    )
    _require(fixture_manifest.get("gzip_sha256") == source.get("fixture_sha256_gzip"), "utility source gzip hash mismatch")
    _require(fixture_manifest.get("sha256") == source.get("fixture_sha256_uncompressed"), "utility source raw hash mismatch")

    study = utility.get("study") or {}
    _require(
        tuple(study.get("generation_seeds") or ()) == EXPECTED_SEEDS,
        "utility seed plan mismatch",
    )
    _require(study.get("train_rows") == 3500, "utility train row count mismatch")
    _require(study.get("test_rows") == 1500, "utility test row count mismatch")
    _require(
        study.get("train_rows") == study.get("generated_rows_per_seed"),
        "utility sample-size parity mismatch",
    )
    baseline = utility.get("real_train_baseline") or {}
    baseline_auc = _number(baseline.get("roc_auc"), "utility baseline ROC AUC")
    baseline_auc_skill = baseline_auc - 0.5
    _require(baseline_auc_skill > 0, "utility baseline ROC AUC has no skill above chance")
    _require(
        study.get("roc_auc_skill_retention_definition")
        == "(synthetic_roc_auc - 0.5) / (real_train_baseline_roc_auc - 0.5)",
        "utility skill-retention definition mismatch",
    )
    results = utility.get("synthetic_train_results") or []
    _require(isinstance(results, list) and len(results) == 10, "utility seed results incomplete")
    by_seed: dict[int, dict[str, Any]] = {}
    generated_hashes: set[str] = set()
    for result in results:
        _require(isinstance(result, dict), "utility seed result must be an object")
        seed = result.get("seed")
        _require(seed in EXPECTED_SEEDS and seed not in by_seed, "utility seed result inventory mismatch")
        _require(result.get("generated_rows") == 3500, f"utility generated rows mismatch for seed {seed}")
        generated_hash = str(result.get("generated_sha256") or "")
        _require(HEX_64.fullmatch(generated_hash) is not None, f"bad utility generated hash for seed {seed}")
        _require(generated_hash not in generated_hashes, f"duplicate utility generated hash for seed {seed}")
        generated_hashes.add(generated_hash)
        retention = _number(
            result.get("roc_auc_skill_retention"),
            f"utility skill retention seed {seed}",
        )
        auc = _number((result.get("metrics") or {}).get("roc_auc"), f"utility ROC AUC seed {seed}")
        _close(
            retention,
            (auc - 0.5) / baseline_auc_skill,
            f"utility skill retention seed {seed}",
        )
        by_seed[int(seed)] = result
    _require(set(by_seed) == set(EXPECTED_SEEDS), "utility completed seed set mismatch")

    bands = utility.get("synthetic_train_bands") or {}
    metric_names = set((results[0].get("metrics") or {}))
    _require(
        set(bands) == metric_names | {"roc_auc_skill_retention"},
        "utility band inventory mismatch",
    )
    for metric in sorted(metric_names):
        values = [
            _number((by_seed[seed].get("metrics") or {}).get(metric), f"utility {metric} seed {seed}")
            for seed in EXPECTED_SEEDS
        ]
        _verify_band(
            bands.get(metric) or {},
            values,
            f"utility {metric}",
            sample_stdev=True,
        )
    retention_values = [
        _number(
            by_seed[seed].get("roc_auc_skill_retention"),
            f"utility skill retention seed {seed}",
        )
        for seed in EXPECTED_SEEDS
    ]
    _verify_band(
        bands.get("roc_auc_skill_retention") or {},
        retention_values,
        "utility ROC AUC skill retention",
        sample_stdev=True,
    )
    return {
        "utility_seeds": len(results),
        "utility_bands_recomputed": len(bands),
        "utility_fixture_rows": fixture_rows,
        "utility_below_chance_seeds": sum(
            _number(
                (by_seed[seed].get("metrics") or {}).get("roc_auc"),
                f"utility ROC AUC seed {seed}",
            )
            < 0.5
            for seed in EXPECTED_SEEDS
        ),
    }


def _verify_robustness_and_utility(
    bundle: Bundle, expected_utility_sha256: str
) -> dict[str, Any]:
    return {
        **_verify_robustness(bundle),
        **_verify_utility(bundle, expected_utility_sha256),
    }


def _characterization_screen_relation(
    point: float, lower: float, upper: float, screen: float
) -> tuple[str, str]:
    point_relation = "at/above" if point >= screen else "below"
    if upper < screen:
        interval_relation = "entirely below"
    elif lower >= screen:
        interval_relation = "entirely above"
    else:
        interval_relation = "crosses"
    return point_relation, interval_relation


def _characterization_quality(
    certificate: dict[str, Any], branch: str
) -> dict[str, Any]:
    statistical = certificate.get("statistical_comparison") or {}
    correlation = certificate.get("correlation_analysis") or {}
    demographic = certificate.get("demographic_alignment") or {}
    privacy = certificate.get("privacy_metrics") or {}
    return {
        "branch": branch,
        "overall_quality_score": _number(
            certificate.get("overall_quality_score"), f"{branch} quality"
        ),
        "quality_threshold": _number(
            certificate.get("quality_threshold_used"), f"{branch} threshold"
        ),
        "quality_threshold_met": certificate.get("quality_threshold_met") is True,
        "distribution_score": _number(
            statistical.get("overall_distribution_score"),
            f"{branch} distribution",
        ),
        "correlation_preservation_score": _number(
            correlation.get("correlation_preservation_score"),
            f"{branch} correlation",
        ),
        "max_correlation_difference": _number(
            correlation.get("max_correlation_difference"),
            f"{branch} max correlation difference",
        ),
        "demographic_max_drift_pp": _number(
            demographic.get("max_abs_pp_drift"), f"{branch} demographic drift"
        ),
        "privacy_heuristic_score": _number(
            privacy.get("privacy_preservation_score"),
            f"{branch} privacy heuristic",
        ),
        "privacy_heuristic_scope": privacy.get("privacy_preservation_score_scope"),
        "exact_output_wall_pre_duplicates": int(
            privacy.get("exact_output_wall_pre_duplicate_count")
        ),
        "exact_output_wall_post_duplicates": int(
            privacy.get("exact_output_wall_post_duplicate_count")
        ),
        "near_duplicate_status": privacy.get("near_duplicate_count_status"),
        "differential_privacy_claimed": False,
        "certified_utility_status": certificate.get("synthetic_utility_check"),
    }


def _expected_characterization_summary(
    bundle: Bundle, expected_utility_sha256: str
) -> dict[str, Any]:
    intake_manifest = bundle.json("intake/manifest.json")
    slices_payload = bundle.json("intake/fairness_slices.json")
    uncertainty = bundle.json("intake/metrics_uncertainty.json")
    robustness = bundle.json(
        "evidence/v5.0.1/robustness/robustness_summary_merged.json"
    )
    utility = _digest_anchored_json(
        bundle, UTILITY_SUMMARY_PATH, expected_utility_sha256
    )
    amplification_certificate = bundle.json(
        "intake/certificates/branch_amplification__synthetic_quality_certificate.json"
    )
    intrinsic_certificate = bundle.json(
        "intake/certificates/branch_intrinsic__synthetic_quality_certificate.json"
    )

    screen = _number(slices_payload.get("air_threshold"), "summary AIR screen")
    _close(screen, INTERNAL_AIR_SCREEN, "summary AIR screen")
    labels = {
        "historical": "Historical fixture",
        "amplification": "Amplification branch",
        "intrinsic": "Intrinsic parity-policy control",
    }
    slice_rows: list[dict[str, Any]] = []
    source_slices = slices_payload.get("slices") or {}
    for key in ("historical", "amplification", "intrinsic"):
        source = source_slices.get(key) or {}
        air = source.get("air") or {}
        srg = source.get("srg") or {}
        air_interval = air.get("ci95") or [None, None]
        srg_range = srg.get("ci95") or [None, None]
        point = _number(air.get("point"), f"summary {key} AIR")
        lower = _number(air_interval[0], f"summary {key} AIR lower")
        upper = _number(air_interval[1], f"summary {key} AIR upper")
        point_relation, interval_relation = _characterization_screen_relation(
            point, lower, upper, screen
        )
        inference_status = "conditional_on_generated_fixture"
        interval_status = "conditional_95_percent_interval"
        p_value_status = "conditional_two_proportion_test"
        if key == "intrinsic":
            interval_relation = "not_applicable_policy_determined"
            inference_status = "policy_determined"
            interval_status = "format_symmetry_only_not_inferential"
            p_value_status = "format_symmetry_only_not_inferential"
        counts = source.get("counts") or {}
        slice_rows.append(
            {
                "id": key,
                "label": labels[key],
                "reference_group": source.get("reference_group"),
                "protected_group": source.get("protected_group"),
                "reference_n": int(counts.get("ref_n")),
                "protected_n": int(counts.get("prot_n")),
                "air": point,
                "air_ci95": [lower, upper],
                "air_interval_display_status": interval_status,
                "p_value": _number(
                    air.get("p_value"), f"summary {key} p-value"
                ),
                "p_value_display_status": p_value_status,
                "srg": _number(srg.get("point"), f"summary {key} SRG"),
                "srg_endpoint_range": [
                    _number(srg_range[0], f"summary {key} SRG lower"),
                    _number(srg_range[1], f"summary {key} SRG upper"),
                ],
                "srg_method": SRG_METHOD,
                "srg_range_status": (
                    "difference_of_95_percent_wilson_endpoints_"
                    "not_a_calibrated_95_percent_interval"
                ),
                "inference_status": inference_status,
                "point_screen_relation": point_relation,
                "interval_screen_relation": interval_relation,
            }
        )

    fairness = uncertainty.get("fairness_uncertainty") or {}
    race = fairness.get("race") or {}
    race_pairs = race.get("pairs") or {}
    minimum_count_group = min(
        race_pairs,
        key=lambda group: int(
            (race_pairs[group].get("counts") or {}).get("prot_n")
        ),
    )
    observed_race = race.get("observed") or {}
    display_policy = (
        (race.get("policy") or {}).get("display_race_in_main_pdf") or {}
    )
    minimum_group_n = int(observed_race.get("min_group_n"))
    minimum_group_pct = _number(
        observed_race.get("min_group_pct"),
        "summary race minimum group share",
    )
    display_min_group_n = int(display_policy.get("min_group_n"))
    display_min_group_pct = _number(
        display_policy.get("min_group_pct"),
        "summary race display share floor",
    )
    count_floor_met = minimum_group_n >= display_min_group_n
    share_floor_met = minimum_group_pct >= display_min_group_pct
    display_expected = count_floor_met and share_floor_met
    suppression_reasons = []
    if not count_floor_met:
        suppression_reasons.append(
            "minimum_observed_group_count_below_configured_display_floor"
        )
    if not share_floor_met:
        suppression_reasons.append(
            "minimum_observed_group_share_below_configured_display_floor"
        )
    if not count_floor_met and not share_floor_met:
        suppression_reason = (
            "minimum observed group count and share below respective "
            "configured display floors"
        )
    elif not count_floor_met:
        suppression_reason = (
            "minimum observed group count below configured display floor"
        )
    else:
        suppression_reason = (
            "minimum observed group share below configured display floor"
        )
    robustness_rows: list[dict[str, Any]] = []
    for scenario_id in ("balanced", "gender_bias", "outliers", "security"):
        aggregates = (
            ((robustness.get("scenarios") or {}).get(scenario_id) or {}).get(
                "aggregates"
            )
            or {}
        )
        band = (aggregates.get("numeric_bands") or {}).get("di") or {}
        robustness_rows.append(
            {
                "id": scenario_id,
                "label": scenario_id.replace("_", " ").title(),
                "passes": int(aggregates.get("pass_count")),
                "runs": int(aggregates.get("planned_seed_count")),
                "air_min": _number(
                    band.get("min"), f"summary {scenario_id} AIR min"
                ),
                "air_mean": _number(
                    band.get("mean"), f"summary {scenario_id} AIR mean"
                ),
                "air_max": _number(
                    band.get("max"), f"summary {scenario_id} AIR max"
                ),
                "air_stdev": _number(
                    band.get("stdev"), f"summary {scenario_id} AIR stdev"
                ),
            }
        )

    return {
        "schema_version": "flbsa.whitepaper_characterization.v2",
        "document_version": "WP-5.0.1-candidate.3",
        "as_of": "2026-08-05",
        "publication_status": "candidate_not_published",
        "product": {
            "tag": PRODUCT_TAG,
            "commit": PRODUCT_COMMIT,
            "tag_object": PRODUCT_TAG_OBJECT,
        },
        "evidence": {
            "run_id": int(PRODUCT_RUN_ID),
            "run_attempt": 1,
            "run_uuid": intake_manifest.get("run_id"),
            "dataset_hash": intake_manifest.get("dataset_hash"),
            "primary_bundle_sha256": PRIMARY_BUNDLE_SHA256,
        },
        "fairness": {
            "internal_air_screen": screen,
            "screen_is_legal_verdict": False,
            "single_run_inference_scope": (
                "conditional_on_generated_fixture_and_configured_row_count"
            ),
            "srg_range_scope": (
                "difference_of_separate_95_percent_wilson_endpoints; "
                "not_a_calibrated_95_percent_interval"
            ),
            "slices": slice_rows,
            "race": {
                "configured_reference_group": race.get(
                    "configured_reference_group"
                ),
                "effective_reference_group": race.get("reference_group"),
                "reference_policy": race.get("reference_group_selection_policy"),
                "display_in_main_pdf": display_expected,
                "suppression_reason": suppression_reason,
                "suppression_reasons": suppression_reasons,
                "minimum_count_group": minimum_count_group,
                "lowest_selection_rate_group": (
                    race.get("selection_rate_range") or {}
                ).get("min_group"),
                "minimum_group_n": minimum_group_n,
                "minimum_group_pct": minimum_group_pct,
                "display_min_group_n": display_min_group_n,
                "display_min_group_pct": display_min_group_pct,
                "minimum_group_n_floor_met": count_floor_met,
                "minimum_group_pct_floor_met": share_floor_met,
                "worst_case_pair": race.get("worst_case_pair"),
                "air_intervals_multiplicity_adjusted": False,
                "air_p_value_adjustment": "holm_bonferroni",
            },
        },
        "quality": {
            "amplification": _characterization_quality(
                amplification_certificate, "amplification"
            ),
            "intrinsic": _characterization_quality(
                intrinsic_certificate, "intrinsic"
            ),
        },
        "robustness": {
            "complete": robustness.get("complete") is True,
            "planned_seeds": robustness.get("planned_seeds"),
            "scenarios": robustness_rows,
            "total_runs": sum(row["runs"] for row in robustness_rows),
            "total_passes": sum(row["passes"] for row in robustness_rows),
        },
        "utility": utility,
        "interpretation": {
            "intrinsic": (
                "mechanical parity-policy branch-separation control; "
                "not a causal counterfactual"
            ),
            "certificate_integrity": (
                "hash and internal predecessor linkage; public key absent from companion"
            ),
            "regulatory": "governance mapping only; no compliance determination",
        },
    }


def _verify_characterization_summary(
    bundle: Bundle, expected_utility_sha256: str
) -> dict[str, int]:
    summary = bundle.json(
        "evidence/v5.0.1/publication/characterization_summary.json"
    )
    expected = _expected_characterization_summary(
        bundle, expected_utility_sha256
    )
    _require(
        set(summary) == set(expected),
        "characterization summary top-level inventory mismatch",
    )
    for key, expected_value in expected.items():
        _require(
            summary.get(key) == expected_value,
            f"characterization summary {key} projection mismatch",
        )
    return {"characterization_summary_sections_cross_checked": len(expected)}


def _verify_publication_overlays(
    bundle: Bundle, expected_utility_sha256: str
) -> dict[str, int]:
    corrections = bundle.json("evidence/v5.0.1/publication/interpretation_corrections.json")
    _require(
        corrections.get("schema_version")
        == "flbsa.whitepaper_interpretation_corrections.v1",
        "unsupported correction-ledger schema",
    )
    _require(corrections.get("as_of") == "2026-08-05", "wrong correction date")
    _require(corrections.get("producer_evidence_mutated") is False, "producer mutation flag mismatch")
    correction_rows = corrections.get("corrections") or []
    _require(
        {row.get("id") for row in correction_rows if isinstance(row, dict)}
        == {
            "srg-method",
            "race-reference",
            "intrinsic-estimand",
            "internal-screen",
            "single-run-inference",
            "race-multiplicity",
            "utility-skill-normalisation",
            "integrity-language",
            "regulatory-current-state",
        },
        "correction-ledger inventory mismatch",
    )
    rows = list(
        csv.DictReader(
            io.StringIO(
                bundle.read("evidence/v5.0.1/publication/regulatory_mapping_2026-08-05.csv").decode("utf-8")
            )
        )
    )
    _require(len(rows) == 5, "regulatory mapping must contain five reviewed rows")
    _require(all(row.get("as_of") == "2026-08-05" for row in rows), "regulatory mapping date mismatch")
    return _verify_characterization_summary(bundle, expected_utility_sha256)


def verify(
    path: Path,
    *,
    expected_utility_sha256: str,
    expected_gold_manifest_sha256: str,
    expected_gold_index_sha256: str,
    expected_gold_summary_sha256: str,
) -> dict[str, Any]:
    for label, digest in (
        ("utility", expected_utility_sha256),
        ("Gold evidence manifest", expected_gold_manifest_sha256),
        ("Gold index", expected_gold_index_sha256),
        ("Gold summary", expected_gold_summary_sha256),
    ):
        _require(
            HEX_64.fullmatch(digest) is not None,
            f"expected {label} SHA-256 must be 64 lowercase hexadecimal characters",
        )
    bundle = Bundle(path)
    manifest = bundle.json("MANIFEST.json")
    _verify_file_manifest(bundle, manifest)
    gold_anchors = _verify_gold_anchors(
        bundle,
        expected_gold_manifest_sha256=expected_gold_manifest_sha256,
        expected_gold_index_sha256=expected_gold_index_sha256,
        expected_gold_summary_sha256=expected_gold_summary_sha256,
    )
    producer = _verify_original_producer_bundle(bundle)
    _verify_identity(bundle, manifest)
    fairness = _verify_fairness(bundle)
    certificates = _verify_certificates(bundle)
    studies = _verify_robustness_and_utility(
        bundle, expected_utility_sha256
    )
    overlays = _verify_publication_overlays(
        bundle, expected_utility_sha256
    )
    return {
        "status": "verified",
        "bundle": str(path),
        "bundle_sha256": _sha256(path.read_bytes()) if path.is_file() else None,
        "product_tag": PRODUCT_TAG,
        "product_commit": PRODUCT_COMMIT,
        "utility_summary_sha256_expected": expected_utility_sha256,
        **gold_anchors,
        **producer,
        **fairness,
        **certificates,
        **studies,
        **overlays,
        "signature_scope": "metadata_encoding_only_public_key_not_bundled",
        "integrity_scope": "hash_and_internal_linkage",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expected-utility-sha256",
        required=True,
        help="utility_summary.json digest copied from the trusted PDF",
    )
    parser.add_argument(
        "--expected-gold-manifest-sha256",
        required=True,
        help="Gold evidence_manifest.json digest copied from the trusted PDF",
    )
    parser.add_argument(
        "--expected-gold-index-sha256",
        required=True,
        help="Gold robustness_index.csv digest copied from the trusted PDF",
    )
    parser.add_argument(
        "--expected-gold-summary-sha256",
        required=True,
        help="Gold robustness_summary_merged.json digest copied from the trusted PDF",
    )
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    try:
        result = verify(
            args.bundle,
            expected_utility_sha256=args.expected_utility_sha256,
            expected_gold_manifest_sha256=(
                args.expected_gold_manifest_sha256
            ),
            expected_gold_index_sha256=args.expected_gold_index_sha256,
            expected_gold_summary_sha256=args.expected_gold_summary_sha256,
        )
    except VerificationError as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
