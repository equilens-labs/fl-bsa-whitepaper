#!/usr/bin/env python3
"""Generate reviewed v5.0.1 characterization summaries, tables, and figures."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from characterization_contract import (
    INTERNAL_AIR_SCREEN,
    UTILITY_SUMMARY_PATH,
    UTILITY_SUMMARY_SHA256,
)


PRODUCT_COMMIT = "cc32b3a8d13cb75419b0dec1d4b9bdf5a3eb90c2"
PRODUCT_TAG = "v5.0.1"
SRG_METHOD = "conservative_wilson_endpoint_difference"
PDF_METADATA = {
    "Creator": "Equilens FL-BSA whitepaper",
    "Producer": "Equilens FL-BSA whitepaper",
    "CreationDate": None,
    "ModDate": None,
}
COLORS = {
    "navy": "#1B365D",
    "blue": "#0072B2",
    "orange": "#E69F00",
    "green": "#009E73",
    "red": "#D55E00",
    "grey": "#777777",
}


class AssetError(ValueError):
    """Raised when the source evidence does not satisfy publication contracts."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssetError(f"unable to read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AssetError(f"{path} must contain a JSON object")
    return value


def _read_digest_anchored_json(
    path: Path, expected_sha256: str
) -> dict[str, Any]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise AssetError(f"unable to read {path}: {exc}") from exc
    actual_sha256 = hashlib.sha256(data).hexdigest()
    _require(
        actual_sha256 == expected_sha256,
        f"{path} does not match PDF-disclosed SHA-256",
    )
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssetError(f"unable to read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AssetError(f"{path} must contain a JSON object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssetError(message)


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AssetError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise AssetError(f"{label} must be finite")
    return number


def _fmt(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def _fmt_p(value: float) -> str:
    return f"{value:.3f}" if value >= 0.001 else f"{value:.2e}"


def _tex(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(char, char) for char in value)


def _screen_relation(
    point: float, lower: float, upper: float, screen: float
) -> tuple[str, str]:
    point_relation = "at/above" if point >= screen else "below"
    if upper < screen:
        interval_relation = "entirely below"
    elif lower >= screen:
        interval_relation = "entirely above"
    else:
        interval_relation = "crosses"
    return point_relation, interval_relation


def _quality(cert: dict[str, Any], branch: str) -> dict[str, Any]:
    statistical = cert.get("statistical_comparison") or {}
    correlation = cert.get("correlation_analysis") or {}
    demographic = cert.get("demographic_alignment") or {}
    privacy = cert.get("privacy_metrics") or {}
    utility_status = cert.get("synthetic_utility_check")
    _require(utility_status == "not_evaluated", f"unexpected certified utility status for {branch}")
    _require(privacy.get("differential_privacy_claimed") is False, f"unexpected privacy claim for {branch}")
    return {
        "branch": branch,
        "overall_quality_score": _finite(cert.get("overall_quality_score"), f"{branch} quality"),
        "quality_threshold": _finite(cert.get("quality_threshold_used"), f"{branch} threshold"),
        "quality_threshold_met": cert.get("quality_threshold_met") is True,
        "distribution_score": _finite(statistical.get("overall_distribution_score"), f"{branch} distribution"),
        "correlation_preservation_score": _finite(correlation.get("correlation_preservation_score"), f"{branch} correlation"),
        "max_correlation_difference": _finite(correlation.get("max_correlation_difference"), f"{branch} max correlation difference"),
        "demographic_max_drift_pp": _finite(demographic.get("max_abs_pp_drift"), f"{branch} demographic drift"),
        "privacy_heuristic_score": _finite(privacy.get("privacy_preservation_score"), f"{branch} privacy heuristic"),
        "privacy_heuristic_scope": privacy.get("privacy_preservation_score_scope"),
        "exact_output_wall_pre_duplicates": int(privacy.get("exact_output_wall_pre_duplicate_count")),
        "exact_output_wall_post_duplicates": int(privacy.get("exact_output_wall_post_duplicate_count")),
        "near_duplicate_status": privacy.get("near_duplicate_count_status"),
        "differential_privacy_claimed": False,
        "certified_utility_status": utility_status,
    }


def build_summary(root: Path) -> dict[str, Any]:
    manifest = _read_json(root / "intake/manifest.json")
    slices_payload = _read_json(root / "intake/fairness_slices.json")
    uncertainty = _read_json(root / "intake/metrics_uncertainty.json")
    robustness = _read_json(
        root / "evidence/v5.0.1/robustness/robustness_summary_merged.json"
    )
    utility = _read_digest_anchored_json(
        root / UTILITY_SUMMARY_PATH, UTILITY_SUMMARY_SHA256
    )
    amp_cert = _read_json(
        root
        / "intake/certificates/branch_amplification__synthetic_quality_certificate.json"
    )
    intrinsic_cert = _read_json(
        root / "intake/certificates/branch_intrinsic__synthetic_quality_certificate.json"
    )

    _require(manifest.get("source_commit") == PRODUCT_COMMIT, "manifest is not exact v5.0.1")
    screen = _finite(slices_payload.get("air_threshold"), "AIR screen")
    _require(screen == INTERNAL_AIR_SCREEN, "unexpected AIR screen")
    slice_rows: list[dict[str, Any]] = []
    labels = {
        "historical": "Historical fixture",
        "amplification": "Amplification branch",
        "intrinsic": "Intrinsic parity-policy control",
    }
    for key in ("historical", "amplification", "intrinsic"):
        row = (slices_payload.get("slices") or {}).get(key) or {}
        air = row.get("air") or {}
        srg = row.get("srg") or {}
        point = _finite(air.get("point"), f"{key} AIR")
        lower = _finite((air.get("ci95") or [None, None])[0], f"{key} AIR lower")
        upper = _finite((air.get("ci95") or [None, None])[1], f"{key} AIR upper")
        _require(srg.get("method") == SRG_METHOD, f"wrong SRG method for {key}")
        point_relation, interval_relation = _screen_relation(
            point, lower, upper, screen
        )
        inference_status = "conditional_on_generated_fixture"
        interval_status = "conditional_95_percent_interval"
        p_value_status = "conditional_two_proportion_test"
        if key == "intrinsic":
            interval_relation = "not_applicable_policy_determined"
            inference_status = "policy_determined"
            interval_status = "format_symmetry_only_not_inferential"
            p_value_status = "format_symmetry_only_not_inferential"
        slice_rows.append(
            {
                "id": key,
                "label": labels[key],
                "reference_group": row.get("reference_group"),
                "protected_group": row.get("protected_group"),
                "reference_n": int((row.get("counts") or {}).get("ref_n")),
                "protected_n": int((row.get("counts") or {}).get("prot_n")),
                "air": point,
                "air_ci95": [lower, upper],
                "air_interval_display_status": interval_status,
                "p_value": _finite(air.get("p_value"), f"{key} p-value"),
                "p_value_display_status": p_value_status,
                "srg": _finite(srg.get("point"), f"{key} SRG"),
                "srg_endpoint_range": [
                    _finite((srg.get("ci95") or [None, None])[0], f"{key} SRG lower"),
                    _finite((srg.get("ci95") or [None, None])[1], f"{key} SRG upper"),
                ],
                "srg_method": SRG_METHOD,
                "srg_range_status": (
                    "difference_of_95_percent_wilson_endpoints_"
                    "not_a_calibrated_95_percent_interval"
                ),
                "inference_status": inference_status,
                "point_screen_relation": point_relation,
                "interval_screen_relation": interval_relation,
            }
        )

    fairness = uncertainty.get("fairness_uncertainty") or {}
    race = fairness.get("race") or {}
    _require(race.get("configured_reference_group") == "white", "wrong configured race reference")
    _require(race.get("reference_group") == "black", "wrong effective race reference")
    _require(
        race.get("reference_group_selection_policy") == "highest_selection_rate_four_fifths",
        "wrong race policy",
    )
    race_pairs = race.get("pairs") or {}
    _require(bool(race_pairs), "race pair evidence is missing")
    minimum_count_group = min(
        race_pairs,
        key=lambda group: int((race_pairs[group].get("counts") or {}).get("prot_n")),
    )
    observed_race = race.get("observed") or {}
    display_policy = (
        (race.get("policy") or {}).get("display_race_in_main_pdf") or {}
    )
    minimum_group_n = int(observed_race.get("min_group_n"))
    minimum_group_pct = _finite(
        observed_race.get("min_group_pct"), "race minimum group share"
    )
    display_min_group_n = int(display_policy.get("min_group_n"))
    display_min_group_pct = _finite(
        display_policy.get("min_group_pct"), "race display share floor"
    )
    count_floor_met = minimum_group_n >= display_min_group_n
    share_floor_met = minimum_group_pct >= display_min_group_pct
    display_expected = count_floor_met and share_floor_met
    _require(
        race.get("display_in_main_pdf") is display_expected,
        "race display policy result mismatch",
    )
    _require(not display_expected, "race display policy changed")
    suppression_reasons = []
    if not count_floor_met:
        suppression_reasons.append(
            "minimum_observed_group_count_below_configured_display_floor"
        )
    if not share_floor_met:
        suppression_reasons.append(
            "minimum_observed_group_share_below_configured_display_floor"
        )
    if not count_floor_met and not share_floor_met:
        suppression_reason = (
            "minimum observed group count and share below respective "
            "configured display floors"
        )
    elif not count_floor_met:
        suppression_reason = (
            "minimum observed group count below configured display floor"
        )
    else:
        suppression_reason = (
            "minimum observed group share below configured display floor"
        )

    robustness_rows: list[dict[str, Any]] = []
    for scenario_id in ("balanced", "gender_bias", "outliers", "security"):
        aggregates = ((robustness.get("scenarios") or {}).get(scenario_id) or {}).get("aggregates") or {}
        band = (aggregates.get("numeric_bands") or {}).get("di") or {}
        _require(aggregates.get("pass_count") == 10, f"robustness failures in {scenario_id}")
        robustness_rows.append(
            {
                "id": scenario_id,
                "label": scenario_id.replace("_", " ").title(),
                "passes": int(aggregates.get("pass_count")),
                "runs": int(aggregates.get("planned_seed_count")),
                "air_min": _finite(band.get("min"), f"{scenario_id} AIR min"),
                "air_mean": _finite(band.get("mean"), f"{scenario_id} AIR mean"),
                "air_max": _finite(band.get("max"), f"{scenario_id} AIR max"),
                "air_stdev": _finite(band.get("stdev"), f"{scenario_id} AIR stdev"),
            }
        )

    return {
        "schema_version": "flbsa.whitepaper_characterization.v2",
        "document_version": "WP-5.0.1-candidate.1",
        "as_of": "2026-08-05",
        "publication_status": "candidate_not_published",
        "product": {
            "tag": PRODUCT_TAG,
            "commit": PRODUCT_COMMIT,
            "tag_object": "3a0ea6e4faea9d61aabcedebab2a838624fb587d",
        },
        "evidence": {
            "run_id": 30765888408,
            "run_attempt": 1,
            "run_uuid": manifest.get("run_id"),
            "dataset_hash": manifest.get("dataset_hash"),
            "primary_bundle_sha256": "f6a0bd9390565f7bd852b451e11b7384b1628c24caba02865b1ec94c1e263026",
        },
        "fairness": {
            "internal_air_screen": screen,
            "screen_is_legal_verdict": False,
            "single_run_inference_scope": "conditional_on_generated_fixture_and_configured_row_count",
            "srg_range_scope": (
                "difference_of_separate_95_percent_wilson_endpoints; "
                "not_a_calibrated_95_percent_interval"
            ),
            "slices": slice_rows,
            "race": {
                "configured_reference_group": race.get("configured_reference_group"),
                "effective_reference_group": race.get("reference_group"),
                "reference_policy": race.get("reference_group_selection_policy"),
                "display_in_main_pdf": display_expected,
                "suppression_reason": suppression_reason,
                "suppression_reasons": suppression_reasons,
                "minimum_count_group": minimum_count_group,
                "lowest_selection_rate_group": (race.get("selection_rate_range") or {}).get("min_group"),
                "minimum_group_n": minimum_group_n,
                "minimum_group_pct": minimum_group_pct,
                "display_min_group_n": display_min_group_n,
                "display_min_group_pct": display_min_group_pct,
                "minimum_group_n_floor_met": count_floor_met,
                "minimum_group_pct_floor_met": share_floor_met,
                "worst_case_pair": race.get("worst_case_pair"),
                "air_intervals_multiplicity_adjusted": False,
                "air_p_value_adjustment": "holm_bonferroni",
            },
        },
        "quality": {
            "amplification": _quality(amp_cert, "amplification"),
            "intrinsic": _quality(intrinsic_cert, "intrinsic"),
        },
        "robustness": {
            "complete": robustness.get("complete") is True,
            "planned_seeds": robustness.get("planned_seeds"),
            "scenarios": robustness_rows,
            "total_runs": sum(row["runs"] for row in robustness_rows),
            "total_passes": sum(row["passes"] for row in robustness_rows),
        },
        "utility": utility,
        "interpretation": {
            "intrinsic": "mechanical parity-policy branch-separation control; not a causal counterfactual",
            "certificate_integrity": "hash and internal predecessor linkage; public key absent from companion",
            "regulatory": "governance mapping only; no compliance determination",
        },
    }


def _write_macros(summary: dict[str, Any], output: Path) -> None:
    slices = {row["id"]: row for row in summary["fairness"]["slices"]}
    quality = summary["quality"]
    utility = summary["utility"]
    bands = utility["synthetic_train_bands"]
    baseline = utility["real_train_baseline"]
    below_chance_seed_count = sum(
        _finite((row.get("metrics") or {}).get("roc_auc"), "utility seed ROC AUC")
        < 0.5
        for row in utility["synthetic_train_results"]
    )
    race = summary["fairness"]["race"]
    macros = {
        "CharacterizationDocumentVersion": summary["document_version"],
        "ProductTag": summary["product"]["tag"],
        "InternalAIRScreen": _fmt(summary["fairness"]["internal_air_screen"], 2),
        "HistoricalAIR": _fmt(slices["historical"]["air"]),
        "HistoricalAIRLower": _fmt(slices["historical"]["air_ci95"][0]),
        "HistoricalAIRUpper": _fmt(slices["historical"]["air_ci95"][1]),
        "AmplificationAIR": _fmt(slices["amplification"]["air"]),
        "AmplificationAIRLower": _fmt(slices["amplification"]["air_ci95"][0]),
        "AmplificationAIRUpper": _fmt(slices["amplification"]["air_ci95"][1]),
        "IntrinsicAIR": _fmt(slices["intrinsic"]["air"]),
        "IntrinsicAIRLower": _fmt(slices["intrinsic"]["air_ci95"][0]),
        "IntrinsicAIRUpper": _fmt(slices["intrinsic"]["air_ci95"][1]),
        "AmplificationQuality": _fmt(quality["amplification"]["overall_quality_score"]),
        "IntrinsicQuality": _fmt(quality["intrinsic"]["overall_quality_score"]),
        "RaceConfiguredReference": str(race["configured_reference_group"]),
        "RaceEffectiveReference": str(race["effective_reference_group"]),
        "RaceMinimumGroupN": str(race["minimum_group_n"]),
        "RaceMinimumGroupPct": _fmt(race["minimum_group_pct"] * 100, 2),
        "RaceDisplayMinGroupN": str(race["display_min_group_n"]),
        "RaceDisplayMinGroupPct": _fmt(
            race["display_min_group_pct"] * 100, 2
        ),
        "RaceCountFloorRelation": (
            "meets" if race["minimum_group_n_floor_met"] else "fails"
        ),
        "RaceShareFloorRelation": (
            "meets" if race["minimum_group_pct_floor_met"] else "fails"
        ),
        "RobustnessTotalRuns": str(summary["robustness"]["total_runs"]),
        "RobustnessTotalPasses": str(summary["robustness"]["total_passes"]),
        "UtilityBaselineAUC": _fmt(baseline["roc_auc"]),
        "UtilitySyntheticAUCMean": _fmt(bands["roc_auc"]["mean"]),
        "UtilitySyntheticAUCMin": _fmt(bands["roc_auc"]["min"]),
        "UtilitySyntheticAUCMax": _fmt(bands["roc_auc"]["max"]),
        "UtilitySkillRetentionMean": _fmt(bands["roc_auc_skill_retention"]["mean"]),
        "UtilitySkillRetentionMin": _fmt(bands["roc_auc_skill_retention"]["min"]),
        "UtilitySkillRetentionMax": _fmt(bands["roc_auc_skill_retention"]["max"]),
        "UtilitySkillRetentionMeanPct": _fmt(
            bands["roc_auc_skill_retention"]["mean"] * 100, 1
        ),
        "UtilityBelowChanceSeedCount": str(below_chance_seed_count),
        "UtilitySummaryShaRaw": UTILITY_SUMMARY_SHA256,
    }
    lines = ["% Auto-generated by scripts/gen_characterization_assets.py"]
    lines.extend(f"\\newcommand{{\\{key}}}{{{_tex(value)}}}" for key, value in macros.items())
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_tables(summary: dict[str, Any], outdir: Path) -> None:
    slice_lines = [
        r"\AccessibleTableHeaderRow",
        r"\begin{tabular}{@{}lrrrrl@{}}",
        r"\toprule",
        r"Slice & $n_{prot}$ & $n_{ref}$ & AIR & Reported range & Relation to 0.80 \\",
        r"\midrule",
    ]
    for row in summary["fairness"]["slices"]:
        if row["inference_status"] == "policy_determined":
            relation = f"point {row['point_screen_relation']}; inference N/A"
        else:
            relation = (
                f"point {row['point_screen_relation']}; "
                f"CI {row['interval_screen_relation']}"
            )
        slice_lines.append(
            f"{_tex(row['label'])} & {row['protected_n']} & {row['reference_n']} & "
            f"{_fmt(row['air'])} & [{_fmt(row['air_ci95'][0])}, {_fmt(row['air_ci95'][1])}] & "
            f"{_tex(relation)} \\\\"
        )
    slice_lines.extend([r"\bottomrule", r"\end{tabular}"])
    (outdir / "table_characterization_slices.tex").write_text(
        "\n".join(slice_lines) + "\n", encoding="utf-8"
    )

    quality_lines = [
        r"\AccessibleTableHeaderRow",
        r"\begin{tabular}{@{}lrrl@{}}",
        r"\toprule",
        r"Measure & Amplification & Intrinsic & Scope \\",
        r"\midrule",
    ]
    amp = summary["quality"]["amplification"]
    intrinsic = summary["quality"]["intrinsic"]
    quality_rows = (
        ("Overall quality", amp["overall_quality_score"], intrinsic["overall_quality_score"], "branch certificate"),
        ("Distribution score", amp["distribution_score"], intrinsic["distribution_score"], "univariate distribution"),
        ("Correlation preservation", amp["correlation_preservation_score"], intrinsic["correlation_preservation_score"], "eligible numeric pairs"),
        ("Privacy heuristic", amp["privacy_heuristic_score"], intrinsic["privacy_heuristic_score"], "not a privacy guarantee"),
    )
    for label, left, right, scope in quality_rows:
        quality_lines.append(
            f"{_tex(label)} & {_fmt(left)} & {_fmt(right)} & {_tex(scope)} \\\\"
        )
    quality_lines.extend([r"\bottomrule", r"\end{tabular}"])
    (outdir / "table_quality_summary.tex").write_text(
        "\n".join(quality_lines) + "\n", encoding="utf-8"
    )

    robustness_lines = [
        r"\AccessibleTableHeaderRow",
        r"\begin{tabular}{@{}lrrrr@{}}",
        r"\toprule",
        r"Scenario & Runs passing & AIR min & AIR mean & AIR max \\",
        r"\midrule",
    ]
    for row in summary["robustness"]["scenarios"]:
        robustness_lines.append(
            f"{_tex(row['label'])} & {row['passes']}/{row['runs']} & "
            f"{_fmt(row['air_min'])} & {_fmt(row['air_mean'])} & {_fmt(row['air_max'])} \\\\"
        )
    robustness_lines.extend([r"\bottomrule", r"\end{tabular}"])
    (outdir / "table_robustness_summary.tex").write_text(
        "\n".join(robustness_lines) + "\n", encoding="utf-8"
    )

    baseline = summary["utility"]["real_train_baseline"]
    bands = summary["utility"]["synthetic_train_bands"]
    utility_lines = [
        r"\AccessibleTableHeaderRow",
        r"\begin{tabular}{@{}lrrr@{}}",
        r"\toprule",
        r"Metric & Real-train baseline & Synthetic mean & Synthetic range \\",
        r"\midrule",
        f"ROC AUC & {_fmt(baseline['roc_auc'])} & {_fmt(bands['roc_auc']['mean'])} & [{_fmt(bands['roc_auc']['min'])}, {_fmt(bands['roc_auc']['max'])}] \\\\",
        f"Average precision & {_fmt(baseline['average_precision'])} & {_fmt(bands['average_precision']['mean'])} & [{_fmt(bands['average_precision']['min'])}, {_fmt(bands['average_precision']['max'])}] \\\\",
        f"Log loss & {_fmt(baseline['log_loss'])} & {_fmt(bands['log_loss']['mean'])} & [{_fmt(bands['log_loss']['min'])}, {_fmt(bands['log_loss']['max'])}] \\\\",
        r"\bottomrule",
        r"\end{tabular}",
    ]
    (outdir / "table_utility_summary.tex").write_text(
        "\n".join(utility_lines) + "\n", encoding="utf-8"
    )


def _style() -> None:
    mpl.rcParams.update(
        {
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
        }
    )


def _save(fig: Any, path: Path) -> None:
    fig.savefig(path, bbox_inches="tight", metadata=PDF_METADATA)
    plt.close(fig)


def _write_plots(summary: dict[str, Any], outdir: Path) -> None:
    _style()

    def box(ax: Any, x: float, y: float, width: float, height: float, title: str, body: str, color: str) -> None:
        patch = FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.02,rounding_size=0.02",
            linewidth=1.2,
            edgecolor=color,
            facecolor="white",
        )
        ax.add_patch(patch)
        ax.text(x + width / 2, y + height * 0.67, title, ha="center", va="center", weight="bold", color=color)
        ax.text(x + width / 2, y + height * 0.32, body, ha="center", va="center", fontsize=7.5, color="#222222")

    def arrow(ax: Any, start: tuple[float, float], end: tuple[float, float]) -> None:
        ax.add_patch(
            FancyArrowPatch(
                start,
                end,
                arrowstyle="-|>",
                mutation_scale=11,
                linewidth=1.1,
                color=COLORS["grey"],
                connectionstyle="arc3,rad=0",
            )
        )

    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    box(ax, 0.02, 0.35, 0.18, 0.30, "Run inputs", "Synthetic fixture\nSAP + branch policy", COLORS["navy"])
    box(ax, 0.29, 0.61, 0.23, 0.27, "Amplification", "Outcome retained\nSignal-preservation test", COLORS["blue"])
    box(ax, 0.29, 0.12, 0.23, 0.27, "Intrinsic control", "Outcome excluded\nEqual-rate post-label policy", COLORS["green"])
    box(ax, 0.61, 0.35, 0.18, 0.30, "Evidence\nsurfaces", "Fairness + quality\nHashes + provenance", COLORS["orange"])
    box(ax, 0.84, 0.35, 0.14, 0.30, "Human\nreview", "Interpret limits\nDecide use", COLORS["red"])
    arrow(ax, (0.20, 0.50), (0.29, 0.745))
    arrow(ax, (0.20, 0.50), (0.29, 0.255))
    arrow(ax, (0.52, 0.745), (0.61, 0.53))
    arrow(ax, (0.52, 0.255), (0.61, 0.47))
    arrow(ax, (0.79, 0.50), (0.84, 0.50))
    ax.text(0.5, 0.96, "FL-BSA dual-branch characterization flow", ha="center", va="center", fontsize=11, weight="bold")
    ax.text(0.5, 0.02, "The branch gap is an audit object; the intrinsic result is policy-imposed, not causal.", ha="center", va="bottom", fontsize=8)
    _save(fig, outdir / "characterization_architecture.pdf")

    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    chain = [
        (0.01, "v5.0.1 tag", "tag object +\nproduct commit", COLORS["navy"]),
        (0.18, "Runtime", "OCI image\ndigest", COLORS["blue"]),
        (0.35, "Release run", "run 30765888408\nattempt 1", COLORS["green"]),
        (0.52, "Evidence", "intake + 40-run\nGold aggregate", COLORS["orange"]),
        (0.69, "Companion", "file manifest +\nZIP digest", COLORS["red"]),
        (0.86, "Paper", "source commit +\nreview status", COLORS["navy"]),
    ]
    for x, title, body, color in chain:
        box(ax, x, 0.34, 0.13, 0.34, title, body, color)
    for (x1, *_), (x2, *__) in zip(chain, chain[1:]):
        arrow(ax, (x1 + 0.13, 0.51), (x2, 0.51))
    ax.text(0.5, 0.90, "Evidence and publication identity chain", ha="center", fontsize=11, weight="bold")
    ax.text(
        0.5,
        0.08,
        "Hashes provide integrity linkage. Independent reliance requires a trusted delivered ZIP digest or signature.",
        ha="center",
        fontsize=8,
    )
    _save(fig, outdir / "characterization_evidence_chain.pdf")

    slices = summary["fairness"]["slices"]
    labels = ["Historical\nfixture", "Amplification", "Intrinsic\nparity-policy"]
    points = np.array([row["air"] for row in slices])
    lows = np.array([row["air_ci95"][0] for row in slices])
    highs = np.array([row["air_ci95"][1] for row in slices])
    fig, ax = plt.subplots(figsize=(6.6, 3.1))
    xpos = np.arange(3)
    ax.errorbar(
        xpos,
        points,
        yerr=[points - lows, highs - points],
        fmt="o",
        color=COLORS["navy"],
        ecolor=COLORS["navy"],
        capsize=4,
        markersize=6,
        linewidth=1.3,
    )
    ax.axhline(
        INTERNAL_AIR_SCREEN,
        color=COLORS["orange"],
        linestyle="--",
        label="Internal screen 0.80",
    )
    ax.set_xticks(xpos, labels)
    ax.set_ylabel("Gender disparity ratio (AIR)")
    ax.set_ylim(0.67, 1.07)
    ax.grid(axis="y", color="#dddddd", linewidth=0.6)
    ax.legend(loc="upper left")
    ax.set_title("AIR points; intrinsic range is display-only")
    _save(fig, outdir / "characterization_air_slices.pdf")

    amp = summary["quality"]["amplification"]
    intrinsic = summary["quality"]["intrinsic"]
    components = ["Overall", "Distribution", "Correlation", "Privacy\nheuristic"]
    amp_values = [
        amp["overall_quality_score"],
        amp["distribution_score"],
        amp["correlation_preservation_score"],
        amp["privacy_heuristic_score"],
    ]
    intrinsic_values = [
        intrinsic["overall_quality_score"],
        intrinsic["distribution_score"],
        intrinsic["correlation_preservation_score"],
        intrinsic["privacy_heuristic_score"],
    ]
    fig, ax = plt.subplots(figsize=(6.6, 3.3))
    xpos = np.arange(len(components))
    width = 0.35
    ax.bar(xpos - width / 2, amp_values, width, label="Amplification", color=COLORS["blue"])
    ax.bar(xpos + width / 2, intrinsic_values, width, label="Intrinsic", color=COLORS["green"])
    ax.axhline(0.8, color=COLORS["orange"], linestyle="--", linewidth=1, label="Overall-quality gate")
    ax.set_xticks(xpos, components)
    ax.set_ylim(0.60, 1.02)
    ax.set_ylabel("Score")
    ax.set_title("Branch quality components; privacy value is heuristic only")
    ax.grid(axis="y", color="#dddddd", linewidth=0.6)
    ax.legend(ncol=3, loc="lower center", bbox_to_anchor=(0.5, -0.34))
    _save(fig, outdir / "characterization_quality.pdf")

    scenarios = summary["robustness"]["scenarios"]
    means = np.array([row["air_mean"] for row in scenarios])
    mins = np.array([row["air_min"] for row in scenarios])
    maxs = np.array([row["air_max"] for row in scenarios])
    fig, ax = plt.subplots(figsize=(6.6, 3.2))
    ypos = np.arange(len(scenarios))
    ax.errorbar(
        means,
        ypos,
        xerr=[means - mins, maxs - means],
        fmt="o",
        color=COLORS["navy"],
        ecolor=COLORS["navy"],
        capsize=4,
    )
    ax.axvline(
        INTERNAL_AIR_SCREEN,
        color=COLORS["orange"],
        linestyle="--",
        label="Internal screen 0.80",
    )
    ax.set_yticks(ypos, [row["label"] for row in scenarios])
    ax.set_xlim(0.60, 1.07)
    ax.set_xlabel("Scenario disparity ratio: min–mean–max across 10 seeds")
    ax.grid(axis="x", color="#dddddd", linewidth=0.6)
    ax.legend(loc="lower right")
    ax.set_title("Release Gold robustness: 40/40 scenario runs passed")
    _save(fig, outdir / "characterization_robustness.pdf")

    utility = summary["utility"]
    results = utility["synthetic_train_results"]
    aucs = [row["metrics"]["roc_auc"] for row in results]
    fig, ax = plt.subplots(figsize=(6.6, 3.2))
    ax.scatter(range(1, 11), aucs, color=COLORS["blue"], label="Synthetic-train AUC")
    ax.axhline(
        utility["real_train_baseline"]["roc_auc"],
        color=COLORS["green"],
        linewidth=1.2,
        label="Real-train baseline",
    )
    ax.axhline(0.5, color=COLORS["grey"], linestyle=":", label="Chance reference")
    ax.set_xticks(range(1, 11), [str(row["seed"]) for row in results], rotation=35, ha="right")
    ax.set_ylim(0.34, 0.73)
    ax.set_xlabel("Generation seed")
    ax.set_ylabel("Held-out fixture ROC AUC")
    ax.grid(axis="y", color="#dddddd", linewidth=0.6)
    ax.legend(ncol=3, loc="lower center", bbox_to_anchor=(0.5, -0.42))
    ax.set_title("TSTR utility varies materially across generation seeds")
    _save(fig, outdir / "characterization_utility.pdf")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--outdir", type=Path, default=Path("includes"))
    parser.add_argument("--figures", type=Path, default=Path("figures"))
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("evidence/v5.0.1/publication/characterization_summary.json"),
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()
    outdir = (root / args.outdir).resolve() if not args.outdir.is_absolute() else args.outdir
    figures = (root / args.figures).resolve() if not args.figures.is_absolute() else args.figures
    summary_path = (root / args.summary).resolve() if not args.summary.is_absolute() else args.summary
    outdir.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary = build_summary(root)
    summary_bytes = (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8")
    summary_path.write_bytes(summary_bytes)
    _write_macros(summary, outdir / "characterization_macros.tex")
    _write_tables(summary, outdir)
    _write_plots(summary, figures)
    print(
        json.dumps(
            {
                "summary": str(summary_path),
                "summary_sha256": hashlib.sha256(summary_bytes).hexdigest(),
                "figures": 6,
                "tables": 4,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
