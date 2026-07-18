import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METRICS_GENERATOR = ROOT / "scripts" / "gen_tex_macros_from_metrics.py"
PREAMBLE_GENERATOR = ROOT / "scripts" / "gen_tex_preamble_from_manifest.py"
HYPERPARAMS_GENERATOR = ROOT / "scripts" / "gen_tex_hyperparams_from_yaml.py"
SENTINEL = "existing reviewed output\n"


class StrictMacroGenerationTests(unittest.TestCase):
    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def _assert_failure_without_output(
        self, command: list[str], output_path: Path
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(SENTINEL, encoding="utf-8")

        replaced = self._run(command)
        self.assertNotEqual(0, replaced.returncode, replaced.stdout + replaced.stderr)
        self.assertEqual(SENTINEL, output_path.read_text(encoding="utf-8"))
        self.assertEqual([output_path], sorted(output_path.parent.iterdir()))

        output_path.unlink()
        created = self._run(command)
        self.assertNotEqual(0, created.returncode, created.stdout + created.stderr)
        self.assertFalse(output_path.exists())
        self.assertEqual([], list(output_path.parent.iterdir()))

    def _metrics_command(
        self,
        outdir: Path,
        *,
        uncertainty: Path | None = None,
        slices: Path | None = None,
        metrics: Path | None = None,
        sap: Path | None = None,
    ) -> list[str]:
        return [
            sys.executable,
            str(METRICS_GENERATOR),
            "--strict",
            "--uncertainty",
            str(uncertainty or ROOT / "intake" / "metrics_uncertainty.json"),
            "--slices",
            str(slices or ROOT / "intake" / "fairness_slices.json"),
            "--metrics",
            str(metrics or ROOT / "intake" / "metrics_long.csv"),
            "--sap",
            str(sap or ROOT / "config" / "sap.yaml"),
            "--outdir",
            str(outdir),
        ]

    def _preamble_command(
        self,
        output: Path,
        *,
        manifest: Path | None = None,
        sap: Path | None = None,
        metrics: Path | None = None,
    ) -> list[str]:
        return [
            sys.executable,
            str(PREAMBLE_GENERATOR),
            "--strict",
            "--manifest",
            str(manifest or ROOT / "intake" / "manifest.json"),
            "--sap",
            str(sap or ROOT / "config" / "sap.yaml"),
            "--metrics",
            str(metrics or ROOT / "intake" / "metrics_long.csv"),
            "--out",
            str(output),
            "--quiet",
        ]

    def _hyperparams_command(
        self,
        outdir: Path,
        *,
        config: Path | None = None,
        cert_amplification: Path | None = None,
        cert_intrinsic: Path | None = None,
        hp_cert_amplification: Path | None = None,
        hp_cert_intrinsic: Path | None = None,
    ) -> list[str]:
        cert_dir = ROOT / "intake" / "certificates"
        return [
            sys.executable,
            str(HYPERPARAMS_GENERATOR),
            "--strict",
            "--config",
            str(config or ROOT / "intake" / "model_hyperparams.yaml"),
            "--cert-amplification",
            str(
                cert_amplification
                or cert_dir / "model_certificate_amplification.json"
            ),
            "--cert-intrinsic",
            str(cert_intrinsic or cert_dir / "model_certificate_intrinsic.json"),
            "--hp-cert-amplification",
            str(
                hp_cert_amplification
                or cert_dir / "hyperparameter_tuning_certificate_amplification.json"
            ),
            "--hp-cert-intrinsic",
            str(
                hp_cert_intrinsic
                or cert_dir / "hyperparameter_tuning_certificate_intrinsic.json"
            ),
            "--outdir",
            str(outdir),
        ]

    def test_metrics_strict_rejects_missing_input_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outdir = root / "includes"
            command = self._metrics_command(
                outdir, metrics=root / "missing-metrics.csv"
            )
            self._assert_failure_without_output(
                command, outdir / "metrics_macros.tex"
            )

    def test_metrics_strict_rejects_malformed_input_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            malformed = root / "uncertainty.json"
            malformed.write_text("{", encoding="utf-8")
            outdir = root / "includes"
            command = self._metrics_command(outdir, uncertainty=malformed)
            self._assert_failure_without_output(
                command, outdir / "metrics_macros.tex"
            )

    def test_metrics_strict_rejects_wrong_shape_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wrong_shape = root / "sap.yaml"
            wrong_shape.write_text("[]\n", encoding="utf-8")
            outdir = root / "includes"
            command = self._metrics_command(outdir, sap=wrong_shape)
            self._assert_failure_without_output(
                command, outdir / "metrics_macros.tex"
            )

    def test_metrics_tex_table_escapes_all_csv_text_cells(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics = root / "metrics.csv"
            with (ROOT / "intake" / "metrics_long.csv").open(
                "r", encoding="utf-8", newline=""
            ) as source:
                reader = csv.DictReader(source)
                fieldnames = list(reader.fieldnames or [])
                rows = list(reader)
            injected = dict(rows[0])
            injected.update(
                {
                    "run_id": "\\input{private-run}",
                    "model_id": "model&private",
                    "split": "split_private",
                    "metric": "ece",
                    "value": "0.01",
                    "lower_ci": "0.009",
                    "upper_ci": "0.011",
                    "n": "10",
                }
            )
            with metrics.open("w", encoding="utf-8", newline="") as target:
                writer = csv.DictWriter(target, fieldnames=fieldnames, lineterminator="\n")
                writer.writeheader()
                writer.writerow(injected)

            outdir = root / "includes"
            completed = self._run(self._metrics_command(outdir, metrics=metrics))
            self.assertEqual(
                0, completed.returncode, completed.stdout + completed.stderr
            )
            table = (outdir / "table_ece_summary.tex").read_text(encoding="utf-8")
            self.assertNotIn("\\input{private-run}", table)
            self.assertIn("\\textbackslash", table)
            self.assertIn("model\\&private", table)
            self.assertIn("split\\_private", table)

    def test_preamble_strict_rejects_missing_input_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "includes" / "provenance_macros.tex"
            command = self._preamble_command(
                output, metrics=root / "missing-metrics.csv"
            )
            self._assert_failure_without_output(command, output)

    def test_preamble_strict_rejects_malformed_input_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            malformed = root / "manifest.json"
            malformed.write_text("{", encoding="utf-8")
            output = root / "includes" / "provenance_macros.tex"
            command = self._preamble_command(output, manifest=malformed)
            self._assert_failure_without_output(command, output)

    def test_preamble_strict_rejects_wrong_shape_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wrong_shape = root / "sap.yaml"
            wrong_shape.write_text("[]\n", encoding="utf-8")
            output = root / "includes" / "provenance_macros.tex"
            command = self._preamble_command(output, sap=wrong_shape)
            self._assert_failure_without_output(command, output)

    def test_hyperparams_strict_rejects_missing_input_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outdir = root / "includes"
            command = self._hyperparams_command(
                outdir, hp_cert_amplification=root / "missing-certificate.json"
            )
            self._assert_failure_without_output(
                command, outdir / "table_hparams_chosen.tex"
            )

    def test_hyperparams_strict_rejects_malformed_input_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            malformed = root / "model-certificate.json"
            malformed.write_text("{", encoding="utf-8")
            outdir = root / "includes"
            command = self._hyperparams_command(
                outdir, cert_amplification=malformed
            )
            self._assert_failure_without_output(
                command, outdir / "table_hparams_chosen.tex"
            )

    def test_hyperparams_strict_rejects_wrong_shape_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wrong_shape = root / "model_hyperparams.yaml"
            wrong_shape.write_text("[]\n", encoding="utf-8")
            outdir = root / "includes"
            command = self._hyperparams_command(outdir, config=wrong_shape)
            self._assert_failure_without_output(
                command, outdir / "table_hparams_chosen.tex"
            )

    def test_tracked_stable_intake_passes_all_strict_generators(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics_out = root / "metrics"
            preamble_out = root / "provenance_macros.tex"
            hyperparams_out = root / "hyperparams"

            for command in (
                self._metrics_command(metrics_out),
                self._preamble_command(preamble_out),
                self._hyperparams_command(hyperparams_out),
            ):
                completed = self._run(command)
                self.assertEqual(
                    0, completed.returncode, completed.stdout + completed.stderr
                )

            self.assertTrue((metrics_out / "metrics_macros.tex").is_file())
            self.assertTrue((metrics_out / "table_air_summary.tex").is_file())
            self.assertTrue(preamble_out.is_file())
            self.assertNotIn(
                "not_available", preamble_out.read_text(encoding="utf-8")
            )
            hyperparams_table = hyperparams_out / "table_hparams_chosen.tex"
            self.assertTrue(hyperparams_table.is_file())
            self.assertIn(
                "first-party evidence-native",
                hyperparams_table.read_text(encoding="utf-8"),
            )

    def test_documented_build_and_intake_sync_are_fail_closed(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        intake_workflow = (
            ROOT / ".github" / "workflows" / "pull-wp-intake.yml"
        ).read_text(encoding="utf-8")

        for script in (
            "gen_tex_macros_from_metrics.py",
            "gen_tex_preamble_from_manifest.py",
            "gen_tex_hyperparams_from_yaml.py",
        ):
            self.assertRegex(makefile, rf"{script}[^\n]*--strict")
            self.assertRegex(intake_workflow, rf"{script}[^\n]*--strict")
            self.assertNotRegex(makefile, rf"{script}[^\n]*\|\| true")
        self.assertRegex(
            makefile, r"gen_plots_from_intake.py[^\n]*--require-all"
        )
        self.assertNotRegex(
            makefile, r"gen_plots_from_intake.py[^\n]*\|\| true"
        )


if __name__ == "__main__":
    unittest.main()
