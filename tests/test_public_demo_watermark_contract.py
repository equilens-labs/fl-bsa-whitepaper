import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

RELEASE_GENERATION_MARKERS = (
    "scripts/release_whitepaper.py",
    "scripts/canonicalize_release_pdf.py",
    "scripts/check_release_layout.py",
    "scripts/check_release_pdf_passive.py",
    "make release-",
    "release/main.tex",
    "dist/release-whitepaper",
    "PDF text tooling for release paper",
    "latexmk",
    "pdflatex",
    "pdftotext",
    "gen_tex_",
    "gen_plots_from_intake.py",
    "arxiv_pack.sh",
    "publication_profile.local.tex",
)
RELEASE_GENERATION_STEPS = {
    "Prepare exact release whitepaper",
    "Install PDF text tooling for release paper",
    "Compile exact release whitepaper",
    "Canonicalize exact release whitepaper bytes",
    "Verify exact release whitepaper layout",
    "Verify exact release whitepaper is passive",
    "Finalize exact release whitepaper manifest",
    "Upload exact release whitepaper",
}


def _assert_release_generators_are_exactly_guarded(workflow: dict) -> None:
    on_section = workflow.get(True, workflow.get("on"))
    if on_section != {"repository_dispatch": {"types": ["wp-intake-ready"]}}:
        raise AssertionError("intake workflow is not release-dispatch-only")

    steps = workflow["jobs"]["fetch-build"]["steps"]
    release_steps = []
    for step in steps:
        rendered = str(step)
        if any(marker in rendered for marker in RELEASE_GENERATION_MARKERS):
            if step.get("name") not in RELEASE_GENERATION_STEPS:
                raise AssertionError(
                    f"unexpected release generator step: {step.get('name')}"
                )
            if "if" in step:
                raise AssertionError(
                    f"release-only generator keeps a redundant condition: {step.get('name')}"
                )
            release_steps.append(step)
    if {step.get("name") for step in release_steps} != RELEASE_GENERATION_STEPS:
        raise AssertionError("release generator inventory is incomplete")


def _artifact_uploads(workflow: dict) -> list[tuple[str, str, str]]:
    steps = workflow["jobs"]["fetch-build"]["steps"]
    uploads = []
    for step in steps:
        action = str(step.get("uses") or "")
        if action.split("@", 1)[0] != "actions/upload-artifact":
            continue
        uploads.append((action, step["with"]["name"], step["with"]["path"]))
    return uploads


class PublicDemoWatermarkContractTests(unittest.TestCase):
    def test_candidate_profile_and_target_are_canonical(self) -> None:
        profile = (ROOT / "profiles" / "publication_profile.candidate.tex").read_text(
            encoding="utf-8"
        )
        self.assertEqual("\\drafttrue\n", profile)

        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        candidate = makefile.split("candidate: test assets", 1)[1].split(
            "arxiv: identity", 1
        )[0]
        copy_profile = "cp $(CANDIDATE_PROFILE) $(LOCAL_PROFILE)"
        clean_latex = "latexmk -C main.tex"
        compile_latex = "latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex"
        marker_check = "test \"$$(pdftotext main.pdf - | grep -F -c 'DEMO / EVALUATION ONLY')\" -eq 1"
        identity_check = "scripts/verify_pdf_release_identity.py"
        structure_check = "scripts/check_pdf_tag_structure.py"
        for required in (
            copy_profile,
            clean_latex,
            compile_latex,
            identity_check,
            marker_check,
            structure_check,
        ):
            self.assertIn(required, candidate)
        self.assertLess(candidate.index(copy_profile), candidate.index(clean_latex))
        self.assertLess(candidate.index(clean_latex), candidate.index(compile_latex))
        self.assertLess(candidate.index(compile_latex), candidate.index(identity_check))
        self.assertLess(candidate.index(identity_check), candidate.index(marker_check))
        self.assertLess(candidate.index(marker_check), candidate.index(structure_check))

        publication = makefile.split("publication-candidate:", 1)[1].split("clean:", 1)[
            0
        ]
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
        watermark = main_tex.split(r"\AddToShipoutPictureBG", 1)[1].split(r"\fi", 1)[0]
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
        workflow_path = ROOT / ".github" / "workflows" / "latex.yml"
        workflow = workflow_path.read_text(encoding="utf-8")
        self.assertIn("Enable public demo watermark", workflow)
        self.assertIn("includes/publication_profile.local.tex", workflow)
        self.assertIn(
            "cp profiles/publication_profile.candidate.tex includes/publication_profile.local.tex",
            workflow,
        )
        self.assertIn("Ensure pdftotext available", workflow)
        self.assertIn("Assert exact archival release identity in PDF", workflow)
        self.assertIn("scripts/verify_pdf_release_identity.py", workflow)
        self.assertIn("Assert public demo watermark in PDF", workflow)
        self.assertIn("Assert reviewed PDF tag structure", workflow)
        self.assertIn("scripts/check_pdf_tag_structure.py", workflow)
        self.assertIn("pdftotext main.pdf -", workflow)
        self.assertIn("DEMO / EVALUATION ONLY", workflow)
        self.assertIn('if [ "$hits" -ne 1 ]; then', workflow)
        self.assertIn("name: fl-bsa-v5.0.1-archival-whitepaper", workflow)

        parsed = yaml.safe_load(workflow)
        smoke = parsed["jobs"]["release-template-smoke"]
        self.assertEqual("release-template-smoke", smoke["name"])
        self.assertEqual("ubuntu-24.04", smoke["runs-on"])
        smoke_steps = smoke["steps"]
        compile_step = next(
            step
            for step in smoke_steps
            if step.get("name") == "Compile release template smoke"
        )
        self.assertEqual("release/main.tex", compile_step["with"]["root_file"])
        canonical = next(
            step
            for step in smoke_steps
            if step.get("name") == "Canonicalize release template PDF bytes"
        )
        self.assertEqual(
            "python3 scripts/canonicalize_release_pdf.py main.pdf",
            canonical["run"],
        )
        self.assertLess(smoke_steps.index(compile_step), smoke_steps.index(canonical))
        layout = next(
            step
            for step in smoke_steps
            if step.get("name") == "Verify release template layout"
        )
        self.assertEqual(
            "python3 scripts/check_release_layout.py main.log --max-overfull-pt 2",
            layout["run"],
        )
        self.assertLess(smoke_steps.index(canonical), smoke_steps.index(layout))
        passive = next(
            step
            for step in smoke_steps
            if step.get("name") == "Verify release template PDF is passive"
        )
        self.assertEqual(
            "python3 scripts/check_release_pdf_passive.py main.pdf",
            passive["run"],
        )
        self.assertLess(smoke_steps.index(layout), smoke_steps.index(passive))
        prepare = next(
            step
            for step in smoke_steps
            if step.get("name") == "Generate release-template smoke inputs"
        )
        self.assertIn("make release-assets", prepare["run"])
        self.assertIn("write_identity_tex", prepare["run"])
        verify = next(
            step
            for step in smoke_steps
            if step.get("name") == "Verify release template smoke identity and marker"
        )
        self.assertIn("verify_pdf_release_identity.py", verify["run"])
        self.assertLess(smoke_steps.index(passive), smoke_steps.index(verify))
        for coordinate in (
            "--evidence-run-attempt",
            "--generator-backend-id",
            "--whitepaper-run-id",
            "--whitepaper-run-attempt",
            "--intake-snapshot-id",
            "--intake-bundle-sha256",
        ):
            self.assertIn(coordinate, verify["run"])
        self.assertIn("--require-release-claims", verify["run"])
        self.assertIn("grep -F -c 'DEMO / EVALUATION ONLY' || true", verify["run"])
        self.assertIn('[[ "$hits" =~ ^[1-9][0-9]*$ ]]', verify["run"])

        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        release_pdf = makefile.split("release-pdf: release-assets", 1)[1].split(
            "companion: assets", 1
        )[0]
        self.assertIn(
            "python3 scripts/check_release_layout.py main.log --max-overfull-pt 2",
            release_pdf,
        )
        self.assertIn(
            "python3 scripts/check_release_pdf_passive.py main.pdf", release_pdf
        )
        self.assertIn(
            "python3 scripts/canonicalize_release_pdf.py main.pdf", release_pdf
        )
        self.assertLess(
            release_pdf.index("python3 scripts/canonicalize_release_pdf.py main.pdf"),
            release_pdf.index("python3 scripts/check_release_pdf_passive.py main.pdf"),
        )

    def test_intake_workflow_builds_only_an_exact_release_scoped_paper(self) -> None:
        workflow_text = (
            ROOT / ".github" / "workflows" / "pull-wp-intake.yml"
        ).read_text(encoding="utf-8")
        workflow = yaml.safe_load(workflow_text)
        steps = workflow["jobs"]["fetch-build"]["steps"]

        self.assertIn("name: whitepaper-intake-receipt-", workflow_text)
        self.assertIn("path: intake/whitepaper_snapshot.json", workflow_text)
        for forbidden in (
            "whitepaper-pdf-from-intake",
            "arxiv-source-from-intake",
            "profiles/publication_profile.candidate.tex",
            "root_file: main.tex",
        ):
            self.assertNotIn(forbidden, workflow_text)

        _assert_release_generators_are_exactly_guarded(workflow)
        release_steps = {
            step["name"]: step
            for step in steps
            if step.get("name") in RELEASE_GENERATION_STEPS
        }
        self.assertTrue(
            {
                "Prepare exact release whitepaper",
                "Install PDF text tooling for release paper",
                "Compile exact release whitepaper",
                "Canonicalize exact release whitepaper bytes",
                "Verify exact release whitepaper is passive",
                "Finalize exact release whitepaper manifest",
                "Upload exact release whitepaper",
            }.issubset(release_steps)
        )

        compile_step = release_steps["Compile exact release whitepaper"]
        self.assertEqual("release/main.tex", compile_step["with"]["root_file"])
        tooling_step = release_steps["Install PDF text tooling for release paper"]
        self.assertIn("poppler-utils", tooling_step["run"])
        self.assertIn("mupdf-tools", tooling_step["run"])
        self.assertIn("mutool version 1.23.10", tooling_step["run"])
        self.assertEqual("ubuntu-24.04", workflow["jobs"]["fetch-build"]["runs-on"])
        canonical_step = release_steps["Canonicalize exact release whitepaper bytes"]
        self.assertEqual(
            "python3 scripts/canonicalize_release_pdf.py main.pdf",
            canonical_step["run"],
        )
        self.assertLess(steps.index(compile_step), steps.index(canonical_step))
        passive_step = release_steps["Verify exact release whitepaper is passive"]
        self.assertEqual(
            "python3 scripts/check_release_pdf_passive.py main.pdf",
            passive_step["run"],
        )
        self.assertLess(
            steps.index(canonical_step),
            steps.index(release_steps["Verify exact release whitepaper layout"]),
        )
        self.assertLess(
            steps.index(release_steps["Verify exact release whitepaper layout"]),
            steps.index(passive_step),
        )
        self.assertLess(
            steps.index(passive_step),
            steps.index(release_steps["Finalize exact release whitepaper manifest"]),
        )
        upload_step = release_steps["Upload exact release whitepaper"]
        self.assertEqual(
            "dist/release-whitepaper/whitepaper.pdf\n"
            "dist/release-whitepaper/whitepaper_release.json\n",
            upload_step["with"]["path"],
        )

        upload_action = (
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
        )
        self.assertEqual(
            [
                (
                    upload_action,
                    "whitepaper-intake-receipt-${{ github.run_attempt }}",
                    "intake/whitepaper_snapshot.json",
                ),
                (
                    upload_action,
                    "release-whitepaper-${{ github.run_attempt }}",
                    "dist/release-whitepaper/whitepaper.pdf\n"
                    "dist/release-whitepaper/whitepaper_release.json\n",
                ),
            ],
            _artifact_uploads(workflow),
        )

    def test_a_sixth_unguarded_release_generator_is_rejected(self) -> None:
        workflow = yaml.safe_load(
            (ROOT / ".github" / "workflows" / "pull-wp-intake.yml").read_text(
                encoding="utf-8"
            )
        )
        workflow["jobs"]["fetch-build"]["steps"].append(
            {
                "name": "Unexpected release generator",
                "run": "python scripts/release_whitepaper.py finalize",
            }
        )
        with self.assertRaisesRegex(AssertionError, "unexpected release generator step"):
            _assert_release_generators_are_exactly_guarded(workflow)

    def test_intake_upload_inventory_detects_a_differently_pinned_upload(self) -> None:
        workflow = yaml.safe_load(
            (ROOT / ".github" / "workflows" / "pull-wp-intake.yml").read_text(
                encoding="utf-8"
            )
        )
        workflow["jobs"]["fetch-build"]["steps"].append(
            {
                "uses": "actions/upload-artifact@" + "0" * 40,
                "with": {"name": "forbidden", "path": "dist/current-paper.bin"},
            }
        )
        self.assertEqual(3, len(_artifact_uploads(workflow)))

    def test_local_watermark_override_is_not_committed_by_intake_pr(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "pull-wp-intake.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("includes/publication_profile.local.tex", gitignore)
        self.assertNotIn("git add", workflow)
        self.assertNotIn("WP_INTAKE_PR_TOKEN", workflow)
        self.assertNotIn("Persist intake snapshot", workflow)


if __name__ == "__main__":
    unittest.main()
