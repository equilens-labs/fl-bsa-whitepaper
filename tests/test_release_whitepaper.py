import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import release_whitepaper as release_wp  # noqa: E402

PRODUCT_SHA = "a" * 40
WHITEPAPER_SHA = "b" * 40
BUNDLE_SHA = "c" * 64
CONTRACT_SHA = "d" * 64
ARTIFACT_DIGEST = "sha256:" + "e" * 64


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_id(producer: dict, whitepaper: dict) -> str:
    identity = {
        "producer_repo": producer["repo"],
        "producer_workflow": producer["workflow"],
        "producer_branch": producer["branch"],
        "producer_run_id": producer["run_id"],
        "producer_run_attempt": producer["run_attempt"],
        "producer_head_sha": producer["head_sha"],
        "producer_artifact": producer["artifact"],
        "producer_artifact_id": producer["artifact_id"],
        "producer_artifact_digest": producer["artifact_digest"],
        "producer_contract_sha256": producer["contract_sha256"],
        "product_sha": producer["product_sha"],
        "bundle_filename": producer["bundle_filename"],
        "bundle_sha256": producer["bundle_sha256"],
        "whitepaper_repo": whitepaper["repo"],
        "whitepaper_base_commit": whitepaper["base_commit"],
    }
    encoded = (
        json.dumps(identity, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class ReleaseWhitepaperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifest_path = self.root / "manifest.json"
        self.pack_path = self.root / "pack_intent.json"
        self.snapshot_path = self.root / "whitepaper_snapshot.json"
        self.manifest = {
            "schema_version": "wp-intake.v1",
            "software_version": "v5.0.3",
            "build_ref": "v5.0.3",
            "commit_sha": PRODUCT_SHA,
            "code_commit": PRODUCT_SHA,
            "source_commit": PRODUCT_SHA,
            "software_commit": PRODUCT_SHA,
            "generator_backend": {"backend_id": "first_party_evidence_native"},
        }
        self.pack = {
            "schema_version": "wp.pack_intent.v1",
            "purpose": "intake",
            "evidence_grade": False,
            "certificate_signing_expected": False,
        }
        _write_json(self.manifest_path, self.manifest)
        _write_json(self.pack_path, self.pack)
        producer = {
            "repo": "equilens-labs/fl-bsa",
            "workflow": "release-evidence.yml",
            "branch": "main",
            "run_id": "12345",
            "run_attempt": "2",
            "head_sha": PRODUCT_SHA,
            "artifact": "wp-intake-bundle-v4-2",
            "artifact_id": "67890",
            "artifact_digest": ARTIFACT_DIGEST,
            "contract_sha256": CONTRACT_SHA,
            "product_sha": PRODUCT_SHA,
            "bundle_filename": "WhitePaper_Intake_Bundle_v4.zip",
            "bundle_sha256": BUNDLE_SHA,
        }
        whitepaper = {
            "repo": "equilens-labs/fl-bsa-whitepaper",
            "base_commit": WHITEPAPER_SHA,
            "manifest_sha256": _sha(self.manifest_path),
            "pack_intent_sha256": _sha(self.pack_path),
        }
        self.snapshot = {
            "schema_version": "flbsa.whitepaper_intake_snapshot.v3",
            "snapshot_id": _snapshot_id(producer, whitepaper),
            "claims": {
                "customer_evidence_eligible": False,
                "customer_evidence_disposition": "characterization_only",
                "publication_status": "candidate_not_published",
            },
            "producer": producer,
            "whitepaper": whitepaper,
        }
        _write_json(self.snapshot_path, self.snapshot)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(self) -> dict:
        return release_wp.build_identity(
            snapshot_path=self.snapshot_path,
            manifest_path=self.manifest_path,
            pack_intent_path=self.pack_path,
            whitepaper_commit=WHITEPAPER_SHA,
            whitepaper_run_id="24680",
            whitepaper_run_attempt="1",
        )

    def test_build_identity_binds_release_and_both_workflow_runs(self) -> None:
        identity = self.build()
        self.assertEqual(identity["release"]["tag"], "v5.0.3")
        self.assertEqual(identity["product"]["run_id"], "12345")
        self.assertEqual(identity["whitepaper"]["run_id"], "24680")
        self.assertEqual(identity["whitepaper"]["branch"], "main")
        self.assertEqual(
            identity["intake"]["snapshot_id"], self.snapshot["snapshot_id"]
        )
        self.assertFalse(identity["claims"]["customer_evidence_eligible"])

    def test_rejects_nightly_intake(self) -> None:
        self.snapshot["producer"]["workflow"] = "wp-evidence-nightly.yml"
        self.snapshot["snapshot_id"] = _snapshot_id(
            self.snapshot["producer"], self.snapshot["whitepaper"]
        )
        _write_json(self.snapshot_path, self.snapshot)
        with self.assertRaisesRegex(
            release_wp.ReleaseWhitepaperError, "producer workflow"
        ):
            self.build()

    def test_rejects_non_release_software_version(self) -> None:
        self.manifest["software_version"] = "5.0.3"
        self.manifest["build_ref"] = "5.0.3"
        _write_json(self.manifest_path, self.manifest)
        self.snapshot["whitepaper"]["manifest_sha256"] = _sha(self.manifest_path)
        self.snapshot["snapshot_id"] = _snapshot_id(
            self.snapshot["producer"], self.snapshot["whitepaper"]
        )
        _write_json(self.snapshot_path, self.snapshot)
        with self.assertRaisesRegex(release_wp.ReleaseWhitepaperError, "release tag"):
            self.build()

    def test_rejects_missing_product_commit_alias(self) -> None:
        del self.manifest["software_commit"]
        _write_json(self.manifest_path, self.manifest)
        self.snapshot["whitepaper"]["manifest_sha256"] = _sha(self.manifest_path)
        self.snapshot["snapshot_id"] = _snapshot_id(
            self.snapshot["producer"], self.snapshot["whitepaper"]
        )
        _write_json(self.snapshot_path, self.snapshot)
        with self.assertRaisesRegex(
            release_wp.ReleaseWhitepaperError, "manifest software_commit"
        ):
            self.build()

    def test_rejects_noncanonical_release_artifact_name(self) -> None:
        self.snapshot["producer"]["artifact"] = "wp-intake-bundle-v4"
        self.snapshot["snapshot_id"] = _snapshot_id(
            self.snapshot["producer"], self.snapshot["whitepaper"]
        )
        _write_json(self.snapshot_path, self.snapshot)
        with self.assertRaisesRegex(
            release_wp.ReleaseWhitepaperError, "product artifact name"
        ):
            self.build()

    def test_rejects_claim_boundary_expansion(self) -> None:
        self.snapshot["claims"]["customer_evidence_eligible"] = True
        _write_json(self.snapshot_path, self.snapshot)
        with self.assertRaisesRegex(
            release_wp.ReleaseWhitepaperError, "customer_evidence_eligible"
        ):
            self.build()

    def test_finalize_binds_pdf_digest_and_visible_identities(self) -> None:
        identity = self.build()
        identity_path = self.root / "identity.json"
        pdf_path = self.root / "whitepaper.pdf"
        _write_json(identity_path, identity)
        pdf_path.write_bytes(b"deterministic fake PDF bytes")
        text = (
            f"Product v5.0.3 at {PRODUCT_SHA} "
            "Evidence release workflow run 12345 (attempt 2) "
            "Generator backend first_party_evidence_native "
            f"Whitepaper source {WHITEPAPER_SHA} "
            "Whitepaper workflow run 24680 (attempt 1) "
            f"Intake snapshot {self.snapshot['snapshot_id']} "
            f"Intake bundle SHA-256 {BUNDLE_SHA} "
            "customer_evidence_eligible=false "
            "customer_evidence_disposition=characterization_only "
            "publication_status=candidate_not_published "
            "DEMO / EVALUATION ONLY"
        )
        with patch.object(release_wp, "extract_text", return_value=text):
            result = release_wp.finalize(identity_path, pdf_path)
        self.assertEqual(result["schema_version"], "flbsa.release_whitepaper.v1")
        self.assertEqual(result["pdf"]["filename"], "whitepaper.pdf")
        self.assertEqual(result["pdf"]["sha256"], _sha(pdf_path))
        self.assertEqual(result["pdf"]["size_bytes"], pdf_path.stat().st_size)

    def test_regulatory_table_is_generated_from_every_exact_escaped_cell(self) -> None:
        matrix = self.root / "regulatory_matrix.csv"
        fieldnames = [
            "framework",
            "citation",
            "requirement_text",
            "control_assurance",
            "evidence_artifact",
            "owner",
            "status",
            "notes",
        ]
        rows = [
            {
                "framework": "Framework A & Co.",
                "citation": "Citation A #1",
                "requirement_text": "Requirement A %",
                "control_assurance": "Control A_100%",
                "evidence_artifact": "evidence/A_$1.json",
                "owner": "Owner A^",
                "status": "Status A~",
                "notes": r"Notes A {review} \ path",
            },
            {
                "framework": "Framework B",
                "citation": "Citation B",
                "requirement_text": "Requirement B",
                "control_assurance": "Control B",
                "evidence_artifact": "Evidence B",
                "owner": "Owner B",
                "status": "Status B",
                "notes": "Notes B original",
            },
        ]

        def write_rows() -> None:
            with matrix.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

        write_rows()
        rendered = release_wp.render_regulatory_table(matrix)
        for expected in (
            r"Framework A \& Co.",
            r"Citation A \#1",
            r"Requirement A \%",
            r"Control A\_100\%",
            r"evidence/A\_\$1.json",
            r"Owner A\textasciicircum{}",
            r"Status A\textasciitilde{}",
            r"Notes A \{review\} \textbackslash{} path",
            "Framework B",
            "Citation B",
            "Requirement B",
            "Control B",
            "Evidence B",
            "Owner B",
            "Status B",
            "Notes B original",
        ):
            self.assertIn(expected, rendered)

        rows[0]["citation"] = "Citation A changed"
        write_rows()
        citation_changed = release_wp.render_regulatory_table(matrix)
        self.assertNotEqual(rendered, citation_changed)
        self.assertIn("Citation A changed", citation_changed)
        self.assertNotIn(r"Citation A \#1", citation_changed)

        rows[1]["notes"] = "Notes B changed"
        write_rows()
        later_row_changed = release_wp.render_regulatory_table(matrix)
        self.assertNotEqual(citation_changed, later_row_changed)
        self.assertIn("Notes B changed", later_row_changed)
        self.assertNotIn("Notes B original", later_row_changed)

    def test_regulatory_table_rejects_schema_and_cell_ambiguity(self) -> None:
        matrix = self.root / "regulatory_matrix.csv"
        matrix.write_text("framework,citation\nEU AI Act,Art. 10\n", encoding="utf-8")
        with self.assertRaisesRegex(
            release_wp.ReleaseWhitepaperError, "columns must exactly match"
        ):
            release_wp.render_regulatory_table(matrix)

        matrix.write_text(
            "framework,citation,requirement_text,control_assurance,evidence_artifact,owner,status,notes\n"
            "EU AI Act,Art. 10,Requirement,Control,Evidence,Owner, ,Notes\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            release_wp.ReleaseWhitepaperError, "must be non-empty"
        ):
            release_wp.render_regulatory_table(matrix)

        for unsupported in ("check ✓", "greater ≥", "less ≤", "漢字"):
            with self.subTest(unsupported=unsupported):
                matrix.write_text(
                    "framework,citation,requirement_text,control_assurance,evidence_artifact,owner,status,notes\n"
                    f"EU AI Act,Art. 10,{unsupported},Control,Evidence,Owner,review_required,Notes\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(
                    release_wp.ReleaseWhitepaperError,
                    "must be ASCII text for the reviewed pdfLaTeX release path",
                ):
                    release_wp.render_regulatory_table(matrix)

    def test_write_identity_tex_emits_every_visible_exact_binding(self) -> None:
        identity = release_wp.build_identity(
            snapshot_path=self.snapshot_path,
            manifest_path=self.manifest_path,
            pack_intent_path=self.pack_path,
            whitepaper_commit=WHITEPAPER_SHA,
            whitepaper_run_id="24680",
            whitepaper_run_attempt="3",
        )
        output = self.root / "release_identity.tex"
        release_wp.write_identity_tex(identity, output)
        lines = output.read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            [
                "% Generated by scripts/release_whitepaper.py; do not edit.",
                r"\newcommand{\ProductReleaseTag}{v5.0.3}",
                rf"\newcommand{{\ProductCommit}}{{{PRODUCT_SHA}}}",
                r"\newcommand{\EvidenceReleaseRunId}{12345}",
                r"\newcommand{\EvidenceReleaseRunAttempt}{2}",
                r"\newcommand{\ReleaseGeneratorBackend}{first\_party\_evidence\_native}",
                rf"\newcommand{{\WhitepaperSourceCommit}}{{{WHITEPAPER_SHA}}}",
                r"\newcommand{\WhitepaperWorkflowRunId}{24680}",
                r"\newcommand{\WhitepaperWorkflowRunAttempt}{3}",
                rf"\newcommand{{\IntakeSnapshotId}}{{{self.snapshot['snapshot_id']}}}",
                rf"\newcommand{{\IntakeBundleSha}}{{{BUNDLE_SHA}}}",
            ],
            lines,
        )

    def test_release_assets_compile_only_the_generated_regulatory_table(self) -> None:
        root = Path(__file__).resolve().parents[1]
        makefile = (root / "Makefile").read_text(encoding="utf-8")
        appendix = (
            root / "release" / "sections" / "appendix_d_regulatory_matrix.tex"
        ).read_text(encoding="utf-8")
        self.assertIn("release-regulatory:", makefile)
        self.assertIn(
            "release-assets: release-claims-lint release-macros release-plots release-regulatory",
            makefile,
        )
        self.assertIn("scripts/lint_release_claims.py", makefile)
        self.assertIn("--matrix intake/regulatory_matrix.csv", makefile)
        self.assertIn(r"\input{release/includes/table_regulatory_matrix}", appendix)
        self.assertIn("are not adopted by this paper", appendix)


if __name__ == "__main__":
    unittest.main()
