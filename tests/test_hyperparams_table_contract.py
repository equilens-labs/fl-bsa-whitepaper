import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HyperparamsTableContractTests(unittest.TestCase):
    def test_native_certificates_render_characterization_not_ctgan_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cert_dir = root / "intake" / "certificates"
            out_dir = root / "includes"
            cert_dir.mkdir(parents=True)
            (root / "intake").mkdir(exist_ok=True)

            for branch in ("amplification", "intrinsic"):
                (cert_dir / f"model_certificate_{branch}.json").write_text(
                    json.dumps(
                        {
                            "hyperparameters": {
                                "algorithm": "native_branch_profile_empirical_sampler",
                                "backend_id": "first_party_evidence_native",
                                "batch_size": None,
                                "epochs": 0,
                                "pac": None,
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                (cert_dir / f"hyperparameter_tuning_certificate_{branch}.json").write_text(
                    json.dumps(
                        {
                            "fallback_reason": (
                                "first_party_backend_has_no_tunable_hyperparameters"
                            ),
                            "hyperparameter_validation_passed": False,
                            "status": "valid_with_limitations",
                        }
                    ),
                    encoding="utf-8",
                )

            stale_yaml = root / "intake" / "model_hyperparams.yaml"
            stale_yaml.write_text(
                "model_family: CTGAN\nbranches:\n  amplification:\n    chosen:\n"
                "      epochs: 100\n      pac: 10\n",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "gen_tex_hyperparams_from_yaml.py"),
                    "--config",
                    str(stale_yaml),
                    "--cert-amplification",
                    str(cert_dir / "model_certificate_amplification.json"),
                    "--cert-intrinsic",
                    str(cert_dir / "model_certificate_intrinsic.json"),
                    "--hp-cert-amplification",
                    str(cert_dir / "hyperparameter_tuning_certificate_amplification.json"),
                    "--hp-cert-intrinsic",
                    str(cert_dir / "hyperparameter_tuning_certificate_intrinsic.json"),
                    "--outdir",
                    str(out_dir),
                ],
                check=True,
            )

            table = (out_dir / "table_hparams_chosen.tex").read_text(encoding="utf-8")
            self.assertIn("first-party evidence-native", table)
            self.assertIn("No tunable GAN hyperparameters", table)
            self.assertNotIn("None & 0 & None", table)
            self.assertNotIn("CTGAN", table)

    def test_checked_in_native_intake_is_not_stale_ctgan(self) -> None:
        yaml_text = (ROOT / "intake" / "model_hyperparams.yaml").read_text(encoding="utf-8")
        table = (ROOT / "includes" / "table_hparams_chosen.tex").read_text(encoding="utf-8")
        appendix = (ROOT / "sections" / "appendix_f_hyperparams.tex").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("model_family: CTGAN", yaml_text)
        self.assertNotIn("None & 0 & None", table)
        self.assertNotIn("Model Hyperparameters (CTGAN)", appendix)
        self.assertIn("first-party evidence-native", table)


if __name__ == "__main__":
    unittest.main()
