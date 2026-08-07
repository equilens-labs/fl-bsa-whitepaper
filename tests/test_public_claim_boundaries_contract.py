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

        self.assertIn("customer_evidence_eligible=false", summary)
        self.assertIn("customer_evidence_disposition=characterization_only", summary)
        joined = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in (
                "main.tex",
                "sections/01_executive_summary.tex",
                "sections/07_compliance.tex",
                "sections/08_security_privacy.tex",
                "sections/10_limitations_monitoring.tex",
            )
        )
        joined = " ".join(joined.split())
        for non_claim in (
            "Marketplace go-live",
            "live decisioning",
            "commercial authorization",
            "vendor-authored evidence",
            "regulator approval",
            "compliance determination",
            "Near-duplicate",
            "formal guarantee",
            "supervisory acceptance",
        ):
            with self.subTest(non_claim=non_claim):
                self.assertIn(non_claim, joined)

    def test_signature_metadata_is_not_claimed_as_standalone_authentication(self) -> None:
        pack_intent = json.loads((ROOT / "intake" / "pack_intent.json").read_text())
        self.assertIs(pack_intent["certificate_signing_expected"], False)

        signature_fields = {
            "certificate_signature",
            "public_key_fingerprint",
            "signature_algorithm",
            "signed_at",
        }
        certs = sorted((ROOT / "intake" / "certificates").glob("*.json"))
        self.assertEqual(21, len(certs))
        for cert in certs:
            with self.subTest(cert=cert.name):
                data = json.loads(cert.read_text(encoding="utf-8"))
                self.assertTrue(signature_fields.issubset(data.keys()))
                self.assertEqual("ECDSA-P256-SHA256", data["signature_algorithm"])

        integrity = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in (
                "sections/04_model_algorithm.tex",
                "sections/08_security_privacy.tex",
                "sections/09_reproducibility.tex",
            )
        )
        self.assertIn("public key is not included", integrity)
        self.assertIn("encoding, not their cryptographic authorship", integrity)
        self.assertIn("integrity linkage", integrity)
        self.assertNotIn("Each certificate is cryptographically signed", integrity)

    def test_pre_v5_intake_files_are_archived_not_current_claim_surfaces(self) -> None:
        stale_root_names = {
            "claims_to_substantiate.md",
            "dataset_summary_20251007T101329Z.csv",
            "feature_missingness_20251007T101329Z.csv",
            "group_summary_20251007T101329Z.csv",
            "manifest_gate_wp.json",
            "runs.json",
        }
        stale_root_names.update(path.name for path in (ROOT / "intake").glob("manifest_*.json"))

        for name in stale_root_names:
            with self.subTest(name=name):
                self.assertFalse((ROOT / "intake" / name).exists())

        archive_readme = (
            ROOT / "intake" / "archive" / "legacy-pre-v5" / "README.md"
        ).read_text(encoding="utf-8")
        self.assertIn("not part of the current stable", archive_readme)
        self.assertIn("Do not cite them as the current evidence inventory", archive_readme)
        self.assertIn("current intake basis", archive_readme)

        archived_claims = (
            ROOT / "intake" / "archive" / "legacy-pre-v5" / "claims_to_substantiate.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Evidence/run vintage:** 2025-10-07", archived_claims)
        self.assertIn("Last substantive claim edit:** 2026-05-19", archived_claims)
        self.assertIn("Archived:** 2026-07-09", archived_claims)
        self.assertIn("retained for historical traceability only", archived_claims)

        historical_compilation = (
            ROOT / "docs" / "WhitePaper_Intake_Compiled.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Historical Pre-v5 Compilation", historical_compilation)
        self.assertIn("retained for traceability only", historical_compilation)
        self.assertIn("intake/pack_intent.json", historical_compilation)
        self.assertIn("intake/metrics_uncertainty.json", historical_compilation)
        self.assertNotIn("Artifacts Provided (Current Intake Surface)", historical_compilation)

    def test_obsolete_ctgan_working_documents_are_not_current_surfaces(self) -> None:
        for relative in (
            "tasks/ACTIVE/ECE-Gap.md",
            "docs/WhitePaper_RFI.md",
            "templates/intake_templates/model_hyperparams.yaml",
        ):
            with self.subTest(relative=relative):
                self.assertFalse((ROOT / relative).exists())

        publication_sources = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in (
                "README.md",
                "main.tex",
                "sections/01_executive_summary.tex",
                "sections/04_model_algorithm.tex",
                "sections/10_limitations_monitoring.tex",
            )
        ).lower()
        self.assertNotIn("ctgan", publication_sources)
        self.assertNotIn("datacebo", publication_sources)

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
        self.assertIn(
            "no differential-privacy mechanism, budget, accountant, or formal guarantee",
            privacy,
        )
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

        current = (ROOT / "sections" / "07_compliance.tex").read_text(
            encoding="utf-8"
        )
        self.assertEqual({"EU AI Act", "CFPB/ECOA", "FCA Consumer Duty"}, frameworks)
        overlay_path = (
            ROOT
            / "evidence"
            / "v5.0.1"
            / "publication"
            / "regulatory_mapping_2026-08-05.csv"
        )
        with overlay_path.open(newline="", encoding="utf-8") as handle:
            overlay = list(csv.DictReader(handle))
        self.assertEqual(5, len(overlay))
        self.assertTrue(all(row["as_of"] == "2026-08-05" for row in overlay))
        self.assertTrue(all(row["source_url"].startswith("https://") for row in overlay))
        self.assertIn("SR 26-2", current)
        self.assertIn("effective 21 July 2026", current)
        self.assertIn("rule of thumb, not a legal definition", current)
        self.assertIn("not presented as a Regulation B requirement", current)

    def test_alpha_source_uses_math_macro_not_literal_backslash(self) -> None:
        methods = (ROOT / "sections" / "03_methods.tex").read_text(encoding="utf-8")

        self.assertIn(r"$\alpha=0.05$", methods)
        self.assertNotIn(r"$\\alpha=0.05$", methods)


if __name__ == "__main__":
    unittest.main()
