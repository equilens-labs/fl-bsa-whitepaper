import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from typing import Any
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
    @staticmethod
    def _receipt_fixture() -> tuple[dict, dict, dict[str, Any], dict[str, str]]:
        repository = "equilens-labs/fl-bsa-whitepaper"
        commit = "a" * 40
        run_id = 123
        run_attempt = 2
        artifacts = {
            "whitepaper_pdf": {
                "id": 11,
                "name": "whitepaper-pdf-2",
                "digest": "sha256:" + "b" * 64,
            },
            "arxiv_source": {
                "id": 12,
                "name": "arxiv-source-2",
                "digest": "sha256:" + "c" * 64,
            },
            "stable_v5_publication_candidate": {
                "id": 13,
                "name": "stable-v5-publication-candidate-2",
                "digest": "sha256:" + "d" * 64,
            },
        }
        candidate = {
            "schema_version": "flbsa.whitepaper_publication_candidate.v1",
            "publication_status": "candidate_not_published",
            "whitepaper": {"commit": commit},
            "artifact_profile": {"scope": "characterization_only"},
        }
        receipt = json.loads(json.dumps(candidate))
        receipt["schema_version"] = "flbsa.whitepaper_publication_receipt.v1"
        receipt["publication_status"] = (
            "github_draft_release_assets_staged_characterization_only"
        )
        receipt["release_receipt"] = {
            "repo": repository,
            "release_id": 99,
            "release_url": "https://github.com/equilens-labs/fl-bsa-whitepaper/releases/tag/v5.0.0",
            "release_created_at": "2026-07-18T00:00:00Z",
            "tag": "v5.0.0",
            "tag_commit": commit,
            "draft": True,
            "published_at": None,
            "asset_bytes_verified": True,
        }
        receipt["source_workflow"] = {
            "repository": repository,
            "workflow": ".github/workflows/latex.yml",
            "run_id": run_id,
            "run_attempt": run_attempt,
            "source_commit": commit,
            "artifacts": artifacts,
        }
        fixtures: dict[str, Any] = {
            f"repos/{repository}/actions/runs/{run_id}/attempts/{run_attempt}": {
                "id": run_id,
                "run_attempt": run_attempt,
                "path": ".github/workflows/latex.yml",
                "head_sha": commit,
                "event": "workflow_dispatch",
                "status": "completed",
                "conclusion": "success",
                "repository": {"full_name": repository},
            },
            (
                f"repos/{repository}/actions/runs/{run_id}/attempts/"
                f"{run_attempt}/jobs?per_page=100"
            ): [
                {
                    "total_count": 1,
                    "jobs": [
                        {
                            "id": 456,
                            "run_id": run_id,
                            "run_attempt": run_attempt,
                            "workflow_name": "latex-build",
                            "name": "build",
                            "head_sha": commit,
                            "status": "completed",
                            "conclusion": "success",
                        }
                    ],
                }
            ],
        }
        for identity in artifacts.values():
            fixtures[f"repos/{repository}/actions/artifacts/{identity['id']}"] = {
                "id": identity["id"],
                "name": identity["name"],
                "digest": identity["digest"],
                "expired": False,
                "size_in_bytes": 100,
                "workflow_run": {"id": run_id, "head_sha": commit},
            }
        environment = {
            "GITHUB_REPOSITORY": repository,
            "RELEASE_ID": "99",
            "RELEASE_URL": receipt["release_receipt"]["release_url"],
            "RELEASE_CREATED_AT": "2026-07-18T00:00:00Z",
            "RELEASE_TAG": "v5.0.0",
            "EXPECTED_BUILD_COMMIT": commit,
            "RECEIPT_ALREADY_STAGED": "true",
        }
        return candidate, receipt, fixtures, environment

    @staticmethod
    def _receipt_inline_code() -> str:
        workflow = (ROOT / ".github" / "workflows" / "latex.yml").read_text(
            encoding="utf-8"
        )
        here_doc = workflow.index("            python - <<'PY'")
        start = workflow.index("          import json\n", here_doc)
        end = workflow.index("          PY\n", start)
        return textwrap.dedent(workflow[start:end])

    def _run_receipt_inline(
        self,
        root: Path,
        candidate: dict,
        receipt: dict,
        fixtures: dict[str, Any],
        environment: dict[str, str],
        *,
        receipt_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        dist = root / "dist"
        dist.mkdir(parents=True)
        (dist / "publication-manifest.json").write_text(
            json.dumps(candidate), encoding="utf-8"
        )
        (dist / "stable-v5-publication-receipt.json").write_text(
            receipt_text if receipt_text is not None else json.dumps(receipt),
            encoding="utf-8",
        )
        tool_dir = root / "bin"
        tool_dir.mkdir()
        fake_gh = tool_dir / "gh"
        fake_gh.write_text(
            """#!/usr/bin/env python3
import json
import os
import sys

if len(sys.argv) < 3 or sys.argv[1] != "api":
    raise SystemExit(2)
fixture = json.loads(os.environ["GH_API_FIXTURES"]).get(sys.argv[-1])
if fixture is None:
    raise SystemExit(3)
print(json.dumps(fixture))
""",
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)
        env = os.environ.copy()
        env.update(environment)
        env["GH_API_FIXTURES"] = json.dumps(fixtures)
        env["PATH"] = str(tool_dir) + os.pathsep + env["PATH"]
        return subprocess.run(
            [sys.executable, "-c", self._receipt_inline_code()],
            cwd=root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_manifest_binds_source_trees_artifacts_and_claims(self) -> None:
        commit = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "whitepaper.pdf"
            arxiv = Path(tmp) / "whitepaper_arxiv_source.zip"
            compatibility = Path(tmp) / "stable-v5-intake-compatibility.zip"
            pdf.write_bytes(b"stable-v5 pdf candidate")
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
            with mock.patch.object(PUBLICATION, "_assert_pdf_marker") as marker:
                manifest = PUBLICATION.build_manifest(
                    repo_root=ROOT,
                    anchor_path=ROOT / "baselines" / "stable-v5-characterization.json",
                    intake_manifest_path=ROOT / "intake" / "manifest.json",
                    whitepaper_commit=commit,
                    publication_status="candidate_not_published",
                    pdf_path=pdf,
                    arxiv_path=arxiv,
                    compatibility_intake_path=compatibility,
                )
                marker.assert_called_once_with(pdf, "pdftotext")

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
            "7ee3709869d398eb3e2aa548a47b361fc74d5a61cfb7619c2eb03fc8b0de2f1d",
            manifest["whitepaper"]["publication_input_projection"]["sha256"],
        )
        self.assertEqual(
            hashlib.sha256(b"stable-v5 pdf candidate").hexdigest(),
            manifest["artifacts"]["pdf"]["sha256"],
        )
        self.assertEqual(23, manifest["artifacts"]["pdf"]["size_bytes"])
        self.assertEqual(
            "42bcdcc72043a9ddd70f1821cf88b2c9963d34bd8f4444ee3b4093ed34276060",
            manifest["artifacts"]["compatibility_intake"]["sha256"],
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
            arxiv = tmp_path / "source.zip"
            compatibility = tmp_path / "compatibility.zip"
            intake.write_text(json.dumps(original), encoding="utf-8")
            pdf.write_bytes(b"pdf")
            arxiv.write_bytes(b"zip")
            compatibility.write_bytes(b"not reached")
            with mock.patch.object(PUBLICATION, "_assert_pdf_marker"):
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
                        arxiv_path=arxiv,
                        compatibility_intake_path=compatibility,
                    )

    def test_pdf_marker_check_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "candidate.pdf"
            pdf.write_bytes(b"not a PDF")
            with self.assertRaisesRegex(
                PUBLICATION.AnchorError, "inspect publication PDF"
            ):
                PUBLICATION._assert_pdf_marker(pdf, "pdftotext")

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

    def test_latex_workflow_builds_and_attaches_bounded_manifest(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "latex.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("Write stable-v5 publication manifest", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("draft_release_tag:", workflow)
        self.assertIn("Record exact source commit", workflow)
        self.assertIn("Bind draft staging to the exact dispatch tag", workflow)
        self.assertIn('[ "$DISPATCH_REF" != "refs/tags/${RELEASE_TAG}" ]', workflow)
        self.assertIn('[ "$DISPATCH_HEAD_SHA" != "$BUILD_COMMIT" ]', workflow)
        self.assertLess(
            workflow.index("- name: Ensure pdftotext available"),
            workflow.index("- name: Run workflow contract tests"),
        )
        self.assertIn("Require a full same-attempt draft-staging run", workflow)
        self.assertIn(
            '[ "$SOURCE_RUN_ATTEMPT" != "$CURRENT_RUN_ATTEMPT" ]', workflow
        )
        self.assertIn("Generate TeX macros from pinned intake (strict)", workflow)
        self.assertNotIn("make macros", workflow)
        self.assertIn('commit="$(git rev-parse HEAD)"', workflow)
        self.assertIn("Tracked publication sources changed during the build", workflow)
        self.assertIn("python scripts/build_publication_manifest.py", workflow)
        self.assertIn('--whitepaper-commit "$BUILD_COMMIT"', workflow)
        self.assertIn("--publication-status candidate_not_published", workflow)
        self.assertIn("Build stable-v5 compatibility intake", workflow)
        self.assertIn("dist/stable-v5-intake-compatibility.zip", workflow)
        self.assertIn(
            "name: stable-v5-publication-candidate-${{ github.run_attempt }}",
            workflow,
        )
        self.assertIn("name: whitepaper-pdf-${{ github.run_attempt }}", workflow)
        self.assertIn("name: arxiv-source-${{ github.run_attempt }}", workflow)
        self.assertIn(
            "pdf_artifact_id: ${{ steps.upload_pdf.outputs.artifact-id }}", workflow
        )
        self.assertIn(
            "stable_candidate_artifact_digest: "
            "${{ steps.upload_stable_candidate.outputs.artifact-digest }}",
            workflow,
        )
        self.assertIn("dist/publication-manifest.json", workflow)
        self.assertIn("release-assets:", workflow)
        self.assertIn("inputs.draft_release_tag != ''", workflow)
        self.assertIn("needs: build", workflow)
        self.assertIn("actions: read", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn(
            "group: latex-build-${{ inputs.draft_release_tag || github.ref }}", workflow
        )
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("queue: max", workflow)
        self.assertIn(
            "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093",
            workflow,
        )
        self.assertIn("Stage or byte-verify draft release assets and receipt", workflow)
        self.assertIn("Validate exact source artifact identities", workflow)
        self.assertIn("verify_candidate_artifact()", workflow)
        self.assertIn(
            "verify_candidate_artifact pdf dist/whitepaper.pdf whitepaper.pdf",
            workflow,
        )
        self.assertIn('"run_attempt": int(os.environ["SOURCE_RUN_ATTEMPT"])', workflow)
        self.assertIn('"digest": os.environ["SOURCE_PDF_ARTIFACT_DIGEST"]', workflow)
        self.assertIn("set(release_receipt) != expected_release_receipt_keys", workflow)
        self.assertIn("object_pairs_hook=unique_json_object", workflow)
        self.assertIn("JSON object contains duplicate keys", workflow)
        self.assertIn(
            'candidate.get("schema_version") '
            '!= "flbsa.whitepaper_publication_candidate.v1"',
            workflow,
        )
        self.assertIn("set(source) != expected_source_keys", workflow)
        self.assertIn("set(artifacts) != set(expected_names)", workflow)
        self.assertIn('set(identity) != {"id", "name", "digest"}', workflow)
        self.assertIn('type(source.get("run_id")) is not int', workflow)
        self.assertIn('type(source_attempt) is not int', workflow)
        self.assertIn('type(identity.get("id")) is not int', workflow)
        self.assertIn(
            'release_receipt.get("release_url") != os.environ["RELEASE_URL"]',
            workflow,
        )
        self.assertIn(
            '!= os.environ["RELEASE_CREATED_AT"]',
            workflow,
        )
        self.assertIn(
            'f"{source[\'run_id\']}/attempts/{source_attempt}"', workflow
        )
        self.assertIn('source_run.get("event") != "workflow_dispatch"', workflow)
        self.assertIn('source_build.get("conclusion") != "success"', workflow)
        self.assertIn("/jobs?per_page=100", workflow)
        self.assertIn('["gh", "api", "--paginate", "--slurp", endpoint]', workflow)
        self.assertIn(
            'f"{identity[\'id\']}"',
            workflow,
        )
        self.assertIn('api_artifact.get("digest") != identity["digest"]', workflow)
        self.assertIn('api_artifact.get("expired") is not False', workflow)
        self.assertIn('workflow_run.get("id") != source["run_id"]', workflow)
        self.assertIn(".draft == true", workflow)
        self.assertIn(".published_at == null", workflow)
        self.assertIn("(.immutable != true)", workflow)
        self.assertIn("git/ref/tags/${tag}", workflow)
        self.assertIn("git/tags/${object_sha}", workflow)
        self.assertIn("releases/${release_id}/assets?per_page=100", workflow)
        self.assertIn("gh api --paginate --slurp", workflow)
        self.assertIn("publish_or_verify()", workflow)
        self.assertIn("gh release upload", workflow)
        self.assertNotIn("--clobber", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("gh release edit", workflow)
        self.assertNotIn("types: [ published ]", workflow)
        self.assertIn("Existing release asset ${name} is not byte-identical", workflow)
        build_job = workflow.split("  release-assets:", 1)[0]
        self.assertNotIn(
            "github_draft_release_assets_staged_characterization_only", build_job
        )
        publish_step = workflow.split(
            "- name: Stage or byte-verify draft release assets and receipt", 1
        )[1]
        self.assertLess(
            publish_step.index(
                "publish_or_verify dist/stable-v5-intake-compatibility.zip"
            ),
            publish_step.index(
                'receipt["publication_status"] = "github_draft_release_assets_staged_characterization_only"'
            ),
        )

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        publication_doc = (ROOT / "docs" / "stable_v5_publication.md").read_text(
            encoding="utf-8"
        )
        exact_dispatch = (
            "gh workflow run latex.yml --ref v5.0.0 "
            "-f draft_release_tag=v5.0.0"
        )
        self.assertIn(exact_dispatch, readme)
        self.assertIn(exact_dispatch, publication_doc)
        self.assertLess(
            publish_step.index(
                'receipt["publication_status"] = "github_draft_release_assets_staged_characterization_only"'
            ),
            publish_step.index(
                "publish_or_verify dist/stable-v5-publication-receipt.json"
            ),
        )

    def test_existing_receipt_is_bound_to_live_actions_metadata(self) -> None:
        candidate, receipt, fixtures, environment = self._receipt_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_receipt_inline(
                Path(tmp), candidate, receipt, fixtures, environment
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("preserving original bytes", result.stdout)

        candidate, receipt, fixtures, environment = self._receipt_fixture()
        fixtures[
            "repos/equilens-labs/fl-bsa-whitepaper/actions/runs/123/attempts/2"
        ]["path"] = ".github/workflows/latex.yml@v5.0.0"
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_receipt_inline(
                Path(tmp), candidate, receipt, fixtures, environment
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)

        candidate, receipt, fixtures, environment = self._receipt_fixture()
        fixtures[
            "repos/equilens-labs/fl-bsa-whitepaper/actions/runs/123/attempts/2"
        ]["conclusion"] = "failure"
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_receipt_inline(
                Path(tmp), candidate, receipt, fixtures, environment
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)

        for label in (
            "failed source build",
            "artifact digest mismatch",
            "artifact run mismatch",
        ):
            candidate, receipt, fixtures, environment = self._receipt_fixture()
            artifact_fixture = fixtures[
                "repos/equilens-labs/fl-bsa-whitepaper/actions/artifacts/11"
            ]
            source_jobs_fixture = fixtures[
                "repos/equilens-labs/fl-bsa-whitepaper/actions/runs/123/attempts/2/jobs?per_page=100"
            ]
            if label == "failed source build":
                source_jobs_fixture[0]["jobs"][0]["conclusion"] = "failure"
            elif label == "artifact digest mismatch":
                artifact_fixture["digest"] = "sha256:" + "e" * 64
            else:
                artifact_fixture["workflow_run"]["id"] = 999
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                result = self._run_receipt_inline(
                    Path(tmp), candidate, receipt, fixtures, environment
                )
                self.assertNotEqual(0, result.returncode)

        candidate, receipt, fixtures, environment = self._receipt_fixture()
        duplicate = json.dumps(receipt).replace(
            '"schema_version":',
            '"schema_version":"duplicate","schema_version":',
            1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_receipt_inline(
                Path(tmp),
                candidate,
                receipt,
                fixtures,
                environment,
                receipt_text=duplicate,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("unique-key JSON", result.stderr)


if __name__ == "__main__":
    unittest.main()
