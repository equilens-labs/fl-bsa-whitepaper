#!/usr/bin/env python3
"""Fail closed when private producer data crosses into the public repository.

The archive-member allowlist in ``pull-wp-intake.yml`` controls filenames. This
validator controls the disclosed structure and high-confidence sensitive content
inside those files. Incoming JSON/YAML fields and CSV columns must already exist
in the reviewed, tracked public baseline. A producer schema expansion therefore
requires an ordinary repository review before the new data can be ingested.
"""

from __future__ import annotations

import argparse
import csv
import ipaddress
import json
import math
import re
from pathlib import Path
from typing import Any

import yaml


class DisclosureError(ValueError):
    """Raised when an intake file is not safe for public disclosure."""


_MAX_TEXT_BYTES = 20 * 1024 * 1024
_MAX_CSV_ROWS = 100_000
_MAX_CSV_COLUMNS = 256
_MAX_CELL_OR_STRING_CHARS = 4_096

_SENSITIVE_KEY_TOKENS = {
    "access_key",
    "address",
    "api_key",
    "credentials",
    "customer_id",
    "email",
    "first_name",
    "full_name",
    "last_name",
    "password",
    "phone",
    "private_key",
    "raw_records",
    "raw_rows",
    "secret",
    "subject_id",
    "token",
}

_TEXT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "email address",
        re.compile(
            r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@"
            r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])"
        ),
    ),
    ("Unix home path", re.compile(r"/(?:home|Users)/[^/\s]+(?:/|(?=\s|$))")),
    (
        "Windows user path",
        re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s]+(?:\\|(?=\s|$))"),
    ),
    ("private key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    (
        "GitHub stateless installation token",
        re.compile(
            r"(?<![A-Za-z0-9._-])ghs_[0-9]{1,20}_"
            r"[A-Za-z0-9._-]{20,}(?![A-Za-z0-9._-])"
        ),
    ),
    (
        "GitHub token",
        re.compile(
            r"(?<![A-Za-z0-9._-])gh[pousr]_[A-Za-z0-9._-]{20,}"
            r"(?![A-Za-z0-9._-])"
        ),
    ),
    (
        "TeX control sequence",
        re.compile(r"\\[A-Za-z]+"),
    ),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("bearer credential", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
)
_IPV4_CANDIDATE = re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])")
_IPV6_CANDIDATE = re.compile(
    r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{0,4}:){2,}[0-9A-Fa-f]{0,4}"
    r"(?![0-9A-Fa-f:])"
)
_CONTROL_CHARACTER = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BROKEN_CORRELATION_ITEM_SCHEMA = {
    "column1": "",
    "column2": "",
    "difference": 0.0,
    "real_correlation": 0.0,
    "synthetic_correlation": 0.0,
}
_BROKEN_CORRELATIONS_SUFFIX = ".correlation_analysis.broken_correlations"
_RANGE_VIOLATION_ITEM_SCHEMA = {
    "real_range": [0.0],
    "synthetic_range": [0.0],
    "violation_type": "",
}
_RANGE_VIOLATIONS_SUFFIX = ".statistical_comparison.range_violations"
_CI_RUNTIME_PROVENANCE_SCHEMA = {
    "schema_version": "",
    "source_ci": {
        "repository": "",
        "workflow": "",
        "run_id": 0,
        "run_attempt": 0,
        "head_sha": "",
        "contract_artifact": {
            "id": 0,
            "name": "",
            "digest": "",
            "size_in_bytes": 0,
        },
    },
    "runtime_image": {
        "digest": "",
        "digest_ref": "",
        "api_digest_ref": "",
        "worker_digest_ref": "",
        "image_build_sha": "",
        "build_disposition": "",
        "runtime_input_projection": {"algorithm": "", "sha256": ""},
    },
    "claims": {"bounded_runtime_contract_verified": False, "full_ci_proven": False},
}
_CI_RUNTIME_MANIFEST_LOCATIONS = {
    "intake/manifest.json",
    "provenance/manifest.json",
}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CI_RUNTIME_BUILD_DISPOSITIONS = {
    "built_for_source",
    "reused_exact_sha_tag_matching_projection",
    "reused_exact_sha_tag_projection_equivalent",
    "reused_main_profile_latest_matching_projection",
}
_CI_RUNTIME_SAME_SOURCE_DISPOSITIONS = {
    "built_for_source",
    "reused_exact_sha_tag_matching_projection",
}


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise DisclosureError("YAML contains a duplicate key; key redacted")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DisclosureError("JSON contains a duplicate key; key redacted")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    del value
    raise DisclosureError("JSON contains a non-finite number")


def _read_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DisclosureError(f"unable to read {path}: {exc}") from exc
    if len(raw) > _MAX_TEXT_BYTES:
        raise DisclosureError(
            f"{path} exceeds the {_MAX_TEXT_BYTES}-byte disclosure limit"
        )
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DisclosureError(f"{path} is not UTF-8: {exc}") from exc


def _scan_text(value: str, location: str) -> None:
    if len(value) > _MAX_CELL_OR_STRING_CHARS:
        raise DisclosureError(
            f"{location} exceeds the {_MAX_CELL_OR_STRING_CHARS}-character value limit"
        )
    if _CONTROL_CHARACTER.search(value):
        raise DisclosureError(f"{location} contains a control character")
    for label, pattern in _TEXT_PATTERNS:
        if pattern.search(value):
            raise DisclosureError(f"{location} contains a high-confidence {label}")
    for candidate in _IPV4_CANDIDATE.findall(value) + _IPV6_CANDIDATE.findall(value):
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if address.is_private:
            raise DisclosureError(
                f"{location} contains a private IP address; value redacted"
            )


def _normalized_key(value: Any) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value))
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _is_sensitive_key(value: Any) -> bool:
    normalized = _normalized_key(value)
    wrapped = f"_{normalized}_"
    return any(f"_{token}_" in wrapped for token in _SENSITIVE_KEY_TOKENS)


def _scalar_kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def _validate_structure(
    candidate: Any, baseline: Any, location: str, *, depth: int = 0
) -> None:
    if depth > 64:
        raise DisclosureError(f"{location} exceeds the reviewed nesting-depth limit")
    # A producer may redact or omit a reviewed value by setting it to null. This
    # discloses no new structure. The inverse remains forbidden: a non-null
    # candidate cannot expand a baseline field whose only reviewed shape is null.
    if candidate is None:
        return
    if isinstance(candidate, dict):
        if not isinstance(baseline, dict):
            raise DisclosureError(
                f"{location} changed from {_scalar_kind(baseline)} to object"
            )
        if (
            not baseline
            and location.startswith("certificates/")
            and location.endswith(_RANGE_VIOLATIONS_SUFFIX)
        ):
            # Column names and exact value semantics are checked against the
            # certificate's already-reviewed matrix below. Use a redacted
            # location here so an invalid producer key cannot reach logs.
            for key, value in candidate.items():
                if _is_sensitive_key(key):
                    raise DisclosureError(
                        f"{location} contains a forbidden sensitive field; key redacted"
                    )
                _validate_structure(
                    value,
                    _RANGE_VIOLATION_ITEM_SCHEMA,
                    f"{location}.[reviewed-column]",
                    depth=depth + 1,
                )
            return
        for key, value in candidate.items():
            if _is_sensitive_key(key):
                raise DisclosureError(
                    f"{location} contains a forbidden sensitive field; key redacted"
                )
            if (
                location in _CI_RUNTIME_MANIFEST_LOCATIONS
                and key == "ci_runtime_provenance"
            ):
                # This is an explicitly reviewed extension, not a shape inferred
                # from whichever stable intake happens to be tracked today. Keep
                # enforcing its exact schema and bounded semantics after the
                # first accepted value becomes part of the public baseline.
                _validate_structure(
                    value,
                    _CI_RUNTIME_PROVENANCE_SCHEMA,
                    f"{location}.ci_runtime_provenance",
                    depth=depth + 1,
                )
                _validate_ci_runtime_provenance(
                    value, f"{location}.ci_runtime_provenance"
                )
                continue
            if key not in baseline:
                raise DisclosureError(
                    f"{location} contains a field outside the reviewed public schema; "
                    "key redacted"
                )
            _validate_structure(
                value, baseline[key], f"{location}.{key}", depth=depth + 1
            )
        return

    if isinstance(candidate, list):
        if not isinstance(baseline, list):
            raise DisclosureError(
                f"{location} changed from {_scalar_kind(baseline)} to array"
            )
        item_schemas = baseline
        if (
            not baseline
            and location.startswith("certificates/")
            and location.endswith(_BROKEN_CORRELATIONS_SUFFIX)
        ):
            # Stable-v5 happened to contain no broken pairs, but this aggregate's
            # shape is public and reviewed. Column membership is constrained
            # separately to names already disclosed by the tracked certificate.
            item_schemas = [_BROKEN_CORRELATION_ITEM_SCHEMA]
        if candidate and not item_schemas:
            raise DisclosureError(
                f"{location} has values but the reviewed public schema is empty"
            )
        for index, value in enumerate(candidate):
            failures: list[str] = []
            for baseline_item in item_schemas:
                try:
                    _validate_structure(
                        value,
                        baseline_item,
                        f"{location}[{index}]",
                        depth=depth + 1,
                    )
                    break
                except DisclosureError as exc:
                    failures.append(str(exc))
            else:
                detail = failures[0] if failures else "no reviewed item schema"
                raise DisclosureError(
                    f"{location}[{index}] matches no reviewed public item schema: {detail}"
                )
        return

    if isinstance(candidate, str):
        _scan_text(candidate, location)
    if isinstance(candidate, float) and not math.isfinite(candidate):
        raise DisclosureError(f"{location} contains a non-finite number")
    if _scalar_kind(candidate) != _scalar_kind(baseline):
        raise DisclosureError(
            f"{location} changed type from {_scalar_kind(baseline)} "
            f"to {_scalar_kind(candidate)}"
        )


def _require_exact_keys(
    value: Any, expected: set[str], location: str
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise DisclosureError(
            f"{location} does not contain the exact reviewed fields; keys redacted"
        )
    return value


def _validate_ci_runtime_provenance(value: Any, location: str) -> None:
    """Validate the reviewed, bounded product-CI provenance extension."""

    root = _require_exact_keys(value, set(_CI_RUNTIME_PROVENANCE_SCHEMA), location)
    if root.get("schema_version") != "wp.ci_runtime_provenance.v2":
        raise DisclosureError(f"{location} has an unreviewed schema version")

    source_schema = _CI_RUNTIME_PROVENANCE_SCHEMA["source_ci"]
    assert isinstance(source_schema, dict)
    source = _require_exact_keys(
        root.get("source_ci"), set(source_schema), f"{location}.source_ci"
    )
    if (
        source.get("repository") != "equilens-labs/fl-bsa"
        or source.get("workflow") != ".github/workflows/ci-comprehensive.yml"
    ):
        raise DisclosureError(f"{location}.source_ci has an unreviewed source identity")
    run_id = source.get("run_id")
    run_attempt = source.get("run_attempt")
    if (
        not isinstance(run_id, int)
        or isinstance(run_id, bool)
        or run_id <= 0
        or not isinstance(run_attempt, int)
        or isinstance(run_attempt, bool)
        or run_attempt <= 0
        or not isinstance(source.get("head_sha"), str)
        or not _SHA_RE.fullmatch(source["head_sha"])
    ):
        raise DisclosureError(f"{location}.source_ci has malformed run identity")

    artifact_schema = source_schema["contract_artifact"]
    assert isinstance(artifact_schema, dict)
    artifact = _require_exact_keys(
        source.get("contract_artifact"),
        set(artifact_schema),
        f"{location}.source_ci.contract_artifact",
    )
    artifact_id = artifact.get("id")
    artifact_size = artifact.get("size_in_bytes")
    if (
        not isinstance(artifact_id, int)
        or isinstance(artifact_id, bool)
        or artifact_id <= 0
        or artifact.get("name") != f"ci-runtime-image-contract-{run_attempt}"
        or not isinstance(artifact.get("digest"), str)
        or not _DIGEST_RE.fullmatch(artifact["digest"])
        or not isinstance(artifact_size, int)
        or isinstance(artifact_size, bool)
        or artifact_size <= 0
    ):
        raise DisclosureError(
            f"{location}.source_ci.contract_artifact has malformed identity; values redacted"
        )

    runtime_schema = _CI_RUNTIME_PROVENANCE_SCHEMA["runtime_image"]
    assert isinstance(runtime_schema, dict)
    runtime = _require_exact_keys(
        root.get("runtime_image"), set(runtime_schema), f"{location}.runtime_image"
    )
    digest = runtime.get("digest")
    expected_ref = f"ghcr.io/equilens-labs/fl-bsa-runtime@{digest}"
    if (
        not isinstance(digest, str)
        or not _DIGEST_RE.fullmatch(digest)
        or runtime.get("digest_ref") != expected_ref
        or runtime.get("api_digest_ref") != expected_ref
        or runtime.get("worker_digest_ref") != expected_ref
    ):
        raise DisclosureError(
            f"{location}.runtime_image has malformed or inconsistent digest identity"
        )
    image_build_sha = runtime.get("image_build_sha")
    build_disposition = runtime.get("build_disposition")
    if (
        not isinstance(image_build_sha, str)
        or not _SHA_RE.fullmatch(image_build_sha)
        or build_disposition not in _CI_RUNTIME_BUILD_DISPOSITIONS
    ):
        raise DisclosureError(
            f"{location}.runtime_image has malformed or unreviewed build provenance"
        )
    source_head_sha = source["head_sha"]
    if (
        build_disposition in _CI_RUNTIME_SAME_SOURCE_DISPOSITIONS
        and image_build_sha != source_head_sha
    ):
        raise DisclosureError(
            f"{location}.runtime_image build provenance does not match the source CI head"
        )
    if (
        build_disposition == "reused_exact_sha_tag_projection_equivalent"
        and image_build_sha == source_head_sha
    ):
        raise DisclosureError(
            f"{location}.runtime_image projection-equivalent reuse does not identify "
            "a distinct image build source"
        )
    projection = _require_exact_keys(
        runtime.get("runtime_input_projection"),
        {"algorithm", "sha256"},
        f"{location}.runtime_image.runtime_input_projection",
    )
    if (
        projection.get("algorithm") != "git-ls-tree-z-sha256.v1"
        or not isinstance(projection.get("sha256"), str)
        or not _SHA256_RE.fullmatch(projection["sha256"])
    ):
        raise DisclosureError(
            f"{location}.runtime_image has malformed input projection"
        )

    claims = _require_exact_keys(
        root.get("claims"),
        {"bounded_runtime_contract_verified", "full_ci_proven"},
        f"{location}.claims",
    )
    if claims != {
        "bounded_runtime_contract_verified": True,
        "full_ci_proven": False,
    }:
        raise DisclosureError(f"{location}.claims exceed the reviewed bounded proof")


def _validate_ci_runtime_manifest_binding(manifest: Any, location: str) -> None:
    """Bind the nested runtime receipt to the enclosing reviewed manifest."""

    if not isinstance(manifest, dict) or "ci_runtime_provenance" not in manifest:
        return
    provenance = manifest.get("ci_runtime_provenance")
    # The exact nested structure and scalar formats were already checked above.
    assert isinstance(provenance, dict)
    source = provenance["source_ci"]
    runtime = provenance["runtime_image"]
    assert isinstance(source, dict) and isinstance(runtime, dict)

    head_sha = source["head_sha"]
    for alias in ("commit_sha", "code_commit", "source_commit", "software_commit"):
        if manifest.get(alias) != head_sha:
            raise DisclosureError(
                f"{location}.ci_runtime_provenance is not bound to the enclosing "
                "commit identity; values redacted"
            )

    digest_ref = runtime["digest_ref"]
    container_digests = manifest.get("container_digests")
    if (
        manifest.get("container_digest") != digest_ref
        or not isinstance(container_digests, dict)
        or container_digests.get("api_image_digest") != runtime["api_digest_ref"]
        or container_digests.get("worker_image_digest")
        != runtime["worker_digest_ref"]
    ):
        raise DisclosureError(
            f"{location}.ci_runtime_provenance is not bound to the enclosing "
            "runtime image identity; values redacted"
        )


def _validate_certificate_semantics(
    candidate: Any, baseline: Any, location: str
) -> None:
    """Constrain reviewed certificate aggregates that have an empty baseline."""

    if not isinstance(candidate, dict) or not isinstance(baseline, dict):
        return
    candidate_analysis = candidate.get("correlation_analysis")
    baseline_analysis = baseline.get("correlation_analysis")
    candidate_statistical = candidate.get("statistical_comparison")
    broken = (
        candidate_analysis.get("broken_correlations")
        if isinstance(candidate_analysis, dict)
        else None
    )
    range_violations = (
        candidate_statistical.get("range_violations")
        if isinstance(candidate_statistical, dict)
        else None
    )
    if broken is None and range_violations is None:
        return
    reviewed_matrix = (
        baseline_analysis.get("real_correlation_matrix")
        if isinstance(baseline_analysis, dict)
        else None
    )
    if not isinstance(reviewed_matrix, dict):
        raise DisclosureError(
            f"{location}.correlation_analysis has no reviewed column-name schema"
        )
    reviewed_columns = set(reviewed_matrix)
    if range_violations is not None:
        if not isinstance(range_violations, dict):
            raise DisclosureError(
                f"{location}.statistical_comparison.range_violations is not an object"
            )
        expected_range_keys = set(_RANGE_VIOLATION_ITEM_SCHEMA)
        for column, item in range_violations.items():
            item_location = (
                f"{location}.statistical_comparison.range_violations.[reviewed-column]"
            )
            if column not in reviewed_columns:
                raise DisclosureError(
                    f"{item_location} uses a column outside the reviewed public schema; "
                    "value redacted"
                )
            if not isinstance(item, dict) or set(item) != expected_range_keys:
                raise DisclosureError(
                    f"{item_location} does not contain the exact reviewed aggregate fields; "
                    "keys redacted"
                )
            real_range = item.get("real_range")
            synthetic_range = item.get("synthetic_range")
            if (
                not isinstance(real_range, list)
                or len(real_range) != 2
                or not isinstance(synthetic_range, list)
                or len(synthetic_range) != 2
            ):
                raise DisclosureError(
                    f"{item_location} ranges must each contain exactly two reviewed numbers"
                )
            if not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                for value in (*real_range, *synthetic_range)
            ):
                raise DisclosureError(
                    f"{item_location} ranges must contain only finite numbers"
                )
            if item.get("violation_type") != "out_of_bounds":
                raise DisclosureError(
                    f"{item_location} has an unreviewed violation type; value redacted"
                )
            if real_range[0] > real_range[1] or synthetic_range[0] > synthetic_range[1]:
                raise DisclosureError(f"{item_location} contains a reversed range")

    if broken is not None:
        expected_keys = set(_BROKEN_CORRELATION_ITEM_SCHEMA)
        for index, item in enumerate(broken):
            item_location = (
                f"{location}.correlation_analysis.broken_correlations[{index}]"
            )
            if not isinstance(item, dict) or set(item) != expected_keys:
                raise DisclosureError(
                    f"{item_location} does not contain the exact reviewed aggregate fields; "
                    "keys redacted"
                )
            if (
                item.get("column1") not in reviewed_columns
                or item.get("column2") not in reviewed_columns
            ):
                raise DisclosureError(
                    f"{item_location} references a column outside the reviewed public schema; "
                    "value redacted"
                )


def _load_structured(path: Path) -> Any:
    text = _read_text(path)
    try:
        if path.suffix == ".json":
            return json.loads(
                text,
                object_pairs_hook=_json_object,
                parse_constant=_reject_nonfinite,
            )
        for token in yaml.scan(text):
            if isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)):
                raise DisclosureError("YAML anchors and aliases are forbidden")
        return yaml.load(text, Loader=_UniqueKeySafeLoader)
    except DisclosureError:
        raise
    except json.JSONDecodeError as exc:
        raise DisclosureError(
            f"unable to parse {path}: invalid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = (
            f"line {mark.line + 1}, column {mark.column + 1}"
            if mark is not None
            else "a redacted location"
        )
        raise DisclosureError(
            f"unable to parse {path}: invalid YAML at {location}"
        ) from exc


def _baseline_path(bundle_path: Path, schema_root: Path) -> Path:
    relative = bundle_path.as_posix()
    if relative == "provenance/manifest.json":
        return schema_root / "intake" / "manifest.json"
    if relative.startswith("certificates/"):
        return schema_root / "intake" / relative
    return schema_root / relative


def _validate_csv(candidate_path: Path, baseline_path: Path) -> None:
    candidate_text = _read_text(candidate_path)
    baseline_text = _read_text(baseline_path)
    try:
        candidate_rows = csv.reader(candidate_text.splitlines())
        baseline_rows = csv.reader(baseline_text.splitlines())
        candidate_header = next(candidate_rows)
        baseline_header = next(baseline_rows)
    except (csv.Error, StopIteration) as exc:
        raise DisclosureError(
            f"CSV header validation failed for {candidate_path}"
        ) from exc
    if not candidate_header or candidate_header != baseline_header:
        raise DisclosureError(
            f"{candidate_path} columns are not the reviewed public schema; "
            "candidate header redacted"
        )
    if len(candidate_header) > _MAX_CSV_COLUMNS or len(set(candidate_header)) != len(
        candidate_header
    ):
        raise DisclosureError(f"{candidate_path} has too many or duplicate CSV columns")
    for column, cell in enumerate(candidate_header):
        _scan_text(cell, f"{candidate_path}:header[{column}]")
    for row_number, row in enumerate(candidate_rows, start=2):
        if row_number > _MAX_CSV_ROWS + 1:
            raise DisclosureError(
                f"{candidate_path} exceeds the {_MAX_CSV_ROWS}-row limit"
            )
        if len(row) != len(candidate_header):
            raise DisclosureError(
                f"{candidate_path}:{row_number} has {len(row)} cells; "
                f"expected {len(candidate_header)}"
            )
        for column, cell in enumerate(row):
            _scan_text(
                cell, f"{candidate_path}:{row_number}:{candidate_header[column]}"
            )


def validate_bundle(bundle_root: Path, schema_root: Path) -> None:
    """Validate every extracted public intake file against tracked reviewed schemas."""

    if not bundle_root.is_dir():
        raise DisclosureError(f"bundle root is not a directory: {bundle_root}")
    if not schema_root.is_dir():
        raise DisclosureError(f"schema root is not a directory: {schema_root}")

    candidates = sorted(path for path in bundle_root.rglob("*") if path.is_file())
    if not candidates:
        raise DisclosureError("bundle contains no files")
    for member_index, candidate in enumerate(candidates):
        relative = candidate.relative_to(bundle_root)
        if candidate.suffix not in {".json", ".yaml", ".yml", ".csv"}:
            raise DisclosureError(
                f"bundle member {member_index} has an unsupported public intake format; "
                "name redacted"
            )
        baseline = _baseline_path(relative, schema_root)
        if not baseline.is_file():
            raise DisclosureError(
                f"bundle member {member_index} has no reviewed tracked public schema; "
                "name redacted"
            )
        if candidate.suffix == ".csv":
            _validate_csv(candidate, baseline)
        else:
            candidate_payload = _load_structured(candidate)
            baseline_payload = _load_structured(baseline)
            _validate_structure(
                candidate_payload, baseline_payload, relative.as_posix()
            )
            if relative.as_posix() in _CI_RUNTIME_MANIFEST_LOCATIONS:
                _validate_ci_runtime_manifest_binding(
                    candidate_payload, relative.as_posix()
                )
            if relative.parts[0] == "certificates":
                _validate_certificate_semantics(
                    candidate_payload, baseline_payload, relative.as_posix()
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--schema-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        validate_bundle(args.bundle_root, args.schema_root)
    except DisclosureError as exc:
        parser.error(str(exc))
    print("Public intake content and schema disclosure checks OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
