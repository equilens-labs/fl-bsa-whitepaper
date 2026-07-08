import csv
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicClaimBoundariesContractTests(unittest.TestCase):
    def test_release_posture_limits_are_visible_in_executive_summary(self) -> None:
        summary = (ROOT / "sections" / "01_executive_summary.tex").read_text(
            encoding="utf-8"
        )

        self.assertIn("customer\\_evidence\\_eligible=false", summary)
        self.assertIn("customer\\_evidence\\_disposition=characterization\\_only", summary)
        for non_claim in (
            "legal/compliance certification",
            "near-duplicate privacy",
            "formal differential privacy",
            "regulator approval",
        ):
            with self.subTest(non_claim=non_claim):
                self.assertIn(non_claim, summary)

    def test_unsigned_whitepaper_intake_certificates_are_not_claimed_signed(self) -> None:
        pack_intent = json.loads((ROOT / "intake" / "pack_intent.json").read_text())
        self.assertIs(pack_intent["certificate_signing_expected"], False)

        signature_fields = {
            "certificate_signature",
            "signature_algorithm",
            "signature",
            "signed_at",
            "signer",
        }
        certs = sorted((ROOT / "intake" / "certificates").glob("*.json"))
        self.assertEqual(21, len(certs))
        for cert in certs:
            with self.subTest(cert=cert.name):
                data = json.loads(cert.read_text(encoding="utf-8"))
                self.assertTrue(signature_fields.isdisjoint(data.keys()))

        reproducibility = (ROOT / "sections" / "09_reproducibility.tex").read_text(
            encoding="utf-8"
        )
        self.assertIn("unsigned certificate chain", reproducibility)
        self.assertIn("certificate_signing_expected=false", reproducibility)
        self.assertNotIn("Each certificate is cryptographically signed", reproducibility)

    def test_differential_privacy_is_explicitly_not_claimed(self) -> None:
        manifest = json.loads((ROOT / "intake" / "manifest.json").read_text())
        self.assertIn("not_differential_privacy", json.dumps(manifest))

        quality_certs = (
            ROOT / "intake" / "certificates" / "synthetic_quality_certificate.json",
            ROOT
            / "intake"
            / "certificates"
            / "branch_amplification__synthetic_quality_certificate.json",
            ROOT
            / "intake"
            / "certificates"
            / "branch_intrinsic__synthetic_quality_certificate.json",
        )
        for cert in quality_certs:
            with self.subTest(cert=cert.name):
                data = json.loads(cert.read_text(encoding="utf-8"))
                self.assertIs(data["privacy_metrics"]["differential_privacy_claimed"], False)
                self.assertIs(data["privacy_metrics"]["near_duplicate_privacy_claimed"], False)
                self.assertIn(
                    "near-duplicate privacy and differential privacy are not claimed",
                    json.dumps(data),
                )

        privacy = (ROOT / "sections" / "08_security_privacy.tex").read_text(
            encoding="utf-8"
        )
        self.assertIn("does not claim differential privacy accounting", privacy)
        self.assertNotIn("(if applicable) differential privacy accounting", privacy)

    def test_race_small_n_text_points_to_machine_readable_intake(self) -> None:
        joined = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in (
                "sections/01_executive_summary.tex",
                "sections/06_results.tex",
                "sections/10_limitations_monitoring.tex",
            )
        )

        self.assertIn("machine-readable intake", joined)
        self.assertIn("intake/selection_rates.csv", joined)
        self.assertIn("intake/metrics_uncertainty.json", joined)
        self.assertNotIn("reported in the annex", joined)
        self.assertNotIn("appendix/annex views", joined)

    def test_regulatory_mapping_renders_all_intake_frameworks(self) -> None:
        with (ROOT / "intake" / "regulatory_matrix.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            frameworks = {row["framework"] for row in csv.DictReader(handle)}

        appendix = (ROOT / "sections" / "appendix_d_regulatory_matrix.tex").read_text(
            encoding="utf-8"
        )
        self.assertEqual({"EU AI Act", "CFPB/ECOA", "FCA Consumer Duty"}, frameworks)
        self.assertIn(r"\EUAIAct", appendix)
        self.assertIn(r"CFPB/\ECOA", appendix)
        self.assertIn("FCA Consumer Duty", appendix)
        self.assertIn("Controls and evidence (this run)", appendix)
        self.assertNotIn("reproduces the regulatory mapping", appendix)

    def test_alpha_source_uses_math_macro_not_literal_backslash(self) -> None:
        methods = (ROOT / "sections" / "03_methods.tex").read_text(encoding="utf-8")

        self.assertIn(r"$\alpha=0.05$", methods)
        self.assertNotIn(r"$\\alpha=0.05$", methods)


if __name__ == "__main__":
    unittest.main()
