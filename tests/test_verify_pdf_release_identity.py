import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_pdf_release_identity",
    ROOT / "scripts" / "verify_pdf_release_identity.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)

PRODUCT_SHA = "cc32b3a8d13cb75419b0dec1d4b9bdf5a3eb90c2"
WHITEPAPER_SHA = "248dab12d41073f183236eb2062a9369beb85066"
EVIDENCE_RUN_ID = "30765888408"


class VerifyPdfReleaseIdentityTests(unittest.TestCase):
    def valid_text(self) -> str:
        return "\n".join(
            (
                f"Product commit {PRODUCT_SHA}",
                f"Evidence release workflow run {EVIDENCE_RUN_ID}",
                f"Whitepaper source {WHITEPAPER_SHA}",
            )
        )

    def verify(self, text: str) -> None:
        VERIFY.verify_text(
            text,
            product_sha=PRODUCT_SHA,
            evidence_run_id=EVIDENCE_RUN_ID,
            whitepaper_sha=WHITEPAPER_SHA,
        )

    def test_accepts_exact_release_identity(self) -> None:
        self.verify(self.valid_text())

    def test_rejects_missing_product_identity(self) -> None:
        with self.assertRaisesRegex(VERIFY.PdfIdentityError, "product SHA"):
            self.verify(self.valid_text().replace(PRODUCT_SHA, ""))

    def test_rejects_missing_evidence_run_identity(self) -> None:
        with self.assertRaisesRegex(VERIFY.PdfIdentityError, "evidence run ID"):
            self.verify(self.valid_text().replace(EVIDENCE_RUN_ID, ""))

    def test_rejects_missing_whitepaper_identity(self) -> None:
        with self.assertRaisesRegex(VERIFY.PdfIdentityError, "whitepaper SHA"):
            self.verify(self.valid_text().replace(WHITEPAPER_SHA, ""))

    def test_rejects_fallback_identity_marker(self) -> None:
        with self.assertRaisesRegex(VERIFY.PdfIdentityError, "unresolved identity"):
            self.verify(self.valid_text() + "\nSOURCE-COMMIT-NOT-GENERATED")

    def test_rejects_malformed_expected_identity(self) -> None:
        with self.assertRaisesRegex(VERIFY.PdfIdentityError, "40 lowercase hex"):
            VERIFY.verify_text(
                self.valid_text(),
                product_sha="not-a-sha",
                evidence_run_id=EVIDENCE_RUN_ID,
                whitepaper_sha=WHITEPAPER_SHA,
            )


if __name__ == "__main__":
    unittest.main()
