#!/usr/bin/env python3
"""Create and verify durable whitepaper intake anchors.

The module has three deliberately small responsibilities:

* write a deterministic consumer snapshot record for ``pull-wp-intake``;
* verify the pinned stable-v5 characterization baseline against Git objects; and
* export that pinned baseline as a deterministic compatibility ZIP.

No command publishes a release, creates a tag, or mutates a remote repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from stable_v5_export import StableExportError, build_archive, validate_entries


ANCHOR_SCHEMA = "flbsa.whitepaper_intake_anchor.v1"
SNAPSHOT_SCHEMA = "flbsa.whitepaper_intake_snapshot.v2"
PRODUCER_REPO = "equilens-labs/fl-bsa"
WHITEPAPER_REPO = "equilens-labs/fl-bsa-whitepaper"
NIGHTLY_WORKFLOW = "wp-evidence-nightly.yml"
RELEASE_WORKFLOW = "release-evidence.yml"
PRIMARY_ARTIFACT = "wp-intake-bundle-v4"
LEGACY_ARTIFACT = "wp-reviewer-pack-v4"
PRIMARY_BUNDLE = "WhitePaper_Intake_Bundle_v4.zip"
LEGACY_BUNDLE = "WhitePaper_Reviewer_Pack_v4.zip"
ROLLING_BRANCH = "chore/wp-intake-nightly"
STABLE_ANCHOR_ID = "stable-v5-characterization"
STABLE_RELEASE_TAG = "v5.0.0"
PUBLICATION_PROJECTION_ALGORITHM = "git-object-projection-sha256.v1"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RUN_ID_RE = re.compile(r"^[1-9][0-9]*$")
_REPO_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


class AnchorError(ValueError):
    """Raised when an anchor or snapshot would weaken provenance."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnchorError(f"unable to read JSON from {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AnchorError(f"expected a JSON object in {path}")
    return payload


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise AnchorError(f"unable to hash {path}: {exc}") from exc


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _require_exact(value: Any, expected: Any, label: str) -> None:
    if value != expected:
        raise AnchorError(f"{label}={value!r}; expected {expected!r}")


def _require_match(value: Any, pattern: re.Pattern[str], label: str) -> str:
    text = str(value or "")
    if not pattern.fullmatch(text):
        raise AnchorError(f"invalid {label}: {text!r}")
    return text


def _require_claim_boundary(payload: dict[str, Any], *, label: str) -> None:
    _require_exact(
        payload.get("customer_evidence_eligible"),
        False,
        f"{label}.customer_evidence_eligible",
    )
    _require_exact(
        payload.get("customer_evidence_disposition"),
        "characterization_only",
        f"{label}.customer_evidence_disposition",
    )
    _require_exact(
        payload.get("publication_status"),
        "candidate_not_published",
        f"{label}.publication_status",
    )


def build_snapshot_record(
    *,
    manifest_path: Path,
    pack_intent_path: Path,
    producer_repo: str,
    producer_workflow: str,
    producer_branch: str,
    producer_run_id: str,
    producer_run_attempt: str,
    producer_head_sha: str,
    producer_artifact: str,
    producer_artifact_id: str,
    producer_artifact_digest: str,
    bundle_filename: str,
    bundle_sha256: str,
    whitepaper_repo: str,
    whitepaper_commit: str,
) -> dict[str, Any]:
    """Return an idempotent snapshot record and persistence policy."""

    _require_exact(producer_repo, PRODUCER_REPO, "producer.repo")
    if producer_workflow not in {NIGHTLY_WORKFLOW, RELEASE_WORKFLOW}:
        raise AnchorError(f"unsupported producer workflow: {producer_workflow!r}")
    primary_artifact = producer_artifact == PRIMARY_ARTIFACT or bool(
        re.fullmatch(rf"{re.escape(PRIMARY_ARTIFACT)}-[1-9][0-9]*", producer_artifact)
    )
    if not primary_artifact and producer_artifact != LEGACY_ARTIFACT:
        raise AnchorError(f"unsupported producer artifact: {producer_artifact!r}")
    if bundle_filename not in {PRIMARY_BUNDLE, LEGACY_BUNDLE}:
        raise AnchorError(f"unsupported bundle filename: {bundle_filename!r}")
    expected_bundle = PRIMARY_BUNDLE if primary_artifact else LEGACY_BUNDLE
    _require_exact(
        bundle_filename, expected_bundle, "producer artifact bundle filename"
    )
    _require_exact(whitepaper_repo, WHITEPAPER_REPO, "whitepaper.repo")

    producer_run_id = _require_match(producer_run_id, _RUN_ID_RE, "producer run ID")
    producer_run_attempt = _require_match(
        producer_run_attempt, _RUN_ID_RE, "producer run attempt"
    )
    if producer_artifact == PRIMARY_ARTIFACT:
        if producer_run_attempt != "1":
            raise AnchorError(
                "unqualified primary artifacts are restricted to producer run attempt 1"
            )
    elif producer_artifact == LEGACY_ARTIFACT:
        if producer_run_attempt != "1":
            raise AnchorError(
                "legacy reviewer-pack artifacts are restricted to producer run attempt 1"
            )
    else:
        _require_exact(
            producer_artifact,
            f"{PRIMARY_ARTIFACT}-{producer_run_attempt}",
            "producer artifact run-attempt qualification",
        )
    producer_artifact_id = _require_match(
        producer_artifact_id, _RUN_ID_RE, "producer artifact ID"
    )
    producer_artifact_digest = _require_match(
        producer_artifact_digest,
        _ARTIFACT_DIGEST_RE,
        "producer artifact digest",
    )
    producer_head_sha = _require_match(
        producer_head_sha, _SHA_RE, "producer run head SHA"
    )
    bundle_sha256 = _require_match(bundle_sha256, _SHA256_RE, "bundle SHA-256")
    whitepaper_commit = _require_match(
        whitepaper_commit, _SHA_RE, "whitepaper base commit"
    )

    manifest = _read_json(manifest_path)
    _require_exact(manifest.get("schema_version"), "wp-intake.v1", "manifest schema")
    product_sha = _require_match(
        manifest.get("commit_sha")
        or manifest.get("code_commit")
        or manifest.get("source_commit"),
        _SHA_RE,
        "producer product commit",
    )
    _require_exact(
        producer_head_sha,
        product_sha,
        "producer run head SHA versus bundle product commit",
    )
    consumer_stamp = manifest.get("whitepaper_consumer") or {}
    stamp_producer = consumer_stamp.get("producer") or {}
    expected_stamp = {
        "repo": producer_repo,
        "workflow": producer_workflow,
        "artifact": producer_artifact,
        "bundle_filename": bundle_filename,
        "bundle_sha256": bundle_sha256,
        "branch": producer_branch,
        "run_id": producer_run_id,
        "run_attempt": producer_run_attempt,
        "head_sha": producer_head_sha,
        "artifact_id": producer_artifact_id,
        "artifact_digest": producer_artifact_digest,
    }
    _require_exact(
        consumer_stamp.get("schema_version"),
        "flbsa.whitepaper_consumer.v3",
        "consumer stamp schema",
    )
    _require_exact(consumer_stamp.get("repo"), whitepaper_repo, "consumer stamp repo")
    _require_exact(
        consumer_stamp.get("base_commit"),
        whitepaper_commit,
        "consumer stamp base commit",
    )
    for field, expected in expected_stamp.items():
        _require_exact(
            stamp_producer.get(field), expected, f"consumer stamp producer {field}"
        )

    pack_intent = _read_json(pack_intent_path)
    _require_exact(
        pack_intent.get("schema_version"), "wp.pack_intent.v1", "pack intent schema"
    )
    _require_exact(pack_intent.get("purpose"), "intake", "pack intent purpose")
    _require_exact(pack_intent.get("evidence_grade"), False, "pack evidence_grade")
    _require_exact(
        pack_intent.get("certificate_signing_expected"),
        False,
        "pack certificate_signing_expected",
    )

    if producer_workflow == NIGHTLY_WORKFLOW:
        mode = "rolling_history"
        branch = ROLLING_BRANCH
        workflow_rewrite_allowed = True
    else:
        mode = "workflow_write_once_release_snapshot"
        branch = f"chore/wp-intake-{product_sha[:12]}-{producer_run_id}"
        workflow_rewrite_allowed = False

    identity = {
        "producer_repo": producer_repo,
        "producer_workflow": producer_workflow,
        "producer_branch": producer_branch,
        "producer_run_id": producer_run_id,
        "producer_run_attempt": producer_run_attempt,
        "producer_head_sha": producer_head_sha,
        "producer_artifact": producer_artifact,
        "producer_artifact_id": producer_artifact_id,
        "producer_artifact_digest": producer_artifact_digest,
        "product_sha": product_sha,
        "bundle_filename": bundle_filename,
        "bundle_sha256": bundle_sha256,
        "whitepaper_repo": whitepaper_repo,
        "whitepaper_base_commit": whitepaper_commit,
    }
    snapshot_id = _sha256_bytes(_canonical_json(identity))

    return {
        "schema_version": SNAPSHOT_SCHEMA,
        "snapshot_id": snapshot_id,
        "claims": {
            "customer_evidence_eligible": False,
            "customer_evidence_disposition": "characterization_only",
            "publication_status": "candidate_not_published",
        },
        "producer": {
            "repo": producer_repo,
            "workflow": producer_workflow,
            "branch": producer_branch,
            "run_id": producer_run_id,
            "run_attempt": producer_run_attempt,
            "head_sha": producer_head_sha,
            "artifact": producer_artifact,
            "artifact_id": producer_artifact_id,
            "artifact_digest": producer_artifact_digest,
            "product_sha": product_sha,
            "bundle_filename": bundle_filename,
            "bundle_sha256": bundle_sha256,
        },
        "whitepaper": {
            "repo": whitepaper_repo,
            "base_commit": whitepaper_commit,
            "manifest_sha256": _sha256_file(manifest_path),
            "pack_intent_sha256": _sha256_file(pack_intent_path),
        },
        "persistence": {
            "mode": mode,
            "branch": branch,
            "workflow_rewrite_allowed": workflow_rewrite_allowed,
            "repository_admin_mutable": True,
        },
    }


def _git(root: Path, *args: str, binary: bool = False) -> bytes | str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise AnchorError(f"git {' '.join(args)} failed: {stderr}")
    if binary:
        return completed.stdout
    return completed.stdout.decode("utf-8").strip()


def _validate_export_entries(entries: Any) -> list[dict[str, str]]:
    try:
        return validate_entries(entries)
    except StableExportError as exc:
        raise AnchorError(str(exc)) from exc


def _validate_publication_input_paths(paths: Any) -> list[str]:
    if not isinstance(paths, list) or not paths:
        raise AnchorError("publication_inputs.paths must be a non-empty list")
    validated: list[str] = []
    for index, value in enumerate(paths):
        path = str(value or "")
        parts = PurePosixPath(path).parts
        if (
            not path
            or not _REPO_PATH_RE.fullmatch(path)
            or path.startswith("/")
            or path.endswith("/")
            or "." in parts
            or ".." in parts
        ):
            raise AnchorError(
                f"unsafe publication input path at index {index}: {path!r}"
            )
        if path != "config" and not path.startswith("intake/"):
            raise AnchorError(
                f"publication input path is outside intake/config: {path!r}"
            )
        if path == "intake/archive" or path.startswith("intake/archive/"):
            raise AnchorError(
                f"publication input path includes traceability archive: {path!r}"
            )
        validated.append(path)
    if validated != sorted(set(validated)):
        raise AnchorError("publication_inputs.paths must be unique and sorted")
    return validated


def build_publication_input_projection(
    anchor: dict[str, Any], repo_root: Path, commit: str
) -> dict[str, Any]:
    """Return the descriptor-selected publication-input projection for ``commit``."""

    publication_inputs = anchor.get("publication_inputs")
    if not isinstance(publication_inputs, dict):
        raise AnchorError("anchor publication_inputs block is required")
    _require_exact(
        publication_inputs.get("algorithm"),
        PUBLICATION_PROJECTION_ALGORITHM,
        "publication input projection algorithm",
    )
    paths = _validate_publication_input_paths(publication_inputs.get("paths"))
    commit = _require_match(commit, _SHA_RE, "publication projection commit")
    _git(repo_root, "cat-file", "-e", f"{commit}^{{commit}}")

    entries: list[dict[str, str]] = []
    for path in paths:
        git_oid = str(_git(repo_root, "rev-parse", f"{commit}:{path}"))
        git_type = str(_git(repo_root, "cat-file", "-t", git_oid))
        if git_type not in {"blob", "tree"}:
            raise AnchorError(
                f"publication input {path!r} resolves to unsupported Git type {git_type!r}"
            )
        entries.append({"git_oid": git_oid, "git_type": git_type, "path": path})

    digest = _sha256_bytes(_canonical_json({"entries": entries}))
    return {
        "algorithm": PUBLICATION_PROJECTION_ALGORITHM,
        "path_count": len(paths),
        "sha256": digest,
    }


def validate_anchor(anchor_path: Path, repo_root: Path) -> dict[str, Any]:
    """Validate a stable baseline descriptor and its pinned Git objects."""

    anchor = _read_json(anchor_path)
    _require_exact(anchor.get("schema_version"), ANCHOR_SCHEMA, "anchor schema")
    _require_exact(anchor.get("anchor_id"), STABLE_ANCHOR_ID, "anchor ID")
    _require_claim_boundary(anchor.get("claims") or {}, label="anchor.claims")

    producer = anchor.get("producer")
    consumer = anchor.get("consumer")
    export = anchor.get("export")
    if not isinstance(producer, dict) or not isinstance(consumer, dict):
        raise AnchorError("anchor producer and consumer blocks are required")
    if not isinstance(export, dict):
        raise AnchorError("anchor export block is required")

    _require_exact(producer.get("repo"), PRODUCER_REPO, "anchor producer repo")
    _require_exact(
        producer.get("workflow"), RELEASE_WORKFLOW, "anchor producer workflow"
    )
    _require_exact(producer.get("artifact"), PRIMARY_ARTIFACT, "anchor artifact")
    _require_exact(producer.get("bundle_filename"), PRIMARY_BUNDLE, "anchor bundle")
    _require_exact(
        producer.get("release_tag"), STABLE_RELEASE_TAG, "anchor release tag"
    )
    product_sha = _require_match(
        producer.get("product_sha"), _SHA_RE, "anchor producer product SHA"
    )
    _require_exact(
        producer.get("branch"),
        f"release/{STABLE_RELEASE_TAG}-{product_sha[:8]}",
        "anchor producer branch",
    )
    producer_run_id = _require_match(
        producer.get("run_id"), _RUN_ID_RE, "anchor producer run ID"
    )
    bundle_sha256 = _require_match(
        producer.get("bundle_sha256"), _SHA256_RE, "anchor bundle SHA-256"
    )

    _require_exact(consumer.get("repo"), WHITEPAPER_REPO, "anchor consumer repo")
    commit = _require_match(consumer.get("intake_commit"), _SHA_RE, "intake commit")
    intake_tree = _require_match(
        consumer.get("intake_tree_git_oid"), _SHA_RE, "intake tree Git OID"
    )
    config_tree = _require_match(
        consumer.get("config_tree_git_oid"), _SHA_RE, "config tree Git OID"
    )
    manifest_sha = _require_match(
        consumer.get("manifest_sha256"), _SHA256_RE, "manifest SHA-256"
    )
    pack_intent_sha = _require_match(
        consumer.get("pack_intent_sha256"), _SHA256_RE, "pack intent SHA-256"
    )

    _git(repo_root, "cat-file", "-e", f"{commit}^{{commit}}")
    _require_exact(
        _git(repo_root, "rev-parse", f"{commit}:intake"),
        intake_tree,
        "pinned intake tree",
    )
    _require_exact(
        _git(repo_root, "rev-parse", f"{commit}:config"),
        config_tree,
        "pinned config tree",
    )

    manifest_bytes = _git(
        repo_root, "show", f"{commit}:intake/manifest.json", binary=True
    )
    assert isinstance(manifest_bytes, bytes)
    _require_exact(_sha256_bytes(manifest_bytes), manifest_sha, "pinned manifest hash")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnchorError(
            f"pinned intake manifest is not valid UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(manifest, dict):
        raise AnchorError("pinned intake manifest must be a JSON object")
    _require_exact(
        manifest.get("schema_version"), "wp-intake.v1", "pinned manifest schema"
    )
    _require_exact(manifest.get("commit_sha"), product_sha, "pinned product SHA")
    consumer_stamp = manifest.get("whitepaper_consumer") or {}
    stamp_producer = consumer_stamp.get("producer") or {}
    _require_exact(consumer_stamp.get("repo"), WHITEPAPER_REPO, "consumer repo")
    _require_exact(stamp_producer.get("repo"), PRODUCER_REPO, "consumer producer repo")
    _require_exact(
        stamp_producer.get("workflow"), RELEASE_WORKFLOW, "consumer workflow"
    )
    _require_exact(
        stamp_producer.get("branch"), producer["branch"], "consumer producer branch"
    )
    _require_exact(stamp_producer.get("run_id"), producer_run_id, "consumer run ID")
    _require_exact(
        stamp_producer.get("artifact"), PRIMARY_ARTIFACT, "consumer artifact"
    )
    _require_exact(
        stamp_producer.get("bundle_filename"), PRIMARY_BUNDLE, "consumer bundle"
    )
    _require_exact(
        stamp_producer.get("bundle_sha256"), bundle_sha256, "consumer bundle SHA-256"
    )

    pack_bytes = _git(
        repo_root, "show", f"{commit}:intake/pack_intent.json", binary=True
    )
    assert isinstance(pack_bytes, bytes)
    _require_exact(_sha256_bytes(pack_bytes), pack_intent_sha, "pack intent hash")
    try:
        pack_intent = json.loads(pack_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnchorError(f"pinned pack intent is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(pack_intent, dict):
        raise AnchorError("pinned pack intent must be a JSON object")
    _require_exact(
        pack_intent.get("schema_version"),
        "wp.pack_intent.v1",
        "pinned pack intent schema",
    )
    _require_exact(pack_intent.get("purpose"), "intake", "pinned pack purpose")
    _require_exact(pack_intent.get("evidence_grade"), False, "pinned evidence_grade")
    _require_exact(
        pack_intent.get("certificate_signing_expected"),
        False,
        "pinned certificate_signing_expected",
    )

    _validate_export_entries(export.get("entries"))
    _require_exact(
        export.get("format"),
        "whitepaper_intake_bundle_v4_compat",
        "export format",
    )
    _require_exact(export.get("filename"), PRIMARY_BUNDLE, "export filename")
    script_path = repo_root / str(export.get("script") or "")
    script_sha = _require_match(
        export.get("script_sha256"), _SHA256_RE, "export script SHA-256"
    )
    _require_exact(_sha256_file(script_path), script_sha, "export script hash")
    _require_match(export.get("expected_sha256"), _SHA256_RE, "export SHA-256")

    publication_inputs = anchor.get("publication_inputs")
    if not isinstance(publication_inputs, dict):
        raise AnchorError("anchor publication_inputs block is required")
    expected_projection_sha = _require_match(
        publication_inputs.get("expected_sha256"),
        _SHA256_RE,
        "publication input projection SHA-256",
    )
    historical_projection = build_publication_input_projection(
        anchor, repo_root, commit
    )
    _require_exact(
        historical_projection["sha256"],
        expected_projection_sha,
        "historical publication input projection",
    )

    return anchor


def validate_publication_source(
    anchor: dict[str, Any], repo_root: Path, whitepaper_commit: str
) -> dict[str, Any]:
    """Bind source inputs to the anchor while recording whole-tree identities."""

    whitepaper_commit = _require_match(
        whitepaper_commit, _SHA_RE, "publication source commit"
    )
    _git(repo_root, "cat-file", "-e", f"{whitepaper_commit}^{{commit}}")
    intake_tree = str(_git(repo_root, "rev-parse", f"{whitepaper_commit}:intake"))
    config_tree = str(_git(repo_root, "rev-parse", f"{whitepaper_commit}:config"))
    projection = build_publication_input_projection(
        anchor, repo_root, whitepaper_commit
    )
    _require_exact(
        projection["sha256"],
        anchor["publication_inputs"]["expected_sha256"],
        "publication source input projection",
    )
    source_tree = str(_git(repo_root, "rev-parse", f"{whitepaper_commit}^{{tree}}"))
    return {
        "commit": whitepaper_commit,
        "source_tree_git_oid": source_tree,
        "intake_tree_git_oid": intake_tree,
        "config_tree_git_oid": config_tree,
        "publication_input_projection": projection,
    }


def export_anchor(anchor_path: Path, repo_root: Path, output_path: Path) -> str:
    """Export a deterministic baseline ZIP and return its SHA-256."""

    anchor = validate_anchor(anchor_path, repo_root)
    commit = str(anchor["consumer"]["intake_commit"])
    entries = _validate_export_entries(anchor["export"]["entries"])
    try:
        archive = build_archive(repo_root, commit, entries)
    except StableExportError as exc:
        raise AnchorError(str(exc)) from exc
    archive_sha = _sha256_bytes(archive)
    _require_exact(
        archive_sha,
        anchor["export"]["expected_sha256"],
        "deterministic export SHA-256",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(archive)
    return archive_sha


def _append_github_env(path: Path, record: dict[str, Any]) -> None:
    persistence = record["persistence"]
    values = {
        "INTAKE_SNAPSHOT_ID": record["snapshot_id"],
        "INTAKE_SNAPSHOT_MODE": persistence["mode"],
        "INTAKE_SNAPSHOT_BRANCH": persistence["branch"],
    }
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def _snapshot_command(args: argparse.Namespace) -> int:
    record = build_snapshot_record(
        manifest_path=Path(args.manifest),
        pack_intent_path=Path(args.pack_intent),
        producer_repo=args.producer_repo,
        producer_workflow=args.producer_workflow,
        producer_branch=args.producer_branch,
        producer_run_id=args.producer_run_id,
        producer_run_attempt=args.producer_run_attempt,
        producer_head_sha=args.producer_head_sha,
        producer_artifact=args.producer_artifact,
        producer_artifact_id=args.producer_artifact_id,
        producer_artifact_digest=args.producer_artifact_digest,
        bundle_filename=args.bundle_filename,
        bundle_sha256=args.bundle_sha256,
        whitepaper_repo=args.whitepaper_repo,
        whitepaper_commit=args.whitepaper_commit,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if args.github_env:
        _append_github_env(Path(args.github_env), record)
    print(
        json.dumps(
            {
                "snapshot_id": record["snapshot_id"],
                "mode": record["persistence"]["mode"],
                "branch": record["persistence"]["branch"],
            },
            sort_keys=True,
        )
    )
    return 0


def _validate_command(args: argparse.Namespace) -> int:
    anchor = validate_anchor(Path(args.anchor), Path(args.repo_root))
    print(
        json.dumps(
            {
                "anchor_id": anchor["anchor_id"],
                "intake_commit": anchor["consumer"]["intake_commit"],
                "product_sha": anchor["producer"]["product_sha"],
                "status": "valid",
            },
            sort_keys=True,
        )
    )
    return 0


def _export_command(args: argparse.Namespace) -> int:
    digest = export_anchor(Path(args.anchor), Path(args.repo_root), Path(args.output))
    print(json.dumps({"output": args.output, "sha256": digest}, sort_keys=True))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser(
        "snapshot", help="write a deterministic snapshot record"
    )
    snapshot.add_argument("--manifest", required=True)
    snapshot.add_argument("--pack-intent", required=True)
    snapshot.add_argument("--producer-repo", required=True)
    snapshot.add_argument("--producer-workflow", required=True)
    snapshot.add_argument("--producer-branch", required=True)
    snapshot.add_argument("--producer-run-id", required=True)
    snapshot.add_argument("--producer-run-attempt", required=True)
    snapshot.add_argument("--producer-head-sha", required=True)
    snapshot.add_argument("--producer-artifact", required=True)
    snapshot.add_argument("--producer-artifact-id", required=True)
    snapshot.add_argument("--producer-artifact-digest", required=True)
    snapshot.add_argument("--bundle-filename", required=True)
    snapshot.add_argument("--bundle-sha256", required=True)
    snapshot.add_argument("--whitepaper-repo", required=True)
    snapshot.add_argument("--whitepaper-commit", required=True)
    snapshot.add_argument("--output", required=True)
    snapshot.add_argument("--github-env")
    snapshot.set_defaults(func=_snapshot_command)

    validate = subparsers.add_parser("validate", help="validate a pinned intake anchor")
    validate.add_argument("--anchor", required=True)
    validate.add_argument("--repo-root", default=".")
    validate.set_defaults(func=_validate_command)

    export = subparsers.add_parser("export", help="export a deterministic baseline ZIP")
    export.add_argument("--anchor", required=True)
    export.add_argument("--repo-root", default=".")
    export.add_argument("--output", required=True)
    export.set_defaults(func=_export_command)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except AnchorError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
