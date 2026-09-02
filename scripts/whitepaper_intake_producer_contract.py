#!/usr/bin/env python3
"""Build and validate the versioned FL-BSA-to-whitepaper intake handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "flbsa.whitepaper_intake_producer_contract.v1"
PRODUCER_REPOSITORY = "equilens-labs/fl-bsa"
DISPATCH_EVENT_TYPE = "wp-intake-ready"
PRIMARY_ARTIFACT_TEMPLATE = "wp-intake-bundle-v4-{run_attempt}"
ALLOWED_EVENTS = frozenset({"repository_dispatch"})
EXPECTED_CONTRACT_KEYS = frozenset(
    {
        "allowed_persistence_values",
        "authorities",
        "dispatch_event_type",
        "dispatch_payload_fields",
        "primary_artifact_template",
        "producer_repository",
        "schema_version",
    }
)
EXPECTED_AUTHORITY_KEYS = frozenset({"branch", "events", "workflow"})
EXPECTED_DISPATCH_FIELDS = frozenset(
    {
        "artifact_digest",
        "artifact_id",
        "artifact_name",
        "branch",
        "persist_intake_pr",
        "producer_contract_sha256",
        "producer_repo",
        "producer_run_attempt",
        "producer_run_id",
        "workflow_file",
    }
)
_POSITIVE_DECIMAL_RE = re.compile(r"^[1-9][0-9]*$")
_ARTIFACT_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ContractError(ValueError):
    """Raised when producer and consumer do not share one exact handoff contract."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key is not allowed: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ContractError(f"non-finite JSON number is not allowed: {value}")


def _parse_json(raw: bytes | str, *, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"{label} must be a JSON object")
    return payload


def load_contract(path: Path) -> tuple[dict[str, Any], str]:
    """Load, structurally validate, and hash an intake producer contract."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ContractError(f"unable to read producer contract {path}: {exc}") from exc
    if not raw or len(raw) > 64 * 1024:
        raise ContractError("producer contract has an unsafe size")
    contract = _parse_json(raw, label="producer contract")
    if set(contract) != EXPECTED_CONTRACT_KEYS:
        raise ContractError("producer contract does not contain the exact v1 fields")
    if contract["schema_version"] != SCHEMA_VERSION:
        raise ContractError("unsupported producer contract schema")
    if contract["producer_repository"] != PRODUCER_REPOSITORY:
        raise ContractError("producer contract names an unreviewed repository")
    if contract["dispatch_event_type"] != DISPATCH_EVENT_TYPE:
        raise ContractError("producer contract names an unreviewed dispatch event")
    if contract["primary_artifact_template"] != PRIMARY_ARTIFACT_TEMPLATE:
        raise ContractError("producer contract names an unreviewed artifact template")
    if contract["allowed_persistence_values"] != ["false"]:
        raise ContractError("producer contract must keep public persistence disabled")

    fields = contract["dispatch_payload_fields"]
    if (
        not isinstance(fields, list)
        or any(type(field) is not str for field in fields)
        or len(fields) != len(set(fields))
        or set(fields) != EXPECTED_DISPATCH_FIELDS
    ):
        raise ContractError("producer contract has an invalid dispatch field set")

    authorities = contract["authorities"]
    if not isinstance(authorities, list) or not authorities:
        raise ContractError("producer contract must name at least one authority")
    seen: set[tuple[str, str]] = set()
    for index, authority in enumerate(authorities):
        if not isinstance(authority, dict) or set(authority) != EXPECTED_AUTHORITY_KEYS:
            raise ContractError(f"producer authority {index} has invalid fields")
        workflow = authority["workflow"]
        branch = authority["branch"]
        events = authority["events"]
        if (
            type(workflow) is not str
            or not re.fullmatch(r"[A-Za-z0-9_.-]+\.ya?ml", workflow)
            or branch != "main"
            or not isinstance(events, list)
            or not events
            or any(type(event) is not str for event in events)
            or len(events) != len(set(events))
            or not set(events).issubset(ALLOWED_EVENTS)
        ):
            raise ContractError(f"producer authority {index} is malformed")
        identity = (workflow, branch)
        if identity in seen:
            raise ContractError("producer contract contains duplicate authorities")
        seen.add(identity)

    expected_authorities = {
        ("release-evidence.yml", "main"): {"repository_dispatch"},
    }
    actual_authorities = {
        (authority["workflow"], authority["branch"]): set(authority["events"])
        for authority in authorities
    }
    if actual_authorities != expected_authorities:
        raise ContractError("producer contract does not contain the reviewed v1 authorities")
    return contract, hashlib.sha256(raw).hexdigest()


def authority_events(
    contract: dict[str, Any],
    *,
    producer_repo: str,
    workflow: str,
    branch: str,
) -> frozenset[str]:
    """Return allowed events for one exact producer authority."""

    if producer_repo != contract["producer_repository"]:
        raise ContractError(f"unapproved producer repository: {producer_repo!r}")
    for authority in contract["authorities"]:
        if authority["workflow"] == workflow and authority["branch"] == branch:
            return frozenset(authority["events"])
    raise ContractError(f"unapproved producer workflow/branch: {workflow!r}@{branch!r}")


def validate_authority(
    contract: dict[str, Any],
    *,
    producer_repo: str,
    workflow: str,
    branch: str,
    event: str,
) -> None:
    """Validate one exact producer workflow, branch, and event."""

    events = authority_events(
        contract,
        producer_repo=producer_repo,
        workflow=workflow,
        branch=branch,
    )
    if event not in events:
        raise ContractError(f"unapproved producer workflow/event: {workflow!r}/{event!r}")


def validate_dispatch_payload(
    contract: dict[str, Any],
    contract_sha256: str,
    payload: dict[str, Any],
) -> dict[str, str]:
    """Validate the exact repository-dispatch payload shared by both repositories."""

    expected_fields = set(contract["dispatch_payload_fields"])
    if set(payload) != expected_fields:
        raise ContractError("dispatch payload does not contain the exact contract fields")
    if any(type(value) is not str for value in payload.values()):
        raise ContractError("dispatch payload fields must all be strings")
    typed = {key: str(value) for key, value in payload.items()}
    if (
        not _SHA256_RE.fullmatch(typed["producer_contract_sha256"])
        or typed["producer_contract_sha256"] != contract_sha256
    ):
        raise ContractError("dispatch payload producer contract digest does not match")
    authority_events(
        contract,
        producer_repo=typed["producer_repo"],
        workflow=typed["workflow_file"],
        branch=typed["branch"],
    )
    for field in ("producer_run_id", "producer_run_attempt", "artifact_id"):
        if not _POSITIVE_DECIMAL_RE.fullmatch(typed[field]):
            raise ContractError(f"dispatch payload {field} must be a positive decimal")
    if not _ARTIFACT_DIGEST_RE.fullmatch(typed["artifact_digest"]):
        raise ContractError("dispatch payload artifact_digest must be a SHA-256 digest")
    expected_artifact = contract["primary_artifact_template"].format(
        run_attempt=typed["producer_run_attempt"]
    )
    if typed["artifact_name"] != expected_artifact:
        raise ContractError(
            "dispatch payload artifact_name is not qualified by the exact run attempt"
        )
    if typed["persist_intake_pr"] not in contract["allowed_persistence_values"]:
        raise ContractError("dispatch payload requests unapproved public persistence")
    return typed


def build_dispatch_envelope(
    contract: dict[str, Any],
    contract_sha256: str,
    *,
    producer_repo: str,
    workflow: str,
    branch: str,
    producer_event: str,
    artifact_name: str,
    producer_run_id: str,
    producer_run_attempt: str,
    artifact_id: str,
    artifact_digest: str,
    persist_intake_pr: str,
) -> dict[str, Any]:
    """Build the one canonical dispatch envelope accepted by the consumer."""

    validate_authority(
        contract,
        producer_repo=producer_repo,
        workflow=workflow,
        branch=branch,
        event=producer_event,
    )
    payload: dict[str, Any] = {
        "artifact_digest": artifact_digest,
        "artifact_id": artifact_id,
        "artifact_name": artifact_name,
        "branch": branch,
        "persist_intake_pr": persist_intake_pr,
        "producer_contract_sha256": contract_sha256,
        "producer_repo": producer_repo,
        "producer_run_attempt": producer_run_attempt,
        "producer_run_id": producer_run_id,
        "workflow_file": workflow,
    }
    validated = validate_dispatch_payload(contract, contract_sha256, payload)
    return {
        "event_type": contract["dispatch_event_type"],
        "client_payload": validated,
    }


def _add_authority_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--producer-repo", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--branch", required=True)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    digest = subparsers.add_parser("contract-sha256")
    digest.add_argument("--contract", type=Path, required=True)

    selector = subparsers.add_parser("validate-selector")
    _add_authority_arguments(selector)

    authority = subparsers.add_parser("validate-authority")
    _add_authority_arguments(authority)
    authority.add_argument("--producer-event", required=True)

    dispatch = subparsers.add_parser("validate-dispatch")
    dispatch.add_argument("--contract", type=Path, required=True)
    dispatch.add_argument("--payload-env", required=True)

    build = subparsers.add_parser("build-dispatch")
    _add_authority_arguments(build)
    build.add_argument("--producer-event", required=True)
    build.add_argument("--artifact-name", required=True)
    build.add_argument("--producer-run-id", required=True)
    build.add_argument("--producer-run-attempt", required=True)
    build.add_argument("--artifact-id", required=True)
    build.add_argument("--artifact-digest", required=True)
    build.add_argument("--persist-intake-pr", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run one contract operation without external I/O."""

    args = _parse_args(argv)
    try:
        contract, digest = load_contract(args.contract)
        if args.command == "contract-sha256":
            print(digest)
        elif args.command == "validate-selector":
            authority_events(
                contract,
                producer_repo=args.producer_repo,
                workflow=args.workflow,
                branch=args.branch,
            )
            print(digest)
        elif args.command == "validate-authority":
            validate_authority(
                contract,
                producer_repo=args.producer_repo,
                workflow=args.workflow,
                branch=args.branch,
                event=args.producer_event,
            )
            print(digest)
        elif args.command == "validate-dispatch":
            raw_payload = os.environ.get(args.payload_env)
            if raw_payload is None:
                raise ContractError(f"payload environment variable is absent: {args.payload_env}")
            payload = _parse_json(raw_payload, label="dispatch payload")
            validate_dispatch_payload(contract, digest, payload)
            print(digest)
        else:
            envelope = build_dispatch_envelope(
                contract,
                digest,
                producer_repo=args.producer_repo,
                workflow=args.workflow,
                branch=args.branch,
                producer_event=args.producer_event,
                artifact_name=args.artifact_name,
                producer_run_id=args.producer_run_id,
                producer_run_attempt=args.producer_run_attempt,
                artifact_id=args.artifact_id,
                artifact_digest=args.artifact_digest,
                persist_intake_pr=args.persist_intake_pr,
            )
            print(json.dumps(envelope, sort_keys=True, separators=(",", ":")))
    except ContractError as exc:
        raise SystemExit(f"whitepaper intake producer contract failed: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
