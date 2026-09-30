#!/usr/bin/env python3
"""Verify live GitHub producer state against the v5.0.8 technical source lock."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn


class ProducerStateError(ValueError):
    """Raised when GitHub producer state differs from the reviewed source lock."""


def _fail(message: str) -> NoReturn:
    raise ProducerStateError(message)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProducerStateError(f"unable to read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        _fail(f"JSON root must be an object: {path}")
    return value


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail(f"{label} must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ProducerStateError(f"{label} is not a valid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        _fail(f"{label} must use UTC")
    return parsed


def _repository(run: dict[str, Any]) -> Any:
    repository = run.get("repository")
    if isinstance(repository, dict):
        return repository.get("full_name")
    return repository


def _validate_run(
    run: dict[str, Any],
    *,
    lock: dict[str, Any],
    attempt: int,
    conclusion: str,
    started_at: str,
    updated_at: str | None,
    label: str,
) -> None:
    evidence = lock["release_evidence"]
    product = lock["product"]
    expected = {
        "id": evidence["run_id"],
        "run_attempt": attempt,
        "status": "completed",
        "conclusion": conclusion,
        "event": evidence["event"],
        "head_branch": evidence["branch"],
        "head_sha": product["commit"],
        "run_started_at": started_at,
    }
    for field, value in expected.items():
        if run.get(field) != value:
            _fail(f"{label} {field} differs from the source lock")
    path = run.get("path")
    if not isinstance(path, str) or path.split("@", 1)[0] != evidence["workflow_path"]:
        _fail(f"{label} workflow path differs from the source lock")
    if _repository(run) != lock["product_source_record"]["repository"]:
        _fail(f"{label} repository differs from the source lock")
    if updated_at is not None and run.get("updated_at") != updated_at:
        _fail(f"{label} updated_at differs from the source lock")


def _validate_jobs(payload: dict[str, Any], lock: dict[str, Any]) -> None:
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        _fail("producer jobs payload has no jobs array")
    locked_sources = lock["sources"]
    expected_by_id = {
        source["producer_job"]["id"]: source["producer_job"]
        for source in locked_sources.values()
    }
    matched: dict[int, dict[str, Any]] = {}
    for job in jobs:
        if not isinstance(job, dict):
            _fail("producer jobs payload contains a non-object")
        job_id = job.get("id")
        if job_id in expected_by_id:
            if job_id in matched:
                _fail(f"producer job ID is duplicated: {job_id}")
            matched[job_id] = job
    if set(matched) != set(expected_by_id):
        _fail("one or more exact producer jobs are absent")
    for job_id, expected in expected_by_id.items():
        actual = matched[job_id]
        checks = {
            "name": expected["name"],
            "status": "completed",
            "conclusion": expected["conclusion"],
            "started_at": expected["started_at"],
            "completed_at": expected["completed_at"],
            "run_attempt": lock["release_evidence"]["source_attempt"],
        }
        for field, value in checks.items():
            if actual.get(field) != value:
                _fail(f"producer job {job_id} {field} differs from the source lock")


def _validate_artifact(
    artifact: dict[str, Any],
    *,
    source: dict[str, Any],
    lock: dict[str, Any],
    now: datetime,
    label: str,
) -> None:
    archive = source["actions_archive"]
    checks = {
        "id": archive["id"],
        "name": archive["name"],
        "size_in_bytes": archive["size_bytes"],
        "digest": archive["digest"],
        "created_at": archive["created_at"],
        "expires_at": archive["expires_at"],
        "expired": False,
    }
    for field, value in checks.items():
        if artifact.get(field) != value:
            _fail(f"{label} artifact {field} differs from the source lock")
    if _time(archive["expires_at"], f"{label} expiry") <= now:
        _fail(f"{label} Actions artifact has expired")
    workflow_run = artifact.get("workflow_run")
    if not isinstance(workflow_run, dict):
        _fail(f"{label} artifact workflow identity is missing")
    expected_workflow = {
        "id": lock["release_evidence"]["run_id"],
        "head_branch": lock["release_evidence"]["branch"],
        "head_sha": lock["product"]["commit"],
    }
    for field, value in expected_workflow.items():
        if workflow_run.get(field) != value:
            _fail(f"{label} artifact workflow {field} differs from the source lock")


def verify(
    *,
    lock_path: Path,
    current_run_path: Path,
    source_run_path: Path,
    jobs_path: Path,
    intake_artifact_path: Path,
    robustness_artifact_path: Path,
    current_run_after_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify exact current/source attempts, producer jobs, and artifact metadata."""

    lock = _json(lock_path)
    evidence = lock["release_evidence"]
    current = _json(current_run_path)
    _validate_run(
        current,
        lock=lock,
        attempt=evidence["current_attempt"],
        conclusion=evidence["current_attempt_conclusion"],
        started_at=evidence["current_attempt_started_at"],
        updated_at=None,
        label="current producer run",
    )
    source = _json(source_run_path)
    _validate_run(
        source,
        lock=lock,
        attempt=evidence["source_attempt"],
        conclusion=evidence["source_attempt_conclusion"],
        started_at=evidence["source_attempt_started_at"],
        updated_at=evidence["source_attempt_updated_at"],
        label="source producer attempt",
    )
    _validate_jobs(_json(jobs_path), lock)
    observed_at = now or datetime.now(timezone.utc)
    _validate_artifact(
        _json(intake_artifact_path),
        source=lock["sources"]["intake"],
        lock=lock,
        now=observed_at,
        label="intake",
    )
    _validate_artifact(
        _json(robustness_artifact_path),
        source=lock["sources"]["robustness"],
        lock=lock,
        now=observed_at,
        label="robustness",
    )
    if current_run_after_path is not None:
        current_after = _json(current_run_after_path)
        _validate_run(
            current_after,
            lock=lock,
            attempt=evidence["current_attempt"],
            conclusion=evidence["current_attempt_conclusion"],
            started_at=evidence["current_attempt_started_at"],
            updated_at=None,
            label="post-download producer run",
        )
        stable_fields = {
            "id",
            "run_attempt",
            "status",
            "conclusion",
            "event",
            "head_branch",
            "head_sha",
            "path",
            "run_started_at",
            "updated_at",
        }
        if {field: current.get(field) for field in stable_fields} != {
            field: current_after.get(field) for field in stable_fields
        }:
            _fail("producer run changed while source artifacts were downloaded")

    return {
        "verified": True,
        "run_id": evidence["run_id"],
        "source_attempt": evidence["source_attempt"],
        "current_attempt": evidence["current_attempt"],
        "intake_artifact_id": lock["sources"]["intake"]["actions_archive"]["id"],
        "robustness_artifact_id": lock["sources"]["robustness"]["actions_archive"][
            "id"
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-lock", type=Path, required=True)
    parser.add_argument("--current-run", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--source-jobs", type=Path, required=True)
    parser.add_argument("--intake-artifact", type=Path, required=True)
    parser.add_argument("--robustness-artifact", type=Path, required=True)
    parser.add_argument("--current-run-after", type=Path)
    args = parser.parse_args()
    try:
        result = verify(
            lock_path=args.source_lock,
            current_run_path=args.current_run,
            source_run_path=args.source_run,
            jobs_path=args.source_jobs,
            intake_artifact_path=args.intake_artifact,
            robustness_artifact_path=args.robustness_artifact,
            current_run_after_path=args.current_run_after,
        )
    except (KeyError, OSError, ProducerStateError) as exc:
        print(f"producer-state verification failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
