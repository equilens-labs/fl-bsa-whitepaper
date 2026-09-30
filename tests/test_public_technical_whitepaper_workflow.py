import subprocess
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build-public-technical-whitepaper.yml"


class PublicTechnicalWhitepaperWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.workflow = yaml.safe_load(self.text)

    def test_is_manual_main_only_read_only_build(self) -> None:
        trigger = self.workflow.get(True, self.workflow.get("on"))
        self.assertEqual({"workflow_dispatch"}, set(trigger))
        self.assertEqual({"contents": "read"}, self.workflow["permissions"])
        job = self.workflow["jobs"]["build"]
        self.assertEqual("ubuntu-24.04", job["runs-on"])
        condition = job["if"]
        self.assertIn("github.ref == 'refs/heads/main'", condition)
        self.assertIn("inputs.release_tag == 'v5.0.8'", condition)
        for forbidden in (
            "contents: write",
            "pull_request:",
            "push:",
            "schedule:",
            "repository_dispatch:",
            "gh release create",
            "git push",
        ):
            self.assertNotIn(forbidden, self.text)

    def test_binds_exact_product_and_retained_attempt_sources(self) -> None:
        required = (
            "a853b62b42005477250c08edfe9f1e18f2e2cb50",
            "36152873675/attempts/1",
            "actions/artifacts/10872328152",
            "actions/artifacts/10873891925",
            "technical/releases/v5.0.8.source-lock.json",
            "scripts/verify_technical_producer_state.py",
            "--current-run-after",
            "scripts/technical_source_lock.py",
            "/flbsa/__init__.py",
            "/flbsa/crypto",
            "--intake-actions-archive",
            "--robustness-actions-archive",
            "scripts/extract_actions_artifact.py",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.text)
        self.assertNotIn("latest", self.text.lower())

    def test_product_source_checkout_is_exact_and_minimal(self) -> None:
        steps = self.workflow["jobs"]["build"]["steps"]
        checkout = next(
            step
            for step in steps
            if step.get("name") == "Check out reviewed product source record"
        )
        self.assertEqual(
            "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
            checkout["uses"],
        )
        options = checkout["with"]
        self.assertEqual("equilens-labs/fl-bsa", options["repository"])
        self.assertEqual("a853b62b42005477250c08edfe9f1e18f2e2cb50", options["ref"])
        self.assertEqual("${{ secrets.PRODUCER_TOKEN }}", options["token"])
        self.assertEqual("product-source", options["path"])
        self.assertFalse(options["persist-credentials"])
        self.assertFalse(options["sparse-checkout-cone-mode"])
        self.assertEqual(
            [
                "/config/public-technical-whitepaper-build-sources.v1.json",
                "/tools/ci",
                "/flbsa/__init__.py",
                "/flbsa/crypto",
            ],
            options["sparse-checkout"].splitlines(),
        )

    def test_builds_and_checks_the_complete_exact_review_set(self) -> None:
        required = (
            "public_technical_whitepaper.py prepare",
            "public_technical_whitepaper.py companion",
            "make technical-assets",
            "verify_public_technical_companion.py",
            "root_file: technical/main.tex",
            "check_release_layout.py main.log --pdf main.pdf",
            "check_release_pdf_passive.py main.pdf",
            "--expected-header-cells 47",
            "--expected-figures 1",
            "verify_public_technical_pdf.py",
            "verify_verapdf_ua_preflight.py",
            "public_technical_whitepaper.py finalize",
            "SHA256SUMS.txt",
            "fl-bsa-v5.0.8-technical-companion.zip",
            "whitepaper.pdf",
            "whitepaper_release.json",
            "name: public-technical-whitepaper-v5.0.8-${{ github.run_attempt }}",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.text)

    def test_third_party_actions_and_images_are_digest_pinned(self) -> None:
        for step in self.workflow["jobs"]["build"]["steps"]:
            action = step.get("uses")
            if action:
                self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")
        self.assertIn(
            "ghcr.io/xu-cheng/texlive-full@sha256:"
            "d9bfb267e3e3f5e0820ca86e867ee59ebb133fc29561bb28677d9b5a1a9e84ff",
            self.text,
        )

    def test_local_technical_target_uses_one_fresh_render_path(self) -> None:
        completed = subprocess.run(
            ["make", "--dry-run", "technical-pdf"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        commands = "\n".join(
            " ".join(line.split())
            for line in completed.stdout.replace("\\\n\t", " ").splitlines()
        )
        render_pdf = "build/technical/v5.0.8/render/whitepaper.pdf"
        render_log = "build/technical/v5.0.8/render/whitepaper.log"
        self.assertIn(
            "ghcr.io/xu-cheng/texlive-full@sha256:"
            "d9bfb267e3e3f5e0820ca86e867ee59ebb133fc29561bb28677d9b5a1a9e84ff",
            commands,
        )
        self.assertIn("latexmk -C -outdir=build/technical/v5.0.8/render", commands)
        self.assertIn(f"test ! -e {render_pdf}", commands)
        self.assertIn(f"test -s {render_pdf}", commands)
        self.assertIn(f"test -s {render_log}", commands)
        for validator in (
            "canonicalize_release_pdf.py",
            "check_release_pdf_passive.py",
            "check_pdf_tag_structure.py",
            "verify_public_technical_pdf.py",
        ):
            with self.subTest(validator=validator):
                matching = [line for line in commands.splitlines() if validator in line]
                self.assertEqual(1, len(matching))
                self.assertIn(render_pdf, matching[0])
        self.assertIn(
            f"check_release_layout.py {render_log} --pdf {render_pdf}", commands
        )
        self.assertIn(f"cp {render_pdf} dist/technical/v5.0.8/whitepaper.pdf", commands)
        self.assertIn(
            "docker.io/verapdf/cli@sha256:"
            "e1c674f6dd0ee08418cfa525f6f47040377236432d55d67f747b2bc9c55e7d66",
            self.text,
        )


if __name__ == "__main__":
    unittest.main()
