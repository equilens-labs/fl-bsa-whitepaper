#!/usr/bin/env python3

"""
Reads intake/metrics_long.csv and config/sap.yaml, then writes:
- includes/metrics_macros.tex with summary macros
- includes/table_air_summary.tex, includes/table_eo_summary.tex, includes/table_ece_summary.tex
"""
import pandas as pd, yaml, argparse, math
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", default="intake/metrics_long.csv")
    ap.add_argument("--sap", default="config/sap.yaml")
    ap.add_argument("--outdir", default="includes")
    args = ap.parse_args()

    m = pd.read_csv(args.metrics)
    sap = yaml.safe_load(Path(args.sap).read_text())
    thr = sap.get("thresholds", {})
    air_thr = float(thr.get("air_min", 0.80))
    tpr_thr = float(thr.get("tpr_gap_max", 0.05))
    fpr_thr = float(thr.get("fpr_gap_max", 0.05))
    ece_thr = float(thr.get("ece_max", 0.02))

    # Normalize
    m["metric_l"] = m["metric"].str.lower()
    # AIR
    air = m[m["metric_l"]=="air"].copy()
    min_air = air["value"].min() if not air.empty else float("nan")
    num_air_viol = int((air["value"] < air_thr).sum()) if not air.empty else 0

    # EO gaps
    tprg = m[m["metric_l"]=="tpr_gap"].copy()
    fprg = m[m["metric_l"]=="fpr_gap"].copy()
    num_tpr_viol = int((tprg["value"] > tpr_thr).sum()) if not tprg.empty else 0
    num_fpr_viol = int((fprg["value"] > fpr_thr).sum()) if not fprg.empty else 0

    # ECE
    ece = m[m["metric_l"]=="ece"].copy()
    max_ece = ece["value"].max() if not ece.empty else float("nan")

    # Write macros
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    with open(outdir / "metrics_macros.tex", "w", encoding="utf-8") as f:
        f.write("% Auto-generated metrics macros\n")
        f.write("\\renewcommand{\\AIRThreshold}{%.3f}\n" % air_thr)
        f.write("\\renewcommand{\\TprGapThreshold}{%.3f}\n" % tpr_thr)
        f.write("\\renewcommand{\\FprGapThreshold}{%.3f}\n" % fpr_thr)
        f.write("\\renewcommand{\\EceThreshold}{%.3f}\n" % ece_thr)
        if math.isnan(min_air):
            f.write("\\renewcommand{\\MinAIR}{TBD}\n")
        else:
            f.write("\\renewcommand{\\MinAIR}{%.3f}\n" % min_air)
        if math.isnan(max_ece):
            f.write("\\renewcommand{\\MaxECE}{TBD}\n")
        else:
            f.write("\\renewcommand{\\MaxECE}{%.3f}\n" % max_ece)
        f.write("\\renewcommand{\\NumAIRViolations}{%d}\n" % num_air_viol)
        f.write("\\renewcommand{\\NumTPRGapViol}{%d}\n" % num_tpr_viol)
        f.write("\\renewcommand{\\NumFPRGapViol}{%d}\n" % num_fpr_viol)

    # AIR table (per attribute)
    rows = []
    if not air.empty:
        # Expect group like "attr:global"
        air["attr"] = air["group"].str.split(":").str[0]
        for (attr), sub in air.groupby("attr"):
            for _, r in sub.iterrows():
                rows.append([r.get("run_id",""), r.get("model_id",""), r.get("split",""), attr, r.get("value",""), r.get("lower_ci",""), r.get("upper_ci","")])
    with open(outdir / "table_air_summary.tex", "w", encoding="utf-8") as f:
        f.write("\\begin{tabular}{llllrrr}\n\\toprule\n")
        f.write("run & model & split & attr & AIR & LCI & UCI\\\\\n\\midrule\n")
        for r in rows:
            f.write(f"{r[0]} & {r[1]} & {r[2]} & {r[3]} & {r[4]} & {r[5]} & {r[6]}\\\\\n")
        if not rows:
            f.write("\\multicolumn{7}{c}{\\emph{No AIR rows found in metrics}}\\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n")

    # EO table
    eo_rows = []
    for name in ["tpr_gap","fpr_gap"]:
        sub = m[m["metric_l"]==name]
        for _, r in sub.iterrows():
            eo_rows.append([name, r.get("run_id",""), r.get("model_id",""), r.get("split",""), r.get("group",""), r.get("value",""), r.get("lower_ci",""), r.get("upper_ci","")])
    with open(outdir / "table_eo_summary.tex", "w", encoding="utf-8") as f:
        f.write("\\begin{tabular}{llllllll}\n\\toprule\n")
        f.write("metric & run & model & split & group & value & LCI & UCI\\\\\n\\midrule\n")
        for r in eo_rows:
            f.write(f"{r[0]} & {r[1]} & {r[2]} & {r[3]} & {r[4]} & {r[5]} & {r[6]} & {r[7]}\\\\\n")
        if not eo_rows:
            f.write("\\multicolumn{8}{c}{\\emph{No EO rows found in metrics}}\\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n")

    # ECE table
    ece_rows = []
    for _, r in ece.iterrows():
        ece_rows.append([r.get("run_id",""), r.get("model_id",""), r.get("split",""), r.get("value",""), r.get("lower_ci",""), r.get("upper_ci","")])
    with open(outdir / "table_ece_summary.tex", "w", encoding="utf-8") as f:
        f.write("\\begin{tabular}{llllrr}\n\\toprule\n")
        f.write("run & model & split & ECE & LCI & UCI\\\\\n\\midrule\n")
        for r in ece_rows:
            f.write(f"{r[0]} & {r[1]} & {r[2]} & {r[3]} & {r[4]} & {r[5]}\\\\\n")
        if not ece_rows:
            f.write("\\multicolumn{6}{c}{\\emph{No ECE rows found in metrics}}\\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n")

if __name__ == "__main__":
    main()
