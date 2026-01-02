#!/usr/bin/env python3

"""
Generate publication-quality figures from intake CSVs.

Inputs (default paths):
  - intake/selection_rates.csv
  - intake/metrics_long.csv
  - intake/metrics_uncertainty.json (preferred for v4 SoT)

Outputs (PDF figures under figures/):
  - selection_rates.pdf  (selection rates by attribute with 95% CIs)
  - air_summary.pdf      (AIR per attribute with 95% CIs and threshold line)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def _maybe_set_style() -> None:
    try:
        import matplotlib.pyplot as plt  # type: ignore[import]
    except Exception:
        return

    try:
        plt.style.use("seaborn-v0_8-paper")
    except Exception:
        try:
            plt.style.use("seaborn-paper")
        except Exception:
            # Fall back to defaults
            pass


def _generate_selection_rates_fig(
    selection_rates: pd.DataFrame, metrics_long: pd.DataFrame, out_path: Path
) -> None:
    try:
        import matplotlib.pyplot as plt  # type: ignore[import]
    except Exception:
        return

    if selection_rates.empty or metrics_long.empty:
        return

    m = metrics_long.copy()
    m["metric_l"] = m["metric"].str.lower()
    sel_m = m[m["metric_l"] == "selection_rate"].copy()
    if sel_m.empty:
        return

    # Prefer canonical CI columns when available
    if "ci_low" in sel_m.columns and "ci_high" in sel_m.columns:
        ci_low_col = "ci_low"
        ci_high_col = "ci_high"
    else:
        ci_low_col = "lower_ci"
        ci_high_col = "upper_ci"

    # Extract attribute and group from "{attribute}:{group}" key
    sel_m["attribute"] = sel_m["group"].str.split(":", n=1).str[0]
    sel_m["group_name"] = sel_m["group"].str.split(":", n=1).str[1]

    preferred_attrs = ["gender", "race"]
    present = [a for a in preferred_attrs if a in sel_m["attribute"].unique()]
    if not present:
        present = sorted(sel_m["attribute"].unique())
    if not present:
        return

    n_attr = len(present)
    fig, axes = plt.subplots(
        1, n_attr, figsize=(4.0 * n_attr, 3.0), sharey=True, squeeze=False
    )
    axes_row = axes[0]

    for ax, attr in zip(axes_row, present):
        sub = sel_m[sel_m["attribute"] == attr].copy()
        if sub.empty:
            ax.axis("off")
            continue
        sub = sub.sort_values("group_name")

        x = sub["value"].to_numpy()
        y = sub["group_name"].to_numpy()
        lo = sub[ci_low_col].to_numpy()
        hi = sub[ci_high_col].to_numpy()
        err_low = x - lo
        err_high = hi - x

        ax.errorbar(
            x,
            y,
            xerr=[err_low, err_high],
            fmt="o",
            capsize=3,
            color="black",
            ecolor="black",
            elinewidth=0.8,
            markersize=4,
        )
        ax.set_xlabel("Selection rate")
        ax.set_title(attr.capitalize())
        ax.set_xlim(0.0, 1.0)
        ax.grid(True, axis="x", linestyle=":", linewidth=0.5)

    axes_row[0].set_ylabel("Group")
    fig.suptitle("Selection rates by protected attribute", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_path)
    plt.close(fig)


def _generate_selection_rates_fig_from_uncertainty(
    uncertainty: dict, out_path: Path
) -> None:
    try:
        import matplotlib.pyplot as plt  # type: ignore[import]
    except Exception:
        return

    fu = uncertainty.get("fairness_uncertainty")
    if not isinstance(fu, dict) or not fu:
        return

    rows: list[dict[str, object]] = []

    gender = fu.get("gender") if isinstance(fu.get("gender"), dict) else None
    if isinstance(gender, dict):
        ref = str(gender.get("reference_group") or "")
        prot = str(gender.get("protected_group") or "")
        sel = gender.get("selection_rates") if isinstance(gender.get("selection_rates"), dict) else {}
        ref_sr = sel.get("ref") if isinstance(sel.get("ref"), dict) else {}
        prot_sr = sel.get("prot") if isinstance(sel.get("prot"), dict) else {}
        rows.append(
            {
                "attribute": "gender",
                "group_name": ref,
                "value": ref_sr.get("p"),
                "ci_low": (ref_sr.get("ci95") or [None, None])[0],
                "ci_high": (ref_sr.get("ci95") or [None, None])[1],
            }
        )
        rows.append(
            {
                "attribute": "gender",
                "group_name": prot,
                "value": prot_sr.get("p"),
                "ci_low": (prot_sr.get("ci95") or [None, None])[0],
                "ci_high": (prot_sr.get("ci95") or [None, None])[1],
            }
        )

    race = fu.get("race") if isinstance(fu.get("race"), dict) else None
    if isinstance(race, dict) and bool(race.get("display_in_main_pdf")):
        ref = str(race.get("reference_group") or "")
        pairs = race.get("pairs") if isinstance(race.get("pairs"), dict) else {}
        # Reference selection rate is repeated across pairs; take the first available.
        ref_written = False
        for prot_group, pair in pairs.items():
            if not isinstance(pair, dict):
                continue
            sel = pair.get("selection_rates") if isinstance(pair.get("selection_rates"), dict) else {}
            ref_sr = sel.get("ref") if isinstance(sel.get("ref"), dict) else {}
            prot_sr = sel.get("prot") if isinstance(sel.get("prot"), dict) else {}
            if not ref_written:
                rows.append(
                    {
                        "attribute": "race",
                        "group_name": ref,
                        "value": ref_sr.get("p"),
                        "ci_low": (ref_sr.get("ci95") or [None, None])[0],
                        "ci_high": (ref_sr.get("ci95") or [None, None])[1],
                    }
                )
                ref_written = True
            rows.append(
                {
                    "attribute": "race",
                    "group_name": str(prot_group),
                    "value": prot_sr.get("p"),
                    "ci_low": (prot_sr.get("ci95") or [None, None])[0],
                    "ci_high": (prot_sr.get("ci95") or [None, None])[1],
                }
            )

    if not rows:
        return

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["value", "ci_low", "ci_high"])
    if df.empty:
        return

    preferred_attrs = ["gender", "race"]
    present = [a for a in preferred_attrs if a in df["attribute"].unique()]
    if not present:
        present = sorted(df["attribute"].unique())
    if not present:
        return

    n_attr = len(present)
    fig, axes = plt.subplots(
        1, n_attr, figsize=(4.0 * n_attr, 3.0), sharey=True, squeeze=False
    )
    axes_row = axes[0]

    for ax, attr in zip(axes_row, present):
        sub = df[df["attribute"] == attr].copy()
        if sub.empty:
            ax.axis("off")
            continue
        sub = sub.sort_values("group_name")
        x = sub["value"].to_numpy()
        y = sub["group_name"].to_numpy()
        lo = sub["ci_low"].to_numpy()
        hi = sub["ci_high"].to_numpy()
        err_low = x - lo
        err_high = hi - x
        ax.errorbar(
            x,
            y,
            xerr=[err_low, err_high],
            fmt="o",
            capsize=3,
            color="black",
            ecolor="black",
            elinewidth=0.8,
            markersize=4,
        )
        ax.set_xlabel("Selection rate")
        ax.set_title(attr.capitalize())
        ax.set_xlim(0.0, 1.0)
        ax.grid(True, axis="x", linestyle=":", linewidth=0.5)

    axes_row[0].set_ylabel("Group")
    fig.suptitle("Selection rates by protected attribute", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_path)
    plt.close(fig)


def _generate_air_fig(metrics_long: pd.DataFrame, out_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt  # type: ignore[import]
    except Exception:
        return

    if metrics_long.empty:
        return

    m = metrics_long.copy()
    m["metric_l"] = m["metric"].str.lower()
    air = m[m["metric_l"] == "air"].copy()
    if air.empty:
        return

    # Prefer canonical CI columns when available
    if "ci_low" in air.columns and "ci_high" in air.columns:
        ci_low_col = "ci_low"
        ci_high_col = "ci_high"
    else:
        ci_low_col = "lower_ci"
        ci_high_col = "upper_ci"

    air["attribute"] = air["group"].str.split(":", n=1).str[0]
    air = air.sort_values("attribute")

    x_pos = range(len(air))
    y = air["value"].to_numpy()
    lo = air[ci_low_col].to_numpy()
    hi = air[ci_high_col].to_numpy()
    err_low = y - lo
    err_high = hi - y

    fig, ax = plt.subplots(figsize=(4.0, 3.0))
    ax.errorbar(
        x_pos,
        y,
        yerr=[err_low, err_high],
        fmt="o",
        capsize=3,
        color="black",
        ecolor="black",
        elinewidth=0.8,
        markersize=4,
    )
    ax.axhline(0.8, linestyle="--", color="red", linewidth=0.8, label="Threshold 0.80")
    ax.set_xticks(list(x_pos))
    ax.set_xticklabels(air["attribute"].tolist())
    ax.set_ylabel("Adverse impact ratio (AIR)")
    ymax = max(1.0, float(hi.max()) * 1.05, 0.85)
    ax.set_ylim(0.0, ymax)
    ax.grid(True, axis="y", linestyle=":", linewidth=0.5)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def _generate_air_fig_from_uncertainty(uncertainty: dict, out_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt  # type: ignore[import]
    except Exception:
        return

    fu = uncertainty.get("fairness_uncertainty")
    if not isinstance(fu, dict) or not fu:
        return

    rows: list[dict[str, object]] = []

    gender = fu.get("gender") if isinstance(fu.get("gender"), dict) else None
    if isinstance(gender, dict):
        air = gender.get("air") if isinstance(gender.get("air"), dict) else {}
        rows.append(
            {
                "label": "gender",
                "value": air.get("point"),
                "ci_low": (air.get("ci95") or [None, None])[0],
                "ci_high": (air.get("ci95") or [None, None])[1],
            }
        )

    race = fu.get("race") if isinstance(fu.get("race"), dict) else None
    if isinstance(race, dict) and bool(race.get("display_in_main_pdf")):
        worst = race.get("worst_case_pair")
        pairs = race.get("pairs") if isinstance(race.get("pairs"), dict) else {}
        pair = pairs.get(worst) if isinstance(pairs.get(worst), dict) else {}
        air = pair.get("air") if isinstance(pair.get("air"), dict) else {}
        rows.append(
            {
                "label": f"race ({worst})",
                "value": air.get("point"),
                "ci_low": (air.get("ci95") or [None, None])[0],
                "ci_high": (air.get("ci95") or [None, None])[1],
            }
        )

    if not rows:
        return

    df = pd.DataFrame(rows).dropna(subset=["value", "ci_low", "ci_high"])
    if df.empty:
        return

    x_pos = range(len(df))
    y = df["value"].to_numpy()
    lo = df["ci_low"].to_numpy()
    hi = df["ci_high"].to_numpy()
    err_low = y - lo
    err_high = hi - y

    fig, ax = plt.subplots(figsize=(4.5, 3.0))
    ax.errorbar(
        x_pos,
        y,
        yerr=[err_low, err_high],
        fmt="o",
        capsize=3,
        color="black",
        ecolor="black",
        elinewidth=0.8,
        markersize=4,
    )
    ax.axhline(0.8, linestyle="--", color="red", linewidth=0.8, label="Threshold 0.80")
    ax.set_xticks(list(x_pos))
    ax.set_xticklabels(df["label"].tolist())
    ax.set_ylabel("Disparity ratio (AIR)")
    ymax = max(1.0, float(hi.max()) * 1.05, 0.85)
    ax.set_ylim(0.0, ymax)
    ax.grid(True, axis="y", linestyle=":", linewidth=0.5)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate plots from intake CSVs")
    parser.add_argument(
        "--uncertainty",
        default="intake/metrics_uncertainty.json",
        help="Path to deterministic metrics_uncertainty.json (preferred)",
    )
    parser.add_argument(
        "--selection",
        default="intake/selection_rates.csv",
        help="Path to selection_rates.csv",
    )
    parser.add_argument(
        "--metrics",
        default="intake/metrics_long.csv",
        help="Path to metrics_long.csv",
    )
    parser.add_argument(
        "--outdir", default="figures", help="Output directory for figures"
    )
    args = parser.parse_args()

    selection_path = Path(args.selection)
    metrics_path = Path(args.metrics)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    uncertainty_path = Path(args.uncertainty)
    uncertainty: dict[str, object] = {}
    if uncertainty_path.exists():
        try:
            uncertainty = json.loads(uncertainty_path.read_text(encoding="utf-8"))
        except Exception:
            uncertainty = {}

    if not selection_path.exists() or not metrics_path.exists():
        # Deterministic SoT plots can still be generated without metrics_long.csv
        if uncertainty:
            _generate_selection_rates_fig_from_uncertainty(
                uncertainty, outdir / "selection_rates.pdf"
            )
            _generate_air_fig_from_uncertainty(uncertainty, outdir / "air_summary.pdf")
        return 0

    # If matplotlib is not available, skip plot generation gracefully.
    try:
        import matplotlib.pyplot  # type: ignore[import]  # noqa: F401
    except Exception:
        return 0

    _maybe_set_style()

    sel = pd.read_csv(selection_path)
    mlong = pd.read_csv(metrics_path)

    if uncertainty:
        _generate_selection_rates_fig_from_uncertainty(
            uncertainty, outdir / "selection_rates.pdf"
        )
        _generate_air_fig_from_uncertainty(uncertainty, outdir / "air_summary.pdf")
    else:
        _generate_selection_rates_fig(sel, mlong, outdir / "selection_rates.pdf")
        _generate_air_fig(mlong, outdir / "air_summary.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
