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
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "pull-wp-intake.yml"
)


class PullWpIntakeContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def assert_contract(self, workflow: str) -> None:
        required = (
            "group: pull-wp-intake-persistence",
            "cancel-in-progress: false",
            "queue: max",
            "python scripts/intake_anchor.py snapshot",
            "python scripts/validate_public_intake.py",
            "test -f bundle/intake/pack_intent.json",
            "--pack-intent bundle/intake/pack_intent.json",
            '--producer-head-sha "$SELECTED_PRODUCER_HEAD_SHA"',
            '--producer-run-attempt "$SELECTED_PRODUCER_RUN_ATTEMPT"',
            '--producer-artifact-id "$SELECTED_PRODUCER_ARTIFACT_ID"',
            '--producer-artifact-digest "$SELECTED_PRODUCER_ARTIFACT_DIGEST"',
            "--output intake/whitepaper_snapshot.json",
            'if [[ ! "$run_id" =~ ^[1-9][0-9]*$ ]]; then',
            'gh api "repos/${PRODUCER_REPO}/actions/runs/${run_id}"',
            "for ((attempt=1; attempt<=81; attempt++)); do",
            'if [ "$run_status" = "completed" ]; then',
            'if [ "$run_conclusion" != "success" ]; then',
            "did not complete successfully within the 20-minute bounded wait",
            '((.path // "") | split("@")[0]) == $workflow_path',
            '.head_branch == $branch',
            '.head_repository.full_name == $producer_repo',
            'wp-evidence-nightly.yml:schedule|wp-evidence-nightly.yml:workflow_dispatch|release-evidence.yml:workflow_dispatch',
            'gh api "repos/${PRODUCER_REPO}/git/ref/tags/${release_tag}"',
            'gh api "repos/${PRODUCER_REPO}/git/tags/${release_tag_sha}"',
            'run_attempt="$(jq -r \'.run_attempt | tostring\' <<<"$run_json")"',
            'wp-intake-bundle-v4-${run_attempt}',
            'artifact_match_count="$(jq --arg name "$PRODUCER_ARTIFACT"',
            'gh api "repos/${PRODUCER_REPO}/actions/artifacts/${artifact_id}/zip"',
            'downloaded_digest="sha256:$(sha256sum "$artifact_archive"',
            '[[ "$artifact_created_at" < "$run_started_at" ]]',
            'product_sha != expected_head_sha',
            "Stage and replace managed intake/config surfaces",
            "repo_owned_intake=(",
            "producer_managed_intake=(",
            "producer bundle contains non-public/unreviewed members",
            "names redacted",
            'sync_stage="$(mktemp -d "${RUNNER_TEMP}/wp-intake-sync.XXXXXX")"',
            'cp -a intake/archive/. "$sync_stage/intake/archive/"',
            "rm -rf intake config",
            'mv "$sync_stage/intake" intake',
            'mv "$sync_stage/config" config',
            'plot_stage="$(mktemp -d "${RUNNER_TEMP}/wp-figures.XXXXXX")"',
            "--require-all",
            'branch="$INTAKE_SNAPSHOT_BRANCH"',
            'mode="$INTAKE_SNAPSHOT_MODE"',
            "git add intake config includes figures",
            'snapshot_tree="$(git write-tree)"',
            'git ls-remote --exit-code --heads origin "refs/heads/${branch}"',
            'parent_args=(-p "$GITHUB_SHA")',
            'parent_args+=(-p "$remote_head")',
            'git commit-tree "$snapshot_tree" "${parent_args[@]}" -F "$commit_message"',
            'git push origin "$anchor_commit:refs/heads/$branch"',
            "already exists with a different tree; refusing nondeterministic identity drift",
            'if [ "$mode" = "workflow_write_once_release_snapshot" ] && [ -n "$remote_head" ]; then',
            "already exists with different content; refusing to rewrite it",
            'if [ "$mode" = "rolling_history" ]; then',
            "Routine nightly snapshot retained in append-only history",
            'permission_guard="GitHub Actions is not permitted to create or approve pull requests"',
            'soft_fail_sentinel="${soft_fail_dir}/intake_pr_soft_fail.json"',
            "record_pr_permission_soft_fail()",
            '>> "$GITHUB_STEP_SUMMARY"',
            "name: intake-pr-soft-fail-${{ github.run_attempt }}",
            "path: dist/intake-pr-soft-fail/intake_pr_soft_fail.json",
        )
        for fragment in required:
            self.assertIn(fragment, workflow)

        self.assertNotIn("--force", workflow)
        self.assertNotIn("name: intake-bundle-used", workflow)
        self.assertNotIn("wp-bundle/**/WhitePaper_Intake_Bundle_v4.zip", workflow)
        self.assertLess(
            workflow.index('if [ "$mode" = "rolling_history" ]; then'),
            workflow.index('if gh pr view "$branch"'),
        )

        guard = re.search(
            r"record_pr_permission_soft_fail\(\).*?if ! printf '%s\\n' \"\$pr_output\" "
            r"\| grep -Fq \"\$permission_guard\"; then.*?return 1.*?fi",
            workflow,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(guard, "non-permission PR failures must hard-fail")

        for operation in ("update", "creation"):
            self.assertIn(
                f'record_pr_permission_soft_fail "{operation}" "$branch" "$pr_output"\n'
                "              exit $?",
                workflow,
            )

    def test_pull_wp_intake_preserves_append_only_contract(self) -> None:
        self.assert_contract(self.workflow)

    def test_public_snapshot_persistence_is_explicit_and_defaults_off(self) -> None:
        workflow = yaml.safe_load(self.workflow)
        self.assertEqual("read", workflow["permissions"]["contents"])
        self.assertEqual("read", workflow["permissions"]["pull-requests"])
        steps = workflow["jobs"]["fetch-build"]["steps"]
        checkout = next(item for item in steps if str(item.get("uses", "")).startswith("actions/checkout@"))
        self.assertIs(checkout["with"]["persist-credentials"], False)
        persist = next(item for item in steps if item.get("name") == "Persist intake snapshot")

        expression = persist["env"]["PERSIST_INTAKE_SNAPSHOT"]
        self.assertEqual(
            "${{ github.event_name == 'repository_dispatch' && "
            "format('{0}', github.event.client_payload.persist_intake_pr) || 'false' }}",
            expression,
        )
        self.assertNotIn("|| 'true'", expression)
        self.assertIn(
            'Skipping intake snapshot persistence because persist_intake_pr=${PERSIST_INTAKE_SNAPSHOT}.',
            persist["run"],
        )
        guard = persist["run"].split(
            'if [ -z "${WP_INTAKE_PR_TOKEN:-}" ]; then', 1
        )[0]
        probe = guard + "\nprintf 'persistence-enabled\\n'\n"

        disabled = subprocess.run(
            ["bash", "-c", probe],
            env={**os.environ, "PERSIST_INTAKE_SNAPSHOT": "false"},
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, disabled.returncode, disabled.stderr)
        self.assertNotIn("persistence-enabled", disabled.stdout)

        enabled = subprocess.run(
            ["bash", "-c", probe],
            env={**os.environ, "PERSIST_INTAKE_SNAPSHOT": "true"},
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, enabled.returncode, enabled.stderr)
        self.assertIn("persistence-enabled", enabled.stdout)

        for malformed in ("", "0", "no", "1", "yes", "tru", " false ", "random"):
            with self.subTest(malformed=malformed):
                rejected = subprocess.run(
                    ["bash", "-c", probe],
                    env={**os.environ, "PERSIST_INTAKE_SNAPSHOT": malformed},
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(0, rejected.returncode)
                self.assertIn("expected literal true or false", rejected.stderr)

        self.assertNotIn("GH_TOKEN", persist["env"])
        self.assertEqual(
            "${{ secrets.WP_INTAKE_PR_TOKEN }}",
            persist["env"]["WP_INTAKE_PR_TOKEN"],
        )
        self.assertIn("Explicit public intake persistence requires WP_INTAKE_PR_TOKEN", persist["run"])
        self.assertIn('export GH_TOKEN="$WP_INTAKE_PR_TOKEN"', persist["run"])
        self.assertIn("gh auth setup-git", persist["run"])
        self.assertIn("git remote get-url --all origin", persist["run"])
        self.assertIn("git remote get-url --push --all origin", persist["run"])
        self.assertIn('canonical_origin="https://github.com/${GITHUB_REPOSITORY}"', persist["run"])
        self.assertIn('"${#origin_fetch_urls[@]}" -ne 1', persist["run"])
        self.assertIn('"${#origin_push_urls[@]}" -ne 1', persist["run"])
        self.assertIn('fetch_url="${origin_fetch_urls[0]}"', persist["run"])
        self.assertIn('push_url="${origin_push_urls[0]}"', persist["run"])
        self.assertNotIn("https://github.com/*", persist["run"])
        self.assertNotIn("git@github.com:*", persist["run"])
        self.assertIn('if [ "${GITHUB_ACTIONS:-}" = "true" ]; then', persist["run"])
        self.assertIn("unexpected Actions fetch origin", persist["run"])
        self.assertIn("unexpected Actions push origin", persist["run"])
        self.assertLess(
            persist["run"].index("gh auth setup-git"),
            persist["run"].index('git push origin "$anchor_commit:refs/heads/$branch"'),
        )

    def test_public_persistence_rejects_unexpected_actions_origin_before_mutation(self) -> None:
        workflow = yaml.safe_load(self.workflow)
        persist = next(
            item
            for item in workflow["jobs"]["fetch-build"]["steps"]
            if item.get("name") == "Persist intake snapshot"
        )["run"]

        canonical = "https://github.com/equilens-labs/fl-bsa-whitepaper.git"
        different = "https://github.com/equilens-labs/not-fl-bsa-whitepaper.git"
        ssh = "git@github.com:equilens-labs/fl-bsa-whitepaper.git"
        unexpected_origins = (
            ("local", (), ()),
            (different, (), ()),
            (ssh, (), ()),
            (canonical, (different,), ()),
            (canonical, (ssh,), ()),
            (canonical, (canonical, different), ()),
            (
                canonical,
                (),
                ((f"url.{different}.pushInsteadOf", canonical),),
            ),
            (
                canonical,
                (),
                ((f"url.{different}.insteadOf", canonical),),
            ),
        )
        for fetch_origin, push_origins, url_rewrites in unexpected_origins:
            with self.subTest(
                fetch_origin=fetch_origin,
                push_origins=push_origins,
                url_rewrites=url_rewrites,
            ), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                work = root / "work"
                subprocess.run(["git", "init", "-b", "main", str(work)], check=True)
                origin = fetch_origin
                if origin == "local":
                    remote = root / "remote.git"
                    subprocess.run(["git", "init", "--bare", str(remote)], check=True)
                    origin = str(remote)
                subprocess.run(
                    ["git", "-C", str(work), "remote", "add", "origin", origin],
                    check=True,
                )
                for push_origin in push_origins:
                    subprocess.run(
                        [
                            "git",
                            "-C",
                            str(work),
                            "config",
                            "--add",
                            "remote.origin.pushurl",
                            push_origin,
                        ],
                        check=True,
                    )
                for key, value in url_rewrites:
                    subprocess.run(
                        ["git", "-C", str(work), "config", "--add", key, value],
                        check=True,
                    )

                completed = subprocess.run(
                    ["bash", "-c", persist],
                    cwd=work,
                    env={
                        **os.environ,
                        "GIT_CONFIG_GLOBAL": "/dev/null",
                        "GIT_CONFIG_SYSTEM": "/dev/null",
                        "GITHUB_ACTIONS": "true",
                        "GITHUB_REPOSITORY": "equilens-labs/fl-bsa-whitepaper",
                        "PERSIST_INTAKE_SNAPSHOT": "true",
                        "WP_INTAKE_PR_TOKEN": "unused-test-token",
                    },
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(0, completed.returncode)
                self.assertIn("Refusing public persistence", completed.stderr)
                local_refs = subprocess.check_output(
                    ["git", "-C", str(work), "for-each-ref", "--format=%(refname)"],
                    text=True,
                )
                self.assertEqual("", local_refs)

    def test_public_persistence_accepts_only_canonical_https_origins(self) -> None:
        workflow = yaml.safe_load(self.workflow)
        persist = next(
            item
            for item in workflow["jobs"]["fetch-build"]["steps"]
            if item.get("name") == "Persist intake snapshot"
        )["run"]
        guard = persist.split('branch="$INTAKE_SNAPSHOT_BRANCH"', 1)[0]
        probe = guard + "\nprintf 'origin-approved\\n'\n"

        for suffix in ("", ".git"):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                work = root / "work"
                fake_bin = root / "bin"
                fake_bin.mkdir()
                fake_gh = fake_bin / "gh"
                fake_gh.write_text(
                    '#!/bin/sh\n[ "$1 $2" = "auth setup-git" ]\n',
                    encoding="utf-8",
                )
                fake_gh.chmod(0o755)
                subprocess.run(["git", "init", "-b", "main", str(work)], check=True)
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(work),
                        "remote",
                        "add",
                        "origin",
                        f"https://github.com/equilens-labs/fl-bsa-whitepaper{suffix}",
                    ],
                    check=True,
                )

                completed = subprocess.run(
                    ["bash", "-c", probe],
                    cwd=work,
                    env={
                        **os.environ,
                        "GIT_CONFIG_GLOBAL": "/dev/null",
                        "GIT_CONFIG_SYSTEM": "/dev/null",
                        "GITHUB_ACTIONS": "true",
                        "GITHUB_REPOSITORY": "equilens-labs/fl-bsa-whitepaper",
                        "PATH": f"{fake_bin}:{os.environ['PATH']}",
                        "PERSIST_INTAKE_SNAPSHOT": "true",
                        "WP_INTAKE_PR_TOKEN": "unused-test-token",
                    },
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertIn("origin-approved", completed.stdout)

    def test_required_anchors_are_mutation_sensitive(self) -> None:
        required_fragments = (
            "group: pull-wp-intake-persistence",
            "queue: max",
            "python scripts/intake_anchor.py snapshot",
            "python scripts/validate_public_intake.py",
            'gh api "repos/${PRODUCER_REPO}/actions/runs/${run_id}"',
            "Stage and replace managed intake/config surfaces",
            "producer bundle contains non-public/unreviewed members",
            '.head_repository.full_name == $producer_repo',
            'gh api "repos/${PRODUCER_REPO}/actions/artifacts/${artifact_id}/zip"',
            'downloaded_digest="sha256:$(sha256sum "$artifact_archive"',
            "rm -rf intake config",
            'snapshot_tree="$(git write-tree)"',
            'parent_args+=(-p "$remote_head")',
            'git push origin "$anchor_commit:refs/heads/$branch"',
            "already exists with a different tree; refusing nondeterministic identity drift",
            "already exists with different content; refusing to rewrite it",
            "record_pr_permission_soft_fail()",
            "name: intake-pr-soft-fail-${{ github.run_attempt }}",
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                mutated = self.workflow.replace(fragment, "", 1)
                with self.assertRaises(AssertionError):
                    self.assert_contract(mutated)

    def test_consumer_stamp_is_deterministic(self) -> None:
        sync = self.workflow.split(
            "- name: Stage and replace managed intake/config surfaces", 1
        )[1].split("- name: Write deterministic intake snapshot record", 1)[0]

        self.assertIn('"schema_version": "flbsa.whitepaper_consumer.v3"', sync)
        self.assertIn('"base_commit": os.environ["GITHUB_SHA"]', sync)
        self.assertNotIn("datetime", sync)
        self.assertNotIn("ingested_at", sync)
        self.assertNotIn("GITHUB_RUN_ATTEMPT", sync)
        self.assertIn('"head_sha": os.environ.get("SELECTED_PRODUCER_HEAD_SHA", "")', sync)
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
        self.assertIn('"repo": os.environ.get("SELECTED_PRODUCER_REPO", "")', sync)
        self.assertNotIn('os.environ.get("PRODUCER_REPO"', sync)

    def test_producer_run_metadata_is_verified_before_stamping(self) -> None:
        download = self.workflow.split("- name: Download intake bundle from producer", 1)[
            1
        ].split("- name: Unpack intake bundle", 1)[0]
        schema = self.workflow.split("- name: Validate bundle schema versions", 1)[
            1
        ].split("- name: Stage and replace managed intake/config surfaces", 1)[0]

        self.assertIn('if [[ ! "$run_id" =~ ^[1-9][0-9]*$ ]]; then', download)
        self.assertIn("for ((attempt=1; attempt<=81; attempt++)); do", download)
        self.assertIn('run_status="$(jq -r \'.status\' <<<"$run_json")"', download)
        self.assertIn('run_conclusion="$(jq -r \'.conclusion // ""\' <<<"$run_json")"', download)
        self.assertIn('if [ "$run_status" = "completed" ]; then', download)
        self.assertIn('if [ "$run_conclusion" != "success" ]; then', download)
        self.assertIn("sleep 15", download)
        self.assertIn('((.path // "") | split("@")[0]) == $workflow_path', download)
        self.assertIn('.head_branch == $branch', download)
        self.assertIn('.head_repository.full_name == $producer_repo', download)
        self.assertIn('run_event="$(jq -r \'.event // ""\' <<<"$run_json")"', download)
        self.assertIn('wp-intake-bundle-v4-${run_attempt}', download)
        self.assertIn('[[ "$artifact_created_at" < "$run_started_at" ]]', download)
        self.assertIn('actions/artifacts/${artifact_id}/zip', download)
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

    def test_managed_surfaces_are_replaced_and_archive_is_preserved(self) -> None:
        sync = self.workflow.split(
            "- name: Stage and replace managed intake/config surfaces", 1
        )[1].split("- name: Write deterministic intake snapshot record", 1)[0]

        archive_copy = 'cp -a intake/archive/. "$sync_stage/intake/archive/"'
        removal = "rm -rf intake config"
        self.assertIn(archive_copy, sync)
        self.assertIn(removal, sync)
        self.assertLess(sync.index(archive_copy), sync.index(removal))
        self.assertLess(sync.index(removal), sync.index('mv "$sync_stage/intake" intake'))
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

    def test_raw_bundle_privacy_and_metadata_are_rejected_and_not_uploaded(self) -> None:
        workflow = yaml.safe_load(self.workflow)
        steps = workflow["jobs"]["fetch-build"]["steps"]
        unpack = next(item for item in steps if item.get("name") == "Unpack intake bundle")
        match = re.search(
            r'export BUNDLE_PATH="\$bundle_path"\npython - <<\'PY\'\n(.*?)\nPY',
            unpack["run"],
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        validator = match.group(1)

        required = {
            "intake/metrics_uncertainty.json": b"{}\n",
            "intake/pack_intent.json": b"{}\n",
            "provenance/manifest.json": b"{}\n",
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
            for name in ("metrics_uncertainty.json", "pack_intent.json", "air_status.json"):
                (root / "bundle" / "intake" / name).write_text("{}\n", encoding="utf-8")
            (root / "bundle" / "certificates" / "synthetic_quality_certificate.json").write_text(
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
            (root / "config" / "stale.yaml").write_text("stale: true\n", encoding="utf-8")

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
                "SELECTED_PRODUCER_WORKFLOW": "wp-evidence-nightly.yml",
                "SELECTED_PRODUCER_ARTIFACT": "wp-intake-bundle-v4",
                "SELECTED_PRODUCER_ARTIFACT_ID": "456",
                "SELECTED_PRODUCER_ARTIFACT_DIGEST": "sha256:" + "d" * 64,
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
                    str(WORKFLOW.parents[2] / "scripts" / "gen_tex_hyperparams_from_yaml.py"),
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

    def test_same_snapshot_identity_with_different_tree_fails_in_all_modes(self) -> None:
        workflow = yaml.safe_load(self.workflow)
        persist = next(
            item
            for item in workflow["jobs"]["fetch-build"]["steps"]
            if item.get("name") == "Persist intake snapshot"
        )["run"]

        for mode, branch in (
            ("rolling_history", "chore/wp-intake-nightly"),
            ("workflow_write_once_release_snapshot", "chore/wp-intake-release-123"),
        ):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                remote = root / "remote.git"
                work = root / "work"
                subprocess.run(["git", "init", "--bare", str(remote)], check=True)
                subprocess.run(["git", "init", "-b", "main", str(work)], check=True)
                subprocess.run(["git", "-C", str(work), "config", "user.name", "Test"], check=True)
                subprocess.run(
                    ["git", "-C", str(work), "config", "user.email", "test@example.invalid"],
                    check=True,
                )
                for directory in ("intake", "config", "includes", "figures"):
                    (work / directory).mkdir()
                snapshot_id = "snapshot-identity"
                snapshot = {
                    "snapshot_id": snapshot_id,
                    "producer": {"product_sha": "a" * 40},
                }
                (work / "intake" / "whitepaper_snapshot.json").write_text(
                    json.dumps(snapshot) + "\n", encoding="utf-8"
                )
                (work / "config" / "sap.yaml").write_text("version: 1\n", encoding="utf-8")
                (work / "includes" / "generated.tex").write_text("old\n", encoding="utf-8")
                (work / "figures" / "generated.txt").write_text("same\n", encoding="utf-8")
                subprocess.run(["git", "-C", str(work), "add", "."], check=True)
                subprocess.run(["git", "-C", str(work), "commit", "-m", "base"], check=True)
                base_sha = subprocess.check_output(
                    ["git", "-C", str(work), "rev-parse", "HEAD"], text=True
                ).strip()
                subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(remote)], check=True)
                subprocess.run(
                    ["git", "-C", str(work), "push", "origin", f"HEAD:refs/heads/{branch}"],
                    check=True,
                )
                (work / "includes" / "generated.tex").write_text("drift\n", encoding="utf-8")

                env = {
                    **os.environ,
                    "GITHUB_SHA": base_sha,
                    "GITHUB_REF_NAME": "main",
                    "GITHUB_REPOSITORY": "equilens-labs/fl-bsa-whitepaper",
                    "GITHUB_RUN_ID": "999",
                    "SELECTED_PRODUCER_REPO": "equilens-labs/fl-bsa",
                    "SELECTED_PRODUCER_WORKFLOW": "wp-evidence-nightly.yml",
                    "SELECTED_PRODUCER_BRANCH": "main",
                    "SELECTED_PRODUCER_RUN_ID": "123",
                    "SELECTED_PRODUCER_RUN_ATTEMPT": "1",
                    "SELECTED_PRODUCER_HEAD_SHA": "a" * 40,
                    "SELECTED_PRODUCER_ARTIFACT": "wp-intake-bundle-v4",
                    "SELECTED_PRODUCER_ARTIFACT_ID": "456",
                    "SELECTED_PRODUCER_ARTIFACT_DIGEST": "sha256:" + "d" * 64,
                    "SELECTED_BUNDLE_SHA256": "b" * 64,
                    "INTAKE_SNAPSHOT_BRANCH": branch,
                    "INTAKE_SNAPSHOT_MODE": mode,
                    "INTAKE_SNAPSHOT_ID": snapshot_id,
                    "PERSIST_INTAKE_SNAPSHOT": "true",
                    "GITHUB_ACTIONS": "false",
                    "GH_TOKEN": "unused",
                    "WP_INTAKE_PR_TOKEN": "unused-test-token",
                }
                completed = subprocess.run(
                    ["bash", "-c", persist],
                    cwd=work,
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(0, completed.returncode)
                self.assertIn("different tree", completed.stderr)
                remote_head = subprocess.check_output(
                    ["git", "--git-dir", str(remote), "rev-parse", branch], text=True
                ).strip()
                self.assertEqual(base_sha, remote_head)

    def test_rejects_unconditional_pr_soft_success(self) -> None:
        for operation in ("creation", "update"):
            with self.subTest(operation=operation):
                original = (
                    f'record_pr_permission_soft_fail "{operation}" "$branch" "$pr_output"\n'
                    "              exit $?"
                )
                mutated = self.workflow.replace(
                    original, 'echo "$pr_output"\n              exit 0'
                )
                with self.assertRaises(AssertionError):
                    self.assert_contract(mutated)


if __name__ == "__main__":
    unittest.main()
