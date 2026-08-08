#!/usr/bin/env python3
"""Build a deterministic, self-verifying whitepaper companion evidence ZIP."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any

try:
    from public_path_policy import FORBIDDEN_PUBLIC_PATH_MARKERS
except ModuleNotFoundError:  # Imported as scripts.build_companion_bundle in tests.
    from scripts.public_path_policy import FORBIDDEN_PUBLIC_PATH_MARKERS


DOCUMENT_VERSION = "WP-5.0.1-candidate.3"
PRODUCT_COMMIT = "cc32b3a8d13cb75419b0dec1d4b9bdf5a3eb90c2"
PRODUCT_TAG = "v5.0.1"
PRODUCT_TAG_OBJECT = "3a0ea6e4faea9d61aabcedebab2a838624fb587d"
MAX_FILE_BYTES = 20 * 1024 * 1024
PUBLIC_TEXT_SUFFIXES = frozenset(
    {".csv", ".json", ".md", ".py", ".tex", ".txt", ".yaml", ".yml"}
)
PUBLIC_GZIP_MEMBERS = frozenset(
    {"evidence/v5.0.1/utility/balanced_fixture.csv.gz"}
)
PRIMARY_BUNDLE_SHA256 = (
    "f6a0bd9390565f7bd852b451e11b7384b1628c24caba02865b1ec94c1e263026"
)
PRODUCER_BUNDLE_MEMBER = "producer/WhitePaper_Intake_Bundle_v4.zip"
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


class CompanionError(ValueError):
    """Raised when the companion bundle cannot be built truthfully."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise CompanionError(completed.stderr.strip() or "unable to resolve Git identity")
    return completed.stdout.strip()


def _source_date_epoch(root: Path) -> int:
    value = os.environ.get("SOURCE_DATE_EPOCH") or _git(root, "show", "-s", "--format=%ct", "HEAD")
    try:
        epoch = int(value)
    except ValueError as exc:
        raise CompanionError("SOURCE_DATE_EPOCH must be an integer") from exc
    return max(epoch, 315532800)


def _zip_info(name: str, epoch: int, *, mode: int = 0o100644) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, time.gmtime(epoch)[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (mode & 0xFFFF) << 16
    return info


def _producer_bundle_members(root: Path) -> dict[str, bytes]:
    """Reconstruct the exact producer archive members from reviewed sources."""

    members: dict[str, bytes] = {}
    certificate_dir = root / "intake" / "certificates"
    for path in sorted(certificate_dir.glob("*.json")):
        members[f"certificates/{path.name}"] = path.read_bytes()
    for name in ("fairness_config.yaml", "sap.yaml"):
        members[f"config/{name}"] = (root / "config" / name).read_bytes()
    for name in PRODUCER_INTAKE_FILES:
        path = root / "intake" / name
        if name == "manifest.json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload.pop("whitepaper_consumer", None)
            data = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
        else:
            data = path.read_bytes()
        members[f"intake/{name}"] = data
    members["provenance/manifest.json"] = members["intake/manifest.json"]
    expected_count = 36
    if len(members) != expected_count:
        raise CompanionError(
            f"producer archive must have {expected_count} members, found {len(members)}"
        )
    return dict(sorted(members.items()))


def _build_original_producer_zip(root: Path) -> bytes:
    """Reproduce the release-run producer ZIP byte for byte and pin its digest."""

    output = io.BytesIO()
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        for name, data in _producer_bundle_members(root).items():
            info = _zip_info(name, 315532800, mode=0o100600)
            archive.writestr(info, data, compresslevel=6)
    data = output.getvalue()
    digest = _sha256(data)
    if digest != PRIMARY_BUNDLE_SHA256:
        raise CompanionError(
            "reconstructed producer ZIP digest mismatch: "
            f"expected {PRIMARY_BUNDLE_SHA256}, got {digest}"
        )
    return data


def _assert_no_machine_path(name: str, data: bytes) -> None:
    for marker in FORBIDDEN_PUBLIC_PATH_MARKERS:
        if marker in data:
            raise CompanionError(
                f"public companion member contains machine-local path {marker.decode()}: {name}"
            )


def _assert_public_safe_members(members: dict[str, bytes]) -> None:
    """Reject unknown formats and inspect the contents of supported compressed members."""

    for name, data in members.items():
        _assert_no_machine_path(name, data)
        suffix = Path(name).suffix.lower()
        if suffix in PUBLIC_TEXT_SUFFIXES:
            continue
        if name in PUBLIC_GZIP_MEMBERS:
            try:
                expanded = gzip.decompress(data)
            except (EOFError, OSError) as exc:
                raise CompanionError(f"invalid public gzip member: {name}") from exc
            _assert_no_machine_path(f"{name} (decompressed)", expanded)
            continue
        if name == PRODUCER_BUNDLE_MEMBER:
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    for nested in archive.infolist():
                        if nested.is_dir():
                            continue
                        nested_name = nested.filename
                        if Path(nested_name).suffix.lower() not in PUBLIC_TEXT_SUFFIXES:
                            raise CompanionError(
                                "unsupported public companion member format: "
                                f"{name}!{nested_name}"
                            )
                        _assert_no_machine_path(
                            f"{name}!{nested_name}", archive.read(nested)
                        )
            except zipfile.BadZipFile as exc:
                raise CompanionError(f"invalid public ZIP member: {name}") from exc
            continue
        raise CompanionError(f"unsupported public companion member format: {name}")


def _collect(root: Path) -> dict[str, bytes]:
    exact_files = [
        "config/fairness_config.yaml",
        "config/sap.yaml",
        "contracts/whitepaper-intake-producer-contract.v1.json",
        "intake/air_status.json",
        "intake/ece_status.json",
        "intake/eo_status.json",
        "intake/fairness_slices.json",
        "intake/group_confusion.csv",
        "intake/manifest.json",
        "intake/metrics_long.csv",
        "intake/metrics_uncertainty.json",
        "intake/pack_intent.json",
        "intake/regulatory_matrix.csv",
        "intake/run_summary.json",
        "intake/selection_rates.csv",
        "intake/archive/v5.0.1-release-30765888408.json",
        "scripts/evaluate_fixture_utility.py",
    ]
    members: dict[str, bytes] = {}
    for relative in exact_files:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise CompanionError(f"required companion source missing or unsafe: {relative}")
        members[relative] = path.read_bytes()
    for relative_root in (
        "intake/certificates",
        "evidence/v5.0.1/robustness",
        "evidence/v5.0.1/utility",
        "evidence/v5.0.1/publication",
    ):
        directory = root / relative_root
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise CompanionError(f"symlink companion source is forbidden: {path}")
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                members[relative] = path.read_bytes()
    members["README.md"] = (root / "companion" / "README.md").read_bytes()
    members["verify_companion_bundle.py"] = (
        root / "scripts" / "verify_companion_bundle.py"
    ).read_bytes()
    members["characterization_contract.py"] = (
        root / "scripts" / "characterization_contract.py"
    ).read_bytes()
    members[PRODUCER_BUNDLE_MEMBER] = _build_original_producer_zip(root)
    for name, data in members.items():
        if len(data) > MAX_FILE_BYTES:
            raise CompanionError(f"companion member exceeds size limit: {name}")
    return dict(sorted(members.items()))


def build(root: Path, output: Path) -> dict[str, Any]:
    root = root.resolve()
    commit = _git(root, "rev-parse", "HEAD")
    dirty = bool(_git(root, "status", "--porcelain"))
    members = _collect(root)
    _assert_public_safe_members(members)
    files = [
        {"path": name, "sha256": _sha256(data), "size": len(data)}
        for name, data in members.items()
    ]
    manifest = {
        "schema_version": "flbsa.whitepaper_companion.v1",
        "claim_boundary": {
            "customer_evidence_disposition": "characterization_only",
            "customer_evidence_eligible": False,
            "publication_status": "candidate_not_published",
        },
        "product": {
            "repository": "equilens-labs/fl-bsa",
            "tag": PRODUCT_TAG,
            "tag_object": PRODUCT_TAG_OBJECT,
            "commit": PRODUCT_COMMIT,
        },
        "whitepaper": {
            "repository": "equilens-labs/fl-bsa-whitepaper",
            "commit": commit,
            "source_tree_dirty_at_build": dirty,
            "document_version": DOCUMENT_VERSION,
            "publication_status": "candidate_not_published",
        },
        "evidence": {
            "producer_workflow": "release-evidence.yml",
            "producer_run_id": 30765888408,
            "producer_run_attempt": 1,
            "primary_bundle_member": PRODUCER_BUNDLE_MEMBER,
            "primary_bundle_sha256": PRIMARY_BUNDLE_SHA256,
            "robustness_runs": 40,
            "utility_generation_seeds": 10,
        },
        "files": files,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    epoch = _source_date_epoch(root)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(_zip_info("MANIFEST.json", epoch), manifest_bytes, compresslevel=9)
        for name, data in members.items():
            archive.writestr(_zip_info(name, epoch), data, compresslevel=9)
    return {
        "output": str(output),
        "sha256": _sha256(output.read_bytes()),
        "size": output.stat().st_size,
        "file_count": len(files),
        "whitepaper_commit": commit,
        "source_tree_dirty_at_build": dirty,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.repo_root, args.output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
