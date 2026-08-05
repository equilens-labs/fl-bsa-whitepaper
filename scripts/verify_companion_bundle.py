#!/usr/bin/env python3
"""Verify the standalone FL-BSA v5.0.1 whitepaper companion bundle."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


PRODUCT_COMMIT = "cc32b3a8d13cb75419b0dec1d4b9bdf5a3eb90c2"
PRODUCT_TAG = "v5.0.1"
PRODUCT_TAG_OBJECT = "3a0ea6e4faea9d61aabcedebab2a838624fb587d"
PRODUCT_RUN_ID = "30765888408"
PRIMARY_BUNDLE_SHA256 = (
    "f6a0bd9390565f7bd852b451e11b7384b1628c24caba02865b1ec94c1e263026"
)
SRG_METHOD = "conservative_wilson_endpoint_difference"
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


class Bundle:
    def __init__(self, path: Path):
        self.path = path
        self._zip: zipfile.ZipFile | None = None
        if path.is_file():
            try:
                self._zip = zipfile.ZipFile(path)
            except (OSError, zipfile.BadZipFile) as exc:
                raise VerificationError(f"invalid companion ZIP: {exc}") from exc
            names: list[str] = []
            for info in self._zip.infolist():
                name = _safe_name(info.filename)
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise VerificationError(f"symlink archive member is forbidden: {name}")
                if info.is_dir():
                    raise VerificationError(f"directory archive entries are forbidden: {name}")
                names.append(name)
            if len(names) != len(set(names)):
                raise VerificationError("duplicate archive member")
            self.names = sorted(names)
        elif path.is_dir():
            names = []
            for child in path.rglob("*"):
                if child.is_symlink():
                    raise VerificationError(f"symlink bundle member is forbidden: {child}")
                if child.is_file():
                    names.append(_safe_name(child.relative_to(path).as_posix()))
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


def _certificate_hash(payload: dict[str, Any]) -> str:
    filtered = {
        key: value
        for key, value in payload.items()
        if key not in CERT_HASH_EXCLUDED_FIELDS
    }
    canonical = json.dumps(filtered, sort_keys=True, separators=(",", ":"))
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
    _require(paper.get("document_version") == "WP-5.0.1-candidate.1", "bad document version")
    _require(paper.get("publication_status") == "candidate_not_published", "bad publication status")

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


def _verify_fairness(bundle: Bundle) -> None:
    slices = bundle.json("intake/fairness_slices.json")
    _require(slices.get("attribute") == "gender", "gender slices missing")
    for name in ("historical", "amplification", "intrinsic"):
        row = (slices.get("slices") or {}).get(name) or {}
        _require((row.get("srg") or {}).get("method") == SRG_METHOD, f"wrong SRG method in {name}")

    uncertainty = bundle.json("intake/metrics_uncertainty.json")
    fairness = uncertainty.get("fairness_uncertainty") or {}
    gender = fairness.get("gender") or {}
    _require((gender.get("srg") or {}).get("method") == SRG_METHOD, "wrong gender SRG method")
    race = fairness.get("race") or {}
    _require(race.get("configured_reference_group") == "white", "wrong configured race reference")
    _require(race.get("reference_group") == "black", "wrong effective race reference")
    _require(
        race.get("reference_group_selection_policy") == "highest_selection_rate_four_fifths",
        "wrong race reference policy",
    )
    _require(race.get("display_in_main_pdf") is False, "race display policy mismatch")
    for name, row in (race.get("pairs") or {}).items():
        _require((row.get("srg") or {}).get("method") == SRG_METHOD, f"wrong race SRG method for {name}")


def _verify_certificates(bundle: Bundle) -> dict[str, int]:
    names = [
        name
        for name in bundle.names
        if name.startswith("intake/certificates/") and name.endswith(".json")
    ]
    _require(len(names) == 21, f"expected 21 certificates, found {len(names)}")
    payloads: list[dict[str, Any]] = []
    hashes: set[str] = set()
    for name in names:
        payload = bundle.json(name)
        stored = str(payload.get("certificate_hash") or "")
        _require(HEX_64.fullmatch(stored) is not None, f"invalid stored certificate hash in {name}")
        _require(_certificate_hash(payload) == stored, f"certificate hash mismatch in {name}")
        _require(payload.get("signature_algorithm") == "ECDSA-P256-SHA256", f"signature metadata missing in {name}")
        _require(HEX_16.fullmatch(str(payload.get("public_key_fingerprint") or "")) is not None, f"bad key fingerprint in {name}")
        _require(HEX_128.fullmatch(str(payload.get("certificate_signature") or "")) is not None, f"bad signature encoding in {name}")
        payloads.append(payload)
        hashes.add(stored)
    roots = 0
    links = 0
    for name, payload in zip(names, payloads, strict=True):
        previous = str(payload.get("previous_certificate_hash") or "")
        if not previous:
            roots += 1
            continue
        _require(previous in hashes, f"unresolved predecessor hash in {name}")
        links += 1
    _require(roots == 1 and links == 20, "certificate predecessor linkage is incomplete")
    return {"certificate_files": len(names), "internal_links": links, "roots": roots}


def _verify_robustness_and_utility(bundle: Bundle) -> dict[str, Any]:
    robustness = bundle.json("evidence/v5.0.1/robustness/robustness_summary_merged.json")
    _require(robustness.get("schema_version") == "gold.robustness.v1", "bad robustness schema")
    _require(robustness.get("complete") is True, "robustness evidence is incomplete")
    _require(robustness.get("planned_seeds") == robustness.get("completed_seeds"), "robustness seeds incomplete")
    scenarios = robustness.get("scenarios") or {}
    _require(set(scenarios) == {"balanced", "gender_bias", "outliers", "security"}, "wrong robustness scenarios")
    for name, scenario in scenarios.items():
        aggregates = scenario.get("aggregates") or {}
        _require(aggregates.get("observed_seed_count") == 10, f"wrong seed count for {name}")
        _require(aggregates.get("pass_count") == 10, f"robustness failures in {name}")
        _require(aggregates.get("fail_count") == 0, f"robustness failures in {name}")

    utility = bundle.json("evidence/v5.0.1/utility/utility_summary.json")
    _require((utility.get("product") or {}).get("commit") == PRODUCT_COMMIT, "utility product mismatch")
    study = utility.get("study") or {}
    results = utility.get("synthetic_train_results") or []
    _require(len(study.get("generation_seeds") or []) == 10, "utility seed plan mismatch")
    _require(len(results) == 10, "utility seed results incomplete")
    _require(study.get("train_rows") == study.get("generated_rows_per_seed"), "utility sample-size parity mismatch")
    return {
        "robustness_scenarios": len(scenarios),
        "robustness_runs": sum((row.get("aggregates") or {}).get("pass_count", 0) for row in scenarios.values()),
        "utility_seeds": len(results),
    }


def _verify_publication_overlays(bundle: Bundle) -> None:
    corrections = bundle.json("evidence/v5.0.1/publication/interpretation_corrections.json")
    _require(corrections.get("as_of") == "2026-08-05", "wrong correction date")
    _require(corrections.get("producer_evidence_mutated") is False, "producer mutation flag mismatch")
    rows = list(
        csv.DictReader(
            io.StringIO(
                bundle.read("evidence/v5.0.1/publication/regulatory_mapping_2026-08-05.csv").decode("utf-8")
            )
        )
    )
    _require(len(rows) == 5, "regulatory mapping must contain five reviewed rows")
    _require(all(row.get("as_of") == "2026-08-05" for row in rows), "regulatory mapping date mismatch")


def verify(path: Path) -> dict[str, Any]:
    bundle = Bundle(path)
    manifest = bundle.json("MANIFEST.json")
    _verify_file_manifest(bundle, manifest)
    _verify_identity(bundle, manifest)
    _verify_fairness(bundle)
    certificates = _verify_certificates(bundle)
    studies = _verify_robustness_and_utility(bundle)
    _verify_publication_overlays(bundle)
    return {
        "status": "verified",
        "bundle": str(path),
        "bundle_sha256": _sha256(path.read_bytes()) if path.is_file() else None,
        "product_tag": PRODUCT_TAG,
        "product_commit": PRODUCT_COMMIT,
        **certificates,
        **studies,
        "signature_scope": "metadata_encoding_only_public_key_not_bundled",
        "integrity_scope": "hash_and_internal_linkage",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.bundle)
    except VerificationError as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
