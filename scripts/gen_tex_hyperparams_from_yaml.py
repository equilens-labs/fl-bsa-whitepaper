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


def _strict_nonempty_string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location} must be a non-empty string")
    return value


def _strict_positive_int(value: Any, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{location} must be a positive integer")
    return value


def _strict_positive_number(value: Any, location: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{location} must be a positive finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{location} must be a positive finite number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{location} must be a positive finite number")
    return number


def _strict_validate_tunable_hyperparameters(hp: Dict[str, Any], location: str) -> None:
    for field in ("batch_size", "epochs", "pac"):
        _strict_positive_int(hp.get(field), f"{location}.{field}")
    for field in ("generator_dim", "discriminator_dim"):
        dims = hp.get(field)
        if not isinstance(dims, list) or not dims:
            raise ValueError(f"{location}.{field} must be a non-empty list")
        for index, value in enumerate(dims):
            _strict_positive_int(value, f"{location}.{field}[{index}]")
    for field in ("generator_lr", "discriminator_lr"):
        _strict_positive_number(hp.get(field), f"{location}.{field}")


def _strict_validate_config(config: Dict[str, Any]) -> bool:
    branches = config.get("branches")
    if not isinstance(branches, dict) or not branches:
        raise ValueError("config.branches must be a non-empty mapping")
    native_branches: list[bool] = []
    for branch in ("amplification", "intrinsic"):
        spec = branches.get(branch)
        location = f"config.branches.{branch}"
        if not isinstance(spec, dict):
            raise ValueError(f"{location} must be a mapping")
        chosen = spec.get("chosen")
        if not isinstance(chosen, dict):
            raise ValueError(f"{location}.chosen must be a mapping")
        algorithm = _strict_nonempty_string(
            chosen.get("algorithm"), f"{location}.chosen.algorithm"
        )
        backend_id = _strict_nonempty_string(
            chosen.get("backend_id"), f"{location}.chosen.backend_id"
        )
        branch_is_native = backend_id == NATIVE_BACKEND_ID or algorithm.startswith(
            "native_"
        )
        native_branches.append(branch_is_native)
        if branch_is_native:
            _strict_nonempty_string(
                chosen.get("disposition"), f"{location}.chosen.disposition"
            )
        else:
            _strict_validate_tunable_hyperparameters(chosen, f"{location}.chosen")
    if len(set(native_branches)) != 1:
        raise ValueError("config branches must use the same generator family")
    return native_branches[0]


def _strict_validate_model_cert(
    cert: Dict[str, Any], branch: str, location: str
) -> bool:
    branch_mode = cert.get("branch_mode")
    if branch_mode != branch:
        raise ValueError(f"{location}.branch_mode must be {branch}")
    hp = cert.get("hyperparameters")
    if not isinstance(hp, dict):
        raise ValueError(f"{location}.hyperparameters must be an object")
    algorithm = _strict_nonempty_string(
        hp.get("algorithm"), f"{location}.hyperparameters.algorithm"
    )
    backend_id = _strict_nonempty_string(
        hp.get("backend_id"), f"{location}.hyperparameters.backend_id"
    )
    is_native = backend_id == NATIVE_BACKEND_ID or algorithm.startswith("native_")
    if not is_native:
        _strict_validate_tunable_hyperparameters(
            hp, f"{location}.hyperparameters"
        )
    return is_native


def _strict_validate_hp_cert(
    cert: Dict[str, Any], branch: str, location: str
) -> None:
    branch_mode = cert.get("branch_mode")
    if branch_mode != branch:
        raise ValueError(f"{location}.branch_mode must be {branch}")
    _strict_nonempty_string(cert.get("fallback_reason"), f"{location}.fallback_reason")
    _strict_nonempty_string(cert.get("status"), f"{location}.status")


def _strict_validate_inputs(
    config_path: Path,
    amp_path: Path,
    intr_path: Path,
    hp_amp_path: Path,
    hp_intr_path: Path,
) -> None:
    config = _strict_load_yaml(config_path, "model hyperparameter config")
    native_config = _strict_validate_config(config)

    amp_exists = amp_path.is_file()
    intr_exists = intr_path.is_file()
    if amp_exists != intr_exists:
        raise ValueError("model certificate inputs must be provided as a complete branch pair")
    if not amp_exists:
        if native_config:
            raise ValueError("native generator configuration requires both model certificates")
        return

    amp = _strict_load_json(amp_path, "amplification model certificate")
    intr = _strict_load_json(intr_path, "intrinsic model certificate")
    amp_native = _strict_validate_model_cert(
        amp, "amplification", "amplification model certificate"
    )
    intr_native = _strict_validate_model_cert(
        intr, "intrinsic", "intrinsic model certificate"
    )
    if amp_native != intr_native:
        raise ValueError("model certificate branches must use the same generator family")
    if native_config != amp_native:
        raise ValueError(
            "model hyperparameter config and certificates must use the same generator family"
        )
    if not amp_native:
        return

    hp_amp = _strict_load_json(
        hp_amp_path, "amplification hyperparameter tuning certificate"
    )
    hp_intr = _strict_load_json(
        hp_intr_path, "intrinsic hyperparameter tuning certificate"
    )
    _strict_validate_hp_cert(
        hp_amp,
        "amplification",
        "amplification hyperparameter tuning certificate",
    )
    _strict_validate_hp_cert(
        hp_intr, "intrinsic", "intrinsic hyperparameter tuning certificate"
    )


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
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Reject missing, malformed, or incomplete publication inputs before writing output",
    )
    args = ap.parse_args()

    outdir = Path(args.outdir)
    out_path = outdir / "table_hparams_chosen.tex"

    amp_path = Path(args.cert_amplification)
    intr_path = Path(args.cert_intrinsic)
    hp_amp_path = Path(args.hp_cert_amplification)
    hp_intr_path = Path(args.hp_cert_intrinsic)
    if args.strict:
        try:
            _strict_validate_inputs(
                Path(args.config),
                amp_path,
                intr_path,
                hp_amp_path,
                hp_intr_path,
            )
        except ValueError as exc:
            ap.error(str(exc))

    if amp_path.exists() and intr_path.exists():
        native_rows = _native_rows_from_certs(
            amp_path,
            intr_path,
            hp_amp_path,
            hp_intr_path,
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
