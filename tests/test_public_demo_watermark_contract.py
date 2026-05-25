import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicDemoWatermarkContractTests(unittest.TestCase):
    def test_latex_source_has_optional_text_layer_watermark(self) -> None:
        main_tex = (ROOT / "main.tex").read_text(encoding="utf-8")

        self.assertIn(r"\usepackage{eso-pic}", main_tex)
        self.assertIn("includes/publication_profile.local.tex", main_tex)
        self.assertIn("DEMO / EVALUATION ONLY", main_tex)
        self.assertIn(r"\AddToShipoutPictureBG", main_tex)
        self.assertIn(r"\ifdraft\fancyfoot[C]", main_tex)

    def test_public_ci_artifacts_enable_demo_watermark(self) -> None:
        for workflow_name, artifact_name in (
            ("latex.yml", "whitepaper-pdf"),
            ("pull-wp-intake.yml", "whitepaper-pdf-from-intake"),
        ):
            with self.subTest(workflow=workflow_name):
                workflow = (ROOT / ".github" / "workflows" / workflow_name).read_text(
                    encoding="utf-8"
                )
                self.assertIn("Enable public demo watermark", workflow)
                self.assertIn("includes/publication_profile.local.tex", workflow)
                self.assertIn(r"printf '\\drafttrue\n'", workflow)
                self.assertIn("Ensure pdftotext available", workflow)
                self.assertIn("Assert public demo watermark in PDF", workflow)
                self.assertIn("pdftotext main.pdf -", workflow)
                self.assertIn("DEMO / EVALUATION ONLY", workflow)
                self.assertIn(f"name: {artifact_name}", workflow)

    def test_local_watermark_override_is_not_committed_by_intake_pr(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "pull-wp-intake.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("includes/publication_profile.local.tex", gitignore)
        self.assertIn("git add intake config includes figures", workflow)


if __name__ == "__main__":
    unittest.main()
