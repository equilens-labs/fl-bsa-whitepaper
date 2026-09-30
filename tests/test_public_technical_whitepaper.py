import argparse
import copy
import importlib.util
import json
import stat
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "public_technical_whitepaper",
    ROOT / "scripts" / "public_technical_whitepaper.py",
)
assert SPEC and SPEC.loader
PAPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAPER)


class PublicTechnicalWhitepaperTests(unittest.TestCase):
    def test_integrity_narrative_matches_canonical_zip_metadata(self) -> None:
        narrative = (
            ROOT / "technical" / "sections" / "08_integrity_security_privacy.tex"
        ).read_text(encoding="utf-8")
        self.assertIn("outer ZIP timestamps are fixed to", narrative)
        self.assertIn("1980-01-01", narrative)
        self.assertIn(
            r"mode \texttt{0600} (\texttt{0700} for the offline verifier)", narrative
        )
        self.assertNotIn("timestamps derive from the source", narrative)

    def test_companion_zip_metadata_matches_protected_scanner(self) -> None:
        regular = PAPER._zip_info("evidence/summary.json")
        executable = PAPER._zip_info("verify.py", executable=True)
        for info in (regular, executable):
            self.assertEqual((1980, 1, 1, 0, 0, 0), info.date_time)
            self.assertEqual(3, info.create_system)
            self.assertEqual(PAPER.zipfile.ZIP_DEFLATED, info.compress_type)
        self.assertEqual(
            stat.S_IFREG | 0o600,
            (regular.external_attr >> 16) & 0xFFFF,
        )
        self.assertEqual(
            stat.S_IFREG | 0o700,
            (executable.external_attr >> 16) & 0xFFFF,
        )

    def test_decision_driver_does_not_substitute_lowest_intersection(self) -> None:
        intersectional = {
            "reference_intersection": "male|white",
            "pair_ratios": {"male|asian": 0.9568704102882611},
        }
        race_driver = PAPER._decision_driver(
            {
                "source": "fairness_uncertainty.race.pairs.asian.air",
                "metric": "air",
                "ratio": 0.949797885069366,
                "threshold": 0.8,
                "within_configured_threshold": True,
                "attribute": "race",
                "protected_group": "asian",
                "reference_group": "black",
            },
            intersectional,
            label="balanced seed 42",
        )
        self.assertEqual("race", race_driver["attribute"])
        self.assertEqual("asian", race_driver["tested_group"])
        self.assertEqual("black", race_driver["reference_group"])
        self.assertEqual(0.949797885069366, race_driver["ratio"])

        intersection_driver = PAPER._decision_driver(
            {
                "source": "intersectional_fairness.pairs.male|asian.air",
                "metric": "air",
                "ratio": 0.9568704102882611,
                "threshold": 0.8,
                "within_configured_threshold": True,
                "attribute": "intersectional",
                "pair": "male|asian",
            },
            intersectional,
            label="intersectional control",
        )
        self.assertEqual("male|white", intersection_driver["reference_group"])

    def test_rejects_unsafe_members_and_nonfinite_results(self) -> None:
        for name in ("../escape", "/absolute", "windows\\path", "./noncanonical"):
            with self.subTest(name=name):
                with self.assertRaises(PAPER.TechnicalPaperError):
                    PAPER._safe_member(name)
        for value in (True, float("nan"), float("inf"), "0.7"):
            with self.subTest(value=value):
                with self.assertRaises(PAPER.TechnicalPaperError):
                    PAPER._finite_number(value, "test result")

    def test_quality_projection_recomputes_the_reviewed_formula(self) -> None:
        certificate = {
            "branch_mode": "amplification",
            "overall_quality_score": 0.8,
            "quality_threshold_used": 0.8,
            "quality_threshold_met": True,
            "statistical_comparison": {"overall_distribution_score": 0.8},
            "correlation_analysis": {"correlation_preservation_score": 0.8},
            "bias_analysis": {
                "bias_preservation_score": 0.8,
                "demographic_parity_real": {"gender": {"a": 0.5}},
                "demographic_parity_synthetic": {"gender": {"a": 0.5}},
                "demographic_parity_difference": {"gender": 0.0},
            },
            "privacy_metrics": {
                "privacy_preservation_score": 0.8,
                "exact_duplicate_score_count": 0,
                "near_duplicate_count_status": "not_computed",
                "near_duplicate_privacy_claimed": False,
                "differential_privacy_claimed": False,
                "privacy_preservation_score_scope": (
                    "quality_heuristic_not_formal_privacy_guarantee"
                ),
            },
            "demographic_alignment": {
                "max_abs_pp_drift": 0.1,
                "threshold_pp": 5.0,
                "within_threshold": True,
            },
            "utility_metrics": None,
            "quality_ok": None,
        }
        self.assertEqual(
            0.8, PAPER._quality_projection(certificate)["overall_quality_score"]
        )
        mutations = (
            ("overall_quality_score", float("nan")),
            ("overall_quality_score", 0.81),
            ("quality_threshold_used", 0.7),
            ("quality_threshold_met", False),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                mutated = copy.deepcopy(certificate)
                mutated[field] = value
                with self.assertRaises(PAPER.TechnicalPaperError):
                    PAPER._quality_projection(mutated)
        duplicate_mutation = copy.deepcopy(certificate)
        duplicate_mutation["privacy_metrics"]["exact_duplicate_score_count"] = 1
        with self.assertRaises(PAPER.TechnicalPaperError):
            PAPER._quality_projection(duplicate_mutation)

        intrinsic = copy.deepcopy(certificate)
        intrinsic["branch_mode"] = "intrinsic"
        intrinsic["bias_analysis"] = {
            "bias_preservation_score": 1.0,
            "demographic_parity_real": {},
            "demographic_parity_synthetic": {},
            "demographic_parity_difference": {},
        }
        intrinsic["statistical_comparison"]["overall_distribution_score"] = 0.6
        intrinsic["overall_quality_score"] = 0.8
        projection = PAPER._quality_projection(intrinsic)
        self.assertEqual(
            "not_evaluated_default_one_no_outcome",
            projection["component_dispositions"]["demographic_rate_fidelity"],
        )

    def test_finalize_binds_pdf_companion_and_build_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build = root / "build"
            build.mkdir()
            summary = {
                "claims": {"customer_evidence_eligible": False},
                "publication_model": {
                    "artifact_class": "public_technical_characterization",
                    "distribution_status": "exact_byte_review_pending",
                    "source_public_distribution_authorized": False,
                },
                "identity": {"product_commit": "1" * 40},
                "source": {"intake_bundle_sha256": "2" * 64},
                "companion": {
                    "filename": "companion.zip",
                    "sha256": "3" * 64,
                    "size_bytes": 123,
                },
            }
            (build / "evidence-summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )
            pdf = root / "whitepaper.pdf"
            pdf.write_bytes(b"%PDF-exact-review-bytes")
            output = root / "whitepaper_release.json"
            result = PAPER.finalize(
                argparse.Namespace(
                    build_dir=build,
                    pdf=pdf,
                    output=output,
                    whitepaper_run_id="12345",
                    whitepaper_run_attempt="2",
                )
            )
            self.assertEqual("12345", result["identity"]["whitepaper_build_run_id"])
            self.assertEqual("2", result["identity"]["whitepaper_build_run_attempt"])
            self.assertEqual(PAPER._sha256_file(pdf), result["pdf"]["sha256"])
            self.assertEqual(summary["companion"], result["companion"])
            self.assertEqual(summary["publication_model"], result["publication_model"])
            self.assertEqual(result, json.loads(output.read_text(encoding="utf-8")))

    def test_finalize_rejects_pending_companion_or_invalid_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build = root / "build"
            build.mkdir()
            summary = {
                "claims": {},
                "identity": {},
                "source": {},
                "companion": {"sha256": "pending"},
            }
            (build / "evidence-summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"%PDF-test")
            args = argparse.Namespace(
                build_dir=build,
                pdf=pdf,
                output=root / "sidecar.json",
                whitepaper_run_id="0",
                whitepaper_run_attempt="1",
            )
            with self.assertRaisesRegex(PAPER.TechnicalPaperError, "companion"):
                PAPER.finalize(args)
            summary["companion"] = {
                "filename": "companion.zip",
                "sha256": "3" * 64,
                "size_bytes": 1,
            }
            (build / "evidence-summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )
            with self.assertRaisesRegex(PAPER.TechnicalPaperError, "positive integer"):
                PAPER.finalize(args)


if __name__ == "__main__":
    unittest.main()
