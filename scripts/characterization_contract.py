"""Shared constants for the v5.0.1 paper-owned characterization contract."""

INTERNAL_AIR_SCREEN = 0.80
UTILITY_SUMMARY_PATH = "evidence/v5.0.1/utility/utility_summary.json"

# This exact digest is disclosed in the PDF. It anchors the paper-owned utility
# rows independently of the companion's repairable internal file manifest.
UTILITY_SUMMARY_SHA256 = (
    "2b05a4a2b7ce2d798b9156ed5f837efe890ee87e4f5e914497724802636e4595"
)
