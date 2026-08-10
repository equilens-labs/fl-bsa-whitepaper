import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import lint_release_claims as claims_lint  # noqa: E402


class ReleaseClaimsLintTests(unittest.TestCase):
    def test_current_release_sections_encode_all_nine_corrections(self) -> None:
        claims_lint.lint_release_claims(ROOT / "release" / "sections")

    def test_each_correction_is_mutation_sensitive(self) -> None:
        source = ROOT / "release" / "sections"
        for correction_id, (
            section_name,
            fragments,
        ) in claims_lint.CORRECTION_RULES.items():
            with (
                self.subTest(correction_id=correction_id),
                tempfile.TemporaryDirectory() as tmp,
            ):
                target = Path(tmp) / "sections"
                shutil.copytree(source, target)
                fragment = fragments[0]
                path = target / section_name
                text = path.read_text(encoding="utf-8")
                self.assertGreaterEqual(text.count(fragment), 1, fragment)
                path.write_text(text.replace(fragment, "removed"), encoding="utf-8")
                with self.assertRaisesRegex(
                    claims_lint.ReleaseClaimsLintError, correction_id
                ):
                    claims_lint.lint_release_claims(target)

    def test_each_correction_is_bound_to_its_owner_section(self) -> None:
        source = ROOT / "release" / "sections"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sections"
            shutil.copytree(source, target)
            section_name, _ = claims_lint.CORRECTION_RULES["integrity-language"]
            path = target / section_name
            path.unlink()
            with self.assertRaisesRegex(
                claims_lint.ReleaseClaimsLintError, "lost its owner section"
            ):
                claims_lint.lint_release_claims(target)

    def test_forbidden_claims_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sections"
            shutil.copytree(ROOT / "release" / "sections", target)
            path = target / "10_limitations_monitoring.tex"
            path.write_text(
                path.read_text(encoding="utf-8")
                + "\npotential disparate-impact finding\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                claims_lint.ReleaseClaimsLintError, "forbidden release claim"
            ):
                claims_lint.lint_release_claims(target)


if __name__ == "__main__":
    unittest.main()
