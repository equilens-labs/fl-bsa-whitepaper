import re
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pull-wp-intake.yml"


class PullWpIntakeContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def assert_contract(self, workflow: str) -> None:
        self.assertIn(
            'branch="chore/wp-intake-${short_sha}-${SELECTED_PRODUCER_RUN_ID:-${GITHUB_RUN_ID}}"',
            workflow,
        )
        self.assertIn("git status --short -- intake config includes figures", workflow)
        self.assertIn("git add intake config includes figures", workflow)
        self.assertIn('git push --force-with-lease origin "$branch"', workflow)

        self.assertIn(
            'permission_guard="GitHub Actions is not permitted to create or approve pull requests"',
            workflow,
        )
        self.assertIn('soft_fail_sentinel="${soft_fail_dir}/intake_pr_soft_fail.json"', workflow)
        self.assertIn("record_pr_permission_soft_fail()", workflow)
        self.assertIn(">> \"$GITHUB_STEP_SUMMARY\"", workflow)
        self.assertRegex(workflow, r"name:\s+intake-pr-soft-fail")
        self.assertRegex(
            workflow,
            r"path:\s+dist/intake-pr-soft-fail/intake_pr_soft_fail\.json",
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

        self.assertNotRegex(
            workflow,
            r"gh pr (?:create|edit).*?then\s+(?:.|\n){0,160}?exit 0",
            "PR create/edit failures must not unconditionally exit 0",
        )

    def test_pull_wp_intake_preserves_branch_artifact_contract(self) -> None:
        self.assert_contract(self.workflow)

    def test_rejects_missing_required_audit_anchors(self) -> None:
        required_fragments = (
            'branch="chore/wp-intake-${short_sha}-${SELECTED_PRODUCER_RUN_ID:-${GITHUB_RUN_ID}}"',
            "git status --short -- intake config includes figures",
            "git add intake config includes figures",
            'git push --force-with-lease origin "$branch"',
            'permission_guard="GitHub Actions is not permitted to create or approve pull requests"',
            'soft_fail_sentinel="${soft_fail_dir}/intake_pr_soft_fail.json"',
            "record_pr_permission_soft_fail()",
            '            } >> "$GITHUB_STEP_SUMMARY"',
            "name: intake-pr-soft-fail",
            "path: dist/intake-pr-soft-fail/intake_pr_soft_fail.json",
        )

        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.workflow)
                mutated = self.workflow.replace(fragment, "", 1)
                with self.assertRaises(AssertionError):
                    self.assert_contract(mutated)

    def test_rejects_unconditional_create_soft_success(self) -> None:
        mutated = self.workflow.replace(
            'record_pr_permission_soft_fail "creation" "$branch" "$pr_output"\n'
            "              exit $?",
            'echo "$pr_output"\n              exit 0',
        )
        with self.assertRaises(AssertionError):
            self.assert_contract(mutated)

    def test_rejects_unconditional_update_soft_success(self) -> None:
        mutated = self.workflow.replace(
            'record_pr_permission_soft_fail "update" "$branch" "$pr_output"\n'
            "              exit $?",
            'echo "$pr_output"\n              exit 0',
        )
        with self.assertRaises(AssertionError):
            self.assert_contract(mutated)

    def test_rejects_missing_summary_visibility(self) -> None:
        mutated = self.workflow.replace('            } >> "$GITHUB_STEP_SUMMARY"', "            }")
        with self.assertRaises(AssertionError):
            self.assert_contract(mutated)


if __name__ == "__main__":
    unittest.main()
