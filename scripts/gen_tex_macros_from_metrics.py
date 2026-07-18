#!/usr/bin/env python3

"""
Generate LaTeX macros + tables from the whitepaper intake bundle.

Primary source of truth (v4):
- intake/metrics_uncertainty.json (deterministic fairness uncertainty surface)

Secondary/fallback sources:
- intake/metrics_long.csv (legacy surface; used only for ECE table)
- config/sap.yaml (thresholds)

Outputs (under includes/):
- metrics_macros.tex
- table_air_summary.tex
- table_gender_air_slices.tex
- table_srg_summary.tex
- table_ece_summary.tex
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def _strict_load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"required {label} file is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"required {label} file is malformed: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"required {label} payload must be a JSON object: {path}")
    return payload


def _strict_load_yaml(path: Path, label: str) -> dict[str, Any]:
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
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location} must be a non-empty string")
    return value


def _strict_metric_block(value: Any, location: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{location} must be an object")
    _strict_finite_number(value.get("point"), f"{location}.point")
    ci95 = value.get("ci95")
    if not isinstance(ci95, list) or len(ci95) != 2:
        raise ValueError(f"{location}.ci95 must contain exactly two values")
    lower = _strict_finite_number(ci95[0], f"{location}.ci95[0]")
    upper = _strict_finite_number(ci95[1], f"{location}.ci95[1]")
    if lower > upper:
        raise ValueError(f"{location}.ci95 must be ordered lower-to-upper")
    p_value = _strict_finite_number(value.get("p_value"), f"{location}.p_value")
    if not 0 <= p_value <= 1:
        raise ValueError(f"{location}.p_value must be in [0, 1]")


def _strict_validate_uncertainty(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != "fairness_uncertainty.v1":
        raise ValueError("uncertainty.schema_version must be fairness_uncertainty.v1")
    uncertainty = payload.get("fairness_uncertainty")
    if not isinstance(uncertainty, dict):
        raise ValueError("uncertainty.fairness_uncertainty must be an object")

    gender = uncertainty.get("gender")
    if not isinstance(gender, dict):
        raise ValueError("uncertainty.fairness_uncertainty.gender must be an object")
    _strict_nonempty_string(
        gender.get("reference_group"),
        "uncertainty.fairness_uncertainty.gender.reference_group",
    )
    _strict_nonempty_string(
        gender.get("protected_group"),
        "uncertainty.fairness_uncertainty.gender.protected_group",
    )
    _strict_metric_block(
        gender.get("air"), "uncertainty.fairness_uncertainty.gender.air"
    )
    _strict_metric_block(
        gender.get("srg"), "uncertainty.fairness_uncertainty.gender.srg"
    )

    race = uncertainty.get("race")
    if not isinstance(race, dict):
        raise ValueError("uncertainty.fairness_uncertainty.race must be an object")
    _strict_nonempty_string(
        race.get("reference_group"),
        "uncertainty.fairness_uncertainty.race.reference_group",
    )
    if not isinstance(race.get("display_in_main_pdf"), bool):
        raise ValueError(
            "uncertainty.fairness_uncertainty.race.display_in_main_pdf must be boolean"
        )
    worst_case_pair = _strict_nonempty_string(
        race.get("worst_case_pair"),
        "uncertainty.fairness_uncertainty.race.worst_case_pair",
    )
    pairs = race.get("pairs")
    if not isinstance(pairs, dict) or not pairs:
        raise ValueError("uncertainty.fairness_uncertainty.race.pairs must be non-empty")
    if worst_case_pair not in pairs or not isinstance(pairs[worst_case_pair], dict):
        raise ValueError("uncertainty race worst_case_pair must name a pair object")
    _strict_metric_block(
        pairs[worst_case_pair].get("air"),
        "uncertainty.fairness_uncertainty.race.pairs[worst_case_pair].air",
    )
    _strict_metric_block(
        pairs[worst_case_pair].get("srg"),
        "uncertainty.fairness_uncertainty.race.pairs[worst_case_pair].srg",
    )
    observed = race.get("observed")
    if not isinstance(observed, dict):
        raise ValueError("uncertainty.fairness_uncertainty.race.observed must be an object")
    if _strict_finite_number(
        observed.get("min_group_n"),
        "uncertainty.fairness_uncertainty.race.observed.min_group_n",
    ) <= 0:
        raise ValueError("uncertainty race observed.min_group_n must be positive")
    min_group_pct = _strict_finite_number(
        observed.get("min_group_pct"),
        "uncertainty.fairness_uncertainty.race.observed.min_group_pct",
    )
    if not 0 < min_group_pct <= 1:
        raise ValueError("uncertainty race observed.min_group_pct must be in (0, 1]")


def _strict_validate_slices(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != "fairness_slices.v1":
        raise ValueError("slices.schema_version must be fairness_slices.v1")
    _strict_nonempty_string(payload.get("reference_group"), "slices.reference_group")
    _strict_nonempty_string(payload.get("protected_group"), "slices.protected_group")
    slices = payload.get("slices")
    if not isinstance(slices, dict):
        raise ValueError("slices.slices must be an object")
    for branch in ("historical", "amplification", "intrinsic"):
        entry = slices.get(branch)
        location = f"slices.slices.{branch}"
        if not isinstance(entry, dict):
            raise ValueError(f"{location} must be an object")
        counts = entry.get("counts")
        if not isinstance(counts, dict):
            raise ValueError(f"{location}.counts must be an object")
        for count_name in ("ref_n", "prot_n"):
            count = _strict_finite_number(
                counts.get(count_name), f"{location}.counts.{count_name}"
            )
            if count <= 0 or not count.is_integer():
                raise ValueError(f"{location}.counts.{count_name} must be a positive integer")
        _strict_metric_block(entry.get("air"), f"{location}.air")

    for section, fields in (
        ("bias_preservation", ("abs_delta_air", "rel_delta_air")),
        ("improvement", ("abs_uplift_air", "rel_uplift_air")),
    ):
        values = payload.get(section)
        if not isinstance(values, dict):
            raise ValueError(f"slices.{section} must be an object")
        for field in fields:
            _strict_finite_number(values.get(field), f"slices.{section}.{field}")


def _strict_validate_sap(payload: dict[str, Any]) -> None:
    thresholds = payload.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("sap.thresholds must be a mapping")
    for field in ("air_min", "tpr_gap_max", "fpr_gap_max", "ece_max"):
        value = _strict_finite_number(thresholds.get(field), f"sap.thresholds.{field}")
        if not 0 <= value <= 1:
            raise ValueError(f"sap.thresholds.{field} must be in [0, 1]")


def _strict_validate_metrics_csv(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"required metrics CSV file is missing: {path}")
    try:
        metrics = pd.read_csv(path)
    except (OSError, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError(f"required metrics CSV file is malformed: {path}") from exc
    required_columns = {
        "run_id",
        "split",
        "model_id",
        "metric",
        "group",
        "value",
        "lower_ci",
        "upper_ci",
        "n",
        "method",
        "ci_degenerate",
    }
    if not required_columns.issubset(metrics.columns):
        raise ValueError("metrics CSV is missing required columns")
    if metrics.empty:
        raise ValueError("metrics CSV must contain at least one row")
    for field in ("value", "lower_ci", "upper_ci", "n"):
        try:
            values = pd.to_numeric(metrics[field], errors="raise")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"metrics CSV column {field} must be numeric") from exc
        if not values.map(math.isfinite).all():
            raise ValueError(f"metrics CSV column {field} must contain finite values")
        if field == "n" and (
            (values <= 0).any()
            or not values.map(lambda value: float(value).is_integer()).all()
        ):
            raise ValueError("metrics CSV column n must contain positive integers")


def _strict_validate_inputs(
    uncertainty_path: Path,
    slices_path: Path,
    metrics_path: Path,
    sap_path: Path,
) -> None:
    uncertainty = _strict_load_json(uncertainty_path, "uncertainty")
    slices = _strict_load_json(slices_path, "fairness slices")
    sap = _strict_load_yaml(sap_path, "SAP")
    _strict_validate_uncertainty(uncertainty)
    _strict_validate_slices(slices)
    _strict_validate_sap(sap)
    _strict_validate_metrics_csv(metrics_path)

def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _latex_escape(text: str) -> str:
    return (
        text.replace("\\", "\\textbackslash{}")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("$", "\\$")
        .replace("#", "\\#")
        .replace("_", "\\_")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("~", "\\textasciitilde{}")
        .replace("^", "\\textasciicircum{}")
    )


def _fmt_num(x: Any, *, decimals: int = 3) -> str:
    try:
        val = float(x)
    except Exception:
        return "TBD"
    if not math.isfinite(val):
        return "TBD"
    if float(val).is_integer():
        return f"\\num{{{int(val)}}}"
    formatted = f"{val:.{decimals}f}".rstrip("0").rstrip(".")
    if formatted in {"-0", "-0.0"}:
        formatted = "0"
    return f"\\num{{{formatted}}}"


def _fmt_int_count(x: Any) -> str:
    try:
        val = int(x)
    except Exception:
        return "TBD"
    return str(val)


_P_VALUE_SMALL_SI_OPTS = "round-mode=figures,round-precision=3"
_P_VALUE_MEDIUM_SI_OPTS = "round-mode=places,round-precision=4"


def _fmt_p_value(x: Any) -> str:
    try:
        val = float(x)
    except Exception:
        return "TBD"
    if not math.isfinite(val):
        return "TBD"
    if val == 0:
        # Avoid siunitx underflow-to-zero display; keep numeric for S columns.
        return f"\\num[{_P_VALUE_SMALL_SI_OPTS}]{{1e-308}}"
    if val < 1e-4:
        return f"\\num[{_P_VALUE_SMALL_SI_OPTS}]{{{val:.3e}}}"
    return f"\\num[{_P_VALUE_MEDIUM_SI_OPTS}]{{{val:.4f}}}"


def _truthy_int(val: Any) -> int:
    if isinstance(val, bool):
        return 1 if val else 0
    if val is None:
        return 0
    s = str(val).strip().lower()
    return 1 if s in {"1", "true", "yes", "on"} else 0


def _ci_parts(ci: Any) -> tuple[Any, Any]:
    if isinstance(ci, (list, tuple)) and len(ci) == 2:
        return ci[0], ci[1]
    return None, None


def _write_table(
    out_path: Path,
    *,
    column_spec: str,
    empty_span_cols: int,
    header: str,
    rows: list[list[str]],
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"\\begin{{tabular}}{{{column_spec}}}\n\\toprule\n")
        f.write(header + "\n\\midrule\n")
        for r in rows:
            f.write(" & ".join(r) + "\\\\\n")
        if not rows:
            f.write(
                f"\\multicolumn{{{int(empty_span_cols)}}}{{c}}{{\\emph{{Not evaluated in this scenario}}}}\\\\\n"
            )
        f.write("\\bottomrule\n\\end{tabular}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uncertainty", default="intake/metrics_uncertainty.json")
    ap.add_argument("--slices", default="intake/fairness_slices.json")
    ap.add_argument("--metrics", default="intake/metrics_long.csv")
    ap.add_argument("--sap", default="config/sap.yaml")
    ap.add_argument("--outdir", default="includes")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Reject missing, malformed, or incomplete publication inputs before writing outputs",
    )
    args = ap.parse_args()

    uncertainty_path = Path(args.uncertainty)
    slices_path = Path(args.slices)
    metrics_path = Path(args.metrics)
    sap_path = Path(args.sap)
    if args.strict:
        try:
            _strict_validate_inputs(
                uncertainty_path, slices_path, metrics_path, sap_path
            )
        except ValueError as exc:
            ap.error(str(exc))

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    sap = _load_yaml(sap_path)
    thr = sap.get("thresholds") if isinstance(sap, dict) else {}
    thr = thr if isinstance(thr, dict) else {}
    air_thr = float(thr.get("air_min", 0.80))
    tpr_thr = float(thr.get("tpr_gap_max", 0.05))
    fpr_thr = float(thr.get("fpr_gap_max", 0.05))
    ece_thr = float(thr.get("ece_max", 0.02))

    # Defaults (legacy compatibility macros)
    min_air = float("nan")
    num_air_viol = 0
    max_ece = float("nan")
    num_ece_viol = 0
    num_tpr_viol = 0
    num_fpr_viol = 0

    # Deterministic SoT payload (preferred)
    gender_ref = ""
    gender_prot = ""
    race_ref = ""
    race_worst = ""
    show_race_main = 0
    race_min_group_n = 0
    race_min_group_pct = 0.0

    gender_air_point: Any = None
    gender_air_ci: Any = None
    gender_air_p: Any = None
    gender_srg_point: Any = None
    gender_srg_ci: Any = None

    race_air_point: Any = None
    race_air_ci: Any = None
    race_air_p: Any = None
    race_air_p_adj: Any = None
    race_srg_point: Any = None
    race_srg_ci: Any = None

    air_rows: list[list[str]] = []
    srg_rows: list[list[str]] = []
    slice_rows: list[list[str]] = []
    gender_slices_available = 0

    hist_air_point: Any = None
    hist_air_ci: Any = None
    amp_air_point: Any = None
    amp_air_ci: Any = None
    intr_air_point: Any = None
    intr_air_ci: Any = None
    gender_uplift_abs: Any = None
    gender_uplift_rel: Any = None
    gender_fidelity_abs: Any = None
    gender_fidelity_rel: Any = None

    slices_payload = _load_json(slices_path) if slices_path.exists() else {}
    if (
        isinstance(slices_payload, dict)
        and slices_payload.get("schema_version") == "fairness_slices.v1"
    ):
        slices = slices_payload.get("slices") if isinstance(slices_payload.get("slices"), dict) else {}
        # Prefer slice payload group orientation for display.
        gender_ref = str(slices_payload.get("reference_group") or gender_ref)
        gender_prot = str(slices_payload.get("protected_group") or gender_prot)

        def _pair_air(pair: Any) -> tuple[Any, Any]:
            if not isinstance(pair, dict):
                return None, None
            air = pair.get("air") if isinstance(pair.get("air"), dict) else {}
            return air.get("point"), air.get("ci95")

        def _counts(pair: Any) -> tuple[int, int]:
            if not isinstance(pair, dict):
                return 0, 0
            counts = pair.get("counts") if isinstance(pair.get("counts"), dict) else {}
            try:
                ref_n = int(counts.get("ref_n", 0) or 0)
            except Exception:
                ref_n = 0
            try:
                prot_n = int(counts.get("prot_n", 0) or 0)
            except Exception:
                prot_n = 0
            return ref_n, prot_n

        def _compliance_label(point: Any) -> str:
            try:
                return "PASS" if float(point) >= air_thr else "FAIL"
            except Exception:
                return "TBD"

        for key, label in (
            ("historical", "Historical"),
            ("amplification", "Amplification (bias-preserving)"),
            ("intrinsic", "Intrinsic (de-biased)"),
        ):
            pair = slices.get(key)
            if not isinstance(pair, dict):
                continue
            pt, ci = _pair_air(pair)
            lo, hi = _ci_parts(ci)
            ref_n, prot_n = _counts(pair)
            slice_rows.append(
                [
                    _latex_escape(label),
                    _fmt_int_count(ref_n),
                    _fmt_int_count(prot_n),
                    _fmt_num(pt),
                    _fmt_num(lo),
                    _fmt_num(hi),
                    _latex_escape(_compliance_label(pt)),
                ]
            )

        hist_air_point, hist_air_ci = _pair_air(slices.get("historical"))
        amp_air_point, amp_air_ci = _pair_air(slices.get("amplification"))
        intr_air_point, intr_air_ci = _pair_air(slices.get("intrinsic"))

        gender_slices_available = int(
            isinstance(slices.get("historical"), dict)
            and isinstance(slices.get("amplification"), dict)
            and isinstance(slices.get("intrinsic"), dict)
        )

        imp = slices_payload.get("improvement") if isinstance(slices_payload.get("improvement"), dict) else {}
        bp = (
            slices_payload.get("bias_preservation")
            if isinstance(slices_payload.get("bias_preservation"), dict)
            else {}
        )
        gender_uplift_abs = imp.get("abs_uplift_air")
        gender_uplift_rel = imp.get("rel_uplift_air")
        gender_fidelity_abs = bp.get("abs_delta_air")
        gender_fidelity_rel = bp.get("rel_delta_air")

    uncertainty = _load_json(uncertainty_path) if uncertainty_path.exists() else {}
    fu = uncertainty.get("fairness_uncertainty") if isinstance(uncertainty, dict) else None

    if isinstance(fu, dict) and fu:
        gender = fu.get("gender") if isinstance(fu.get("gender"), dict) else {}
        race = fu.get("race") if isinstance(fu.get("race"), dict) else {}

        gender_ref = str(gender.get("reference_group") or "")
        gender_prot = str(gender.get("protected_group") or "")
        gender_air = gender.get("air") if isinstance(gender.get("air"), dict) else {}
        gender_srg = gender.get("srg") if isinstance(gender.get("srg"), dict) else {}

        gender_air_point = gender_air.get("point")
        gender_air_ci = gender_air.get("ci95")
        gender_air_p = gender_air.get("p_value")
        gender_srg_point = gender_srg.get("point")
        gender_srg_ci = gender_srg.get("ci95")

        g_lo, g_hi = _ci_parts(gender_air_ci)
        air_rows.append(
            [
                "gender",
                _latex_escape(gender_prot),
                _latex_escape(gender_ref),
                _fmt_num(gender_air_point),
                _fmt_num(g_lo),
                _fmt_num(g_hi),
                _fmt_p_value(gender_air_p),
            ]
        )
        gs_lo, gs_hi = _ci_parts(gender_srg_ci)
        srg_rows.append(
            [
                "gender",
                _latex_escape(gender_prot),
                _latex_escape(gender_ref),
                _fmt_num(gender_srg_point),
                _fmt_num(gs_lo),
                _fmt_num(gs_hi),
                _fmt_p_value(gender_air_p),
            ]
        )

        try:
            if isinstance(gender_air_point, (int, float)) and not math.isnan(
                float(gender_air_point)
            ):
                min_air = float(gender_air_point)
                num_air_viol = int(float(gender_air_point) < air_thr)
        except Exception:
            pass

        race_ref = str(race.get("reference_group") or "")
        show_race_main = _truthy_int(race.get("display_in_main_pdf"))
        observed = race.get("observed") if isinstance(race.get("observed"), dict) else {}
        try:
            race_min_group_n = int(observed.get("min_group_n", 0) or 0)
        except Exception:
            race_min_group_n = 0
        try:
            race_min_group_pct = float(observed.get("min_group_pct", 0.0) or 0.0)
        except Exception:
            race_min_group_pct = 0.0

        pairs = race.get("pairs") if isinstance(race.get("pairs"), dict) else {}
        race_worst = str(race.get("worst_case_pair") or "")
        worst_pair = pairs.get(race_worst) if isinstance(pairs.get(race_worst), dict) else {}
        worst_air = worst_pair.get("air") if isinstance(worst_pair.get("air"), dict) else {}
        worst_srg = worst_pair.get("srg") if isinstance(worst_pair.get("srg"), dict) else {}

        race_air_point = worst_air.get("point")
        race_air_ci = worst_air.get("ci95")
        race_air_p = worst_air.get("p_value")
        race_air_p_adj = worst_air.get("p_value_adjusted")
        race_srg_point = worst_srg.get("point")
        race_srg_ci = worst_srg.get("ci95")

        if show_race_main and race_worst:
            r_lo, r_hi = _ci_parts(race_air_ci)
            air_rows.append(
                [
                    "race",
                    _latex_escape(race_worst),
                    _latex_escape(race_ref),
                    _fmt_num(race_air_point),
                    _fmt_num(r_lo),
                    _fmt_num(r_hi),
                    _fmt_p_value(race_air_p_adj if race_air_p_adj is not None else race_air_p),
                ]
            )
            rs_lo, rs_hi = _ci_parts(race_srg_ci)
            srg_rows.append(
                [
                    "race",
                    _latex_escape(race_worst),
                    _latex_escape(race_ref),
                    _fmt_num(race_srg_point),
                    _fmt_num(rs_lo),
                    _fmt_num(rs_hi),
                    _fmt_p_value(race_air_p_adj if race_air_p_adj is not None else race_air_p),
                ]
            )

            try:
                if isinstance(race_air_point, (int, float)) and not math.isnan(
                    float(race_air_point)
                ):
                    min_air = (
                        float(min(float(min_air), float(race_air_point)))
                        if not math.isnan(min_air)
                        else float(race_air_point)
                    )
                    num_air_viol += int(float(race_air_point) < air_thr)
            except Exception:
                pass

    # Synthetic quality (SQ) from certificate (optional, used for v4 advisory text).
    sq_threshold_used: Any = None
    sq_threshold_met: Any = None
    sq_score: Any = None
    for p in (
        Path("intake/certificates/synthetic_quality_certificate.json"),
        Path("certificates/synthetic_quality_certificate.json"),
    ):
        if p.exists():
            sq = _load_json(p)
            sq_threshold_used = sq.get("quality_threshold_used")
            sq_threshold_met = sq.get("quality_threshold_met")
            sq_score = sq.get("overall_quality_score")
            break

    # Legacy ECE parsing (from metrics_long.csv) so the calibration section can
    # truthfully show “not evaluated” when ECE is absent.
    ece = pd.DataFrame()
    if metrics_path.exists():
        try:
            m = pd.read_csv(metrics_path)
            m["metric_l"] = m["metric"].astype(str).str.lower()
            ece = m[m["metric_l"] == "ece"].copy()
            if not ece.empty:
                max_ece = float(ece["value"].max())
                num_ece_viol = int((ece["value"] > ece_thr).sum())
        except Exception:
            ece = pd.DataFrame()

    # Write macros (thresholds + key SoT values)
    with (outdir / "metrics_macros.tex").open("w", encoding="utf-8") as f:
        f.write("% Auto-generated metrics macros\n")
        f.write(f"\\renewcommand{{\\AIRThreshold}}{{{air_thr:.3f}}}\n")
        f.write(f"\\renewcommand{{\\TprGapThreshold}}{{{tpr_thr:.3f}}}\n")
        f.write(f"\\renewcommand{{\\FprGapThreshold}}{{{fpr_thr:.3f}}}\n")
        f.write(f"\\renewcommand{{\\EceThreshold}}{{{ece_thr:.3f}}}\n")

        if math.isnan(min_air):
            f.write("\\renewcommand{\\MinAIR}{TBD}\n")
        else:
            f.write(f"\\renewcommand{{\\MinAIR}}{{{_fmt_num(min_air)}}}\n")

        f.write(f"\\renewcommand{{\\NumAIRViolations}}{{{int(num_air_viol)}}}\n")

        if math.isnan(max_ece):
            f.write("\\renewcommand{\\MaxECE}{TBD}\n")
        else:
            f.write(f"\\renewcommand{{\\MaxECE}}{{{_fmt_num(max_ece)}}}\n")

        f.write(f"\\renewcommand{{\\NumTPRGapViol}}{{{int(num_tpr_viol)}}}\n")
        f.write(f"\\renewcommand{{\\NumFPRGapViol}}{{{int(num_fpr_viol)}}}\n")
        f.write(f"\\renewcommand{{\\NumECEViolations}}{{{int(num_ece_viol)}}}\n")

        f.write(f"\\renewcommand{{\\GenderReferenceGroup}}{{{_latex_escape(gender_ref)}}}\n")
        f.write(
            f"\\renewcommand{{\\GenderProtectedGroup}}{{{_latex_escape(gender_prot)}}}\n"
        )
        f.write(f"\\renewcommand{{\\GenderAIR}}{{{_fmt_num(gender_air_point)}}}\n")
        if isinstance(gender_air_ci, (list, tuple)) and len(gender_air_ci) == 2:
            f.write(f"\\renewcommand{{\\GenderAIRLCI}}{{{_fmt_num(gender_air_ci[0])}}}\n")
            f.write(f"\\renewcommand{{\\GenderAIRUCI}}{{{_fmt_num(gender_air_ci[1])}}}\n")
        f.write(
            f"\\renewcommand{{\\GenderAIRPValue}}{{{_fmt_p_value(gender_air_p)}}}\n"
        )
        f.write(f"\\renewcommand{{\\GenderSRG}}{{{_fmt_num(gender_srg_point)}}}\n")
        if isinstance(gender_srg_ci, (list, tuple)) and len(gender_srg_ci) == 2:
            f.write(f"\\renewcommand{{\\GenderSRGLCI}}{{{_fmt_num(gender_srg_ci[0])}}}\n")
            f.write(f"\\renewcommand{{\\GenderSRGUCI}}{{{_fmt_num(gender_srg_ci[1])}}}\n")

        # Slice-level gender AIR (historical / amplification / intrinsic)
        f.write(f"\\renewcommand{{\\GenderSlicesAvailable}}{{{int(gender_slices_available)}}}\n")
        f.write(f"\\renewcommand{{\\GenderAIRHistorical}}{{{_fmt_num(hist_air_point)}}}\n")
        if isinstance(hist_air_ci, (list, tuple)) and len(hist_air_ci) == 2:
            f.write(
                f"\\renewcommand{{\\GenderAIRHistoricalLCI}}{{{_fmt_num(hist_air_ci[0])}}}\n"
            )
            f.write(
                f"\\renewcommand{{\\GenderAIRHistoricalUCI}}{{{_fmt_num(hist_air_ci[1])}}}\n"
            )
        else:
            f.write("\\renewcommand{\\GenderAIRHistoricalLCI}{TBD}\n")
            f.write("\\renewcommand{\\GenderAIRHistoricalUCI}{TBD}\n")

        f.write(f"\\renewcommand{{\\GenderAIRAmplification}}{{{_fmt_num(amp_air_point)}}}\n")
        if isinstance(amp_air_ci, (list, tuple)) and len(amp_air_ci) == 2:
            f.write(
                f"\\renewcommand{{\\GenderAIRAmplificationLCI}}{{{_fmt_num(amp_air_ci[0])}}}\n"
            )
            f.write(
                f"\\renewcommand{{\\GenderAIRAmplificationUCI}}{{{_fmt_num(amp_air_ci[1])}}}\n"
            )
        else:
            f.write("\\renewcommand{\\GenderAIRAmplificationLCI}{TBD}\n")
            f.write("\\renewcommand{\\GenderAIRAmplificationUCI}{TBD}\n")

        f.write(f"\\renewcommand{{\\GenderAIRIntrinsic}}{{{_fmt_num(intr_air_point)}}}\n")
        if isinstance(intr_air_ci, (list, tuple)) and len(intr_air_ci) == 2:
            f.write(
                f"\\renewcommand{{\\GenderAIRIntrinsicLCI}}{{{_fmt_num(intr_air_ci[0])}}}\n"
            )
            f.write(
                f"\\renewcommand{{\\GenderAIRIntrinsicUCI}}{{{_fmt_num(intr_air_ci[1])}}}\n"
            )
        else:
            f.write("\\renewcommand{\\GenderAIRIntrinsicLCI}{TBD}\n")
            f.write("\\renewcommand{\\GenderAIRIntrinsicUCI}{TBD}\n")

        # Uplift/fidelity summaries (AIR)
        f.write(f"\\renewcommand{{\\GenderAIRUpliftAbs}}{{{_fmt_num(gender_uplift_abs)}}}\n")
        try:
            f.write(
                f"\\renewcommand{{\\GenderAIRUpliftRelPct}}{{\\num{{{float(gender_uplift_rel) * 100.0:.3f}}}}}\n"
            )
        except Exception:
            f.write("\\renewcommand{\\GenderAIRUpliftRelPct}{TBD}\n")

        f.write(f"\\renewcommand{{\\GenderAIRFidelityAbs}}{{{_fmt_num(gender_fidelity_abs)}}}\n")
        try:
            f.write(
                f"\\renewcommand{{\\GenderAIRFidelityRelPct}}{{\\num{{{float(gender_fidelity_rel) * 100.0:.2f}}}}}\n"
            )
        except Exception:
            f.write("\\renewcommand{\\GenderAIRFidelityRelPct}{TBD}\n")

        f.write(f"\\renewcommand{{\\ShowRaceMain}}{{{int(show_race_main)}}}\n")
        f.write(f"\\renewcommand{{\\RaceReferenceGroup}}{{{_latex_escape(race_ref)}}}\n")
        f.write(f"\\renewcommand{{\\RaceWorstCaseGroup}}{{{_latex_escape(race_worst)}}}\n")
        f.write(f"\\renewcommand{{\\RaceWorstAIR}}{{{_fmt_num(race_air_point)}}}\n")
        if isinstance(race_air_ci, (list, tuple)) and len(race_air_ci) == 2:
            f.write(f"\\renewcommand{{\\RaceWorstAIRLCI}}{{{_fmt_num(race_air_ci[0])}}}\n")
            f.write(f"\\renewcommand{{\\RaceWorstAIRUCI}}{{{_fmt_num(race_air_ci[1])}}}\n")
        f.write(
            f"\\renewcommand{{\\RaceWorstAIRPValue}}{{{_fmt_p_value(race_air_p)}}}\n"
        )
        f.write(
            f"\\renewcommand{{\\RaceWorstAIRPValueAdj}}{{{_fmt_p_value(race_air_p_adj)}}}\n"
        )
        f.write(f"\\renewcommand{{\\RaceObservedMinGroupN}}{{{int(race_min_group_n)}}}\n")
        f.write(f"\\renewcommand{{\\RaceObservedMinGroupPct}}{{{race_min_group_pct:.4f}}}\n")

        if sq_threshold_used is not None:
            try:
                f.write(
                    f"\\renewcommand{{\\SqThresholdUsed}}{{{float(sq_threshold_used):.3f}}}\n"
                )
            except Exception:
                f.write("\\renewcommand{\\SqThresholdUsed}{TBD}\n")
        if sq_threshold_met is not None:
            f.write(f"\\renewcommand{{\\SqThresholdMet}}{{{_truthy_int(sq_threshold_met)}}}\n")
        if sq_score is not None:
            f.write(f"\\renewcommand{{\\SqScore}}{{{_fmt_num(sq_score)}}}\n")

    # Deterministic SoT tables
    _write_table(
        outdir / "table_air_summary.tex",
        column_spec="lllSSSr",
        empty_span_cols=7,
        header="attribute & protected & reference & {AIR} & {LCI} & {UCI} & {p}\\\\",
        rows=air_rows,
    )
    _write_table(
        outdir / "table_srg_summary.tex",
        column_spec="lllSSSr",
        empty_span_cols=7,
        header="attribute & protected & reference & {SRG} & {LCI} & {UCI} & {p}\\\\",
        rows=srg_rows,
    )

    # ECE table (legacy; may be empty)
    ece_rows: list[list[str]] = []
    if not ece.empty:
        if "ci_low" in ece.columns and "ci_high" in ece.columns:
            ci_low_col = "ci_low"
            ci_high_col = "ci_high"
        else:
            ci_low_col = "lower_ci"
            ci_high_col = "upper_ci"
        for _, r in ece.iterrows():
            ece_rows.append(
                [
                    _latex_escape(str(r.get("run_id", ""))),
                    _latex_escape(str(r.get("model_id", ""))),
                    _latex_escape(str(r.get("split", ""))),
                    _fmt_num(r.get("value", "")),
                    _fmt_num(r.get(ci_low_col, "")),
                    _fmt_num(r.get(ci_high_col, "")),
                ]
            )
    _write_table(
        outdir / "table_ece_summary.tex",
        column_spec="lllSSS",
        empty_span_cols=6,
        header="run & model & split & {ECE} & {LCI} & {UCI}\\\\",
        rows=ece_rows,
    )

    # Slice table (gender only)
    _write_table(
        outdir / "table_gender_air_slices.tex",
        column_spec="lrrSSSl",
        empty_span_cols=7,
        header="slice & {$n_{ref}$} & {$n_{prot}$} & {AIR} & {LCI} & {UCI} & {compliance}\\\\",
        rows=slice_rows,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
