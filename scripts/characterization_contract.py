"""Shared constants for the v5.0.1 paper-owned characterization contract."""

INTERNAL_AIR_SCREEN = 0.80
UTILITY_SUMMARY_PATH = "evidence/v5.0.1/utility/utility_summary.json"
GOLD_EVIDENCE_MANIFEST_PATH = (
    "evidence/v5.0.1/robustness/evidence_manifest.json"
)
GOLD_INDEX_PATH = "evidence/v5.0.1/robustness/robustness_index.csv"
GOLD_SUMMARY_PATH = (
    "evidence/v5.0.1/robustness/robustness_summary_merged.json"
)

# This exact digest is disclosed in the PDF. It anchors the paper-owned utility
# rows independently of the companion's repairable internal file manifest.
UTILITY_SUMMARY_SHA256 = (
    "2b05a4a2b7ce2d798b9156ed5f837efe890ee87e4f5e914497724802636e4595"
)

# These Gold digests are disclosed in the PDF. The manifest and index remain
# exact producer bytes. The summary is the deterministic public projection
# documented in evidence_identity.json; it removes only machine-local paths.
GOLD_EVIDENCE_MANIFEST_SHA256 = (
    "353cd77907a5b5b0f64534ce6e5b00defeb872f5a8585aec43006ec24f96e073"
)
GOLD_INDEX_SHA256 = (
    "9ffb2c04a95f428f068d471732c7d9ed1e27a16d553749c2ec828907fbe9166c"
)
GOLD_SUMMARY_SHA256 = (
    "4339828263ce4cb3b81353f1fdb3e11ae5c99aeaebe9b3477be18dfe5a436a63"
)
GOLD_SOURCE_SUMMARY_SHA256 = (
    "15bee5d51c6816e4bd8bffdde3bcb657e5a25932f9742f17496c7a53884858ce"
)
GOLD_SUMMARY_PROJECTION = {
    "algorithm": "remove-machine-local-path-fields.v1",
    "removed_fields": {"run_dir": 40, "scenario_dir": 40},
}
