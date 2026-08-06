import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicDemoWatermarkContractTests(unittest.TestCase):
    def test_candidate_profile_and_target_are_canonical(self) -> None:
        profile = (
            ROOT / "profiles" / "publication_profile.candidate.tex"
        ).read_text(encoding="utf-8")
        self.assertEqual("\\drafttrue\n", profile)

        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        candidate = makefile.split("candidate: test assets", 1)[1].split(
            "arxiv: identity", 1
        )[0]
        copy_profile = "cp $(CANDIDATE_PROFILE) $(LOCAL_PROFILE)"
        clean_latex = "latexmk -C main.tex"
        compile_latex = "latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex"
        marker_check = (
            "test \"$$(pdftotext main.pdf - | grep -F -c "
            "'DEMO / EVALUATION ONLY')\" -eq 1"
        )
        for required in (copy_profile, clean_latex, compile_latex, marker_check):
            self.assertIn(required, candidate)
        self.assertLess(candidate.index(copy_profile), candidate.index(clean_latex))
        self.assertLess(candidate.index(clean_latex), candidate.index(compile_latex))
        self.assertLess(candidate.index(compile_latex), candidate.index(marker_check))

        publication = makefile.split("publication-candidate:", 1)[1].split(
            "clean:", 1
        )[0]
        for required in (
            "$(MAKE) candidate",
            "$(MAKE) arxiv",
            "scripts/intake_anchor.py export",
            "scripts/build_publication_manifest.py",
        ):
            self.assertIn(required, publication)
        self.assertLess(
            publication.index("$(MAKE) candidate"),
            publication.index("$(MAKE) arxiv"),
        )
        self.assertLess(
            publication.index("$(MAKE) arxiv"),
            publication.index("scripts/intake_anchor.py export"),
        )
        self.assertLess(
            publication.index("scripts/intake_anchor.py export"),
            publication.index("scripts/build_publication_manifest.py"),
        )

    def test_latex_source_has_optional_text_layer_watermark(self) -> None:
        main_tex = (ROOT / "main.tex").read_text(encoding="utf-8")

        self.assertIn(r"\usepackage{eso-pic}", main_tex)
        self.assertIn("includes/publication_profile.local.tex", main_tex)
        self.assertIn("DEMO / EVALUATION ONLY", main_tex)
        self.assertIn(r"\AddToShipoutPictureBG", main_tex)
        watermark = main_tex.split(r"\AddToShipoutPictureBG", 1)[1].split(
            r"\fi", 1
        )[0]
        self.assertIn(r"\tagmcbegin{artifact}", watermark)
        self.assertIn(r"\tagmcend", watermark)
        self.assertLess(
            watermark.index(r"\tagmcbegin{artifact}"),
            watermark.index(r"\DemoEvaluationWatermark"),
        )
        self.assertLess(
            watermark.index(r"\DemoEvaluationWatermark"),
            watermark.index(r"\tagmcend"),
        )
        self.assertIn(
            r"\ifdraft\par\smallskip{\small\bfseries\DemoEvaluationWatermark}\fi",
            main_tex,
        )
        self.assertNotIn(r"\ifdraft\fancyfoot[C]", main_tex)
        self.assertIn(
            r"\fancyfoot[L]{\scriptsize \DocumentVersion{} \textbar{} \PublicationStatus}",
            main_tex,
        )

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
                self.assertIn(
                    "cp profiles/publication_profile.candidate.tex "
                    "includes/publication_profile.local.tex",
                    workflow,
                )
                self.assertIn("Ensure pdftotext available", workflow)
                self.assertIn("Assert public demo watermark in PDF", workflow)
                self.assertIn("pdftotext main.pdf -", workflow)
                self.assertIn("DEMO / EVALUATION ONLY", workflow)
                self.assertIn('if [ "$hits" -ne 1 ]; then', workflow)
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
