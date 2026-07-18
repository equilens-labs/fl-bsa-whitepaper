import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gen_plots_from_intake.py"


class PlotGenerationContractTests(unittest.TestCase):
    def test_require_all_rejects_missing_inputs_and_removes_stale_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            outdir = temp / "figures"
            outdir.mkdir()
            for name in (
                "air_summary.pdf",
                "gender_air_slices.pdf",
                "selection_rates.pdf",
            ):
                (outdir / name).write_bytes(b"stale")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--uncertainty",
                    str(temp / "missing-uncertainty.json"),
                    "--selection",
                    str(temp / "missing-selection.csv"),
                    "--fairness-slices",
                    str(temp / "missing-slices.json"),
                    "--metrics",
                    str(temp / "missing-metrics.csv"),
                    "--outdir",
                    str(outdir),
                    "--require-all",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(0, completed.returncode)
            self.assertIn(
                "required publication figures were not freshly generated",
                completed.stderr,
            )
            self.assertEqual([], list(outdir.iterdir()))


if __name__ == "__main__":
    unittest.main()
