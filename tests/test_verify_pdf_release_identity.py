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
EVIDENCE_RUN_ATTEMPT = "2"
GENERATOR_BACKEND_ID = "first_party_evidence_native"
WHITEPAPER_RUN_ID = "24680"
WHITEPAPER_RUN_ATTEMPT = "3"
INTAKE_SNAPSHOT_ID = "d" * 64
INTAKE_BUNDLE_SHA256 = "e" * 64


class VerifyPdfReleaseIdentityTests(unittest.TestCase):
    def valid_text(self) -> str:
        return "\n".join(
            (
                f"Product {PRODUCT_TAG} at {PRODUCT_SHA}",
                f"Evidence release workflow run {EVIDENCE_RUN_ID} "
                f"(attempt {EVIDENCE_RUN_ATTEMPT})",
                f"Generator backend {GENERATOR_BACKEND_ID}",
                f"Whitepaper source {WHITEPAPER_SHA}",
                f"Whitepaper workflow run {WHITEPAPER_RUN_ID} "
                f"(attempt {WHITEPAPER_RUN_ATTEMPT})",
                f"Intake snapshot {INTAKE_SNAPSHOT_ID}",
                f"Intake bundle SHA-256 {INTAKE_BUNDLE_SHA256}",
                "customer_evidence_eligible=false",
                "customer_evidence_disposition=characterization_only",
                "publication_status=candidate_not_published",
            )
        )

    def verify(self, text: str) -> None:
        VERIFY.verify_text(
            text,
            product_tag=PRODUCT_TAG,
            product_sha=PRODUCT_SHA,
            evidence_run_id=EVIDENCE_RUN_ID,
            whitepaper_sha=WHITEPAPER_SHA,
            evidence_run_attempt=EVIDENCE_RUN_ATTEMPT,
            generator_backend_id=GENERATOR_BACKEND_ID,
            whitepaper_run_id=WHITEPAPER_RUN_ID,
            whitepaper_run_attempt=WHITEPAPER_RUN_ATTEMPT,
            intake_snapshot_id=INTAKE_SNAPSHOT_ID,
            intake_bundle_sha256=INTAKE_BUNDLE_SHA256,
            require_release_claims=True,
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

    def test_rejects_each_missing_extended_identity(self) -> None:
        mutations = (
            (
                "evidence run identity",
                f"(attempt {EVIDENCE_RUN_ATTEMPT})",
                "(attempt removed)",
            ),
            (
                "generator backend identity",
                f"Generator backend {GENERATOR_BACKEND_ID}",
                "Generator backend removed",
            ),
            (
                "whitepaper workflow run identity",
                f"Whitepaper workflow run {WHITEPAPER_RUN_ID}",
                "Whitepaper workflow run removed",
            ),
            (
                "whitepaper workflow run identity",
                f"(attempt {WHITEPAPER_RUN_ATTEMPT})",
                "(attempt removed)",
            ),
            (
                "intake snapshot identity",
                f"Intake snapshot {INTAKE_SNAPSHOT_ID}",
                "Intake snapshot removed",
            ),
            (
                "intake bundle identity",
                f"Intake bundle SHA-256 {INTAKE_BUNDLE_SHA256}",
                "Intake bundle SHA-256 removed",
            ),
        )
        for expected_error, old, new in mutations:
            with self.subTest(expected_error=expected_error):
                text = self.valid_text().replace(old, new, 1)
                with self.assertRaisesRegex(VERIFY.PdfIdentityError, expected_error):
                    self.verify(text)

    def test_rejects_fallback_identity_marker(self) -> None:
        with self.assertRaisesRegex(VERIFY.PdfIdentityError, "unresolved identity"):
            self.verify(self.valid_text() + "\nSOURCE-COMMIT-NOT-GENERATED")

    def test_rejects_each_missing_visible_release_claim(self) -> None:
        mutations = (
            ("customer evidence eligibility claim", "customer_evidence_eligible=false"),
            (
                "customer evidence disposition claim",
                "customer_evidence_disposition=characterization_only",
            ),
            ("publication status claim", "publication_status=candidate_not_published"),
        )
        for expected_error, token in mutations:
            with self.subTest(expected_error=expected_error):
                with self.assertRaisesRegex(VERIFY.PdfIdentityError, expected_error):
                    self.verify(self.valid_text().replace(token, "claim_removed", 1))

    def test_accepts_claim_token_broken_across_extracted_lines(self) -> None:
        wrapped = self.valid_text().replace(
            "customer_evidence_disposition=characterization_only",
            "customer_evidence_disposition=characterization_\nonly",
        )
        self.verify(wrapped)

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
            "product identity": self.valid_text().replace(
                PRODUCT_SHA, PRODUCT_SHA + "x"
            ),
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
