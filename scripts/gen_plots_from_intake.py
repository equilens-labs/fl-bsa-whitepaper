#!/usr/bin/env python3

"""
Generate publication-quality figures from intake CSVs.

Inputs (default paths):
  - intake/selection_rates.csv
  - intake/metrics_long.csv

Outputs (PDF figures under figures/):
  - selection_rates.pdf  (selection rates by attribute with 95% CIs)
  - air_summary.pdf      (AIR per attribute with 95% CIs and threshold line)
"""

from __future__ import annotations

import argparse
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate plots from intake CSVs")
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

    if not selection_path.exists() or not metrics_path.exists():
        return 0

    # If matplotlib is not available, skip plot generation gracefully.
    try:
        import matplotlib.pyplot  # type: ignore[import]  # noqa: F401
    except Exception:
        return 0

    _maybe_set_style()

    sel = pd.read_csv(selection_path)
    mlong = pd.read_csv(metrics_path)

    _generate_selection_rates_fig(sel, mlong, outdir / "selection_rates.pdf")
    _generate_air_fig(mlong, outdir / "air_summary.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
