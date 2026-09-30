import csv
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_public_technical_companion",
    ROOT / "scripts" / "verify_public_technical_companion.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class VerifyPublicTechnicalCompanionTests(unittest.TestCase):
    def test_rejects_noncanonical_member_names(self) -> None:
        for name in ("./member", "directory//member", "/absolute", "windows\\member"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(
                    VERIFY.VerificationError, "unsafe companion member"
                ):
                    VERIFY._safe_name(name)

    def _intake(self) -> bytes:
        output = io.BytesIO()
        manifest = {
            "schema_version": "wp-intake.v1",
            "commit_sha": VERIFY.EXPECTED_PRODUCT_SHA,
            "code_commit": VERIFY.EXPECTED_PRODUCT_SHA,
            "source_commit": VERIFY.EXPECTED_PRODUCT_SHA,
            "software_commit": VERIFY.EXPECTED_PRODUCT_SHA,
        }
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("intake/manifest.json", json.dumps(manifest))
        return output.getvalue()

    @staticmethod
    def _csv(*, aod_status: str = "unavailable") -> bytes:
        output = io.StringIO()
        fieldnames = (
            "scenario",
            "seed",
            "status",
            "aod_status",
            "eod_status",
            "scenario_test_passed",
            "headline_gender_ratio",
            "selection_rate_gap",
            "maximum_demographic_parity_difference",
            "maximum_demographic_parity_attribute",
            "fairness_screen_within_threshold",
            "controlling_attribute",
            "controlling_tested_group",
            "controlling_reference_group",
            "controlling_ratio",
            "controlling_threshold",
            "controlling_within_threshold",
            "lowest_intersection",
            "lowest_intersection_reference",
            "lowest_intersection_ratio",
            "pdf_numeric_parity_passed",
            "certificate_chain_passed",
            "certificate_signatures_passed",
            "evidence_encryption_passed",
            "lc11_contract_certification_passed",
            "amplification_utility",
        )
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        index = 0
        for scenario in (
            "01_balanced",
            "02_gender_bias",
            "03_outliers",
            "04_security",
        ):
            for seed in (7, 11, 23, 42, 101, 1337, 2025, 4096, 8191, 314159):
                auc = 0.71 if index < 4 else 0.69
                index += 1
                accuracy = 0.63 + (index % 3) * 0.01
                controlling = {
                    "attribute": "gender",
                    "tested_group": "female",
                    "reference_group": "male",
                    "ratio": 0.65 if scenario == "02_gender_bias" else 0.9,
                }
                exact_controls = {
                    ("01_balanced", 101): {
                        "attribute": "race",
                        "tested_group": "other",
                        "reference_group": "hispanic",
                        "ratio": 0.8876387210196682,
                    },
                    ("02_gender_bias", 101): {
                        "attribute": "intersectional",
                        "tested_group": "female|asian",
                        "reference_group": "male|white",
                        "ratio": 0.5326046511627907,
                    },
                    ("02_gender_bias", 42): {
                        "attribute": "intersectional",
                        "tested_group": "female|white",
                        "reference_group": "male|white",
                        "ratio": 0.6113118085346579,
                    },
                    ("03_outliers", 1337): {
                        "attribute": "intersectional",
                        "tested_group": "female|other",
                        "reference_group": "male|white",
                        "ratio": 0.8570195449781122,
                    },
                    ("04_security", 11): {
                        "attribute": "intersectional",
                        "tested_group": "male|other",
                        "reference_group": "male|white",
                        "ratio": 0.8716203198253163,
                    },
                }
                controlling = exact_controls.get((scenario, seed), controlling)
                within = controlling["ratio"] >= 0.8
                writer.writerow(
                    {
                        "scenario": scenario,
                        "seed": seed,
                        "status": "pass",
                        "aod_status": aod_status,
                        "eod_status": "unavailable",
                        "scenario_test_passed": True,
                        "headline_gender_ratio": 0.65,
                        "selection_rate_gap": -0.2,
                        "maximum_demographic_parity_difference": 0.2,
                        "maximum_demographic_parity_attribute": "gender",
                        "fairness_screen_within_threshold": within,
                        "controlling_attribute": controlling["attribute"],
                        "controlling_tested_group": controlling["tested_group"],
                        "controlling_reference_group": controlling["reference_group"],
                        "controlling_ratio": controlling["ratio"],
                        "controlling_threshold": 0.8,
                        "controlling_within_threshold": within,
                        "lowest_intersection": (
                            controlling["tested_group"]
                            if controlling["attribute"] == "intersectional"
                            else "female|other"
                        ),
                        "lowest_intersection_reference": "male|white",
                        "lowest_intersection_ratio": (
                            controlling["ratio"]
                            if controlling["attribute"] == "intersectional"
                            else 0.92
                        ),
                        "pdf_numeric_parity_passed": True,
                        "certificate_chain_passed": True,
                        "certificate_signatures_passed": True,
                        "evidence_encryption_passed": True,
                        "lc11_contract_certification_passed": True,
                        "amplification_utility": json.dumps(
                            {
                                "accuracy": accuracy,
                                "auc": auc,
                                "floor": 0.7,
                                "status": "pass" if auc >= 0.7 else "warn",
                            }
                        ),
                    }
                )
        return output.getvalue().encode()

    def _companion(
        self,
        path: Path,
        *,
        aod_status: str = "unavailable",
        distribution_status: str = "exact_byte_review_pending",
        public_distribution_authorized: bool = False,
        intrinsic_fidelity_disposition: str = ("not_evaluated_default_one_no_outcome"),
        source_record: bytes = b"{}\n",
    ) -> tuple[Path, str]:
        intake = self._intake()
        claims = {
            "claim_expansion_authorized": False,
            "customer_evidence_disposition": "characterization_only",
            "customer_evidence_eligible": False,
            "demo_evaluation_only": True,
            "legal_or_compliance_certification": False,
            "marketplace_or_ga_authorization": False,
            "production_utility_established": False,
            "promotion_evidence_eligible": False,
            "regulator_approval": False,
        }
        identity = {
            "product_commit": VERIFY.EXPECTED_PRODUCT_SHA,
            "release_tag": "v5.0.8",
            "release_evidence_run_id": "36152873675",
            "source_attempt": "1",
            "current_attempt": "2",
            "source_attempt_conclusion": "failure",
            "source_producer_job_conclusion": "success",
            "current_attempt_conclusion": "success",
        }
        robustness_csv = self._csv(aod_status=aod_status)
        robustness_rows = list(
            csv.DictReader(io.StringIO(robustness_csv.decode("utf-8")))
        )
        fixture_utilities = [
            json.loads(row["amplification_utility"]) for row in robustness_rows
        ]
        fixture_accuracies = [item["accuracy"] for item in fixture_utilities]
        scenario_summaries = {}
        for scenario in (
            "01_balanced",
            "02_gender_bias",
            "03_outliers",
            "04_security",
        ):
            selected = [row for row in robustness_rows if row["scenario"] == scenario]
            worst = min(selected, key=lambda row: float(row["controlling_ratio"]))
            within = sum(
                row["fairness_screen_within_threshold"] == "True" for row in selected
            )
            scenario_summaries[scenario] = {
                "worst_controlling_comparison": {
                    "seed": int(worst["seed"]),
                    "attribute": worst["controlling_attribute"],
                    "tested_group": worst["controlling_tested_group"],
                    "reference_group": worst["controlling_reference_group"],
                    "ratio": float(worst["controlling_ratio"]),
                    "threshold": float(worst["controlling_threshold"]),
                    "within_configured_threshold": (
                        worst["controlling_within_threshold"] == "True"
                    ),
                },
                "fairness_screen": {
                    "within_threshold": within,
                    "outside_threshold": len(selected) - within,
                },
            }
        summary = {
            "claims": claims,
            "identity": identity,
            "publication_model": {
                "artifact_class": "public_technical_characterization",
                "distribution_status": distribution_status,
                "proposed_public_release_tag": VERIFY.EXPECTED_PUBLIC_RELEASE_TAG,
                "source_build_decision": "approved_for_build_and_exact_byte_review",
                "public_artifact_evidence_disposition": "characterization_only",
                "source_public_distribution_authorized": (
                    public_distribution_authorized
                ),
            },
            "quality": {
                "amplification": {
                    "components": {"bias_preservation_score": 0.99},
                    "component_dispositions": {
                        "demographic_rate_fidelity": "evaluated"
                    },
                },
                "intrinsic": {
                    "components": {"bias_preservation_score": 1.0},
                    "component_dispositions": {
                        "demographic_rate_fidelity": intrinsic_fidelity_disposition
                    },
                },
            },
            "generation": {
                "amplification": {
                    "backend_id": "first_party_evidence_native",
                    "backend_version": "0.1.0",
                    "generated_rows": 10_000,
                    "seed": 42,
                    "exact_output_wall": {"matching_row_instances": 0},
                    "quantile_alignment": {
                        "applied": True,
                        "reference_surface": "original_training_data",
                        "stratify_columns": ["loan_approved"],
                    },
                },
                "intrinsic": {
                    "backend_id": "first_party_evidence_native",
                    "backend_version": "0.1.0",
                    "generated_rows": 10_000,
                    "seed": 42,
                    "sampling_strategy": "intrinsic_anchor_profile_resampling",
                    "stratification_column": "gender,race",
                    "exact_output_wall": {"matching_row_instances": 0},
                },
            },
            "protected_group_scope": {
                "claim_scope": "per_attribute",
                "covered_attributes": ["gender", "race"],
                "excluded_claims": [
                    "absence_of_bias_for_uncovered_protected_bases",
                    "absence_of_intersectional_bias",
                    "multi_level_race_encoding_without_declared_schema_support",
                ],
                "uncovered_ecoa_reg_b_bases": [
                    "color",
                    "religion",
                    "national_origin",
                    "marital_status",
                    "age",
                    "receipt_of_public_assistance",
                    "exercise_of_consumer_credit_rights",
                ],
            },
            "robustness": {
                "runs": 40,
                "passes": 40,
                "scenarios": scenario_summaries,
                "advisory_utility": {
                    "runs": 40,
                    "below_floor": 36,
                    "at_or_above_floor": 4,
                    "intrinsic_status": "not_evaluated",
                    "minimum_auc": 0.69,
                    "mean_auc": 0.692,
                    "maximum_auc": 0.71,
                    "minimum_accuracy": min(fixture_accuracies),
                    "mean_accuracy": sum(fixture_accuracies) / len(fixture_accuracies),
                    "maximum_accuracy": max(fixture_accuracies),
                    "accuracy_threshold_status": "not_configured",
                },
            },
        }
        build_decision = {
            **claims,
            "artifact_profile": "technical_whitepaper_v1",
            "decision": "approved_for_build_and_exact_byte_review",
            "product_sha": VERIFY.EXPECTED_PRODUCT_SHA,
            "proposed_public_release_tag": VERIFY.EXPECTED_PUBLIC_RELEASE_TAG,
            "public_distribution_authorized": public_distribution_authorized,
            "metadata_correction": {
                "field": "whitepaper.customer_evidence_eligible",
                "corrected_value": False,
            },
        }
        members = {
            "producer/WhitePaper_Intake_Bundle_v4.zip": intake,
            "consumer/source-record.json": source_record,
            "authorization/build-source-decision-and-correction.json": (
                json.dumps(build_decision).encode()
            ),
            "evidence/evidence-summary.json": json.dumps(summary).encode(),
            "evidence/robustness-public.csv": robustness_csv,
            "verify_public_technical_companion.py": b"#!/usr/bin/env python3\n",
        }
        manifest = {
            "schema_version": VERIFY.EXPECTED_SCHEMA,
            "claims": claims,
            "identity": identity,
            "files": {
                name: {
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                }
                for name, data in members.items()
            },
        }
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)
            archive.writestr("MANIFEST.json", json.dumps(manifest))
        return path, hashlib.sha256(intake).hexdigest()

    def test_accepts_bounded_fixture_and_rejects_aod_regression(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            valid, intake_sha = self._companion(root / "valid.zip")
            with mock.patch.object(VERIFY, "EXPECTED_INTAKE_SHA256", intake_sha):
                self.assertTrue(VERIFY.verify(valid)["verified"])
            invalid, intake_sha = self._companion(
                root / "invalid.zip", aod_status="available"
            )
            with mock.patch.object(VERIFY, "EXPECTED_INTAKE_SHA256", intake_sha):
                with self.assertRaisesRegex(VERIFY.VerificationError, "AOD available"):
                    VERIFY.verify(invalid)

    def test_rejects_distribution_authorization_or_status_widening(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = (
                {"distribution_status": "published"},
                {"public_distribution_authorized": True},
            )
            for index, changes in enumerate(cases):
                with self.subTest(changes=changes):
                    archive, intake_sha = self._companion(
                        root / f"widened-{index}.zip", **changes
                    )
                    with mock.patch.object(
                        VERIFY, "EXPECTED_INTAKE_SHA256", intake_sha
                    ):
                        with self.assertRaises(VERIFY.VerificationError):
                            VERIFY.verify(archive)

    def test_rejects_private_path_in_public_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive, intake_sha = self._companion(
                Path(temporary) / "private.zip",
                source_record=b'{"workspace":"/home/ci/actions-runner/work"}\n',
            )
            with mock.patch.object(VERIFY, "EXPECTED_INTAKE_SHA256", intake_sha):
                with self.assertRaisesRegex(VERIFY.VerificationError, "private path"):
                    VERIFY.verify(archive)

    def test_rejects_intrinsic_default_presented_as_evaluated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive, intake_sha = self._companion(
                Path(temporary) / "misleading.zip",
                intrinsic_fidelity_disposition="evaluated",
            )
            with mock.patch.object(VERIFY, "EXPECTED_INTAKE_SHA256", intake_sha):
                with self.assertRaisesRegex(
                    VERIFY.VerificationError, "default is not disclosed"
                ):
                    VERIFY.verify(archive)

    def test_rejects_missing_controlling_reference_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, intake_sha = self._companion(root / "reference.zip")
            with zipfile.ZipFile(archive) as source:
                members = {name: source.read(name) for name in source.namelist()}
            rows = list(
                csv.DictReader(
                    io.StringIO(
                        members["evidence/robustness-public.csv"].decode("utf-8")
                    )
                )
            )
            rows[0]["controlling_reference_group"] = ""
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
            members["evidence/robustness-public.csv"] = output.getvalue().encode()
            manifest = json.loads(members["MANIFEST.json"])
            payload = members["evidence/robustness-public.csv"]
            manifest["files"]["evidence/robustness-public.csv"] = {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
            members["MANIFEST.json"] = json.dumps(manifest).encode()
            invalid = root / "missing-reference.zip"
            with zipfile.ZipFile(invalid, "w") as output_archive:
                for name, payload in members.items():
                    output_archive.writestr(name, payload)
            with mock.patch.object(VERIFY, "EXPECTED_INTAKE_SHA256", intake_sha):
                with self.assertRaisesRegex(
                    VERIFY.VerificationError, "controlling groups"
                ):
                    VERIFY.verify(invalid)


if __name__ == "__main__":
    unittest.main()
