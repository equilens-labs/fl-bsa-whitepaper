import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "build_publication_manifest.py"
SPEC = importlib.util.spec_from_file_location(
    "publication_manifest_under_test", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
PUBLICATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLICATION)


class PublicationManifestTests(unittest.TestCase):
    def test_manifest_binds_source_trees_artifacts_and_claims(self) -> None:
        commit = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "whitepaper.pdf"
            companion = Path(tmp) / "fl-bsa-v5.0.1-companion-evidence.zip"
            arxiv = Path(tmp) / "whitepaper_arxiv_source.zip"
            compatibility = Path(tmp) / "stable-v5-intake-compatibility.zip"
            pdf.write_bytes(b"stable-v5 pdf candidate")
            companion.write_bytes(b"stable-v5 companion candidate")
            arxiv.write_bytes(b"stable-v5 arxiv candidate")
            subprocess.run(
                [
                    sys.executable,
                    "-S",
                    str(SCRIPTS / "intake_anchor.py"),
                    "export",
                    "--anchor",
                    str(ROOT / "baselines" / "stable-v5-characterization.json"),
                    "--repo-root",
                    str(ROOT),
                    "--output",
                    str(compatibility),
                ],
                check=True,
            )
            with (
                mock.patch.object(
                    PUBLICATION, "_assert_source_checkout"
                ) as source_checkout,
                mock.patch.object(PUBLICATION, "_assert_pdf_marker") as marker,
            ):
                manifest = PUBLICATION.build_manifest(
                    repo_root=ROOT,
                    anchor_path=ROOT / "baselines" / "stable-v5-characterization.json",
                    intake_manifest_path=ROOT / "intake" / "manifest.json",
                    whitepaper_commit=commit,
                    publication_status="candidate_not_published",
                    pdf_path=pdf,
                    companion_path=companion,
                    arxiv_path=arxiv,
                    compatibility_intake_path=compatibility,
                )
                marker.assert_called_once_with(
                    pdf,
                    "pdftotext",
                    hashlib.sha256(b"stable-v5 companion candidate").hexdigest(),
                )
                source_checkout.assert_called_once_with(ROOT, commit)

        self.assertEqual(
            "flbsa.whitepaper_publication_candidate.v1", manifest["schema_version"]
        )
        self.assertEqual("candidate_not_published", manifest["publication_status"])
        self.assertIs(manifest["claims"]["customer_evidence_eligible"], False)
        self.assertEqual(commit, manifest["whitepaper"]["commit"])
        self.assertRegex(
            manifest["whitepaper"]["source_tree_git_oid"], r"^[0-9a-f]{40}$"
        )
        self.assertEqual(
            "git-object-projection-sha256.v1",
            manifest["whitepaper"]["publication_input_projection"]["algorithm"],
        )
        self.assertEqual(
            "9b40c0e8c8e6291c51b267f38a72c242705895c3269844b37c4b35d23d9526c9",
            manifest["whitepaper"]["publication_input_projection"]["sha256"],
        )
        self.assertEqual(
            hashlib.sha256(b"stable-v5 pdf candidate").hexdigest(),
            manifest["artifacts"]["pdf"]["sha256"],
        )
        self.assertEqual(23, manifest["artifacts"]["pdf"]["size_bytes"])
        self.assertEqual(
            "09f0f404512f0e7366b1070c654c17d5511253b9765a91fcd1e4e9fe9294b626",
            manifest["artifacts"]["compatibility_intake"]["sha256"],
        )
        self.assertEqual(
            hashlib.sha256(b"stable-v5 companion candidate").hexdigest(),
            manifest["artifacts"]["companion"]["sha256"],
        )
        self.assertEqual(
            "git_reconstructed_projection_not_original_attested_zip",
            manifest["intake_anchor"]["compatibility_export_disposition"],
        )

    def test_manifest_rejects_changed_intake(self) -> None:
        commit = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
        original = json.loads((ROOT / "intake" / "manifest.json").read_text())
        original["commit_sha"] = "0" * 40
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            intake = tmp_path / "manifest.json"
            pdf = tmp_path / "whitepaper.pdf"
            companion = tmp_path / "companion.zip"
            arxiv = tmp_path / "source.zip"
            compatibility = tmp_path / "compatibility.zip"
            intake.write_text(json.dumps(original), encoding="utf-8")
            pdf.write_bytes(b"pdf")
            companion.write_bytes(b"companion")
            arxiv.write_bytes(b"zip")
            compatibility.write_bytes(b"not reached")
            with (
                mock.patch.object(
                    PUBLICATION, "_assert_source_checkout"
                ) as source_checkout,
                mock.patch.object(PUBLICATION, "_assert_pdf_marker"),
            ):
                with self.assertRaisesRegex(
                    PUBLICATION.AnchorError,
                    "does not match the stable-v5 producer commit",
                ):
                    PUBLICATION.build_manifest(
                        repo_root=ROOT,
                        anchor_path=ROOT
                        / "baselines"
                        / "stable-v5-characterization.json",
                        intake_manifest_path=intake,
                        whitepaper_commit=commit,
                        publication_status="candidate_not_published",
                        pdf_path=pdf,
                        companion_path=companion,
                        arxiv_path=arxiv,
                        compatibility_intake_path=compatibility,
                    )
                source_checkout.assert_called_once_with(ROOT, commit)

    def test_pdf_marker_check_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "candidate.pdf"
            pdf.write_bytes(b"not a PDF")
            with self.assertRaisesRegex(
                PUBLICATION.AnchorError, "inspect publication PDF"
            ):
                PUBLICATION._assert_pdf_marker(pdf, "pdftotext", "a" * 64)

    def test_pdf_marker_check_requires_exactly_one_extractable_marker(self) -> None:
        companion_sha256 = "a" * 64
        for count in (0, 2):
            with self.subTest(count=count):
                extracted = ("DEMO / EVALUATION ONLY\n" * count) + companion_sha256
                completed = subprocess.CompletedProcess(
                    args=["pdftotext"],
                    returncode=0,
                    stdout=extracted,
                    stderr="",
                )
                with mock.patch.object(
                    PUBLICATION.subprocess, "run", return_value=completed
                ):
                    with self.assertRaisesRegex(
                        PUBLICATION.AnchorError, "exactly one extractable"
                    ):
                        PUBLICATION._assert_pdf_marker(
                            Path("candidate.pdf"), "pdftotext", companion_sha256
                        )

        completed = subprocess.CompletedProcess(
            args=["pdftotext"],
            returncode=0,
            stdout=f"DEMO / EVALUATION ONLY\n{companion_sha256}\n",
            stderr="",
        )
        with mock.patch.object(PUBLICATION.subprocess, "run", return_value=completed):
            PUBLICATION._assert_pdf_marker(
                Path("candidate.pdf"), "pdftotext", companion_sha256
            )

    def test_source_checkout_must_be_exact_head_and_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            subprocess.run(["git", "init", "-b", "main", str(repo)], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.name", "Test"], check=True
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "config",
                    "user.email",
                    "test@example.invalid",
                ],
                check=True,
            )
            source = repo / "main.tex"
            source.write_text("reviewed\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "main.tex"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-m", "source"], check=True
            )
            head = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
            ).strip()

            with self.assertRaisesRegex(
                PUBLICATION.AnchorError, "not the checked-out HEAD"
            ):
                PUBLICATION._assert_source_checkout(repo, "0" * 40)
            source.write_text("dirty\n", encoding="utf-8")
            with self.assertRaisesRegex(
                PUBLICATION.AnchorError, "publication checkout differs"
            ):
                PUBLICATION._assert_source_checkout(repo, head)
            source.write_text("reviewed\n", encoding="utf-8")
            (repo / "untracked.py").write_text("raise RuntimeError\n", encoding="utf-8")
            with self.assertRaisesRegex(
                PUBLICATION.AnchorError, "publication checkout differs"
            ):
                PUBLICATION._assert_source_checkout(repo, head)
    def test_latex_workflow_builds_candidate_without_release_writes(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "latex.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("group: latex-build-${{ github.ref }}", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("queue: max", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("Record exact source commit", workflow)
        self.assertLess(
            workflow.index("- name: Ensure pdftotext available"),
            workflow.index("- name: Run workflow contract tests"),
        )
        self.assertIn("Generate TeX macros from pinned intake (strict)", workflow)
        self.assertIn("make assets", workflow)
        self.assertIn("Build and verify companion evidence identity", workflow)
        self.assertIn("scripts/verify_companion_bundle.py", workflow)
        self.assertIn("scripts/gen_publication_identity.py", workflow)
        self.assertIn('commit="$(git rev-parse HEAD)"', workflow)
        self.assertIn("Tracked publication sources changed during the build", workflow)
        self.assertIn("python scripts/build_publication_manifest.py", workflow)
        self.assertIn('--whitepaper-commit "$BUILD_COMMIT"', workflow)
        self.assertIn("--publication-status candidate_not_published", workflow)
        self.assertIn("Build stable-v5 compatibility intake", workflow)
        self.assertIn("dist/stable-v5-intake-compatibility.zip", workflow)
        self.assertIn("dist/fl-bsa-v5.0.1-companion-evidence.zip", workflow)
        self.assertIn(
            "name: stable-v5-publication-candidate-${{ github.run_attempt }}",
            workflow,
        )
        self.assertIn("name: whitepaper-pdf-${{ github.run_attempt }}", workflow)
        self.assertIn("name: arxiv-source-${{ github.run_attempt }}", workflow)
        self.assertIn("dist/publication-manifest.json", workflow)

        for forbidden in (
            "draft_release_tag",
            "release-assets:",
            "contents: write",
            "gh release upload",
            "gh release create",
            "gh release edit",
            "github_draft_release_assets_staged_characterization_only",
            "stable-v5-publication-receipt.json",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, workflow)

        publication_doc = (ROOT / "docs" / "stable_v5_publication.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## No v5.0.1 draft-release staging", publication_doc)
        self.assertIn("does not contain a release-upload job", publication_doc)
        self.assertIn("Never pre-name a successor version", publication_doc)

        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        reproducibility = (ROOT / "sections" / "09_reproducibility.tex").read_text(
            encoding="utf-8"
        )
        self.assertIn("publication-candidate-repeatability:", makefile)
        repeatability_target = makefile.split(
            "publication-candidate-repeatability:", 1
        )[1].split("\nclean:", 1)[0]
        self.assertEqual(
            2, repeatability_target.count("$(MAKE) publication-candidate;")
        )
        for artifact in (
            "$(CANDIDATE_PDF)",
            "$(COMPANION)",
            "dist/whitepaper_arxiv_source.zip",
            "$(COMPATIBILITY_INTAKE)",
            "$(PUBLICATION_MANIFEST)",
        ):
            with self.subTest(artifact=artifact):
                self.assertGreaterEqual(repeatability_target.count(artifact), 2)
        self.assertIn(
            'cmp "$$reference_dir/$$artifact" "$$artifact"', repeatability_target
        )
        self.assertIn("make publication-candidate-repeatability", reproducibility)


if __name__ == "__main__":
    unittest.main()
