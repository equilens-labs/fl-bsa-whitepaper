Got it—thanks for the crisp status. Here’s a tight resync plus a drop‑in scaffold that closes the exact gaps you called out (EO/ECE metrics with CIs, provenance, schema enforcement, privacy evidence, CI gates).

⸻

TL;DR
	•	I generated a repo‑ready bundle you can drop into the new whitepaper repo to implement the plan’s Block‑2 scope.
	•	It computes AIR, EO gaps (TPR/FPR) and ECE with 95% CIs, captures provenance (container digest, hashes, seeds), enforces schemas, and wires a CI acceptance gate.
	•	Use it to produce the missing artifacts and regenerate the reviewer bundle + draft.

Download the scaffold
	•	wp_resync_scaffold_v3.zip

⸻

What’s inside (and how it maps to your plan)

Gap in your note	What I’m providing	Where
EO/ECE metrics w/ 95% CIs	A single CLI to compute AIR/EO/ECE + CIs from aggregates	scripts/compute_metrics.py
Stable run IDs & manifests	Provenance capture (dataset/code hashes, container digest, seed, timestamps)	provenance/capture_provenance.sh → provenance/manifest.json
Schema enforcement	JSON Schemas + validator for metrics_long and manifest.json	schemas/*.schema.json, scripts/check_acceptance.py
CI gate wiring	GitHub Actions workflow that fails builds if thresholds/schemas aren’t met	ci/acceptance.yml
Formal metrics schema	Explicit row schema for metrics_long	schemas/metrics_long.schema.json
Privacy evidence	Stubs for MI/AI/DP outputs to unblock evidence packaging	privacy/tests/*
Traceability	Script to map claims → observed metrics	scripts/gen_traceability.py
SAP thresholds	Central config for AIR/EO/ECE and bootstrap settings	config/sap.yaml
Working examples	Minimal CSVs for selection rates, confusion counts, and calibration bins	example_inputs/*.csv

These align with your “Where We Stand / Gaps vs Plan / Immediate Actions,” specifically the items you referenced in tasks/WP-Plan.md and tasks/Block-2.md.

⸻

Quickstart (5 commands)

# 0) Unzip into the root of your whitepaper repo
unzip wp_resync_scaffold_v3.zip -d .

# 1) Compute EO/ECE/AIR (+95% CIs) from aggregates (examples included)
python3 scripts/compute_metrics.py \
  --inputs example_inputs \
  --sap config/sap.yaml \
  --out metrics_long.csv

# 2) Capture provenance (container digest, hashes, seeds)
bash provenance/capture_provenance.sh
# (Set CONTAINER_REF, DATASET_PATH, RNG_SEED if you want to override defaults)

# 3) Enforce acceptance criteria (AIR ≥ 0.80, EO gaps ≤ 0.05, ECE ≤ 0.02) + schema checks
python3 scripts/check_acceptance.py \
  --metrics metrics_long.csv \
  --manifests provenance/manifest.json \
  --sap config/sap.yaml

# 4) Generate claims→evidence traceability
python3 scripts/gen_traceability.py --metrics metrics_long.csv --out traceability_matrix.csv

# 5) (CI) Commit and push — .github/workflows/acceptance.yml will run these checks automatically


⸻

What the outputs look like

metrics_long.csv (columns)
run_id, split, model_id, metric, group, value, lower_ci, upper_ci, n
	•	AIR: one row per attribute family (e.g., metric=AIR, group=gender:global) with a bootstrap 95% CI.
	•	EO: tpr_gap / fpr_gap (global per attribute), plus per‑group tpr / fpr rows (Wilson CIs).
	•	Calibration: one ece row (global) with a bootstrap 95% CI.

provenance/manifest.json (schema‑validated)

{
  "run_id": "YYYYMMDD-HHMMSS",
  "dataset_hash": "sha256:…",
  "code_commit": "abcdef1",
  "container_digest": "repo@sha256:…",
  "rng_seed": 42,
  "hardware": "…",
  "start_ts": "…",
  "end_ts": "…"
}

config/sap.yaml centralizes thresholds and bootstrap settings (B=2000, α=0.05 by default).

⸻

Engineering notes
	•	Inputs are aggregated; no row‑level data required.
	•	example_inputs/selection_rates.csv: attr, group_value, selected, n, rate (rate auto‑computed if missing).
	•	example_inputs/group_confusion.csv: attr, group_value, tp, fp, tn, fn.
	•	example_inputs/calibration_bins.csv: bin_lower, bin_upper, n, positives, mean_pred.
	•	CIs
	•	Selection rates / TPR / FPR per group: Wilson 95% CI.
	•	AIR & EO gaps: parametric bootstrap (binomial) percentile CI (B configurable).
	•	ECE: bootstrap across calibration bins (multinomial reweight of bin counts).
	•	CI gates: scripts/check_acceptance.py fails if any threshold in config/sap.yaml is violated or if schemas don’t validate.
	•	Provenance: capture_provenance.sh fetches a container digest if CONTAINER_REF is provided and Docker is available; otherwise uses not_available placeholder (which will cause the manifest schema to pass but you can add a CI rule to require a non-placeholder value).

⸻

RACI for the next push (suggested)

Area	Owner	Reviewer	Output
Audit scoring (EO/ECE)	Platform/QA	MRM	metrics_long.csv with CIs
Provenance capture	Platform	Security	provenance/manifest.json with digest & hashes
Schema/CI gates	QA	MRM/Security	Passing CI on PR (acceptance.yml)
Privacy tests	Security	MRM	JSON evidence in privacy/tests/*.json
Regulatory matrix	Compliance	MRM	Updated regulatory_matrix.csv
Draft refresh	MRM	Execs	PDF/MD w/ updated tables + traceability


⸻

Mapping back to your three bullets
	1.	Immediate Actions
	•	(1) EO/ECE metrics w/ stable run IDs: Use compute_metrics.py and set RUN_ID, then regenerate bundle & draft.
	•	(2) Provenance fields populated: Run capture_provenance.sh (add CONTAINER_REF) to emit digests, hashes, seeds.
	•	(3) Intake checklist: The scaffold includes claims, schemas, and CI to ensure all artifacts are present; use your existing docs/WhitePaper_RFI.md to fill narrative gaps.
	2.	Gaps vs Plan
	•	Audit scoring / EO/ECE metric layer: implemented (see scripts/compute_metrics.py).
	•	Provenance capture: implemented (see provenance/).
	•	Schema enforcement: implemented (see schemas/, scripts/check_acceptance.py).
	•	Privacy attack modules: stubs included — replace with your harness; artifacts wired for CI.
	•	Acceptance criteria: centralized in config/sap.yaml and enforced in CI.
	3.	Where We Stand
	•	Your v3 already had AIR + regulatory + privacy checklist. The scaffold completes the EO/ECE + CIs and provenance pieces so Block‑2 can close. The CI gate will keep the repo aligned with the plan as you iterate.

⸻

Ready-to-run demo

If you want to test locally with the included synthetic aggregates:

python3 scripts/compute_metrics.py --inputs example_inputs --sap config/sap.yaml --out metrics_long.csv
bash provenance/capture_provenance.sh
python3 scripts/check_acceptance.py --metrics metrics_long.csv --manifests provenance/manifest.json --sap config/sap.yaml
python3 scripts/gen_traceability.py --metrics metrics_long.csv --out traceability_matrix.csv

This will produce all artifacts so you can wire them into the draft generation and your reviewer bundle.

⸻

If you’d like, I can also auto‑refresh your WhitePaper_Draft to include EO/ECE tables once you drop your real aggregates into the repo. ￼