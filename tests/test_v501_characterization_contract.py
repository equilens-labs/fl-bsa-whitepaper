import csv
import gzip
import hashlib
import io
import importlib.util
import json
import statistics
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_TAG = "v5.0.1"
PRODUCT_TAG_OBJECT = "3a0ea6e4faea9d61aabcedebab2a838624fb587d"
PRODUCT_COMMIT = "cc32b3a8d13cb75419b0dec1d4b9bdf5a3eb90c2"
PRODUCT_RUN_ID = 30765888408
PRIMARY_BUNDLE_SHA256 = (
    "f6a0bd9390565f7bd852b451e11b7384b1628c24caba02865b1ec94c1e263026"
)
PRIMARY_ARTIFACT_API_DIGEST = (
    "sha256:7241da6013653e96337c540d3670bed69c04454002f3e7d315a95e9c8e197615"
)
UTILITY_ARTIFACT_API_DIGEST = (
    "sha256:1ea221c8bb77313ac0fddfe7703496d191d666c0555fdb5d9b5d1d9f3e94e2f4"
)
UTILITY_ARTIFACT_NAME = "gold-full-artifacts"
UTILITY_FIXTURE_SHA256 = (
    "b04f721d789226723066b3d6ae70e4ab2a3fa17c825ef1d0e04d7d779571982b"
)
GOLD_ARTIFACT_API_DIGEST = (
    "sha256:4fc12773c6410df3e6b4a1b1ded43c14a4ef2c84d013f09ec42d3ba7df1c7988"
)
SRG_METHOD = "conservative_wilson_endpoint_difference"
INTERNAL_AIR_SCREEN = 0.80
UTILITY_SUMMARY_PATH = "evidence/v5.0.1/utility/utility_summary.json"
UTILITY_SUMMARY_SHA256 = (
    "2b05a4a2b7ce2d798b9156ed5f837efe890ee87e4f5e914497724802636e4595"
)


def _read_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _load_module(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    original_sys_path = sys.path.copy()
    try:
        sys.path.insert(0, str(path.parent))
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_sys_path
    return module


def _rewrite_companion_members(
    source: Path, output: Path, replacements: dict[str, bytes]
) -> None:
    with zipfile.ZipFile(source) as archive:
        members = {
            info.filename: archive.read(info.filename)
            for info in archive.infolist()
        }
    manifest = json.loads(members["MANIFEST.json"].decode("utf-8"))
    for member, replacement in replacements.items():
        members[member] = replacement
        entry = next(row for row in manifest["files"] if row["path"] == member)
        entry["size"] = len(replacement)
        entry["sha256"] = hashlib.sha256(replacement).hexdigest()
    members["MANIFEST.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name, data in sorted(members.items()):
            archive.writestr(name, data)


def _rewrite_companion_member(
    source: Path, output: Path, member: str, replacement: bytes
) -> None:
    _rewrite_companion_members(source, output, {member: replacement})


def _sample_band(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "min": min(values),
        "mean": statistics.mean(values),
        "max": max(values),
        "stdev": statistics.stdev(values),
    }


class V501CharacterizationContractTests(unittest.TestCase):
    maxDiff = None

    def test_exact_product_and_release_evidence_identity(self) -> None:
        identity = _read_json(
            "evidence/v5.0.1/publication/evidence_identity.json"
        )
        product = identity["product"]
        workflow = identity["producer_workflow"]
        intake = identity["primary_intake"]
        utility = identity["utility_source"]
        gold = identity["gold_robustness"]

        self.assertEqual(PRODUCT_TAG, product["tag"])
        self.assertEqual(PRODUCT_TAG_OBJECT, product["tag_object"])
        self.assertEqual(PRODUCT_COMMIT, product["commit"])
        self.assertEqual(PRODUCT_COMMIT, workflow["head_commit"])
        self.assertEqual(PRODUCT_RUN_ID, workflow["run_id"])
        self.assertEqual(1, workflow["attempt"])
        self.assertEqual("wp-intake-bundle-v4-1", intake["artifact_name"])
        self.assertEqual(8838967644, intake["artifact_id"])
        self.assertEqual(
            PRIMARY_ARTIFACT_API_DIGEST, intake["artifact_api_digest"]
        )
        self.assertEqual(PRIMARY_BUNDLE_SHA256, intake["bundle_sha256"])
        self.assertEqual(8839094646, utility["artifact_id"])
        self.assertEqual(UTILITY_ARTIFACT_NAME, utility["artifact_name"])
        self.assertEqual(
            UTILITY_ARTIFACT_API_DIGEST, utility["artifact_api_digest"]
        )
        self.assertEqual(UTILITY_FIXTURE_SHA256, utility["fixture_sha256"])
        self.assertEqual(8839160190, gold["artifact_id"])
        self.assertEqual(
            f"gold-robustness-{PRODUCT_COMMIT}-{PRODUCT_RUN_ID}",
            gold["artifact_name"],
        )
        self.assertEqual(
            GOLD_ARTIFACT_API_DIGEST, gold["artifact_api_digest"]
        )
        for field, relative in (
            (
                "evidence_manifest_sha256",
                "evidence/v5.0.1/robustness/evidence_manifest.json",
            ),
            (
                "index_sha256",
                "evidence/v5.0.1/robustness/robustness_index.csv",
            ),
            (
                "summary_sha256",
                "evidence/v5.0.1/robustness/robustness_summary_merged.json",
            ),
        ):
            self.assertEqual(
                gold[field], hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            )

        manifest = _read_json("intake/manifest.json")
        self.assertEqual(PRODUCT_COMMIT, manifest["source_commit"])
        self.assertEqual(PRODUCT_COMMIT, manifest["commit_sha"])

        utility_source = _read_json(
            "evidence/v5.0.1/utility/source_manifest.json"
        )
        self.assertEqual(
            "flbsa.whitepaper_utility_source.v1",
            utility_source["schema_version"],
        )
        self.assertEqual(
            {
                "api_digest": UTILITY_ARTIFACT_API_DIGEST,
                "artifact_id": "8839094646",
                "name": UTILITY_ARTIFACT_NAME,
                "repository": "equilens-labs/fl-bsa",
                "run_attempt": 1,
                "run_id": PRODUCT_RUN_ID,
                "workflow": "release-evidence.yml",
            },
            utility_source["artifact"],
        )
        self.assertEqual(
            {
                "gzip_sha256": (
                    "67785d0488d53d0c4a26f76f66ecb63bb582037ef207790752bd34e971831db9"
                ),
                "path_in_artifact": (
                    "artifacts/gold/20260802T203945Z/01_balanced/"
                    "original_data.csv"
                ),
                "rows": 5000,
                "sha256": UTILITY_FIXTURE_SHA256,
                "synthetic_fixture_only": True,
            },
            utility_source["fixture"],
        )
        self.assertEqual(
            {
                "commit": PRODUCT_COMMIT,
                "tag": PRODUCT_TAG,
                "tag_object": PRODUCT_TAG_OBJECT,
            },
            utility_source["product"],
        )

    def test_release_disposition_comes_from_the_snapshot_not_pack_intent(self) -> None:
        snapshot = _read_json("intake/archive/v5.0.1-release-30765888408.json")
        self.assertEqual(str(PRODUCT_RUN_ID), snapshot["producer"]["run_id"])
        self.assertIs(snapshot["claims"]["customer_evidence_eligible"], False)
        self.assertEqual(
            "characterization_only",
            snapshot["claims"]["customer_evidence_disposition"],
        )
        self.assertEqual(
            "candidate_not_published", snapshot["claims"]["publication_status"]
        )
        pack_intent = _read_json("intake/pack_intent.json")
        self.assertNotIn("customer_evidence_eligible", pack_intent)
        self.assertNotIn("customer_evidence_disposition", pack_intent)

    def test_corrected_srg_method_is_consistent_on_every_consumed_surface(self) -> None:
        slices = _read_json("intake/fairness_slices.json")
        for name, row in slices["slices"].items():
            with self.subTest(surface="fairness_slices", name=name):
                self.assertEqual(SRG_METHOD, row["srg"]["method"])

        uncertainty = _read_json("intake/metrics_uncertainty.json")
        fairness = uncertainty["fairness_uncertainty"]
        self.assertEqual(SRG_METHOD, fairness["gender"]["srg"]["method"])
        for name, row in fairness["race"]["pairs"].items():
            with self.subTest(surface="race", name=name):
                self.assertEqual(SRG_METHOD, row["srg"]["method"])

        for relative in ("intake/manifest.json", "intake/run_summary.json"):
            payload = _read_json(relative)
            self.assertEqual(
                SRG_METHOD,
                payload["inference"]["headline_interval_methods"]["srg"],
            )

        publication = _read_json(
            "evidence/v5.0.1/publication/characterization_summary.json"
        )["fairness"]
        self.assertIn("not_a_calibrated_95_percent_interval", publication["srg_range_scope"])
        for row in publication["slices"]:
            self.assertNotIn("srg_ci95", row)
            self.assertIn(
                "not_a_calibrated_95_percent_interval",
                row["srg_range_status"],
            )

    def test_race_configured_and_effective_references_are_not_conflated(self) -> None:
        race = _read_json("intake/metrics_uncertainty.json")[
            "fairness_uncertainty"
        ]["race"]
        self.assertEqual("white", race["configured_reference_group"])
        self.assertEqual("black", race["reference_group"])
        self.assertEqual(
            "highest_selection_rate_four_fifths",
            race["reference_group_selection_policy"],
        )
        self.assertEqual("other", race["worst_case_pair"])
        self.assertEqual(273, race["observed"]["min_group_n"])
        self.assertEqual(0.0273, race["observed"]["min_group_pct"])
        self.assertIs(race["display_in_main_pdf"], False)

        configured = yaml.safe_load(
            (ROOT / "config/fairness_config.yaml").read_text(encoding="utf-8")
        )["policy"]["display_race_in_main_pdf"]
        self.assertEqual(configured, race["policy"]["display_race_in_main_pdf"])
        self.assertLess(
            race["observed"]["min_group_n"], configured["min_group_n"]
        )
        self.assertLess(
            race["observed"]["min_group_pct"], configured["min_group_pct"]
        )

        summary = _read_json(
            "evidence/v5.0.1/publication/characterization_summary.json"
        )["fairness"]["race"]
        self.assertEqual("hispanic", summary["minimum_count_group"])
        self.assertEqual("other", summary["lowest_selection_rate_group"])
        self.assertEqual(300, summary["display_min_group_n"])
        self.assertEqual(0.05, summary["display_min_group_pct"])
        self.assertIs(summary["minimum_group_n_floor_met"], False)
        self.assertIs(summary["minimum_group_pct_floor_met"], False)
        self.assertEqual(
            [
                "minimum_observed_group_count_below_configured_display_floor",
                "minimum_observed_group_share_below_configured_display_floor",
            ],
            summary["suppression_reasons"],
        )
        self.assertIs(summary["air_intervals_multiplicity_adjusted"], False)
        self.assertEqual("holm_bonferroni", summary["air_p_value_adjustment"])

        appendix = (ROOT / "sections/appendix_a_sap.tex").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("The count condition is met", appendix)
        for macro in (
            r"\RaceDisplayMinGroupN{}",
            r"\RaceDisplayMinGroupPct{}",
            r"\RaceCountFloorRelation{}",
            r"\RaceShareFloorRelation{}",
        ):
            self.assertIn(macro, appendix)
        generated_macros = (
            ROOT / "includes/characterization_macros.tex"
        ).read_text(encoding="utf-8")
        for definition in (
            r"\newcommand{\RaceDisplayMinGroupN}{300}",
            r"\newcommand{\RaceDisplayMinGroupPct}{5.00}",
            r"\newcommand{\RaceCountFloorRelation}{fails}",
            r"\newcommand{\RaceShareFloorRelation}{fails}",
        ):
            self.assertIn(definition, generated_macros)
        all_sections = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "sections").glob("*.tex"))
        )
        self.assertNotIn("count condition is met", all_sections.lower())

    def test_point_and_interval_screen_relations_are_separate(self) -> None:
        slices = _read_json(
            "evidence/v5.0.1/publication/characterization_summary.json"
        )["fairness"]["slices"]
        by_id = {row["id"]: row for row in slices}
        self.assertEqual("below", by_id["historical"]["point_screen_relation"])
        self.assertEqual("crosses", by_id["historical"]["interval_screen_relation"])
        self.assertEqual(
            "entirely below",
            by_id["amplification"]["interval_screen_relation"],
        )
        self.assertEqual(
            "not_applicable_policy_determined",
            by_id["intrinsic"]["interval_screen_relation"],
        )
        self.assertEqual("policy_determined", by_id["intrinsic"]["inference_status"])
        self.assertEqual(
            "format_symmetry_only_not_inferential",
            by_id["intrinsic"]["air_interval_display_status"],
        )
        self.assertEqual(
            "format_symmetry_only_not_inferential",
            by_id["intrinsic"]["p_value_display_status"],
        )
        self.assertAlmostEqual(0.759080055358229, by_id["amplification"]["air"])
        self.assertAlmostEqual(1.0000283291063825, by_id["intrinsic"]["air"])
        results = (ROOT / "sections" / "06_results.tex").read_text(
            encoding="utf-8"
        )
        self.assertIn("shown only for table and figure", results)
        self.assertIn("interval is not multiplicity-adjusted", results)

    def test_quality_reports_both_branches_and_preserves_unevaluated_states(self) -> None:
        summary = _read_json(
            "evidence/v5.0.1/publication/characterization_summary.json"
        )
        quality = summary["quality"]
        self.assertEqual({"amplification", "intrinsic"}, set(quality))
        self.assertAlmostEqual(
            0.9061600112479465, quality["amplification"]["overall_quality_score"]
        )
        self.assertAlmostEqual(
            0.8996413774113724, quality["intrinsic"]["overall_quality_score"]
        )
        for branch in quality.values():
            self.assertEqual("not_evaluated", branch["certified_utility_status"])
            self.assertEqual("not_computed", branch["near_duplicate_status"])
            self.assertIs(branch["differential_privacy_claimed"], False)

    def test_gold_and_utility_seed_evidence_is_complete_and_bounded(self) -> None:
        summary = _read_json(
            "evidence/v5.0.1/publication/characterization_summary.json"
        )
        robustness = summary["robustness"]
        self.assertIs(robustness["complete"], True)
        self.assertEqual(40, robustness["total_runs"])
        self.assertEqual(40, robustness["total_passes"])
        self.assertEqual(4, len(robustness["scenarios"]))

        utility = summary["utility"]
        self.assertEqual(10, len(utility["synthetic_train_results"]))
        self.assertEqual(3500, utility["study"]["train_rows"])
        self.assertEqual(3500, utility["study"]["generated_rows_per_seed"])
        auc = utility["synthetic_train_bands"]["roc_auc"]
        self.assertAlmostEqual(0.5068372196683766, auc["mean"])
        self.assertLess(auc["max"], utility["real_train_baseline"]["roc_auc"])
        self.assertIs(utility["utility_established"], False)
        self.assertNotIn("roc_auc_retention", utility["synthetic_train_bands"])
        skill = utility["synthetic_train_bands"]["roc_auc_skill_retention"]
        expected_skill = (auc["mean"] - 0.5) / (
            utility["real_train_baseline"]["roc_auc"] - 0.5
        )
        self.assertAlmostEqual(expected_skill, skill["mean"])
        self.assertAlmostEqual(0.03441799798421121, skill["mean"])
        self.assertLess(skill["min"], 0)
        self.assertEqual(
            6,
            sum(
                row["metrics"]["roc_auc"] < 0.5
                for row in utility["synthetic_train_results"]
            ),
        )
        for result in utility["synthetic_train_results"]:
            self.assertNotIn("roc_auc_retention", result)
            expected = (result["metrics"]["roc_auc"] - 0.5) / (
                utility["real_train_baseline"]["roc_auc"] - 0.5
            )
            self.assertAlmostEqual(expected, result["roc_auc_skill_retention"])

    def test_utility_fixture_hashes_are_exact(self) -> None:
        utility = _read_json("evidence/v5.0.1/utility/utility_summary.json")
        path = ROOT / utility["source"]["fixture"]
        compressed = path.read_bytes()
        uncompressed = gzip.decompress(compressed)
        self.assertEqual(
            utility["source"]["fixture_sha256_gzip"],
            hashlib.sha256(compressed).hexdigest(),
        )
        self.assertEqual(
            utility["source"]["fixture_sha256_uncompressed"],
            hashlib.sha256(uncompressed).hexdigest(),
        )

    def test_utility_summary_is_pdf_anchored_and_screen_constant_is_shared(
        self,
    ) -> None:
        utility_bytes = (ROOT / UTILITY_SUMMARY_PATH).read_bytes()
        self.assertEqual(
            UTILITY_SUMMARY_SHA256, hashlib.sha256(utility_bytes).hexdigest()
        )

        contract = _load_module(
            "characterization_contract_under_test",
            "scripts/characterization_contract.py",
        )
        generator = _load_module(
            "characterization_generator_under_test",
            "scripts/gen_characterization_assets.py",
        )
        verifier = _load_module(
            "characterization_verifier_under_test",
            "scripts/verify_companion_bundle.py",
        )
        self.assertEqual(INTERNAL_AIR_SCREEN, contract.INTERNAL_AIR_SCREEN)
        self.assertEqual(UTILITY_SUMMARY_PATH, contract.UTILITY_SUMMARY_PATH)
        self.assertEqual(UTILITY_SUMMARY_SHA256, contract.UTILITY_SUMMARY_SHA256)
        expected_relation = ("at/above", "entirely above")
        self.assertEqual(
            expected_relation, generator._screen_relation(0.79, 0.78, 0.80, 0.75)
        )
        self.assertEqual(
            expected_relation,
            verifier._characterization_screen_relation(0.79, 0.78, 0.80, 0.75),
        )
        macros = (ROOT / "includes" / "characterization_macros.tex").read_text(
            encoding="utf-8"
        )
        self.assertIn(UTILITY_SUMMARY_SHA256, macros)
        reproduction = (ROOT / "sections" / "09_reproducibility.tex").read_text(
            encoding="utf-8"
        )
        self.assertIn(r"\IdentityText{\UtilitySummaryShaRaw}", reproduction)
        utility_narrative = "\n".join(
            (ROOT / "sections" / name).read_text(encoding="utf-8")
            for name in ("01_executive_summary.tex", "06_results.tex")
        )
        self.assertGreaterEqual(
            utility_narrative.count(r"\UtilityBelowChanceSeedCount{}"), 2
        )

    def test_regulatory_overlay_is_dated_and_uses_primary_sources(self) -> None:
        path = (
            ROOT
            / "evidence/v5.0.1/publication/regulatory_mapping_2026-08-05.csv"
        )
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(5, len(rows))
        self.assertTrue(all(row["as_of"] == "2026-08-05" for row in rows))
        self.assertTrue(all(row["source_url"].startswith("https://") for row in rows))
        joined = "\n".join(
            row["current_instrument"] + " " + row["current_state"] for row in rows
        )
        self.assertIn("SR 26-2", joined)
        self.assertIn("July 21 2026", joined)
        self.assertIn("rule of thumb", joined)

    def test_security_supersession_is_an_explicit_publication_blocker(self) -> None:
        publication_text = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8")
            for relative in (
                "README.md",
                "docs/stable_v5_publication.md",
                "sections/01_executive_summary.tex",
                "sections/10_limitations_monitoring.tex",
                "bib/references.bib",
                "companion/README.md",
            )
        )
        normalized = " ".join(publication_text.split())
        for required in (
            "CVE-2026-69247",
            r"\texttt{cryptography} 49.0.0",
            "security-superseded",
            "must remain unpublished",
            "v5.0.2",
            "3d27f7d17c2c853753d40cb883858617ead21677",
            "b246e39a23be938397a6d28612c776bedd8b42e2",
            "31087235319",
            r"\texttt{cryptography} 50.0.0",
            "supersedes v5.0.1",
        ):
            self.assertIn(required, normalized)
        for stale in (
            "no exact v5.0.2",
            "no such v5.0.2",
            "neither of which exists",
        ):
            self.assertNotIn(stale, normalized.lower())

    def test_forward_facing_sources_drop_obsolete_generator_names(self) -> None:
        joined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [ROOT / "main.tex", ROOT / "README.md"]
            + sorted((ROOT / "sections").glob("*.tex"))
        ).lower()
        obsolete = "ct" + "gan"
        self.assertNotIn(obsolete, joined)
        self.assertNotIn("no-" + obsolete, joined)

    def test_accessibility_and_visual_contract_is_explicit(self) -> None:
        main = (ROOT / "main.tex").read_text(encoding="utf-8")
        sections = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "sections").glob("*.tex"))
        )
        self.assertIn("pdfstandard=UA-1", main)
        self.assertIn("lang=en-US", main)
        self.assertIn("pdftitle={FL-BSA v5.0.1 Characterization Whitepaper}", main)
        self.assertNotIn(r"\begin{longtable}", sections)
        self.assertGreaterEqual(sections.count("alt={"), 7)
        for name in (
            "characterization_architecture.pdf",
            "characterization_evidence_chain.pdf",
            "characterization_air_slices.pdf",
            "characterization_quality.pdf",
            "characterization_robustness.pdf",
            "characterization_utility.pdf",
            "selection_rates.pdf",
        ):
            self.assertTrue((ROOT / "figures" / name).is_file(), name)

    def test_companion_is_deterministic_self_verifying_and_tamper_detecting(self) -> None:
        builder = _load_module(
            "companion_builder_under_test", "scripts/build_companion_bundle.py"
        )
        verifier = _load_module(
            "companion_verifier_under_test", "scripts/verify_companion_bundle.py"
        )
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.zip"
            second = Path(tmp) / "second.zip"
            first_result = builder.build(ROOT, first)
            second_result = builder.build(ROOT, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first_result["sha256"], second_result["sha256"])
            verified = verifier.verify(
                first, expected_utility_sha256=UTILITY_SUMMARY_SHA256
            )
            self.assertEqual("verified", verified["status"])
            self.assertEqual(21, verified["certificate_files"])
            self.assertEqual(18, verified["certificate_unique_nodes"])
            self.assertEqual(3, verified["certificate_alias_files"])
            self.assertEqual(17, verified["certificate_graph_edges"])
            self.assertEqual(8, verified["fairness_surfaces_recomputed"])
            self.assertEqual(40, verified["robustness_runs"])
            self.assertGreaterEqual(
                verified["robustness_aggregate_bands_recomputed"], 4
            )
            self.assertEqual(10, verified["utility_seeds"])
            self.assertEqual(5000, verified["utility_fixture_rows"])
            self.assertEqual(6, verified["utility_below_chance_seeds"])
            self.assertEqual(
                11, verified["characterization_summary_sections_cross_checked"]
            )

            with zipfile.ZipFile(first) as archive:
                self.assertIn("characterization_contract.py", archive.namelist())
                producer_zip = archive.read(
                    "producer/WhitePaper_Intake_Bundle_v4.zip"
                )
            self.assertEqual(
                PRIMARY_BUNDLE_SHA256, hashlib.sha256(producer_zip).hexdigest()
            )
            with zipfile.ZipFile(io.BytesIO(producer_zip)) as producer:
                self.assertEqual(36, len(producer.infolist()))
                self.assertNotIn(
                    "whitepaper_consumer",
                    json.loads(producer.read("intake/manifest.json")),
                )
                self.assertIn(
                    b"# Four-fifths rule", producer.read("config/sap.yaml")
                )

            extracted = Path(tmp) / "extracted"
            with zipfile.ZipFile(first) as archive:
                archive.extractall(extracted)
            standalone = subprocess.run(
                [
                    sys.executable,
                    str(extracted / "verify_companion_bundle.py"),
                    "--expected-utility-sha256",
                    UTILITY_SUMMARY_SHA256,
                    str(first),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual("verified", json.loads(standalone.stdout)["status"])
            target = extracted / "intake" / "fairness_slices.json"
            target.write_bytes(target.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                verifier.VerificationError, "(size|SHA-256) mismatch"
            ):
                verifier.verify(
                    extracted,
                    expected_utility_sha256=UTILITY_SUMMARY_SHA256,
                )

            utility_tamper = Path(tmp) / "utility-tamper.zip"
            with zipfile.ZipFile(first) as archive:
                utility = json.loads(
                    archive.read(
                        "evidence/v5.0.1/utility/utility_summary.json"
                    )
                )
            utility["synthetic_train_bands"]["roc_auc"]["mean"] += 0.01
            replacement = (
                json.dumps(utility, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            _rewrite_companion_member(
                first,
                utility_tamper,
                "evidence/v5.0.1/utility/utility_summary.json",
                replacement,
            )
            with self.assertRaisesRegex(
                verifier.VerificationError, "does not match PDF-disclosed SHA-256"
            ):
                verifier.verify(
                    utility_tamper,
                    expected_utility_sha256=UTILITY_SUMMARY_SHA256,
                )

            source_identity_tamper = Path(tmp) / "source-identity-tamper.zip"
            with zipfile.ZipFile(first) as archive:
                source_manifest = json.loads(
                    archive.read(
                        "evidence/v5.0.1/utility/source_manifest.json"
                    )
                )
            source_manifest["artifact"]["name"] = "forged-utility-artifact"
            replacement = (
                json.dumps(source_manifest, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            _rewrite_companion_member(
                first,
                source_identity_tamper,
                "evidence/v5.0.1/utility/source_manifest.json",
                replacement,
            )
            with self.assertRaisesRegex(
                verifier.VerificationError,
                "utility source artifact name mismatch",
            ):
                verifier.verify(
                    source_identity_tamper,
                    expected_utility_sha256=UTILITY_SUMMARY_SHA256,
                )

            coherent_utility_tamper = Path(tmp) / "coherent-utility-tamper.zip"
            with zipfile.ZipFile(first) as archive:
                forged_utility = json.loads(archive.read(UTILITY_SUMMARY_PATH))
                forged_characterization = json.loads(
                    archive.read(
                        "evidence/v5.0.1/publication/characterization_summary.json"
                    )
                )
            baseline_auc = forged_utility["real_train_baseline"]["roc_auc"]
            baseline_skill = baseline_auc - 0.5
            target_mean_auc = 0.5 + 0.929 * baseline_skill
            auc_values = []
            retention_values = []
            for index, row in enumerate(
                forged_utility["synthetic_train_results"]
            ):
                auc = target_mean_auc + (index - 4.5) * 0.002
                retention = (auc - 0.5) / baseline_skill
                row["metrics"]["roc_auc"] = auc
                row["roc_auc_skill_retention"] = retention
                auc_values.append(auc)
                retention_values.append(retention)
            forged_utility["synthetic_train_bands"]["roc_auc"] = _sample_band(
                auc_values
            )
            forged_utility["synthetic_train_bands"][
                "roc_auc_skill_retention"
            ] = _sample_band(retention_values)
            self.assertAlmostEqual(
                0.929,
                forged_utility["synthetic_train_bands"][
                    "roc_auc_skill_retention"
                ]["mean"],
            )
            forged_characterization["utility"] = forged_utility
            utility_replacement = (
                json.dumps(forged_utility, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            characterization_replacement = (
                json.dumps(forged_characterization, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            _rewrite_companion_members(
                first,
                coherent_utility_tamper,
                {
                    UTILITY_SUMMARY_PATH: utility_replacement,
                    (
                        "evidence/v5.0.1/publication/"
                        "characterization_summary.json"
                    ): characterization_replacement,
                },
            )
            with self.assertRaisesRegex(
                verifier.VerificationError, "does not match PDF-disclosed SHA-256"
            ):
                verifier.verify(
                    coherent_utility_tamper,
                    expected_utility_sha256=UTILITY_SUMMARY_SHA256,
                )

            coherent_contract_tamper = (
                Path(tmp) / "coherent-utility-and-contract-tamper.zip"
            )
            with zipfile.ZipFile(first) as archive:
                contract_replacement = archive.read(
                    "characterization_contract.py"
                )
            forged_utility_sha256 = hashlib.sha256(
                utility_replacement
            ).hexdigest()
            self.assertIn(
                UTILITY_SUMMARY_SHA256.encode("ascii"), contract_replacement
            )
            contract_replacement = contract_replacement.replace(
                UTILITY_SUMMARY_SHA256.encode("ascii"),
                forged_utility_sha256.encode("ascii"),
            )
            _rewrite_companion_members(
                first,
                coherent_contract_tamper,
                {
                    UTILITY_SUMMARY_PATH: utility_replacement,
                    (
                        "evidence/v5.0.1/publication/"
                        "characterization_summary.json"
                    ): characterization_replacement,
                    "characterization_contract.py": contract_replacement,
                },
            )
            forged_extracted = Path(tmp) / "coherent-contract-extracted"
            with zipfile.ZipFile(coherent_contract_tamper) as archive:
                archive.extractall(forged_extracted)
            forged_standalone = subprocess.run(
                [
                    sys.executable,
                    str(forged_extracted / "verify_companion_bundle.py"),
                    "--expected-utility-sha256",
                    UTILITY_SUMMARY_SHA256,
                    str(coherent_contract_tamper),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, forged_standalone.returncode)
            self.assertIn(
                "does not match PDF-disclosed SHA-256",
                forged_standalone.stderr,
            )

            summary_tamper = Path(tmp) / "characterization-summary-tamper.zip"
            with zipfile.ZipFile(first) as archive:
                characterization = json.loads(
                    archive.read(
                        "evidence/v5.0.1/publication/characterization_summary.json"
                    )
                )
            for row in characterization["fairness"]["slices"]:
                row["air"] = 0.94
            replacement = (
                json.dumps(characterization, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            _rewrite_companion_member(
                first,
                summary_tamper,
                "evidence/v5.0.1/publication/characterization_summary.json",
                replacement,
            )
            with self.assertRaisesRegex(
                verifier.VerificationError,
                "characterization summary fairness projection mismatch",
            ):
                verifier.verify(
                    summary_tamper,
                    expected_utility_sha256=UTILITY_SUMMARY_SHA256,
                )

            producer_projection_tamper = Path(tmp) / "producer-projection-tamper.zip"
            with zipfile.ZipFile(first) as archive:
                fairness = json.loads(archive.read("intake/fairness_slices.json"))
            fairness["slices"]["amplification"]["air"]["point"] += 0.01
            replacement = (
                json.dumps(fairness, indent=2) + "\n"
            ).encode("utf-8")
            _rewrite_companion_member(
                first,
                producer_projection_tamper,
                "intake/fairness_slices.json",
                replacement,
            )
            with self.assertRaisesRegex(
                verifier.VerificationError,
                "consumer intake differs from producer bytes",
            ):
                verifier.verify(
                    producer_projection_tamper,
                    expected_utility_sha256=UTILITY_SUMMARY_SHA256,
                )

    def test_certificate_graph_rejects_cycles_and_unresolved_links(self) -> None:
        verifier = _load_module(
            "companion_graph_verifier_under_test",
            "scripts/verify_companion_bundle.py",
        )
        with self.assertRaisesRegex(
            verifier.VerificationError, "contains a cycle"
        ):
            verifier._assert_single_rooted_graph(
                {"root": "", "a": "b", "b": "a"}
            )
        with self.assertRaisesRegex(
            verifier.VerificationError, "unresolved predecessor"
        ):
            verifier._assert_single_rooted_graph(
                {"root": "", "a": "missing"}
            )

    def test_standalone_instructions_and_pr_artifact_pair_are_coherent(self) -> None:
        companion_readme = (ROOT / "companion" / "README.md").read_text(
            encoding="utf-8"
        )
        reproduction = (ROOT / "sections" / "09_reproducibility.tex").read_text(
            encoding="utf-8"
        )
        for text in (companion_readme, reproduction):
            self.assertIn(
                "fl-bsa-v5.0.1-companion-evidence/verify_companion_bundle.py",
                text,
            )
            self.assertIn(
                "fl-bsa-v5.0.1-companion-evidence.zip", text
            )
            self.assertIn("--expected-utility-sha256", text)
            self.assertIn(UTILITY_SUMMARY_SHA256, text)
        self.assertIn(
            "requires the exact `utility_summary.json` bytes", companion_readme
        )
        normalized_companion_readme = " ".join(companion_readme.split())
        self.assertIn(
            "does not regenerate generator outputs or model predictions",
            normalized_companion_readme,
        )
        self.assertIn("caller-supplied PDF digest", reproduction)
        self.assertIn(
            "whole-ZIP digest comparison is the trust anchor", reproduction
        )
        self.assertIn(
            "when the PDF-disclosed digest is supplied", reproduction
        )
        self.assertIn("does not read the PDF", normalized_companion_readme)
        self.assertIn(
            "cannot independently authenticate", normalized_companion_readme
        )
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn(
            f"UTILITY_SUMMARY_SHA256={UTILITY_SUMMARY_SHA256}", makefile
        )
        self.assertIn(
            "--expected-utility-sha256 $(UTILITY_SUMMARY_SHA256)", makefile
        )
        workflow = (ROOT / ".github" / "workflows" / "latex.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("--expected-utility-sha256", workflow)
        self.assertIn(UTILITY_SUMMARY_SHA256, workflow)
        upload_start = workflow.index("- name: Upload PDF artifact")
        upload_end = workflow.index("- name: Package arXiv source", upload_start)
        upload = workflow[upload_start:upload_end]
        self.assertIn("main.pdf", upload)
        self.assertIn("fl-bsa-v5.0.1-companion-evidence.zip", upload)


if __name__ == "__main__":
    unittest.main()
