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


def _truthy_int(val: Any) -> int:
    if isinstance(val, bool):
        return 1 if val else 0
    if val is None:
        return 0
    s = str(val).strip().lower()
    return 1 if s in {"1", "true", "yes", "on"} else 0


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
        f.write("\\newcommand{\\InferenceMethod}{%s}\n" % method)
        f.write("\\newcommand{\\InferenceReplicates}{%d}\n" % replicates)
        f.write("\\newcommand{\\InferenceAlpha}{%.2f}\n" % alpha)
        if smoothing_val > 0.0:
            f.write("\\newcommand{\\InferenceSmoothing}{%.6f}\n" % smoothing_val)
        else:
            f.write("\\newcommand{\\InferenceSmoothing}{}\n")
        f.write("\\newcommand{\\ScenarioType}{%s}\n" % scenario_type)
        f.write("\\newcommand{\\ScenarioLabel}{%s}\n" % scenario_label)
        f.write("\\newcommand{\\AirMin}{%.3f}\n" % float(thresholds["air_min"]))
        f.write("\\newcommand{\\EoGapMax}{%.3f}\n" % float(thresholds["eo_gap_max"]))
        f.write("\\newcommand{\\EceMax}{%.3f}\n" % float(thresholds["ece_max"]))
        f.write("\\newcommand{\\CodeCommit}{%s}\n" % code_commit)
        f.write("\\newcommand{\\RunId}{%s}\n" % run_id)
        f.write("\\newcommand{\\SchemaVersion}{%s}\n" % schema_version)
        f.write("\\newcommand{\\DatasetHash}{%s}\n" % dataset_hash)
        f.write("\\newcommand{\\ConfigHash}{%s}\n" % config_hash)
        f.write("\\newcommand{\\ApiImageDigest}{%s}\n" % api_image_digest)
        f.write("\\newcommand{\\WorkerImageDigest}{%s}\n" % worker_image_digest)
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
        "--quiet",
        action="store_true",
        help="Suppress informational stdout messages",
    )
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    sap_path = Path(args.sap)
    out_path = Path(args.out)
    metrics_path = Path("intake/metrics_long.csv")

    manifest = _load_json(manifest_path) if manifest_path.exists() else {}
    _emit_macros(
        manifest, sap_path, out_path, metrics_path=metrics_path, quiet=args.quiet
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
