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
PRODUCT_TAG = "v5.0.1"
WHITEPAPER_SHA = "248dab12d41073f183236eb2062a9369beb85066"
EVIDENCE_RUN_ID = "30765888408"


class VerifyPdfReleaseIdentityTests(unittest.TestCase):
    def valid_text(self) -> str:
        return "\n".join(
            (
                f"Product {PRODUCT_TAG} at {PRODUCT_SHA}",
                f"Evidence release workflow run {EVIDENCE_RUN_ID}",
                f"Whitepaper source {WHITEPAPER_SHA}",
            )
        )

    def verify(self, text: str) -> None:
        VERIFY.verify_text(
            text,
            product_tag=PRODUCT_TAG,
            product_sha=PRODUCT_SHA,
            evidence_run_id=EVIDENCE_RUN_ID,
            whitepaper_sha=WHITEPAPER_SHA,
        )

    def test_accepts_exact_release_identity(self) -> None:
        self.verify(self.valid_text())

    def test_rejects_missing_product_identity(self) -> None:
        with self.assertRaisesRegex(VERIFY.PdfIdentityError, "product identity"):
            self.verify(self.valid_text().replace(PRODUCT_SHA, ""))

    def test_rejects_missing_evidence_run_identity(self) -> None:
        with self.assertRaisesRegex(VERIFY.PdfIdentityError, "evidence run identity"):
            self.verify(self.valid_text().replace(EVIDENCE_RUN_ID, ""))

    def test_rejects_missing_whitepaper_identity(self) -> None:
        with self.assertRaisesRegex(VERIFY.PdfIdentityError, "whitepaper identity"):
            self.verify(self.valid_text().replace(WHITEPAPER_SHA, ""))

    def test_rejects_fallback_identity_marker(self) -> None:
        with self.assertRaisesRegex(VERIFY.PdfIdentityError, "unresolved identity"):
            self.verify(self.valid_text() + "\nSOURCE-COMMIT-NOT-GENERATED")

    def test_rejects_values_under_wrong_labels(self) -> None:
        text = "\n".join(
            (
                f"References {PRODUCT_SHA} {WHITEPAPER_SHA} {EVIDENCE_RUN_ID}",
                f"Product {PRODUCT_TAG} at {'f' * 40}",
                f"Evidence release workflow run {EVIDENCE_RUN_ID}0",
                f"Whitepaper source {'e' * 40}",
            )
        )
        with self.assertRaisesRegex(VERIFY.PdfIdentityError, "product identity"):
            self.verify(text)

    def test_rejects_run_id_that_is_only_a_longer_number_prefix(self) -> None:
        text = self.valid_text().replace(EVIDENCE_RUN_ID, EVIDENCE_RUN_ID + "0")
        with self.assertRaisesRegex(VERIFY.PdfIdentityError, "evidence run identity"):
            self.verify(text)

    def test_rejects_alphanumeric_suffixes_on_every_identity(self) -> None:
        mutations = {
            "product identity": self.valid_text().replace(PRODUCT_SHA, PRODUCT_SHA + "x"),
            "evidence run identity": self.valid_text().replace(
                EVIDENCE_RUN_ID, EVIDENCE_RUN_ID + "x"
            ),
            "whitepaper identity": self.valid_text().replace(
                WHITEPAPER_SHA, WHITEPAPER_SHA + "x"
            ),
        }
        for expected_error, text in mutations.items():
            with self.subTest(expected_error=expected_error):
                with self.assertRaisesRegex(VERIFY.PdfIdentityError, expected_error):
                    self.verify(text)

    def test_rejects_malformed_expected_identity(self) -> None:
        with self.assertRaisesRegex(VERIFY.PdfIdentityError, "40 lowercase hex"):
            VERIFY.verify_text(
                self.valid_text(),
                product_tag=PRODUCT_TAG,
                product_sha="not-a-sha",
                evidence_run_id=EVIDENCE_RUN_ID,
                whitepaper_sha=WHITEPAPER_SHA,
            )


if __name__ == "__main__":
    unittest.main()
