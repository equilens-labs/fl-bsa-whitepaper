import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_public_technical_pdf",
    ROOT / "scripts" / "verify_public_technical_pdf.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class VerifyPublicTechnicalPdfTests(unittest.TestCase):
    def setUp(self) -> None:
        self.product = "1" * 40
        self.tag_object = "2" * 40
        self.companion = "3" * 64
        self.intake = "4" * 64
        self.summary = {
            "schema_version": "flbsa.public_technical_whitepaper.v1",
            "claims": {
                "claim_expansion_authorized": False,
                "customer_evidence_disposition": "characterization_only",
                "customer_evidence_eligible": False,
                "demo_evaluation_only": True,
                "legal_or_compliance_certification": False,
                "marketplace_or_ga_authorization": False,
                "production_utility_established": False,
                "promotion_evidence_eligible": False,
                "regulator_approval": False,
            },
            "identity": {
                "release_tag": "v5.0.8",
                "product_commit": self.product,
                "product_tag_object": self.tag_object,
                "release_evidence_run_id": "36152873675",
                "source_attempt": "1",
                "current_attempt": "2",
            },
            "quality": {
                "amplification": {"overall_quality_score": 0.906006125},
                "intrinsic": {"overall_quality_score": 0.897126499},
            },
            "robustness": {
                "runs": 40,
                "passes": 40,
                "advisory_utility": {
                    "minimum_auc": 0.6765233,
                    "mean_auc": 0.6896301,
                    "maximum_auc": 0.7050076,
                    "below_floor": 36,
                    "minimum_accuracy": 0.6298,
                    "mean_accuracy": 0.64064,
                    "maximum_accuracy": 0.6568,
                },
            },
            "companion": {"sha256": self.companion},
            "source": {"intake_bundle_sha256": self.intake},
        }
        self.text = " ".join(
            (
                "FL-BSA v5.0.8 Technical Whitepaper",
                "PUBLIC TECHNICAL CHARACTERIZATION",
                "DEMO / EVALUATION ONLY",
                "Product v5.0.8 at",
                "release-evidence run 36152873675",
                "retained source attempt 1; current successful attempt 2",
                "first_party_evidence_native characterization_only",
                "AOD and EOD are unavailable",
                "customer-evidence ineligible",
                "Production utility is not established",
                (
                    "40/40 0.906006 0.897126 0.676523 0.689630 0.705008 36 of 40 "
                    "0.629800 0.640640 0.656800 no accuracy threshold is configured"
                ),
                self.product,
                self.tag_object,
                self.companion,
                self.intake,
            )
        )

    def _paths(self, root: Path) -> tuple[Path, Path]:
        pdf = root / "paper.pdf"
        pdf.write_bytes(b"%PDF-fake")
        summary = root / "summary.json"
        summary.write_text(json.dumps(self.summary), encoding="utf-8")
        return pdf, summary

    def test_accepts_visible_exact_identity_and_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pdf, summary = self._paths(Path(temporary))
            with mock.patch.object(VERIFY, "_extract", return_value=self.text):
                result = VERIFY.verify(pdf, summary)
        self.assertTrue(result["verified"])
        self.assertFalse(result["customer_evidence_eligible"])

    def test_rejects_numeric_aod_regression(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pdf, summary = self._paths(Path(temporary))
            text = self.text + " AOD: 0.0049"
            with mock.patch.object(VERIFY, "_extract", return_value=text):
                with self.assertRaisesRegex(VERIFY.TechnicalPdfError, "numeric AOD"):
                    VERIFY.verify(pdf, summary)

    def test_rejects_claim_widening_before_reading_pdf(self) -> None:
        self.summary["claims"]["customer_evidence_eligible"] = True
        with tempfile.TemporaryDirectory() as temporary:
            pdf, summary = self._paths(Path(temporary))
            with self.assertRaisesRegex(VERIFY.TechnicalPdfError, "widens"):
                VERIFY.verify(pdf, summary)


if __name__ == "__main__":
    unittest.main()
