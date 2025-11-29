#!/usr/bin/env python3

"""
Generate LaTeX tables for model hyperparameters from the intake hyperparameter
configuration (e.g., CTGAN settings in intake/model_hyperparams.yaml).

Outputs:
  - includes/table_hparams_chosen.tex : branch-level chosen hyperparameters.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _render_chosen_table(cfg: Dict[str, Any], out_path: Path) -> None:
    branches: Dict[str, Any] = cfg.get("branches") or {}
    rows: List[List[str]] = []

    for name, spec in branches.items():
        chosen = spec.get("chosen") or {}
        batch_size = chosen.get("batch_size", "")
        epochs = chosen.get("epochs", "")
        embedding_dim = chosen.get("embedding_dim", "")
        pac = chosen.get("pac", "")
        gen_dims = chosen.get("generator_dim") or []
        disc_dims = chosen.get("discriminator_dim") or []

        def _fmt_layers(dims: Any) -> str:
            try:
                return "-".join(str(int(x)) for x in dims)
            except Exception:
                return ""

        gen_layers = _fmt_layers(gen_dims)
        disc_layers = _fmt_layers(disc_dims)

        rows.append(
            [
                str(name),
                str(batch_size),
                str(epochs),
                str(embedding_dim),
                str(pac),
                gen_layers,
                disc_layers,
            ]
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write("\\begin{tabular}{lrrrrrr}\n\\toprule\n")
        f.write(
            "branch & batch size & epochs & embedding dim & pac & gen. layers & disc. layers\\\\\n"
        )
        f.write("\\midrule\n")
        if rows:
            for r in rows:
                f.write(
                    f"{r[0]} & {r[1]} & {r[2]} & {r[3]} & {r[4]} & {r[5]} & {r[6]}\\\\\n"
                )
        else:
            f.write(
                "\\multicolumn{7}{c}{\\emph{No hyperparameter configuration found in intake}}\\\\\n"
            )
        f.write("\\bottomrule\n\\end{tabular}\n")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate LaTeX hyperparameter tables from intake YAML"
    )
    ap.add_argument(
        "--config",
        default="intake/model_hyperparams.yaml",
        help="Path to model_hyperparams.yaml in the intake bundle",
    )
    ap.add_argument(
        "--outdir",
        default="includes",
        help="Output directory for LaTeX tables",
    )
    args = ap.parse_args()

    cfg = _load_yaml(Path(args.config))
    outdir = Path(args.outdir)
    _render_chosen_table(cfg, outdir / "table_hparams_chosen.tex")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

