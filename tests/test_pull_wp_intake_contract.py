import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pull-wp-intake.yml"
)


class PullWpIntakeContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def assert_contract(self, workflow: str) -> None:
        parsed = yaml.safe_load(workflow)
        on_section = parsed.get(True, parsed.get("on"))
        self.assertEqual(
            {"repository_dispatch": {"types": ["wp-intake-ready"]}},
            on_section,
        )
        self.assertEqual(
            "wp-intake-release-evidence.yml-"
            "${{ github.event.client_payload.producer_run_id }}-"
            "${{ github.event.client_payload.artifact_id }}",
            parsed["run-name"],
        )
        self.assertEqual(
            {
                "contents": "read",
                "actions": "read",
                "attestations": "read",
            },
            parsed["permissions"],
        )
        self.assertEqual(
            "pull-wp-intake-${{ github.event.client_payload.producer_run_id }}",
            parsed["concurrency"]["group"],
        )
        self.assertIs(parsed["concurrency"]["cancel-in-progress"], False)

        required = (
            "scripts/whitepaper_intake_producer_contract.py validate-dispatch",
            "scripts/whitepaper_intake_producer_contract.py validate-authority",
            "contracts/whitepaper-intake-producer-contract.v1.json",
            'if [[ ! "$run_id" =~ ^[1-9][0-9]*$ ]]; then',
            'if ! run_json="$(gh api "repos/${PRODUCER_REPO}/actions/runs/${run_id}")"; then',
            "for ((attempt=1; attempt<=81; attempt++)); do",
            "actions/runs/${run_id}/attempts/${run_attempt}/jobs?per_page=100",
            'producer_job_name="WP Evidence (release-grade)"',
            "Release intake authorized by completed ${producer_job_name} job",
            '((.path // "") | split("@")[0]) == $workflow_path',
            ".head_branch == $branch",
            ".head_repository.full_name == $producer_repo",
            'if [ "$PRODUCER_ARTIFACT" != "wp-intake-bundle-v4-${run_attempt}" ]; then',
            'if [ "$PRODUCER_ARTIFACT_ID" != "$artifact_id" ]; then',
            'if [ "$PRODUCER_ARTIFACT_DIGEST" != "$artifact_digest" ]; then',
            'artifact_match_count="$(jq --arg name "$PRODUCER_ARTIFACT"',
            'gh api "repos/${PRODUCER_REPO}/actions/artifacts/${artifact_id}/zip"',
            'downloaded_digest="sha256:$(sha256sum "$artifact_archive"',
            'expected_bundle_filename="WhitePaper_Intake_Bundle_v4.zip"',
            "gh attestation verify",
            '[[ "$artifact_created_at" < "$run_started_at" ]]',
            "product_sha != expected_head_sha",
            "producer bundle contains non-public/unreviewed members",
            "Stage and replace managed intake/config surfaces",
            "repo_owned_intake=(",
            "producer_managed_intake=(",
            'sync_stage="$(mktemp -d "${RUNNER_TEMP}/wp-intake-sync.XXXXXX")"',
            'cp -a intake/archive/. "$sync_stage/intake/archive/"',
            "rm -rf intake config",
            'mv "$sync_stage/intake" intake',
            'mv "$sync_stage/config" config',
            "python scripts/validate_public_intake.py",
            "python scripts/intake_anchor.py snapshot",
            '--producer-head-sha "$SELECTED_PRODUCER_HEAD_SHA"',
            '--producer-run-attempt "$SELECTED_PRODUCER_RUN_ATTEMPT"',
            '--producer-artifact-id "$SELECTED_PRODUCER_ARTIFACT_ID"',
            '--producer-artifact-digest "$SELECTED_PRODUCER_ARTIFACT_DIGEST"',
            '--producer-contract-sha256 "$SELECTED_PRODUCER_CONTRACT_SHA256"',
            "--output intake/whitepaper_snapshot.json",
            "name: whitepaper-intake-receipt-${{ github.run_attempt }}",
            "name: Prepare exact release whitepaper",
            "python scripts/release_whitepaper.py prepare",
            "name: Compile exact release whitepaper",
            "root_file: release/main.tex",
            "name: Canonicalize exact release whitepaper bytes",
            "python3 scripts/canonicalize_release_pdf.py main.pdf",
            "name: Verify exact release whitepaper layout",
            "python3 scripts/check_release_layout.py main.log --max-overfull-pt 2",
            "name: Verify exact release whitepaper is passive",
            "python3 scripts/check_release_pdf_passive.py main.pdf",
            "name: Finalize exact release whitepaper manifest",
            "python scripts/release_whitepaper.py finalize",
            "name: release-whitepaper-${{ github.run_attempt }}",
            "dist/release-whitepaper/whitepaper.pdf",
            "dist/release-whitepaper/whitepaper_release.json",
        )
        for fragment in required:
            self.assertIn(fragment, workflow)

        forbidden = (
            "schedule:",
            "scheduled",
            "nightly",
            "wp-evidence-nightly",
            "wp-reviewer-pack",
            "validate-selector",
            "gh run list",
            "resolve_latest_producer_run",
            "PERSIST_INTAKE",
            "WP_INTAKE_PR_TOKEN",
            "pull-requests:",
            "git push",
            "gh pr ",
            "intake-pr-soft-fail",
            "github.event.client_payload.workflow_file == 'release-evidence.yml'",
        )
        lowered = workflow.lower()
        for fragment in forbidden:
            self.assertNotIn(fragment.lower(), lowered)

        steps = parsed["jobs"]["fetch-build"]["steps"]
        step_names = [step.get("name") for step in steps]
        for name in (
            "Prepare exact release whitepaper",
            "Install PDF text tooling for release paper",
            "Compile exact release whitepaper",
            "Canonicalize exact release whitepaper bytes",
            "Verify exact release whitepaper layout",
            "Verify exact release whitepaper is passive",
            "Finalize exact release whitepaper manifest",
            "Upload exact release whitepaper",
        ):
            step = next(step for step in steps if step.get("name") == name)
            self.assertNotIn("if", step)

        ordered = (
            "Write deterministic intake snapshot record",
            "Upload exact intake receipt",
            "Prepare exact release whitepaper",
            "Compile exact release whitepaper",
            "Canonicalize exact release whitepaper bytes",
            "Verify exact release whitepaper layout",
            "Verify exact release whitepaper is passive",
            "Finalize exact release whitepaper manifest",
            "Upload exact release whitepaper",
        )
        positions = [step_names.index(name) for name in ordered]
        self.assertEqual(sorted(positions), positions)

    def test_pull_wp_intake_is_release_dispatch_only(self) -> None:
        self.assert_contract(self.workflow)

    def test_repository_dispatch_requires_exact_run_and_artifact_identity(
        self,
    ) -> None:
        workflow = yaml.safe_load(self.workflow)
        download = next(
            step
            for step in workflow["jobs"]["fetch-build"]["steps"]
            if step.get("name") == "Download intake bundle from producer"
        )["run"]
        selector_guard = download.split(
            'token="${PRODUCER_TOKEN:-}"',
            1,
        )[0]
        selector_guard += "\nprintf 'selector-validated\\n'\n"
        contract_path = (
            WORKFLOW.parents[2]
            / "contracts"
            / ("whitepaper-intake-producer-contract.v1.json")
        )
        contract_digest = hashlib.sha256(contract_path.read_bytes()).hexdigest()
        payload = {
            "artifact_digest": "sha256:" + "a" * 64,
            "artifact_id": "456",
            "artifact_name": "wp-intake-bundle-v4-3",
            "branch": "main",
            "persist_intake_pr": "false",
            "producer_contract_sha256": contract_digest,
            "producer_repo": "equilens-labs/fl-bsa",
            "producer_run_attempt": "3",
            "producer_run_id": "123",
            "workflow_file": "release-evidence.yml",
        }
        valid_env = {
            **os.environ,
            "GITHUB_EVENT_NAME": "repository_dispatch",
            "PRODUCER_REPO": "equilens-labs/fl-bsa",
            "PRODUCER_WORKFLOW": "release-evidence.yml",
            "PRODUCER_ARTIFACT": "wp-intake-bundle-v4-3",
            "PRODUCER_BRANCH": "main",
            "PRODUCER_RUN_ID": "123",
            "PRODUCER_RUN_ATTEMPT": "3",
            "PRODUCER_ARTIFACT_ID": "456",
            "PRODUCER_ARTIFACT_DIGEST": "sha256:" + "a" * 64,
            "DISPATCH_PAYLOAD_JSON": json.dumps(payload),
        }

        accepted = subprocess.run(
            ["bash", "-c", selector_guard],
            env=valid_env,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, accepted.returncode, accepted.stderr)
        self.assertIn("selector-validated", accepted.stdout)

        for field, env_field, malformed in (
            ("producer_run_id", "PRODUCER_RUN_ID", ""),
            ("producer_run_id", "PRODUCER_RUN_ID", "latest"),
            ("producer_run_attempt", "PRODUCER_RUN_ATTEMPT", "0"),
            ("artifact_id", "PRODUCER_ARTIFACT_ID", "-1"),
            ("artifact_digest", "PRODUCER_ARTIFACT_DIGEST", "sha256:not-a-digest"),
        ):
            with self.subTest(field=field, malformed=malformed):
                malformed_payload = {**payload, field: malformed}
                rejected = subprocess.run(
                    ["bash", "-c", selector_guard],
                    env={
                        **valid_env,
                        env_field: malformed,
                        "DISPATCH_PAYLOAD_JSON": json.dumps(malformed_payload),
                    },
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(0, rejected.returncode)
                self.assertIn(
                    "whitepaper intake producer contract failed",
                    rejected.stderr,
                )

    def test_required_anchors_are_mutation_sensitive(self) -> None:
        required_fragments = (
            "run-name: wp-intake-release-evidence.yml-${{ github.event.client_payload.producer_run_id }}-${{ github.event.client_payload.artifact_id }}",
            "group: pull-wp-intake-${{ github.event.client_payload.producer_run_id }}",
            "scripts/whitepaper_intake_producer_contract.py validate-dispatch",
            "scripts/whitepaper_intake_producer_contract.py validate-authority",
            "python scripts/intake_anchor.py snapshot",
            "python scripts/validate_public_intake.py",
            'if ! run_json="$(gh api "repos/${PRODUCER_REPO}/actions/runs/${run_id}")"; then',
            "Stage and replace managed intake/config surfaces",
            "producer bundle contains non-public/unreviewed members",
            ".head_repository.full_name == $producer_repo",
            'gh api "repos/${PRODUCER_REPO}/actions/artifacts/${artifact_id}/zip"',
            'downloaded_digest="sha256:$(sha256sum "$artifact_archive"',
            'if [ "$PRODUCER_ARTIFACT" != "wp-intake-bundle-v4-${run_attempt}" ]; then',
            'if [ "$PRODUCER_ARTIFACT_ID" != "$artifact_id" ]; then',
            'if [ "$PRODUCER_ARTIFACT_DIGEST" != "$artifact_digest" ]; then',
            "rm -rf intake config",
            "name: whitepaper-intake-receipt-${{ github.run_attempt }}",
            "name: Prepare exact release whitepaper",
            "name: Upload exact release whitepaper",
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                mutated = self.workflow.replace(fragment, "", 1)
                with self.assertRaises(
                    (AssertionError, KeyError, StopIteration, TypeError)
                ):
                    self.assert_contract(mutated)

    def test_consumer_stamp_is_deterministic(self) -> None:
        sync = self.workflow.split(
            "- name: Stage and replace managed intake/config surfaces", 1
        )[1].split("- name: Write deterministic intake snapshot record", 1)[0]

        self.assertIn('"schema_version": "flbsa.whitepaper_consumer.v4"', sync)
        self.assertIn('"base_commit": os.environ["GITHUB_SHA"]', sync)
        self.assertNotIn("datetime", sync)
        self.assertNotIn("ingested_at", sync)
        self.assertNotIn("GITHUB_RUN_ATTEMPT", sync)
        self.assertIn(
            '"head_sha": os.environ.get("SELECTED_PRODUCER_HEAD_SHA", "")', sync
        )
        self.assertIn(
            '"run_attempt": os.environ.get("SELECTED_PRODUCER_RUN_ATTEMPT", "")',
            sync,
        )
        self.assertIn(
            '"artifact_id": os.environ.get("SELECTED_PRODUCER_ARTIFACT_ID", "")',
            sync,
        )
        self.assertIn(
            '"artifact_digest": os.environ.get("SELECTED_PRODUCER_ARTIFACT_DIGEST", "")',
            sync,
        )
        self.assertIn(
            '"contract_sha256": os.environ.get("SELECTED_PRODUCER_CONTRACT_SHA256", "")',
            sync,
        )
        self.assertIn('"repo": os.environ.get("SELECTED_PRODUCER_REPO", "")', sync)
        self.assertNotIn('os.environ.get("PRODUCER_REPO"', sync)

    def test_producer_run_metadata_is_verified_before_stamping(self) -> None:
        download = self.workflow.split(
            "- name: Download intake bundle from producer", 1
        )[1].split("- name: Unpack intake bundle", 1)[0]
        schema = self.workflow.split("- name: Validate bundle schema versions", 1)[
            1
        ].split("- name: Stage and replace managed intake/config surfaces", 1)[0]

        self.assertIn('if [[ ! "$run_id" =~ ^[1-9][0-9]*$ ]]; then', download)
        self.assertIn("for ((attempt=1; attempt<=81; attempt++)); do", download)
        self.assertIn('run_status="$(jq -r \'.status\' <<<"$run_json")"', download)
        self.assertIn(
            'run_conclusion="$(jq -r \'.conclusion // ""\' <<<"$run_json")"', download
        )
        self.assertIn('case "$run_status" in', download)
        self.assertIn("completed)", download)
        self.assertIn('if [ "$run_conclusion" != "success" ]; then', download)
        self.assertIn('producer_job_name="WP Evidence (release-grade)"', download)
        self.assertIn('if [ "$producer_job_status" = "completed" ]; then', download)
        self.assertIn("sleep 15", download)
        self.assertIn('((.path // "") | split("@")[0]) == $workflow_path', download)
        self.assertIn(".head_branch == $branch", download)
        self.assertIn(".head_repository.full_name == $producer_repo", download)
        self.assertIn('run_event="$(jq -r \'.event // ""\' <<<"$run_json")"', download)
        self.assertIn("wp-intake-bundle-v4-${run_attempt}", download)
        self.assertIn('[[ "$artifact_created_at" < "$run_started_at" ]]', download)
        self.assertIn("actions/artifacts/${artifact_id}/zip", download)
        self.assertIn('test("^[0-9a-f]{40}$")', download)
        self.assertLess(
            download.index('gh api "repos/${PRODUCER_REPO}/actions/runs/${run_id}"'),
            download.index("actions/runs/${run_id}/artifacts"),
        )
        self.assertIn('product_sha = str(m.get("commit_sha") or "")', schema)
        self.assertIn("product_sha != expected_head_sha", schema)
        self.assertIn(
            'for field in ("code_commit", "source_commit", "software_commit")',
            schema,
        )

    def test_release_dispatch_accepts_only_the_exact_successful_producer_job(
        self,
    ) -> None:
        workflow = yaml.safe_load(self.workflow)
        download = next(
            step
            for step in workflow["jobs"]["fetch-build"]["steps"]
            if step.get("name") == "Download intake bundle from producer"
        )["run"]
        predicate = download.split('--arg job_name "$producer_job_name" \'', 1)[
            1
        ].split('\n      \' <<<"$producer_job_json"', 1)[0]
        expected_predicate = """
            (.id | tostring | test("^[1-9][0-9]*$")) and
            (.run_id | tostring) == $run_id and
            (.run_attempt | tostring) == $run_attempt and
            .head_sha == $head_sha and
            .name == $job_name and
            (
              (.status == "completed" and .conclusion == "success") or
              (
                (.status == "queued" or .status == "in_progress" or
                 .status == "requested" or .status == "waiting" or
                 .status == "pending") and
                .conclusion == null
              )
            )
        """
        self.assertEqual(
            " ".join(expected_predicate.split()), " ".join(predicate.split())
        )

        run_id = "12345"
        run_attempt = "2"
        head_sha = "a" * 40
        job_name = "WP Evidence (release-grade)"
        good = {
            "id": 67890,
            "run_id": 12345,
            "run_attempt": 2,
            "head_sha": head_sha,
            "name": job_name,
            "status": "completed",
            "conclusion": "success",
        }

        def run_predicate(payload: dict) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    "jq",
                    "-e",
                    "--arg",
                    "run_id",
                    run_id,
                    "--arg",
                    "run_attempt",
                    run_attempt,
                    "--arg",
                    "head_sha",
                    head_sha,
                    "--arg",
                    "job_name",
                    job_name,
                    predicate,
                ],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(0, run_predicate(good).returncode)
        pending = dict(good, status="in_progress", conclusion=None)
        self.assertEqual(0, run_predicate(pending).returncode)
        mutations = {
            "job id": {**good, "id": 0},
            "run id": {**good, "run_id": 99999},
            "attempt": {**good, "run_attempt": 3},
            "SHA": {**good, "head_sha": "b" * 40},
            "job name": {**good, "name": "Other job"},
            "failed": {**good, "conclusion": "failure"},
            "unknown status": {**good, "status": "mystery", "conclusion": None},
            "premature conclusion": {**good, "status": "in_progress"},
        }
        for label, payload in mutations.items():
            with self.subTest(label=label):
                self.assertNotEqual(0, run_predicate(payload).returncode)

    def test_managed_surfaces_are_replaced_and_archive_is_preserved(self) -> None:
        sync = self.workflow.split(
            "- name: Stage and replace managed intake/config surfaces", 1
        )[1].split("- name: Write deterministic intake snapshot record", 1)[0]

        archive_copy = 'cp -a intake/archive/. "$sync_stage/intake/archive/"'
        removal = "rm -rf intake config"
        self.assertIn(archive_copy, sync)
        self.assertIn(removal, sync)
        self.assertLess(sync.index(archive_copy), sync.index(removal))
        self.assertLess(
            sync.index(removal), sync.index('mv "$sync_stage/intake" intake')
        )
        self.assertNotIn("cp bundle/intake/*.csv intake/", sync)
        self.assertNotIn("cp bundle/intake/*.json intake/", sync)
        self.assertNotIn("cp bundle/certificates/*.json intake/certificates/", sync)
        for repo_owned in (
            "calibration_bins_TEMPLATE.csv",
            "confusion_by_group_TEMPLATE.csv",
            "governance_contacts.csv",
            "licenses_inventory.csv",
            "model_hyperparams.yaml",
            "privacy_audit_checklist.md",
        ):
            self.assertIn(repo_owned, sync)

    def test_raw_bundle_privacy_and_metadata_are_rejected_and_not_uploaded(
        self,
    ) -> None:
        workflow = yaml.safe_load(self.workflow)
        steps = workflow["jobs"]["fetch-build"]["steps"]
        unpack = next(
            item for item in steps if item.get("name") == "Unpack intake bundle"
        )
        match = re.search(
            r'export BUNDLE_PATH="\$bundle_path"\npython - <<\'PY\'\n(.*?)\nPY',
            unpack["run"],
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        validator = match.group(1)

        required = {
            "intake/fairness_slices.json": b"{}\n",
            "intake/metrics_long.csv": b"metric_name,value\n",
            "intake/metrics_uncertainty.json": b"{}\n",
            "intake/pack_intent.json": b"{}\n",
            "intake/regulatory_matrix.csv": b"framework,citation\n",
            "intake/selection_rates.csv": b"attribute,group\n",
            "provenance/manifest.json": b"{}\n",
            "certificates/hyperparameter_tuning_certificate_amplification.json": b"{}\n",
            "certificates/hyperparameter_tuning_certificate_intrinsic.json": b"{}\n",
            "certificates/model_certificate_amplification.json": b"{}\n",
            "certificates/model_certificate_intrinsic.json": b"{}\n",
            "certificates/synthetic_quality_certificate.json": b"{}\n",
            "config/sap.yaml": b"version: 1\n",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            safe_zip = root / "safe.zip"
            unsafe_zip = root / "unsafe.zip"
            with zipfile.ZipFile(safe_zip, "w") as archive:
                for name, payload in required.items():
                    archive.writestr(name, payload)
            with zipfile.ZipFile(unsafe_zip, "w") as archive:
                for name, payload in required.items():
                    archive.writestr(name, payload)
                archive.writestr(
                    "privacy/private-person@example.com.json", b'{"ssn":"blocked"}\n'
                )
                archive.writestr("metadata/tuning_intrinsic.json", b"{}\n")

            safe = subprocess.run(
                ["python3", "-c", validator],
                env={**os.environ, "BUNDLE_PATH": str(safe_zip)},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, safe.returncode, safe.stderr)

            for release_input in (
                "intake/fairness_slices.json",
                "intake/metrics_long.csv",
                "intake/selection_rates.csv",
                "intake/regulatory_matrix.csv",
                "certificates/hyperparameter_tuning_certificate_amplification.json",
                "certificates/hyperparameter_tuning_certificate_intrinsic.json",
                "certificates/model_certificate_amplification.json",
                "certificates/model_certificate_intrinsic.json",
            ):
                with self.subTest(missing=release_input):
                    missing_zip = root / f"missing-{Path(release_input).name}.zip"
                    with zipfile.ZipFile(missing_zip, "w") as archive:
                        for name, payload in required.items():
                            if name != release_input:
                                archive.writestr(name, payload)
                    missing = subprocess.run(
                        ["python3", "-c", validator],
                        env={**os.environ, "BUNDLE_PATH": str(missing_zip)},
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(0, missing.returncode)
                    self.assertIn(release_input, missing.stderr)

            unsafe = subprocess.run(
                ["python3", "-c", validator],
                env={**os.environ, "BUNDLE_PATH": str(unsafe_zip)},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, unsafe.returncode)
            self.assertIn("non-public/unreviewed members", unsafe.stderr)
            self.assertNotIn("private-person@example.com", unsafe.stderr)

        rendered = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("name: intake-bundle-used", rendered)
        self.assertNotIn("wp-bundle/**", rendered)

    def test_unpack_accepts_exact_attempt_qualified_artifacts(self) -> None:
        workflow = yaml.safe_load(self.workflow)
        unpack = next(
            item
            for item in workflow["jobs"]["fetch-build"]["steps"]
            if item.get("name") == "Unpack intake bundle"
        )["run"]
        required = {
            "intake/fairness_slices.json": b"{}\n",
            "intake/metrics_long.csv": b"metric_name,value\n",
            "intake/metrics_uncertainty.json": b"{}\n",
            "intake/pack_intent.json": b"{}\n",
            "intake/regulatory_matrix.csv": b"framework,citation\n",
            "intake/selection_rates.csv": b"attribute,group\n",
            "provenance/manifest.json": b"{}\n",
            "certificates/hyperparameter_tuning_certificate_amplification.json": b"{}\n",
            "certificates/hyperparameter_tuning_certificate_intrinsic.json": b"{}\n",
            "certificates/model_certificate_amplification.json": b"{}\n",
            "certificates/model_certificate_intrinsic.json": b"{}\n",
            "certificates/synthetic_quality_certificate.json": b"{}\n",
            "config/sap.yaml": b"version: 1\n",
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_dir = root / "wp-bundle"
            bundle_dir.mkdir()
            bundle = bundle_dir / "WhitePaper_Intake_Bundle_v4.zip"
            with zipfile.ZipFile(bundle, "w") as archive:
                for name, payload in required.items():
                    archive.writestr(name, payload)

            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$GH_CALL_LOG"\n',
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)
            gh_call_log = root / "gh-calls.log"
            github_env = root / "github-env"
            env = {
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "GH_CALL_LOG": str(gh_call_log),
                "GITHUB_ENV": str(github_env),
                "SELECTED_PRODUCER_REPO": "equilens-labs/fl-bsa",
            }

            for artifact in ("wp-intake-bundle-v4-1", "wp-intake-bundle-v4-10"):
                with self.subTest(artifact=artifact):
                    completed = subprocess.run(
                        ["bash", "-c", unpack],
                        cwd=root,
                        env={**env, "SELECTED_PRODUCER_ARTIFACT": artifact},
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(0, completed.returncode, completed.stderr)

            calls = gh_call_log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(2, len(calls))
            self.assertTrue(
                all(call.startswith("attestation verify ") for call in calls), calls
            )

            for artifact in (
                "wp-intake-bundle-v4-0",
                "wp-intake-bundle-v4-01",
                "wp-intake-bundle-v4-1x",
                "wp-intake-bundle-v4-",
            ):
                with self.subTest(artifact=artifact):
                    completed = subprocess.run(
                        ["bash", "-c", unpack],
                        cwd=root,
                        env={**env, "SELECTED_PRODUCER_ARTIFACT": artifact},
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(0, completed.returncode)
                    self.assertIn(
                        "Malformed selected producer artifact", completed.stderr
                    )

    def test_managed_surface_replacement_removes_omissions(self) -> None:
        workflow = yaml.safe_load(self.workflow)
        step = next(
            item
            for item in workflow["jobs"]["fetch-build"]["steps"]
            if item.get("name") == "Stage and replace managed intake/config surfaces"
        )
        product_sha = "a" * 40
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner_temp = root / "runner-temp"
            runner_temp.mkdir()
            for path in (
                root / "bundle" / "intake",
                root / "bundle" / "provenance",
                root / "bundle" / "certificates",
                root / "bundle" / "config",
                root / "intake" / "archive",
                root / "intake" / "certificates",
                root / "config",
            ):
                path.mkdir(parents=True, exist_ok=True)

            manifest = {"schema_version": "wp-intake.v1", "commit_sha": product_sha}
            (root / "bundle" / "provenance" / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            for name in (
                "fairness_slices.json",
                "metrics_uncertainty.json",
                "pack_intent.json",
                "air_status.json",
            ):
                (root / "bundle" / "intake" / name).write_text("{}\n", encoding="utf-8")
            for name in (
                "metrics_long.csv",
                "regulatory_matrix.csv",
                "selection_rates.csv",
            ):
                (root / "bundle" / "intake" / name).write_text(
                    "header\n", encoding="utf-8"
                )
            for name in (
                "hyperparameter_tuning_certificate_amplification.json",
                "hyperparameter_tuning_certificate_intrinsic.json",
                "model_certificate_amplification.json",
                "model_certificate_intrinsic.json",
                "synthetic_quality_certificate.json",
            ):
                (root / "bundle" / "certificates" / name).write_text(
                    "{}\n", encoding="utf-8"
                )
            (root / "bundle" / "config" / "sap.yaml").write_text(
                "version: 1\n", encoding="utf-8"
            )
            (root / "intake" / "archive" / "legacy.txt").write_text(
                "preserve\n", encoding="utf-8"
            )
            repo_owned = (
                "calibration_bins_TEMPLATE.csv",
                "confusion_by_group_TEMPLATE.csv",
                "governance_contacts.csv",
                "licenses_inventory.csv",
                "privacy_audit_checklist.md",
            )
            for name in repo_owned:
                (root / "intake" / name).write_text("preserve\n", encoding="utf-8")
            (root / "intake" / "model_hyperparams.yaml").write_text(
                (WORKFLOW.parents[2] / "intake" / "model_hyperparams.yaml").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            (root / "intake" / "air_status.json").write_text(
                '{"stale": true}\n', encoding="utf-8"
            )
            (root / "intake" / "stale.json").write_text("{}\n", encoding="utf-8")
            (root / "intake" / "certificates" / "stale.json").write_text(
                "{}\n", encoding="utf-8"
            )
            (root / "config" / "stale.yaml").write_text(
                "stale: true\n", encoding="utf-8"
            )

            env = {
                **os.environ,
                "RUNNER_TEMP": str(runner_temp),
                "GITHUB_REPOSITORY": "equilens-labs/fl-bsa-whitepaper",
                "GITHUB_SHA": "b" * 40,
                "GITHUB_REF": "refs/heads/main",
                "GITHUB_WORKFLOW": "pull-wp-intake",
                "SELECTED_BUNDLE_SHA256": "c" * 64,
                "SELECTED_BUNDLE_FILENAME": "WhitePaper_Intake_Bundle_v4.zip",
                "SELECTED_PRODUCER_REPO": "equilens-labs/fl-bsa",
                "SELECTED_PRODUCER_WORKFLOW": "release-evidence.yml",
                "SELECTED_PRODUCER_ARTIFACT": "wp-intake-bundle-v4-1",
                "SELECTED_PRODUCER_ARTIFACT_ID": "456",
                "SELECTED_PRODUCER_ARTIFACT_DIGEST": "sha256:" + "d" * 64,
                "SELECTED_PRODUCER_CONTRACT_SHA256": "e" * 64,
                "SELECTED_PRODUCER_BRANCH": "main",
                "SELECTED_PRODUCER_RUN_ID": "123",
                "SELECTED_PRODUCER_RUN_ATTEMPT": "1",
                "SELECTED_PRODUCER_HEAD_SHA": product_sha,
            }
            completed = subprocess.run(
                ["bash", "-c", step["run"]],
                cwd=root,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)

            self.assertTrue((root / "intake" / "archive" / "legacy.txt").is_file())
            for name in repo_owned + ("model_hyperparams.yaml",):
                self.assertTrue((root / "intake" / name).is_file())
            self.assertEqual("{}\n", (root / "intake" / "air_status.json").read_text())
            self.assertFalse((root / "intake" / "stale.json").exists())
            self.assertFalse((root / "intake" / "certificates" / "stale.json").exists())
            self.assertFalse((root / "config" / "stale.yaml").exists())
            stamped = json.loads((root / "intake" / "manifest.json").read_text())
            self.assertEqual(
                product_sha, stamped["whitepaper_consumer"]["producer"]["head_sha"]
            )

            generated = subprocess.run(
                [
                    "python3",
                    str(
                        WORKFLOW.parents[2]
                        / "scripts"
                        / "gen_tex_hyperparams_from_yaml.py"
                    ),
                    "--config",
                    str(root / "intake" / "model_hyperparams.yaml"),
                    "--outdir",
                    str(root / "includes"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, generated.returncode, generated.stderr)
