#!/usr/bin/env python3
"""Create the public robustness projection without machine-local path fields."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from public_path_policy import FORBIDDEN_PUBLIC_PATH_MARKERS
except ModuleNotFoundError:  # Imported as scripts.sanitize_robustness_summary in tests.
    from scripts.public_path_policy import FORBIDDEN_PUBLIC_PATH_MARKERS


ALGORITHM = "remove-machine-local-path-fields.v1"
REMOVED_FIELDS = ("run_dir", "scenario_dir")
EXPECTED_REMOVALS = {"run_dir": 40, "scenario_dir": 40}


class ProjectionError(ValueError):
    """Raised when the source or resulting public projection is not exact."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strip_machine_paths(value: Any, counts: dict[str, int]) -> Any:
    if isinstance(value, dict):
        projected: dict[str, Any] = {}
        for key, child in value.items():
            if key in REMOVED_FIELDS:
                if not isinstance(child, str) or not child.startswith("/"):
                    raise ProjectionError(f"{key} must be an absolute source path")
                counts[key] += 1
                continue
            projected[key] = _strip_machine_paths(child, counts)
        return projected
    if isinstance(value, list):
        return [_strip_machine_paths(child, counts) for child in value]
    return value


def project(source_bytes: bytes, *, expected_source_sha256: str) -> bytes:
    if _sha256(source_bytes) != expected_source_sha256:
        raise ProjectionError("source robustness summary SHA-256 mismatch")
    try:
        source = json.loads(source_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectionError(f"invalid robustness summary JSON: {exc}") from exc
    if (
        not isinstance(source, dict)
        or source.get("schema_version") != "gold.robustness.v1"
    ):
        raise ProjectionError("unsupported robustness summary schema")

    counts = {field: 0 for field in REMOVED_FIELDS}
    projected = _strip_machine_paths(source, counts)
    if counts != EXPECTED_REMOVALS:
        raise ProjectionError(
            f"unexpected machine-local field counts: expected {EXPECTED_REMOVALS}, got {counts}"
        )

    output = (json.dumps(projected, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output_text = output.decode("utf-8")
    for marker_bytes in FORBIDDEN_PUBLIC_PATH_MARKERS:
        marker = marker_bytes.decode("ascii")
        if marker in output_text:
            raise ProjectionError(
                f"public projection still contains forbidden path: {marker}"
            )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    output = project(
        args.source.read_bytes(),
        expected_source_sha256=args.expected_source_sha256,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    print(
        json.dumps(
            {
                "algorithm": ALGORITHM,
                "output": str(args.output),
                "sha256": _sha256(output),
                "removed_fields": EXPECTED_REMOVALS,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
