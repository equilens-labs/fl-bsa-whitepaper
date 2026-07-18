#!/usr/bin/env python3

"""
Generate LaTeX macros from the provenance manifest.

Primary source (gate-wp / wp-intake v1):
  provenance/manifest.json with fields:
    - inference{ method, replicates, alpha, seed, smoothing }
    - thresholds{ air_min, eo_gap_max, ece_max }
    - scenario{ type, label }
    - code_commit / commit_sha

Legacy fallback (pre-gate-wp):
  intake/manifest.json with schema_version v1 and a runs[] list.
  In that case we derive a minimal scenario/commit from the first run and
  fall back to SAP thresholds.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Dict

import yaml


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_sap_thresholds(path: Path) -> Dict[str, float]:
    """Fallback thresholds from SAP when manifest lacks a thresholds block."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        thr = (data or {}).get("thresholds") or {}
        return {
            "air_min": float(thr.get("air_min", 0.80)),
            "eo_gap_max": float(thr.get("tpr_gap_max", 0.05)),
            "ece_max": float(thr.get("ece_max", 0.02)),
        }
    except Exception:
        return {"air_min": 0.80, "eo_gap_max": 0.05, "ece_max": 0.02}


def _strict_load_json(path: Path, label: str) -> Dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"required {label} file is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"required {label} file is malformed: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"required {label} payload must be a JSON object: {path}")
    return payload


def _strict_load_yaml(path: Path, label: str) -> Dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"required {label} file is missing: {path}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"required {label} file is malformed: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"required {label} payload must be a YAML mapping: {path}")
    return payload


def _strict_finite_number(value: Any, location: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{location} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{location} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{location} must be a finite number")
    return number


def _strict_nonempty_string(value: Any, location: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value.strip().lower() == "not_available"
    ):
        raise ValueError(f"{location} must be a non-empty available value")
    return value


def _strict_validate_manifest(manifest: Dict[str, Any]) -> None:
    schema = _strict_nonempty_string(manifest.get("schema_version"), "manifest.schema_version")
    if not schema.startswith("wp-intake."):
        raise ValueError("manifest.schema_version must identify a wp-intake schema")

    inference = manifest.get("inference")
    if not isinstance(inference, dict):
        raise ValueError("manifest.inference must be an object")
    _strict_nonempty_string(inference.get("method"), "manifest.inference.method")
    replicates = inference.get("replicates")
    if isinstance(replicates, bool) or not isinstance(replicates, int) or replicates <= 0:
        raise ValueError("manifest.inference.replicates must be a positive integer")
    alpha = _strict_finite_number(inference.get("alpha"), "manifest.inference.alpha")
    if not 0 < alpha < 1:
        raise ValueError("manifest.inference.alpha must be in (0, 1)")
    smoothing = _strict_finite_number(
        inference.get("smoothing"), "manifest.inference.smoothing"
    )
    if smoothing < 0:
        raise ValueError("manifest.inference.smoothing must be non-negative")

    commit = _strict_nonempty_string(
        manifest.get("code_commit") or manifest.get("commit_sha"),
        "manifest.code_commit",
    )
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("manifest.code_commit must be a lowercase 40-hex commit")
    _strict_nonempty_string(manifest.get("run_id"), "manifest.run_id")
    dataset_hash = _strict_nonempty_string(
        manifest.get("dataset_hash"), "manifest.dataset_hash"
    )
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", dataset_hash):
        raise ValueError("manifest.dataset_hash must be a sha256 digest")
    config_hash = _strict_nonempty_string(
        manifest.get("config_hash"), "manifest.config_hash"
    )
    if not re.fullmatch(r"[0-9a-f]{64}", config_hash):
        raise ValueError("manifest.config_hash must be a lowercase 64-hex digest")

    digests = manifest.get("container_digests")
    if not isinstance(digests, dict):
        raise ValueError("manifest.container_digests must be an object")
    digest_pattern = re.compile(r"^\S+@sha256:[0-9a-f]{64}$")
    for field in ("api_image_digest", "worker_image_digest"):
        digest = _strict_nonempty_string(
            digests.get(field), f"manifest.container_digests.{field}"
        )
        if not digest_pattern.fullmatch(digest):
            raise ValueError(
                f"manifest.container_digests.{field} must be an immutable OCI digest reference"
            )

    seeds = manifest.get("seeds")
    if not isinstance(seeds, dict):
        raise ValueError("manifest.seeds must be an object")
    for field in ("rng_seed", "bootstrap_seed"):
        value = seeds.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"manifest.seeds.{field} must be an integer")

    capabilities = manifest.get("capabilities")
    if not isinstance(capabilities, dict):
        raise ValueError("manifest.capabilities must be an object")
    for field in ("eo_enabled", "ece_enabled"):
        if not isinstance(capabilities.get(field), bool):
            raise ValueError(f"manifest.capabilities.{field} must be a boolean")


def _strict_validate_sap(sap: Dict[str, Any]) -> None:
    thresholds = sap.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("sap.thresholds must be a mapping")
    for field in ("air_min", "tpr_gap_max", "ece_max"):
        value = _strict_finite_number(thresholds.get(field), f"sap.thresholds.{field}")
        if not 0 <= value <= 1:
            raise ValueError(f"sap.thresholds.{field} must be in [0, 1]")


def _strict_validate_metrics_csv(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"required metrics CSV file is missing: {path}")
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            if reader.fieldnames is None:
                raise ValueError("metrics CSV is missing a header")
            required = {"metric", "ci_degenerate"}
            if not required.issubset(reader.fieldnames):
                raise ValueError("metrics CSV is missing required columns")
            if next(reader, None) is None:
                raise ValueError("metrics CSV must contain at least one row")
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValueError(f"required metrics CSV file is malformed: {path}") from exc


def _strict_validate_inputs(
    manifest_path: Path, sap_path: Path, metrics_path: Path
) -> Dict[str, Any]:
    manifest = _strict_load_json(manifest_path, "manifest")
    sap = _strict_load_yaml(sap_path, "SAP")
    _strict_validate_manifest(manifest)
    _strict_validate_sap(sap)
    _strict_validate_metrics_csv(metrics_path)
    return manifest


def _truthy_int(val: Any) -> int:
    if isinstance(val, bool):
        return 1 if val else 0
    if val is None:
        return 0
    s = str(val).strip().lower()
    return 1 if s in {"1", "true", "yes", "on"} else 0


_LATEX_ESCAPE_MAP: dict[str, str] = {
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
_LATEX_ESCAPE_RE = re.compile(r"[\\&%$#_{}~^]")


def _latex_escape(value: Any) -> str:
    text = str(value or "")
    return _LATEX_ESCAPE_RE.sub(lambda m: _LATEX_ESCAPE_MAP[m.group(0)], text)


_DIGEST_PREFIX_RE = re.compile(r"^(?P<prefix>[A-Za-z0-9_+-]+:)(?P<body>[0-9a-fA-F]{16,})$")
_SCI_EXP_NORMALIZE_RE = re.compile(r"e([+-])0+(\d+)$", re.IGNORECASE)
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _chunk_for_display(value: str, *, chunk_size: int = 8, separator: str = " ") -> str:
    cleaned = value.strip()
    if not cleaned:
        return cleaned
    if len(cleaned) <= chunk_size:
        return cleaned
    return separator.join(cleaned[i : i + chunk_size] for i in range(0, len(cleaned), chunk_size))


def _chunk_digest_for_display(value: str, *, chunk_size: int = 8, separator: str = " ") -> str:
    cleaned = value.strip()
    if "@" in cleaned:
        image_ref, digest = cleaned.rsplit("@", 1)
        match = _DIGEST_PREFIX_RE.match(digest)
        if match:
            return (
                f"{image_ref}@{match.group('prefix')}"
                f"{_chunk_for_display(match.group('body'), chunk_size=chunk_size, separator=separator)}"
            )
        return cleaned
    match = _DIGEST_PREFIX_RE.match(cleaned)
    if match:
        return f"{match.group('prefix')}{_chunk_for_display(match.group('body'), chunk_size=chunk_size, separator=separator)}"
    return _chunk_for_display(cleaned, chunk_size=chunk_size, separator=separator)


def _tex_texttt_breakable(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    if _UUID_RE.match(cleaned):
        return f"\\texttt{{{_latex_escape(cleaned)}}}"
    chunked = _chunk_digest_for_display(cleaned)
    return f"\\texttt{{{_latex_escape(chunked)}}}"


def _fmt_float_for_siunitx(val: float, *, decimals: int = 6, sci_threshold: float = 1e-4) -> str:
    """Format a float as a siunitx-friendly token without collapsing small values to 0."""
    if not math.isfinite(val):
        return ""
    if val == 0.0:
        return "0"
    if abs(val) < sci_threshold:
        token = f"{val:g}"
        return _SCI_EXP_NORMALIZE_RE.sub(r"e\1\2", token)
    token = f"{val:.{decimals}f}"
    return token.rstrip("0").rstrip(".")


def _emit_macros(
    manifest: Dict[str, Any],
    sap_path: Path,
    out_path: Path,
    *,
    metrics_path: Path | None = None,
    quiet: bool = False,
) -> None:
    # Detect wp-intake style manifest vs legacy runs manifest
    schema = str(manifest.get("schema_version", "") or "")
    is_wp_intake = schema.startswith("wp-intake.")

    if is_wp_intake:
        m = manifest
        inf = (m.get("inference") or {}) if isinstance(m.get("inference"), dict) else {}
        thr = (
            (m.get("thresholds") or {})
            if isinstance(m.get("thresholds"), dict)
            else {}
        )
        sc = (m.get("scenario") or {}) if isinstance(m.get("scenario"), dict) else {}
        code_commit = (
            m.get("code_commit") or m.get("commit_sha") or "not_available"
        )
        thresholds = {
            "air_min": float(thr.get("air_min", 0.80)),
            "eo_gap_max": float(thr.get("eo_gap_max", 0.05)),
            "ece_max": float(thr.get("ece_max", 0.02)),
        }
    else:
        # Legacy aggregator manifest with runs[]
        m = {}
        runs = manifest.get("runs")
        first_run = runs[0] if isinstance(runs, list) and runs else {}
        code_commit = first_run.get("code_commit") or "not_available"
        scenario_label = first_run.get("scenario") or "Synthetic audit"
        sc = {"type": "synthetic_audit", "label": scenario_label}
        inf = {}
        thresholds = _load_sap_thresholds(sap_path)

    raw_method = (inf.get("method", "percentile") or "percentile").lower()
    if raw_method == "bca":
        method = "BCa"
    else:
        method = raw_method
    try:
        replicates = int(inf.get("replicates", 2000) or 2000)
    except Exception:
        replicates = 2000
    try:
        alpha = float(inf.get("alpha", 0.05) or 0.05)
    except Exception:
        alpha = 0.05
    try:
        smoothing_val = float(inf.get("smoothing", 0.0) or 0.0)
    except Exception:
        smoothing_val = 0.0

    scenario_type = sc.get("type", "synthetic_audit") or "synthetic_audit"
    scenario_label = sc.get("label", "Synthetic audit") or "Synthetic audit"

    # General provenance fields for templating/appendices
    run_id = str(manifest.get("run_id") or "not_available")
    schema_version = str(manifest.get("schema_version") or "not_available")
    dataset_hash = str(manifest.get("dataset_hash") or "not_available")
    config_hash = str(manifest.get("config_hash") or "not_available")

    dig = manifest.get("container_digests") if isinstance(manifest, dict) else None
    if not isinstance(dig, dict):
        dig = {}
    api_image_digest = str(dig.get("api_image_digest") or "not_available")
    worker_image_digest = str(dig.get("worker_image_digest") or "not_available")

    seeds = manifest.get("seeds") if isinstance(manifest, dict) else None
    if not isinstance(seeds, dict):
        seeds = {}
    rng_seed = seeds.get("rng_seed")
    bootstrap_seed = seeds.get("bootstrap_seed")

    caps = manifest.get("capabilities") if isinstance(manifest, dict) else None
    if not isinstance(caps, dict):
        caps = {}
    eo_enabled = _truthy_int(caps.get("eo_enabled"))
    ece_enabled = _truthy_int(caps.get("ece_enabled") or caps.get("calibration_enabled"))

    # Optional metrics inspection (for ECE / degeneracy flags)
    has_ece = False
    has_degenerate = False
    if metrics_path is not None and metrics_path.exists():
        try:
            with metrics_path.open("r", encoding="utf-8") as mf:
                reader = csv.DictReader(mf)
                for row in reader:
                    metric_name = (row.get("metric") or "").strip().lower()
                    if metric_name == "ece":
                        has_ece = True
                    ci_deg = (row.get("ci_degenerate") or "").strip().lower()
                    if ci_deg in {"true", "1", "yes"}:
                        has_degenerate = True
        except Exception:
            has_ece = False
            has_degenerate = False
    # Fall back to manifest capabilities when present
    caps = manifest.get("capabilities") if isinstance(manifest, dict) else None
    if isinstance(caps, dict):
        if not has_ece:
            has_ece = bool(caps.get("calibration_enabled") or caps.get("ece_enabled"))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write("% Auto-generated provenance/inference macros\n")
        f.write("\\newcommand{\\InferenceMethod}{%s}\n" % _latex_escape(method))
        f.write("\\newcommand{\\InferenceReplicates}{%d}\n" % replicates)
        f.write("\\newcommand{\\InferenceAlpha}{%.2f}\n" % alpha)
        if smoothing_val > 0.0:
            f.write(
                "\\newcommand{\\InferenceSmoothing}{%s}\n"
                % _fmt_float_for_siunitx(smoothing_val, decimals=6)
            )
        else:
            f.write("\\newcommand{\\InferenceSmoothing}{}\n")
        f.write("\\newcommand{\\ScenarioType}{%s}\n" % _latex_escape(scenario_type))
        f.write("\\newcommand{\\ScenarioLabel}{%s}\n" % _latex_escape(scenario_label))
        f.write("\\newcommand{\\AirMin}{%.3f}\n" % float(thresholds["air_min"]))
        f.write("\\newcommand{\\EoGapMax}{%.3f}\n" % float(thresholds["eo_gap_max"]))
        f.write("\\newcommand{\\EceMax}{%.3f}\n" % float(thresholds["ece_max"]))
        f.write("\\newcommand{\\CodeCommit}{%s}\n" % _latex_escape(code_commit))
        f.write("\\newcommand{\\RunId}{%s}\n" % _latex_escape(run_id))
        f.write("\\newcommand{\\SchemaVersion}{%s}\n" % _latex_escape(schema_version))
        f.write("\\newcommand{\\DatasetHash}{%s}\n" % _latex_escape(dataset_hash))
        f.write("\\newcommand{\\ConfigHash}{%s}\n" % _latex_escape(config_hash))
        f.write("\\newcommand{\\ApiImageDigest}{%s}\n" % _latex_escape(api_image_digest))
        f.write("\\newcommand{\\WorkerImageDigest}{%s}\n" % _latex_escape(worker_image_digest))
        f.write("\\newcommand{\\CodeCommitDisplay}{%s}\n" % _tex_texttt_breakable(code_commit))
        f.write("\\newcommand{\\RunIdDisplay}{%s}\n" % _tex_texttt_breakable(run_id))
        f.write(
            "\\newcommand{\\DatasetHashDisplay}{%s}\n"
            % _tex_texttt_breakable(dataset_hash)
        )
        f.write("\\newcommand{\\ConfigHashDisplay}{%s}\n" % _tex_texttt_breakable(config_hash))
        f.write(
            "\\newcommand{\\ApiImageDigestDisplay}{%s}\n"
            % _tex_texttt_breakable(api_image_digest)
        )
        f.write(
            "\\newcommand{\\WorkerImageDigestDisplay}{%s}\n"
            % _tex_texttt_breakable(worker_image_digest)
        )
        f.write("\\newcommand{\\RngSeed}{%s}\n" % (rng_seed if rng_seed is not None else ""))
        f.write(
            "\\newcommand{\\BootstrapSeed}{%s}\n"
            % (bootstrap_seed if bootstrap_seed is not None else "")
        )
        f.write("\\newcommand{\\EoEnabled}{%d}\n" % eo_enabled)
        f.write("\\newcommand{\\EceEnabled}{%d}\n" % ece_enabled)
        f.write("\\newcommand{\\HasDegenerateCIs}{%d}\n" % (1 if has_degenerate else 0))
        f.write("\\newcommand{\\EceEvaluated}{%d}\n" % (1 if has_ece else 0))

    if not quiet:
        print(f"Wrote LaTeX provenance macros to {out_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate LaTeX macros from manifest")
    ap.add_argument(
        "--manifest",
        default="intake/manifest.json",
        help="Path to provenance manifest JSON",
    )
    ap.add_argument(
        "--sap",
        default="config/sap.yaml",
        help="SAP YAML (for threshold fallback)",
    )
    ap.add_argument(
        "--out",
        default="includes/provenance_macros.tex",
        help="Output .tex file with \\newcommand macros",
    )
    ap.add_argument(
        "--metrics",
        default="intake/metrics_long.csv",
        help="Metrics CSV used for ECE and degeneracy flags",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Reject missing, malformed, or incomplete publication inputs before writing output",
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress informational stdout messages",
    )
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    sap_path = Path(args.sap)
    out_path = Path(args.out)
    metrics_path = Path(args.metrics)

    if args.strict:
        try:
            manifest = _strict_validate_inputs(manifest_path, sap_path, metrics_path)
        except ValueError as exc:
            ap.error(str(exc))
    else:
        manifest = _load_json(manifest_path) if manifest_path.exists() else {}
    _emit_macros(
        manifest, sap_path, out_path, metrics_path=metrics_path, quiet=args.quiet
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
