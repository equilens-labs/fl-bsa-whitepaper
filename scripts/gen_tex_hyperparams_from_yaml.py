#!/usr/bin/env python3

"""
Generate LaTeX tables for branch generator configuration.

Preferred source (when present): model certificate JSONs under:
- intake/certificates/model_certificate_amplification.json
- intake/certificates/model_certificate_intrinsic.json

Fallback source: intake/model_hyperparams.yaml for legacy tunable-model intakes.

Outputs:
  - includes/table_hparams_chosen.tex : branch-level generator configuration.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List

import yaml

NATIVE_BACKEND_ID = "first_party_evidence_native"
NATIVE_FALLBACK_REASON = "first_party_backend_has_no_tunable_hyperparameters"


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
        val = float(x)
    except Exception:
        return ""
    if not math.isfinite(val):
        return ""
    # Use significant-figure rounding locally so small learning rates don't
    # collapse to 0.000 under the paper's global siunitx round-mode=places.
    return f"\\num[round-mode=figures,round-precision=3]{{{val:.3e}}}"


def _escape_tex(value: Any) -> str:
    text = "" if value is None else str(value)
    replacements = {
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
    return "".join(replacements.get(ch, ch) for ch in text)


def _display_backend(value: Any) -> str:
    if value == NATIVE_BACKEND_ID:
        return "first-party evidence-native"
    return _escape_tex(value)


def _display_algorithm(value: Any) -> str:
    if value == "native_branch_profile_empirical_sampler":
        return "branch-profile empirical sampler"
    return _escape_tex(value)


def _is_native_hyperparameters(hp: Any) -> bool:
    if not isinstance(hp, dict):
        return False
    backend_id = str(hp.get("backend_id") or "")
    algorithm = str(hp.get("algorithm") or "")
    return backend_id == NATIVE_BACKEND_ID or algorithm.startswith("native_")


def _native_disposition(hp_cert: Dict[str, Any]) -> str:
    reason = str(hp_cert.get("fallback_reason") or "")
    if reason == NATIVE_FALLBACK_REASON:
        return (
            "No tunable GAN hyperparameters; epochs, PAC, batch size, and GAN layers "
            "are not applicable."
        )
    status = str(hp_cert.get("status") or "")
    if status:
        return f"Recorded as {_escape_tex(status.replace('_', ' '))}; see intake certificate."
    return "Native generator configuration recorded in model certificate."


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


def _render_native_table(rows: List[List[str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write(
            "\\begin{tabular}{@{}p{0.14\\linewidth}p{0.20\\linewidth}"
            "p{0.20\\linewidth}p{0.32\\linewidth}@{}}\n"
        )
        f.write("\\toprule\n")
        f.write("branch & backend & generator & disposition\\\\\n")
        f.write("\\midrule\n")
        for row in rows:
            f.write(f"{row[0]} & {row[1]} & {row[2]} & {row[3]}\\\\\n")
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


def _native_rows_from_certs(
    amp_path: Path,
    intr_path: Path,
    hp_amp_path: Path,
    hp_intr_path: Path,
) -> List[List[str]]:
    rows: List[List[str]] = []

    for name, model_path, hp_path in [
        ("amplification", amp_path, hp_amp_path),
        ("intrinsic", intr_path, hp_intr_path),
    ]:
        cert = _load_json(model_path)
        hp = cert.get("hyperparameters") if isinstance(cert, dict) else None
        if not _is_native_hyperparameters(hp):
            return []

        hp_cert = _load_json(hp_path)
        assert isinstance(hp, dict)
        rows.append(
            [
                _escape_tex(name),
                _display_backend(hp.get("backend_id")),
                _display_algorithm(hp.get("algorithm")),
                _native_disposition(hp_cert),
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
        "--hp-cert-amplification",
        default="intake/certificates/hyperparameter_tuning_certificate_amplification.json",
        help="Amplification hyperparameter tuning certificate JSON",
    )
    ap.add_argument(
        "--hp-cert-intrinsic",
        default="intake/certificates/hyperparameter_tuning_certificate_intrinsic.json",
        help="Intrinsic hyperparameter tuning certificate JSON",
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
        native_rows = _native_rows_from_certs(
            amp_path,
            intr_path,
            Path(args.hp_cert_amplification),
            Path(args.hp_cert_intrinsic),
        )
        if native_rows:
            _render_native_table(native_rows, out_path)
        else:
            rows = _rows_from_certs(amp_path, intr_path)
            _render_chosen_table(rows, out_path)
        return 0

    cfg = _load_yaml(Path(args.config))
    rows = _rows_from_yaml(cfg)
    _render_chosen_table(rows, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
