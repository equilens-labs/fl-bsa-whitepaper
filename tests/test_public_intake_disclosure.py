import csv
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate_public_intake.py"
SPEC = importlib.util.spec_from_file_location(
    "validate_public_intake_under_test", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
DISCLOSURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DISCLOSURE)


class PublicIntakeDisclosureTests(unittest.TestCase):
    def _bundle(self, root: Path) -> Path:
        bundle = root / "bundle"
        for path in (
            "intake/metrics_uncertainty.json",
            "intake/metrics_long.csv",
            "certificates/synthetic_quality_certificate.json",
            "config/sap.yaml",
            "provenance/manifest.json",
        ):
            if path == "provenance/manifest.json":
                source = ROOT / "intake" / "manifest.json"
            elif path.startswith("certificates/"):
                source = ROOT / "intake" / path
            else:
                source = ROOT / path
            target = bundle / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        return bundle

    @staticmethod
    def _ci_runtime_provenance(
        head_sha: str = "a" * 40,
        digest: str = "sha256:" + "c" * 64,
        *,
        image_build_sha: str | None = None,
        build_disposition: str = "built_for_source",
    ) -> dict:
        digest_ref = f"ghcr.io/equilens-labs/fl-bsa-runtime@{digest}"
        if image_build_sha is None:
            image_build_sha = head_sha
        return {
            "schema_version": "wp.ci_runtime_provenance.v2",
            "source_ci": {
                "repository": "equilens-labs/fl-bsa",
                "workflow": ".github/workflows/ci-comprehensive.yml",
                "run_id": 123,
                "run_attempt": 2,
                "head_sha": head_sha,
                "contract_artifact": {
                    "id": 456,
                    "name": "ci-runtime-image-contract-2",
                    "digest": "sha256:" + "b" * 64,
                    "size_in_bytes": 789,
                },
            },
            "runtime_image": {
                "digest": digest,
                "digest_ref": digest_ref,
                "api_digest_ref": digest_ref,
                "worker_digest_ref": digest_ref,
                "image_build_sha": image_build_sha,
                "build_disposition": build_disposition,
                "runtime_input_projection": {
                    "algorithm": "git-ls-tree-z-sha256.v1",
                    "sha256": "d" * 64,
                },
            },
            "claims": {
                "bounded_runtime_contract_verified": True,
                "full_ci_proven": False,
            },
        }

    def test_reviewed_tracked_shapes_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            DISCLOSURE.validate_bundle(self._bundle(Path(tmp)), ROOT)

    def test_reviewed_ci_runtime_provenance_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            manifest_path = bundle / "provenance" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["ci_runtime_provenance"] = self._ci_runtime_provenance(
                manifest["commit_sha"], manifest["container_digest"].rsplit("@", 1)[1]
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_reviewed_runtime_build_dispositions_pass(self) -> None:
        cases = (
            ("built_for_source", False),
            ("reused_exact_sha_tag_matching_projection", False),
            ("reused_exact_sha_tag_projection_equivalent", True),
            ("reused_main_profile_latest_matching_projection", False),
            ("reused_main_profile_latest_matching_projection", True),
        )
        for disposition, distinct_build_sha in cases:
            with (
                self.subTest(
                    disposition=disposition, distinct_build_sha=distinct_build_sha
                ),
                tempfile.TemporaryDirectory() as tmp,
            ):
                bundle = self._bundle(Path(tmp))
                manifest_path = bundle / "provenance" / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                head_sha = manifest["commit_sha"]
                image_build_sha = "e" * 40 if distinct_build_sha else head_sha
                manifest["ci_runtime_provenance"] = self._ci_runtime_provenance(
                    head_sha,
                    manifest["container_digest"].rsplit("@", 1)[1],
                    image_build_sha=image_build_sha,
                    build_disposition=disposition,
                )
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_incomplete_runtime_provenance_v1_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            manifest_path = bundle / "provenance" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            provenance = self._ci_runtime_provenance(manifest["commit_sha"])
            provenance["schema_version"] = "wp.ci_runtime_provenance.v1"
            manifest["ci_runtime_provenance"] = provenance
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                DISCLOSURE.DisclosureError, "unreviewed schema version"
            ):
                DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_runtime_build_provenance_fields_are_required(self) -> None:
        for field in ("image_build_sha", "build_disposition"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                bundle = self._bundle(Path(tmp))
                manifest_path = bundle / "provenance" / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                provenance = self._ci_runtime_provenance(manifest["commit_sha"])
                del provenance["runtime_image"][field]
                manifest["ci_runtime_provenance"] = provenance
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(
                    DISCLOSURE.DisclosureError, "exact reviewed fields"
                ):
                    DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_runtime_image_build_sha_must_be_full_lowercase_sha(self) -> None:
        for image_build_sha in ("A" * 40, "a" * 39, "g" * 40):
            with (
                self.subTest(image_build_sha=image_build_sha),
                tempfile.TemporaryDirectory() as tmp,
            ):
                bundle = self._bundle(Path(tmp))
                manifest_path = bundle / "provenance" / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["ci_runtime_provenance"] = self._ci_runtime_provenance(
                    manifest["commit_sha"], image_build_sha=image_build_sha
                )
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(
                    DISCLOSURE.DisclosureError,
                    "malformed or unreviewed build provenance",
                ):
                    DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_unknown_runtime_build_disposition_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            manifest_path = bundle / "provenance" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["ci_runtime_provenance"] = self._ci_runtime_provenance(
                manifest["commit_sha"], build_disposition="unreviewed_reuse_mode"
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                DISCLOSURE.DisclosureError,
                "malformed or unreviewed build provenance",
            ):
                DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_runtime_build_disposition_enforces_source_sha_coherence(self) -> None:
        cases = (
            ("built_for_source", "e" * 40, "does not match the source CI head"),
            (
                "reused_exact_sha_tag_matching_projection",
                "e" * 40,
                "does not match the source CI head",
            ),
            (
                "reused_exact_sha_tag_projection_equivalent",
                None,
                "does not identify a distinct image build source",
            ),
        )
        for disposition, image_build_sha, expected in cases:
            with (
                self.subTest(disposition=disposition),
                tempfile.TemporaryDirectory() as tmp,
            ):
                bundle = self._bundle(Path(tmp))
                manifest_path = bundle / "provenance" / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["ci_runtime_provenance"] = self._ci_runtime_provenance(
                    manifest["commit_sha"],
                    image_build_sha=image_build_sha,
                    build_disposition=disposition,
                )
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(DISCLOSURE.DisclosureError, expected):
                    DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_duplicate_runtime_build_disposition_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            manifest_path = bundle / "provenance" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["ci_runtime_provenance"] = self._ci_runtime_provenance(
                manifest["commit_sha"]
            )
            candidate = json.dumps(manifest)
            needle = '"build_disposition": "built_for_source"'
            duplicate = (
                '"build_disposition": "built_for_source", '
                '"build_disposition": "reused_main_profile_latest_matching_projection"',
            )
            self.assertEqual(candidate.count(needle), 1)
            manifest_path.write_text(
                candidate.replace(needle, "".join(duplicate)), encoding="utf-8"
            )
            with self.assertRaisesRegex(DISCLOSURE.DisclosureError, "duplicate key"):
                DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_ci_runtime_provenance_attempt_mismatch_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            manifest_path = bundle / "provenance" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            provenance = self._ci_runtime_provenance(manifest["commit_sha"])
            sentinel = "ci-runtime-image-contract-never-private"
            provenance["source_ci"]["contract_artifact"]["name"] = sentinel
            manifest["ci_runtime_provenance"] = provenance
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                DISCLOSURE.DisclosureError, "malformed identity"
            ) as raised:
                DISCLOSURE.validate_bundle(bundle, ROOT)
            self.assertNotIn(sentinel, str(raised.exception))

    def test_baselined_ci_runtime_provenance_still_enforces_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bundle = self._bundle(tmp_path)
            schema_root = tmp_path / "schema"
            shutil.copytree(ROOT / "intake", schema_root / "intake")
            (schema_root / "config").mkdir(parents=True)
            shutil.copyfile(ROOT / "config" / "sap.yaml", schema_root / "config" / "sap.yaml")

            baseline_path = schema_root / "intake" / "manifest.json"
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            baseline["ci_runtime_provenance"] = self._ci_runtime_provenance(
                baseline["commit_sha"]
            )
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

            candidate_path = bundle / "provenance" / "manifest.json"
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            provenance = self._ci_runtime_provenance(candidate["commit_sha"])
            provenance["claims"]["full_ci_proven"] = True
            candidate["ci_runtime_provenance"] = provenance
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

            with self.assertRaisesRegex(
                DISCLOSURE.DisclosureError, "claims exceed the reviewed bounded proof"
            ):
                DISCLOSURE.validate_bundle(bundle, schema_root)

    def test_runtime_claim_booleans_reject_numeric_equivalents(self) -> None:
        for field, numeric_equivalent in (
            ("bounded_runtime_contract_verified", 1),
            ("full_ci_proven", 0),
        ):
            with self.subTest(field=field):
                provenance = self._ci_runtime_provenance()
                provenance["claims"][field] = numeric_equivalent
                with self.assertRaisesRegex(
                    DISCLOSURE.DisclosureError,
                    "claims exceed the reviewed bounded proof",
                ):
                    DISCLOSURE._validate_ci_runtime_provenance(
                        provenance, "ci_runtime_provenance"
                    )
                with tempfile.TemporaryDirectory() as tmp:
                    bundle = self._bundle(Path(tmp))
                    manifest_path = bundle / "provenance" / "manifest.json"
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    provenance = self._ci_runtime_provenance(manifest["commit_sha"])
                    provenance["claims"][field] = numeric_equivalent
                    manifest["ci_runtime_provenance"] = provenance
                    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                    with self.assertRaisesRegex(
                        DISCLOSURE.DisclosureError,
                        "changed type from boolean to number",
                    ):
                        DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_nonstandard_json_numbers_fail_closed(self) -> None:
        for nonstandard_number in ("NaN", "Infinity", "-Infinity"):
            with (
                self.subTest(nonstandard_number=nonstandard_number),
                tempfile.TemporaryDirectory() as tmp,
            ):
                bundle = self._bundle(Path(tmp))
                manifest_path = bundle / "provenance" / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["ci_runtime_provenance"] = self._ci_runtime_provenance(
                    manifest["commit_sha"]
                )
                candidate = json.dumps(manifest)
                self.assertEqual(candidate.count('"run_id": 123'), 1)
                manifest_path.write_text(
                    candidate.replace(
                        '"run_id": 123', f'"run_id": {nonstandard_number}'
                    ),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(
                    DISCLOSURE.DisclosureError, "non-finite number"
                ):
                    DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_runtime_provenance_owned_objects_require_exact_fields(self) -> None:
        for label, path in (
            ("root", ()),
            ("source_ci", ("source_ci",)),
            ("contract_artifact", ("source_ci", "contract_artifact")),
            ("runtime_image", ("runtime_image",)),
            (
                "runtime_input_projection",
                ("runtime_image", "runtime_input_projection"),
            ),
            ("claims", ("claims",)),
        ):
            with self.subTest(label=label):
                provenance = self._ci_runtime_provenance()
                owned_object = provenance
                for segment in path:
                    owned_object = owned_object[segment]
                owned_object["unreviewed_extra"] = "redacted"
                with self.assertRaisesRegex(
                    DISCLOSURE.DisclosureError, "exact reviewed fields"
                ):
                    DISCLOSURE._validate_ci_runtime_provenance(
                        provenance, "ci_runtime_provenance"
                    )

    def test_ci_runtime_provenance_binds_enclosing_commit_and_image(self) -> None:
        for mutation, expected in (
            ("head", "commit identity"),
            ("image", "runtime image identity"),
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                bundle = self._bundle(Path(tmp))
                manifest_path = bundle / "provenance" / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                provenance = self._ci_runtime_provenance(manifest["commit_sha"])
                if mutation == "head":
                    provenance["source_ci"]["head_sha"] = "e" * 40
                    provenance["runtime_image"]["image_build_sha"] = "e" * 40
                else:
                    manifest["container_digest"] = (
                        "ghcr.io/equilens-labs/fl-bsa-runtime@sha256:" + "e" * 64
                    )
                manifest["ci_runtime_provenance"] = provenance
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(DISCLOSURE.DisclosureError, expected):
                    DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_null_redaction_of_reviewed_object_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            manifest_path = bundle / "provenance" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["capabilities"] = None
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_reviewed_broken_correlation_aggregate_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            certificate_path = (
                bundle / "certificates" / "synthetic_quality_certificate.json"
            )
            certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
            certificate["correlation_analysis"]["broken_correlations"] = [
                {
                    "column1": "age",
                    "column2": "credit_score",
                    "difference": 0.2,
                    "real_correlation": 0.3,
                    "synthetic_correlation": 0.1,
                }
            ]
            certificate_path.write_text(json.dumps(certificate), encoding="utf-8")
            DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_unreviewed_broken_correlation_column_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            certificate_path = (
                bundle / "certificates" / "synthetic_quality_certificate.json"
            )
            certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
            sentinel = "never-reviewed-private-column"
            certificate["correlation_analysis"]["broken_correlations"] = [
                {
                    "column1": "age",
                    "column2": sentinel,
                    "difference": 0.2,
                    "real_correlation": 0.3,
                    "synthetic_correlation": 0.1,
                }
            ]
            certificate_path.write_text(json.dumps(certificate), encoding="utf-8")
            with self.assertRaisesRegex(
                DISCLOSURE.DisclosureError, "outside the reviewed public schema"
            ) as raised:
                DISCLOSURE.validate_bundle(bundle, ROOT)
            self.assertNotIn(sentinel, str(raised.exception))

    def test_reviewed_range_violation_aggregate_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            certificate_path = (
                bundle / "certificates" / "synthetic_quality_certificate.json"
            )
            certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
            certificate["statistical_comparison"]["range_violations"] = {
                "debt_to_income": {
                    "real_range": [0.0, 0.5],
                    "synthetic_range": [0.0, 0.6],
                    "violation_type": "out_of_bounds",
                }
            }
            certificate_path.write_text(json.dumps(certificate), encoding="utf-8")
            DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_unreviewed_range_violation_column_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            certificate_path = (
                bundle / "certificates" / "synthetic_quality_certificate.json"
            )
            certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
            sentinel = "never-reviewed-private-column"
            certificate["statistical_comparison"]["range_violations"] = {
                sentinel: {
                    "real_range": [0.0, 0.5],
                    "synthetic_range": [0.0, 0.6],
                    "violation_type": "out_of_bounds",
                }
            }
            certificate_path.write_text(json.dumps(certificate), encoding="utf-8")
            with self.assertRaisesRegex(
                DISCLOSURE.DisclosureError, "outside the reviewed public schema"
            ) as raised:
                DISCLOSURE.validate_bundle(bundle, ROOT)
            self.assertNotIn(sentinel, str(raised.exception))

    def test_range_column_check_survives_redacted_correlation_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            certificate_path = (
                bundle / "certificates" / "synthetic_quality_certificate.json"
            )
            certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
            sentinel = "private-person@example.com"
            certificate["correlation_analysis"] = None
            certificate["statistical_comparison"]["range_violations"] = {
                sentinel: {
                    "real_range": [0.0, 0.5],
                    "synthetic_range": [0.0, 0.6],
                    "violation_type": "out_of_bounds",
                }
            }
            certificate_path.write_text(json.dumps(certificate), encoding="utf-8")
            with self.assertRaisesRegex(
                DISCLOSURE.DisclosureError, "outside the reviewed public schema"
            ) as raised:
                DISCLOSURE.validate_bundle(bundle, ROOT)
            self.assertNotIn(sentinel, str(raised.exception))

    def test_range_violation_null_bound_fails_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            certificate_path = (
                bundle / "certificates" / "synthetic_quality_certificate.json"
            )
            certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
            certificate["statistical_comparison"]["range_violations"] = {
                "age": {
                    "real_range": [None, 0.5],
                    "synthetic_range": [0.0, 0.6],
                    "violation_type": "out_of_bounds",
                }
            }
            certificate_path.write_text(json.dumps(certificate), encoding="utf-8")
            with self.assertRaisesRegex(
                DISCLOSURE.DisclosureError, "only finite numbers"
            ):
                DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_sensitive_key_tokens_are_rejected_and_redacted(self) -> None:
        sentinel = "backup_api_key_material"
        with self.assertRaisesRegex(
            DISCLOSURE.DisclosureError, "forbidden sensitive field"
        ) as raised:
            DISCLOSURE._validate_structure(
                {sentinel: "redacted"}, {sentinel: "reviewed"}, "test"
            )
        self.assertNotIn(sentinel, str(raised.exception))

    def test_new_nested_field_and_sensitive_content_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            manifest_path = bundle / "provenance" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["unreviewed_customer_export"] = {"email": "person@example.com"}
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            sentinel = "unreviewed_customer_export"
            with self.assertRaisesRegex(
                DISCLOSURE.DisclosureError, "outside the reviewed public schema"
            ) as raised:
                DISCLOSURE.validate_bundle(bundle, ROOT)
            self.assertNotIn(sentinel, str(raised.exception))

    def test_known_string_field_still_rejects_private_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            manifest_path = bundle / "provenance" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            sentinel = "/home/private-operator"
            manifest["commit_sha"] = sentinel
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                DISCLOSURE.DisclosureError, "Unix home path"
            ) as raised:
                DISCLOSURE.validate_bundle(bundle, ROOT)
            self.assertNotIn(sentinel, str(raised.exception))

    def test_current_github_token_formats_are_rejected_and_redacted(self) -> None:
        tokens = (
            "github_pat_11AA22BB33CC44DD55EE66FF77GG88HH99II",
            "ghs_123456_eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiIxMjM0NTYifQ.signature1234567890",
            "ghp_" + "A" * 20 + "_" + "B" * 20,
            "gho_" + "A" * 20 + "_" + "B" * 20,
            "ghu_" + "A" * 20 + "_" + "B" * 20,
            "ghr_" + "A" * 20 + "_" + "B" * 20,
            "ghs_" + "A" * 20 + "_" + "B" * 20,
            "ghs_" + "A" * 39 + "-",
        )
        for sentinel in tokens:
            with (
                self.subTest(prefix=sentinel.split("_", 1)[0]),
                tempfile.TemporaryDirectory() as tmp,
            ):
                bundle = self._bundle(Path(tmp))
                manifest_path = bundle / "provenance" / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["run_id"] = sentinel
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(
                    DISCLOSURE.DisclosureError, "GitHub .*token"
                ) as raised:
                    DISCLOSURE.validate_bundle(bundle, ROOT)
                self.assertNotIn(sentinel, str(raised.exception))

    def test_tex_control_sequence_in_csv_is_rejected_and_redacted(self) -> None:
        for sentinel in (
            "\\input{private-evidence}",
            "\\input_private-evidence",
            "\\input1",
            "\\write18x",
            "\\write 018{private-evidence}",
        ):
            with self.subTest(value=sentinel), tempfile.TemporaryDirectory() as tmp:
                bundle = self._bundle(Path(tmp))
                csv_path = bundle / "intake" / "metrics_long.csv"
                rows = list(
                    csv.reader(csv_path.read_text(encoding="utf-8").splitlines())
                )
                rows[1][0] = sentinel
                with csv_path.open("w", encoding="utf-8", newline="") as handle:
                    csv.writer(handle, lineterminator="\n").writerows(rows)
                with self.assertRaisesRegex(
                    DISCLOSURE.DisclosureError, "TeX control sequence"
                ) as raised:
                    DISCLOSURE.validate_bundle(bundle, ROOT)
                self.assertNotIn(sentinel, str(raised.exception))

    def test_csv_column_expansion_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            csv_path = bundle / "intake" / "metrics_long.csv"
            rows = list(csv.reader(csv_path.read_text(encoding="utf-8").splitlines()))
            rows[0].append("subject_id")
            for row in rows[1:]:
                row.append("private-subject")
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                csv.writer(handle, lineterminator="\n").writerows(rows)
            with self.assertRaisesRegex(
                DISCLOSURE.DisclosureError, "columns are not the reviewed public schema"
            ):
                DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_duplicate_json_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            manifest_path = bundle / "provenance" / "manifest.json"
            manifest_path.write_text(
                '{"schema_version":"wp-intake.v1","schema_version":"bypass"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(DISCLOSURE.DisclosureError, "duplicate key"):
                DISCLOSURE.validate_bundle(bundle, ROOT)

    def test_rejection_redacts_private_ip_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle(Path(tmp))
            manifest_path = bundle / "provenance" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            sentinel = "10.23.45.67"
            manifest["commit_sha"] = sentinel
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                DISCLOSURE.DisclosureError, "private IP address"
            ) as raised:
                DISCLOSURE.validate_bundle(bundle, ROOT)
            self.assertNotIn(sentinel, str(raised.exception))

    def test_rejection_covers_and_redacts_private_ipv6(self) -> None:
        for sentinel in ("fd00::1", "::1"):
            with self.subTest(address=sentinel), tempfile.TemporaryDirectory() as tmp:
                bundle = self._bundle(Path(tmp))
                manifest_path = bundle / "provenance" / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["commit_sha"] = sentinel
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(
                    DISCLOSURE.DisclosureError, "private IP address"
                ) as raised:
                    DISCLOSURE.validate_bundle(bundle, ROOT)
                self.assertNotIn(sentinel, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
