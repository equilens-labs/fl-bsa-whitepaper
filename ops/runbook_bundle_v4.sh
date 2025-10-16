#!/usr/bin/env bash
set -euo pipefail
# Run from repo root: /data/projects/fl-bsa-whitepaper

RUN_ID="${RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
MODEL_ID="${MODEL_ID:-generator_both.pkl}"
SPLIT="${SPLIT:-synthetic}"

mkdir -p intake out privacy/tests provenance

echo "[1/5] Compute AIR/EO/ECE -> intake/metrics_long.csv"
python3 scripts/compute_metrics.py   --inputs intake   --sap config/sap.yaml   --out intake/metrics_long.csv   --run-id "$RUN_ID"   --model-id "$MODEL_ID"   --split "$SPLIT"

echo "[2/5] Capture provenance -> provenance/manifest.json"
bash provenance/capture_provenance.sh   CONTAINER_REF="${CONTAINER_REF:-}"   DATASET_PATH="intake/selection_rates.csv"   RNG_SEED="${RNG_SEED:-42}"

echo "[3/5] Acceptance: thresholds + schemas"
python3 scripts/check_acceptance.py   --metrics intake/metrics_long.csv   --manifests provenance/manifest.json   --sap config/sap.yaml

echo "[4/5] Verify reviewer bundle completeness"
python3 scripts/verify_reviewer_bundle.py   --metrics intake/metrics_long.csv   --manifest provenance/manifest.json   --regulatory intake/regulatory_matrix.csv   --privacy privacy/tests   --sap config/sap.yaml

echo "[5/5] Package -> out/WhitePaper_Reviewer_Pack_v4.zip"
python3 scripts/build_reviewer_bundle.py --out-dir out --zip-name WhitePaper_Reviewer_Pack_v4.zip

echo "All done. Packaged: out/WhitePaper_Reviewer_Pack_v4.zip"
