#!/usr/bin/env python3

"""
Generate LaTeX tables for model hyperparameters.

Preferred source (when present): model certificate JSONs under:
- intake/certificates/model_certificate_amplification.json
- intake/certificates/model_certificate_intrinsic.json

Fallback source: intake/model_hyperparams.yaml

Outputs:
  - includes/table_hparams_chosen.tex : branch-level chosen hyperparameters.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _fmt_layers(dims: Any) -> str:
    try:
        return "-".join(str(int(x)) for x in dims)
    except Exception:
        return ""


def _fmt_num(x: Any) -> str:
    try:
        return f"\\num{{{float(x):.3g}}}"
    except Exception:
        return ""


def _render_chosen_table(rows: List[List[str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write("\\begin{tabular}{lrrrllrr}\n\\toprule\n")
        f.write(
            "branch & batch size & epochs & pac & gen. layers & disc. layers & gen. lr & disc. lr\\\\\n"
        )
        f.write("\\midrule\n")
        if rows:
            for r in rows:
                f.write(
                    f"{r[0]} & {r[1]} & {r[2]} & {r[3]} & {r[4]} & {r[5]} & {r[6]} & {r[7]}\\\\\n"
                )
        else:
            f.write(
                "\\multicolumn{8}{c}{\\emph{No hyperparameter configuration found in intake}}\\\\\n"
            )
        f.write("\\bottomrule\n\\end{tabular}\n")


def _rows_from_certs(amp_path: Path, intr_path: Path) -> List[List[str]]:
    rows: List[List[str]] = []

    amp = _load_json(amp_path)
    intr = _load_json(intr_path)
    for name, cert in [("amplification", amp), ("intrinsic", intr)]:
        hp = cert.get("hyperparameters") if isinstance(cert, dict) else None
        if not isinstance(hp, dict):
            hp = {}
        batch_size = hp.get("batch_size", "")
        epochs = hp.get("epochs", "")
        pac = hp.get("pac", "")
        gen_layers = _fmt_layers(hp.get("generator_dim") or [])
        disc_layers = _fmt_layers(hp.get("discriminator_dim") or [])
        gen_lr = _fmt_num(hp.get("generator_lr"))
        disc_lr = _fmt_num(hp.get("discriminator_lr"))
        rows.append(
            [
                str(name),
                str(batch_size),
                str(epochs),
                str(pac),
                gen_layers,
                disc_layers,
                gen_lr,
                disc_lr,
            ]
        )

    return rows


def _rows_from_yaml(cfg: Dict[str, Any]) -> List[List[str]]:
    branches: Dict[str, Any] = cfg.get("branches") or {}
    rows: List[List[str]] = []
    for name, spec in branches.items():
        chosen = spec.get("chosen") or {}
        batch_size = chosen.get("batch_size", "")
        epochs = chosen.get("epochs", "")
        pac = chosen.get("pac", "")
        gen_layers = _fmt_layers(chosen.get("generator_dim") or [])
        disc_layers = _fmt_layers(chosen.get("discriminator_dim") or [])
        gen_lr = _fmt_num(chosen.get("generator_lr"))
        disc_lr = _fmt_num(chosen.get("discriminator_lr"))
        rows.append(
            [
                str(name),
                str(batch_size),
                str(epochs),
                str(pac),
                gen_layers,
                disc_layers,
                gen_lr,
                disc_lr,
            ]
        )
    return rows


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
        "--cert-amplification",
        default="intake/certificates/model_certificate_amplification.json",
        help="Amplification model certificate JSON (preferred source)",
    )
    ap.add_argument(
        "--cert-intrinsic",
        default="intake/certificates/model_certificate_intrinsic.json",
        help="Intrinsic model certificate JSON (preferred source)",
    )
    ap.add_argument(
        "--outdir",
        default="includes",
        help="Output directory for LaTeX tables",
    )
    args = ap.parse_args()

    outdir = Path(args.outdir)
    out_path = outdir / "table_hparams_chosen.tex"

    amp_path = Path(args.cert_amplification)
    intr_path = Path(args.cert_intrinsic)
    if amp_path.exists() and intr_path.exists():
        rows = _rows_from_certs(amp_path, intr_path)
        _render_chosen_table(rows, out_path)
        return 0

    cfg = _load_yaml(Path(args.config))
    rows = _rows_from_yaml(cfg)
    _render_chosen_table(rows, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
