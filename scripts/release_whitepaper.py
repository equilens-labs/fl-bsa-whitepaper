#!/usr/bin/env python3
"""Build and verify the exact identity for an automatically generated release paper.

The release paper is deliberately separate from the fixed archival publication.  It may
only be prepared from a ``release-evidence.yml`` intake receipt, and it preserves the
characterization-only claim boundary of that receipt.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from verify_pdf_release_identity import PdfIdentityError, extract_text, verify_text

IDENTITY_SCHEMA = "flbsa.release_whitepaper_identity.v1"
RELEASE_SCHEMA = "flbsa.release_whitepaper.v1"
SNAPSHOT_SCHEMA = "flbsa.whitepaper_intake_snapshot.v3"
MANIFEST_SCHEMA = "wp-intake.v1"
PACK_INTENT_SCHEMA = "wp.pack_intent.v1"
PRODUCT_REPO = "equilens-labs/fl-bsa"
WHITEPAPER_REPO = "equilens-labs/fl-bsa-whitepaper"
RELEASE_WORKFLOW = "release-evidence.yml"
RELEASE_BRANCH = "main"
PUBLICATION_STATUS = "candidate_not_published"
CUSTOMER_EVIDENCE_DISPOSITION = "characterization_only"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RUN_ID_RE = re.compile(r"^[1-9][0-9]*$")
_TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_BACKEND_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_REGULATORY_COLUMNS = (
    "framework",
    "citation",
    "requirement_text",
    "control_assurance",
    "evidence_artifact",
    "owner",
    "status",
    "notes",
)
_CONTROL_CHARACTER_RE = re.compile(r"[\x00-\x1f\x7f]")
_MAX_REGULATORY_ROWS = 50
_MAX_REGULATORY_CELL_LENGTH = 2_000


class ReleaseWhitepaperError(ValueError):
    """Raised when the release-paper identity is incomplete or inconsistent."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseWhitepaperError(f"unable to read JSON from {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReleaseWhitepaperError(f"expected a JSON object in {path}")
    return payload


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ReleaseWhitepaperError(f"unable to hash {path}: {exc}") from exc


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _require_exact(value: Any, expected: Any, label: str) -> None:
    if value != expected:
        raise ReleaseWhitepaperError(f"{label}={value!r}; expected {expected!r}")


def _require_match(value: Any, pattern: re.Pattern[str], label: str) -> str:
    text = str(value or "")
    if not pattern.fullmatch(text):
        raise ReleaseWhitepaperError(f"invalid {label}: {text!r}")
    return text


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReleaseWhitepaperError(f"{label} must be a JSON object")
    return value


def _validate_claims(claims: dict[str, Any], *, label: str) -> None:
    _require_exact(
        claims.get("customer_evidence_eligible"),
        False,
        f"{label}.customer_evidence_eligible",
    )
    _require_exact(
        claims.get("customer_evidence_disposition"),
        CUSTOMER_EVIDENCE_DISPOSITION,
        f"{label}.customer_evidence_disposition",
    )
    _require_exact(
        claims.get("publication_status"),
        PUBLICATION_STATUS,
        f"{label}.publication_status",
    )


def _validate_snapshot_id(snapshot: dict[str, Any]) -> None:
    producer = _require_mapping(snapshot.get("producer"), "snapshot.producer")
    whitepaper = _require_mapping(snapshot.get("whitepaper"), "snapshot.whitepaper")
    identity = {
        "producer_repo": producer.get("repo"),
        "producer_workflow": producer.get("workflow"),
        "producer_branch": producer.get("branch"),
        "producer_run_id": producer.get("run_id"),
        "producer_run_attempt": producer.get("run_attempt"),
        "producer_head_sha": producer.get("head_sha"),
        "producer_artifact": producer.get("artifact"),
        "producer_artifact_id": producer.get("artifact_id"),
        "producer_artifact_digest": producer.get("artifact_digest"),
        "producer_contract_sha256": producer.get("contract_sha256"),
        "product_sha": producer.get("product_sha"),
        "bundle_filename": producer.get("bundle_filename"),
        "bundle_sha256": producer.get("bundle_sha256"),
        "whitepaper_repo": whitepaper.get("repo"),
        "whitepaper_base_commit": whitepaper.get("base_commit"),
    }
    expected = hashlib.sha256(_canonical_json(identity)).hexdigest()
    _require_exact(snapshot.get("snapshot_id"), expected, "snapshot.snapshot_id")


def build_identity(
    *,
    snapshot_path: Path,
    manifest_path: Path,
    pack_intent_path: Path,
    whitepaper_commit: str,
    whitepaper_run_id: str,
    whitepaper_run_attempt: str,
) -> dict[str, Any]:
    """Validate one release intake and return its immutable paper identity."""

    whitepaper_commit = _require_match(whitepaper_commit, _SHA_RE, "whitepaper commit")
    whitepaper_run_id = _require_match(
        whitepaper_run_id, _RUN_ID_RE, "whitepaper workflow run ID"
    )
    whitepaper_run_attempt = _require_match(
        whitepaper_run_attempt, _RUN_ID_RE, "whitepaper workflow run attempt"
    )

    snapshot = _read_json(snapshot_path)
    manifest = _read_json(manifest_path)
    pack_intent = _read_json(pack_intent_path)
    _require_exact(snapshot.get("schema_version"), SNAPSHOT_SCHEMA, "snapshot schema")
    _validate_claims(
        _require_mapping(snapshot.get("claims"), "snapshot.claims"),
        label="snapshot.claims",
    )
    _validate_snapshot_id(snapshot)

    producer = _require_mapping(snapshot.get("producer"), "snapshot.producer")
    consumer = _require_mapping(snapshot.get("whitepaper"), "snapshot.whitepaper")
    _require_exact(producer.get("repo"), PRODUCT_REPO, "snapshot producer repo")
    _require_exact(
        producer.get("workflow"), RELEASE_WORKFLOW, "snapshot producer workflow"
    )
    _require_exact(producer.get("branch"), RELEASE_BRANCH, "snapshot producer branch")
    product_run_id = _require_match(
        producer.get("run_id"), _RUN_ID_RE, "product workflow run ID"
    )
    product_run_attempt = _require_match(
        producer.get("run_attempt"), _RUN_ID_RE, "product workflow run attempt"
    )
    product_sha = _require_match(producer.get("product_sha"), _SHA_RE, "product commit")
    _require_exact(producer.get("head_sha"), product_sha, "product head SHA")
    artifact_id = _require_match(
        producer.get("artifact_id"), _RUN_ID_RE, "product artifact ID"
    )
    artifact_digest = _require_match(
        producer.get("artifact_digest"),
        _ARTIFACT_DIGEST_RE,
        "product artifact digest",
    )
    expected_artifact = f"wp-intake-bundle-v4-{product_run_attempt}"
    _require_exact(producer.get("artifact"), expected_artifact, "product artifact name")
    _require_exact(
        producer.get("bundle_filename"),
        "WhitePaper_Intake_Bundle_v4.zip",
        "intake bundle filename",
    )
    contract_sha256 = _require_match(
        producer.get("contract_sha256"), _SHA256_RE, "producer contract SHA-256"
    )
    bundle_sha256 = _require_match(
        producer.get("bundle_sha256"), _SHA256_RE, "intake bundle SHA-256"
    )
    snapshot_id = _require_match(snapshot.get("snapshot_id"), _SHA256_RE, "snapshot ID")

    _require_exact(consumer.get("repo"), WHITEPAPER_REPO, "snapshot whitepaper repo")
    _require_exact(
        consumer.get("base_commit"),
        whitepaper_commit,
        "snapshot whitepaper base commit",
    )
    _require_exact(
        consumer.get("manifest_sha256"),
        _sha256_file(manifest_path),
        "snapshot manifest SHA-256",
    )
    _require_exact(
        consumer.get("pack_intent_sha256"),
        _sha256_file(pack_intent_path),
        "snapshot pack-intent SHA-256",
    )

    _require_exact(manifest.get("schema_version"), MANIFEST_SCHEMA, "manifest schema")
    for field in ("commit_sha", "code_commit", "source_commit", "software_commit"):
        _require_exact(manifest.get(field), product_sha, f"manifest {field}")
    release_tag = _require_match(
        manifest.get("software_version"), _TAG_RE, "release tag"
    )
    _require_exact(manifest.get("build_ref"), release_tag, "manifest build_ref")
    backend = _require_mapping(manifest.get("generator_backend"), "generator backend")
    backend_id = _require_match(
        backend.get("backend_id"), _BACKEND_RE, "generator backend ID"
    )

    _require_exact(
        pack_intent.get("schema_version"), PACK_INTENT_SCHEMA, "pack-intent schema"
    )
    _require_exact(pack_intent.get("purpose"), "intake", "pack-intent purpose")
    _require_exact(pack_intent.get("evidence_grade"), False, "pack evidence_grade")
    _require_exact(
        pack_intent.get("certificate_signing_expected"),
        False,
        "pack certificate_signing_expected",
    )

    return {
        "schema_version": IDENTITY_SCHEMA,
        "claims": {
            "customer_evidence_eligible": False,
            "customer_evidence_disposition": CUSTOMER_EVIDENCE_DISPOSITION,
            "publication_status": PUBLICATION_STATUS,
        },
        "release": {"tag": release_tag},
        "product": {
            "repo": PRODUCT_REPO,
            "workflow": RELEASE_WORKFLOW,
            "branch": RELEASE_BRANCH,
            "run_id": product_run_id,
            "run_attempt": product_run_attempt,
            "commit_sha": product_sha,
            "artifact": producer.get("artifact"),
            "artifact_id": artifact_id,
            "artifact_digest": artifact_digest,
            "contract_sha256": contract_sha256,
            "generator_backend_id": backend_id,
        },
        "intake": {
            "snapshot_id": snapshot_id,
            "bundle_filename": producer.get("bundle_filename"),
            "bundle_sha256": bundle_sha256,
            "manifest_sha256": consumer.get("manifest_sha256"),
            "pack_intent_sha256": consumer.get("pack_intent_sha256"),
        },
        "whitepaper": {
            "repo": WHITEPAPER_REPO,
            "branch": "main",
            "commit_sha": whitepaper_commit,
            "workflow": "pull-wp-intake.yml",
            "run_id": whitepaper_run_id,
            "run_attempt": whitepaper_run_attempt,
        },
    }


def _tex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def _regulatory_cell(value: Any, *, row_number: int, column: str) -> str:
    if not isinstance(value, str):
        raise ReleaseWhitepaperError(
            f"regulatory matrix row {row_number} column {column!r} must be text"
        )
    if not value or value != value.strip():
        raise ReleaseWhitepaperError(
            f"regulatory matrix row {row_number} column {column!r} "
            "must be non-empty without surrounding whitespace"
        )
    if len(value) > _MAX_REGULATORY_CELL_LENGTH or _CONTROL_CHARACTER_RE.search(value):
        raise ReleaseWhitepaperError(
            f"regulatory matrix row {row_number} column {column!r} "
            "contains unsupported text"
        )
    return value


def render_regulatory_table(matrix_path: Path) -> str:
    """Render every exact regulatory-matrix cell as escaped, non-executable TeX."""

    try:
        with matrix_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            if tuple(reader.fieldnames or ()) != _REGULATORY_COLUMNS:
                raise ReleaseWhitepaperError(
                    "regulatory matrix columns must exactly match the reviewed release schema"
                )
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ReleaseWhitepaperError(
            f"unable to read regulatory matrix from {matrix_path}: {exc}"
        ) from exc

    if not rows or len(rows) > _MAX_REGULATORY_ROWS:
        raise ReleaseWhitepaperError(
            f"regulatory matrix must contain between 1 and {_MAX_REGULATORY_ROWS} rows"
        )

    lines = [
        "% Generated from the exact release intake by scripts/release_whitepaper.py; do not edit.",
        r"\begin{table}[htbp]",
        r"\centering",
        r"\small",
        r"\begin{tabular}{@{}p{0.16\linewidth}p{0.13\linewidth}p{0.28\linewidth}p{0.28\linewidth}@{}}",
        r"\toprule",
        "Framework & Citation & Requirement & Controls and evidence (this run) \\\\",
        r"\midrule",
    ]
    for row_number, row in enumerate(rows, start=2):
        if tuple(row) != _REGULATORY_COLUMNS:
            raise ReleaseWhitepaperError(
                f"regulatory matrix row {row_number} does not match the reviewed schema"
            )
        cells = {
            column: _tex_escape(
                _regulatory_cell(row[column], row_number=row_number, column=column)
            )
            for column in _REGULATORY_COLUMNS
        }
        controls = (
            f"{cells['control_assurance']} "
            rf"\newline \textit{{Evidence artifacts:}} {cells['evidence_artifact']} "
            rf"\newline \textit{{Owner/status:}} {cells['owner']} / {cells['status']} "
            rf"\newline \textit{{Notes:}} {cells['notes']}"
        )
        lines.append(
            f"{cells['framework']} & {cells['citation']} & "
            f"{cells['requirement_text']} & {controls} " + r"\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\caption{Regulatory mapping generated directly from every row and column of the exact release intake matrix.}",
            r"\label{tab:reg_matrix}",
            r"\end{table}",
        ]
    )
    return "\n".join(lines) + "\n"


def write_regulatory_table(matrix_path: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_regulatory_table(matrix_path), encoding="utf-8")


def write_identity_tex(identity: dict[str, Any], output: Path) -> None:
    product = identity["product"]
    intake = identity["intake"]
    whitepaper = identity["whitepaper"]
    values = {
        "ProductReleaseTag": identity["release"]["tag"],
        "ProductCommit": product["commit_sha"],
        "EvidenceReleaseRunId": product["run_id"],
        "EvidenceReleaseRunAttempt": product["run_attempt"],
        "ReleaseGeneratorBackend": product["generator_backend_id"],
        "WhitepaperSourceCommit": whitepaper["commit_sha"],
        "WhitepaperWorkflowRunId": whitepaper["run_id"],
        "WhitepaperWorkflowRunAttempt": whitepaper["run_attempt"],
        "IntakeSnapshotId": intake["snapshot_id"],
        "IntakeBundleSha": intake["bundle_sha256"],
    }
    lines = ["% Generated by scripts/release_whitepaper.py; do not edit."]
    lines.extend(
        rf"\newcommand{{\{name}}}{{{_tex_escape(str(value))}}}"
        for name, value in values.items()
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def finalize(identity_path: Path, pdf_path: Path) -> dict[str, Any]:
    """Verify the rendered PDF and return its release-manifest record."""

    identity = _read_json(identity_path)
    _require_exact(identity.get("schema_version"), IDENTITY_SCHEMA, "identity schema")
    _validate_claims(
        _require_mapping(identity.get("claims"), "identity.claims"),
        label="identity.claims",
    )
    product = _require_mapping(identity.get("product"), "identity.product")
    release = _require_mapping(identity.get("release"), "identity.release")
    intake = _require_mapping(identity.get("intake"), "identity.intake")
    whitepaper = _require_mapping(identity.get("whitepaper"), "identity.whitepaper")

    try:
        text = extract_text(pdf_path)
        verify_text(
            text,
            product_tag=str(release.get("tag") or ""),
            product_sha=str(product.get("commit_sha") or ""),
            evidence_run_id=str(product.get("run_id") or ""),
            whitepaper_sha=str(whitepaper.get("commit_sha") or ""),
        )
    except PdfIdentityError as exc:
        raise ReleaseWhitepaperError(str(exc)) from exc
    normalized = re.sub(r"\s+", " ", text)
    snapshot_id = _require_match(
        intake.get("snapshot_id"), _SHA256_RE, "identity snapshot ID"
    )
    if f"Intake snapshot {snapshot_id}" not in normalized:
        raise ReleaseWhitepaperError(
            "PDF does not contain the exact labelled intake snapshot"
        )
    if "DEMO / EVALUATION ONLY" not in normalized:
        raise ReleaseWhitepaperError("PDF does not contain the demo/evaluation marker")

    result = dict(identity)
    result["schema_version"] = RELEASE_SCHEMA
    result["pdf"] = {
        "filename": "whitepaper.pdf",
        "sha256": _sha256_file(pdf_path),
        "size_bytes": pdf_path.stat().st_size,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--snapshot", type=Path, required=True)
    prepare.add_argument("--manifest", type=Path, required=True)
    prepare.add_argument("--pack-intent", type=Path, required=True)
    prepare.add_argument("--whitepaper-commit", required=True)
    prepare.add_argument("--whitepaper-run-id", required=True)
    prepare.add_argument("--whitepaper-run-attempt", required=True)
    prepare.add_argument("--identity-output", type=Path, required=True)
    prepare.add_argument("--tex-output", type=Path, required=True)

    regulatory = subparsers.add_parser("regulatory-table")
    regulatory.add_argument("--matrix", type=Path, required=True)
    regulatory.add_argument("--output", type=Path, required=True)

    finish = subparsers.add_parser("finalize")
    finish.add_argument("--identity", type=Path, required=True)
    finish.add_argument("--pdf", type=Path, required=True)
    finish.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "prepare":
            identity = build_identity(
                snapshot_path=args.snapshot,
                manifest_path=args.manifest,
                pack_intent_path=args.pack_intent,
                whitepaper_commit=args.whitepaper_commit,
                whitepaper_run_id=args.whitepaper_run_id,
                whitepaper_run_attempt=args.whitepaper_run_attempt,
            )
            write_json(identity, args.identity_output)
            write_identity_tex(identity, args.tex_output)
            print(identity["release"]["tag"])
            return 0
        if args.command == "regulatory-table":
            write_regulatory_table(args.matrix, args.output)
            return 0
        if args.command == "finalize":
            result = finalize(args.identity, args.pdf)
            write_json(result, args.output)
            return 0
        raise ReleaseWhitepaperError(f"unsupported command: {args.command}")
    except ReleaseWhitepaperError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
