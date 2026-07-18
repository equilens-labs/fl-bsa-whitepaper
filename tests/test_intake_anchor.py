import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ONLY_COMMIT = "e93a0fef4c88d7cb4c2c38df6f7dd26a11b75837"
MODULE_PATH = ROOT / "scripts" / "intake_anchor.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("intake_anchor_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
ANCHOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANCHOR)


class IntakeAnchorTests(unittest.TestCase):
    maxDiff = None

    def _fixture(self, root: Path, workflow: str) -> tuple[Path, Path, dict]:
        product_sha = "a" * 40
        base_commit = "b" * 40
        run_id = "123456789"
        bundle_sha = "c" * 64
        artifact = ANCHOR.PRIMARY_ARTIFACT
        bundle_filename = ANCHOR.PRIMARY_BUNDLE
        manifest = {
            "schema_version": "wp-intake.v1",
            "commit_sha": product_sha,
            "whitepaper_consumer": {
                "schema_version": "flbsa.whitepaper_consumer.v3",
                "repo": ANCHOR.WHITEPAPER_REPO,
                "base_commit": base_commit,
                "producer": {
                    "repo": ANCHOR.PRODUCER_REPO,
                    "workflow": workflow,
                    "artifact": artifact,
                    "bundle_filename": bundle_filename,
                    "bundle_sha256": bundle_sha,
                    "branch": "main",
                    "run_id": run_id,
                    "run_attempt": "1",
                    "head_sha": product_sha,
                    "artifact_id": "456",
                    "artifact_digest": "sha256:" + "d" * 64,
                },
            },
        }
        pack_intent = {
            "schema_version": "wp.pack_intent.v1",
            "purpose": "intake",
            "evidence_grade": False,
            "certificate_signing_expected": False,
        }
        manifest_path = root / "manifest.json"
        pack_path = root / "pack_intent.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        pack_path.write_text(json.dumps(pack_intent), encoding="utf-8")
        kwargs = {
            "manifest_path": manifest_path,
            "pack_intent_path": pack_path,
            "producer_repo": ANCHOR.PRODUCER_REPO,
            "producer_workflow": workflow,
            "producer_branch": "main",
            "producer_run_id": run_id,
            "producer_run_attempt": "1",
            "producer_head_sha": product_sha,
            "producer_artifact": artifact,
            "producer_artifact_id": "456",
            "producer_artifact_digest": "sha256:" + "d" * 64,
            "bundle_filename": bundle_filename,
            "bundle_sha256": bundle_sha,
            "whitepaper_repo": ANCHOR.WHITEPAPER_REPO,
            "whitepaper_commit": base_commit,
        }
        return manifest_path, pack_path, kwargs

    def test_nightly_snapshot_is_deterministic_and_rolling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, _, kwargs = self._fixture(Path(tmp), ANCHOR.NIGHTLY_WORKFLOW)
            first = ANCHOR.build_snapshot_record(**kwargs)
            second = ANCHOR.build_snapshot_record(**kwargs)

        self.assertEqual(first, second)
        self.assertRegex(first["snapshot_id"], r"^[0-9a-f]{64}$")
        self.assertEqual("rolling_history", first["persistence"]["mode"])
        self.assertEqual(ANCHOR.ROLLING_BRANCH, first["persistence"]["branch"])
        self.assertIs(first["persistence"]["workflow_rewrite_allowed"], True)
        self.assertIs(first["persistence"]["repository_admin_mutable"], True)
        self.assertIs(first["claims"]["customer_evidence_eligible"], False)
        self.assertEqual("a" * 40, first["producer"]["head_sha"])

    def test_release_snapshot_branch_is_workflow_write_once_and_run_specific(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, _, kwargs = self._fixture(Path(tmp), ANCHOR.RELEASE_WORKFLOW)
            record = ANCHOR.build_snapshot_record(**kwargs)

        self.assertEqual(
            "workflow_write_once_release_snapshot", record["persistence"]["mode"]
        )
        self.assertEqual(
            "chore/wp-intake-aaaaaaaaaaaa-123456789",
            record["persistence"]["branch"],
        )
        self.assertIs(record["persistence"]["workflow_rewrite_allowed"], False)
        self.assertIs(record["persistence"]["repository_admin_mutable"], True)

    def test_snapshot_rejects_weakened_or_inconsistent_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path, pack_path, kwargs = self._fixture(
                root, ANCHOR.NIGHTLY_WORKFLOW
            )

            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            pack["evidence_grade"] = True
            pack_path.write_text(json.dumps(pack), encoding="utf-8")
            with self.assertRaisesRegex(ANCHOR.AnchorError, "evidence_grade"):
                ANCHOR.build_snapshot_record(**kwargs)

            pack["evidence_grade"] = False
            pack_path.write_text(json.dumps(pack), encoding="utf-8")
            wrong_bundle = {**kwargs, "bundle_filename": ANCHOR.LEGACY_BUNDLE}
            with self.assertRaisesRegex(ANCHOR.AnchorError, "bundle filename"):
                ANCHOR.build_snapshot_record(**wrong_bundle)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["whitepaper_consumer"]["producer"]["run_id"] = "999"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ANCHOR.AnchorError, "consumer stamp"):
                ANCHOR.build_snapshot_record(**kwargs)

            manifest["whitepaper_consumer"]["producer"]["run_id"] = kwargs[
                "producer_run_id"
            ]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            wrong_head = {**kwargs, "producer_head_sha": "d" * 40}
            with self.assertRaisesRegex(ANCHOR.AnchorError, "run head SHA versus"):
                ANCHOR.build_snapshot_record(**wrong_head)

    def test_snapshot_enforces_artifact_run_attempt_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path, _, kwargs = self._fixture(root, ANCHOR.NIGHTLY_WORKFLOW)

            unqualified_retry = {**kwargs, "producer_run_attempt": "2"}
            with self.assertRaisesRegex(ANCHOR.AnchorError, "restricted.*attempt 1"):
                ANCHOR.build_snapshot_record(**unqualified_retry)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            producer = manifest["whitepaper_consumer"]["producer"]
            producer["run_attempt"] = "3"
            producer["artifact"] = f"{ANCHOR.PRIMARY_ARTIFACT}-2"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            mismatched_qualification = {
                **kwargs,
                "producer_run_attempt": "3",
                "producer_artifact": f"{ANCHOR.PRIMARY_ARTIFACT}-2",
            }
            with self.assertRaisesRegex(
                ANCHOR.AnchorError, "run-attempt qualification"
            ):
                ANCHOR.build_snapshot_record(**mismatched_qualification)

    def test_checked_in_stable_anchor_validates_and_exports_deterministically(
        self,
    ) -> None:
        anchor_path = ROOT / "baselines" / "stable-v5-characterization.json"
        anchor = ANCHOR.validate_anchor(anchor_path, ROOT)
        expected_sha = anchor["export"]["expected_sha256"]

        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.zip"
            second = Path(tmp) / "second.zip"
            self.assertEqual(
                expected_sha, ANCHOR.export_anchor(anchor_path, ROOT, first)
            )
            self.assertEqual(
                expected_sha, ANCHOR.export_anchor(anchor_path, ROOT, second)
            )
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(
                expected_sha, hashlib.sha256(first.read_bytes()).hexdigest()
            )
            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
                compression_types = {info.compress_type for info in archive.infolist()}

        self.assertEqual(names, sorted(names))
        self.assertIn("provenance/manifest.json", names)
        self.assertIn("intake/pack_intent.json", names)
        self.assertIn("certificates/synthetic_quality_certificate.json", names)
        self.assertNotIn("intake/whitepaper_snapshot.json", names)
        self.assertEqual({zipfile.ZIP_STORED}, compression_types)

    def test_publication_projection_accepts_pr26_archive_only_tree_change(self) -> None:
        anchor_path = ROOT / "baselines" / "stable-v5-characterization.json"
        anchor = ANCHOR.validate_anchor(anchor_path, ROOT)
        historical_commit = anchor["consumer"]["intake_commit"]

        historical = ANCHOR.build_publication_input_projection(
            anchor, ROOT, historical_commit
        )
        archived = ANCHOR.build_publication_input_projection(
            anchor, ROOT, ARCHIVE_ONLY_COMMIT
        )
        historical_intake_tree = ANCHOR._git(
            ROOT, "rev-parse", f"{historical_commit}:intake"
        )
        archived_intake_tree = ANCHOR._git(
            ROOT, "rev-parse", f"{ARCHIVE_ONLY_COMMIT}:intake"
        )

        self.assertNotEqual(historical_intake_tree, archived_intake_tree)
        self.assertEqual(historical, archived)
        publication_source = ANCHOR.validate_publication_source(
            anchor, ROOT, ARCHIVE_ONLY_COMMIT
        )
        self.assertEqual(
            archived_intake_tree, publication_source["intake_tree_git_oid"]
        )
        self.assertEqual(
            anchor["publication_inputs"]["expected_sha256"],
            publication_source["publication_input_projection"]["sha256"],
        )

    def test_publication_projection_excludes_traceability_archive(self) -> None:
        source = ROOT / "baselines" / "stable-v5-characterization.json"
        anchor = json.loads(source.read_text(encoding="utf-8"))
        anchor["publication_inputs"]["paths"].append("intake/archive")
        anchor["publication_inputs"]["paths"].sort()

        with self.assertRaisesRegex(ANCHOR.AnchorError, "traceability archive"):
            ANCHOR.build_publication_input_projection(
                anchor, ROOT, anchor["consumer"]["intake_commit"]
            )

    def test_publication_projection_binds_model_hyperparameters(self) -> None:
        anchor_path = ROOT / "baselines" / "stable-v5-characterization.json"
        anchor = ANCHOR.validate_anchor(anchor_path, ROOT)
        self.assertIn(
            "intake/model_hyperparams.yaml", anchor["publication_inputs"]["paths"]
        )

    def test_anchor_rejects_claim_boundary_tampering(self) -> None:
        source = ROOT / "baselines" / "stable-v5-characterization.json"
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload["claims"]["customer_evidence_eligible"] = True
        with tempfile.TemporaryDirectory() as tmp:
            tampered = Path(tmp) / "anchor.json"
            tampered.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ANCHOR.AnchorError, "customer_evidence_eligible"
            ):
                ANCHOR.validate_anchor(tampered, ROOT)


if __name__ == "__main__":
    unittest.main()
