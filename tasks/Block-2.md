Absolutely—thanks for flagging the repo split. I’ve rewritten the spec so it’s explicitly tailored to the separate whitepaper repo (e.g., /data/projects/fl-bsa-whitepaper), with all paths rooted there and no accidental ties to the main ../fl-bsa codebase (except optional use of its published container digest).

Delivered now (ready to drop into the whitepaper repo)
	•	Bundle Spec v4 (Markdown) — clean, structured, and repo‑accurate
Download
	•	CI patch snippet — updates the strict workflow to use intake/ paths
Download
	•	Runbook script — one‑shot commands to build/verify/package v4 bundle
Download

⸻

What’s in the spec (highlights)
	•	Overview & Goal → Produces out/WhitePaper_Reviewer_Pack_v4.zip with:
	•	intake/metrics_long.csv (AIR, tpr_gap, fpr_gap, ece + 95% CIs and n; plus per‑group selection_rate/tpr/fpr with CIs),
	•	provenance/manifest.json (real container_digest, dataset sha256, commit, seed, timestamps),
	•	intake/regulatory_matrix.csv (no TBDs for in‑scope),
	•	privacy/tests/*.json (MI/AI evidence, DP accounting),
	•	config/sap.yaml (AIR ≥ 0.80, EO ≤ 0.05, ECE ≤ 0.02; bootstrap settings).
	•	Directory Mappings → Uses intake/ as the canonical place for aggregated inputs and generated metrics; provenance/, privacy/tests/, docs/, out/ as described. Clear separation from ../fl-bsa; the only optional interaction is passing a container digest published by that repo into capture_provenance.sh.
	•	Required Contents & Validation Rules → Column‑level requirements for metrics_long.csv, required keys in manifest.json, allowed status values in regulatory_matrix.csv, and structure for privacy evidence JSONs.
	•	Generation Flow (repo‑aligned) → Commands use intake/ everywhere:
	1.	Compute metrics (AIR/EO/ECE) → intake/metrics_long.csv
	2.	Capture provenance (digest/hash/seed) → provenance/manifest.json
	3.	Acceptance checks (thresholds + schemas)
	4.	Bundle verify (completeness)
	5.	Package → out/WhitePaper_Reviewer_Pack_v4.zip
	•	CI Enforcement → A patch to ensure .github/workflows/acceptance_strict.yml calls verify_reviewer_bundle.py with intake/ paths.
	•	Style & Consistency → lowercase metric names, attr:value group labels, stable run_id, include lower_ci/upper_ci/n on every proportion/global row, and regenerate traceability when claims/metrics change.
	•	Repo Independence → Whitepaper repo is self‑contained; no code coupling to ../fl-bsa. If you need a digest, grab it from your registry and pass it in as CONTAINER_REF.

⸻

How to use (copy/paste into the whitepaper repo)
	1.	Drop the files into the repo root:
	•	Put Bundle_Spec_v4.md in docs/ (or keep at root—your choice).
	•	Apply the CI patch content to .github/workflows/acceptance_strict.yml.
	•	Place runbook_bundle_v4.sh at repo root and chmod +x.
	2.	Run the runbook (from /data/projects/fl-bsa-whitepaper):

bash runbook_bundle_v4.sh
# or step-by-step:
#   python3 scripts/compute_metrics.py --inputs intake --sap config/sap.yaml --out intake/metrics_long.csv --run-id "$(date +%Y%m%d-%H%M%S)"
#   bash provenance/capture_provenance.sh CONTAINER_REF=registry.example.com/fl-bsa/generator@sha256:… DATASET_PATH=intake/selection_rates.csv RNG_SEED=42
#   python3 scripts/check_acceptance.py --metrics intake/metrics_long.csv --manifests provenance/manifest.json --sap config/sap.yaml
#   python3 scripts/verify_reviewer_bundle.py --metrics intake/metrics_long.csv --manifest provenance/manifest.json --regulatory intake/regulatory_matrix.csv --privacy privacy/tests --sap config/sap.yaml
#   python3 scripts/build_reviewer_bundle.py --out-dir out --zip-name WhitePaper_Reviewer_Pack_v4.zip

	3.	CI
Ensure the strict workflow uses the intake/ pathing (use the provided patch content). CI blocks merges if thresholds fail, schemas break, privacy JSONs are missing, or container_digest is a placeholder.

⸻

If you want me to also generate a PR checklist tailored to this v4 spec (with your company’s section headings), I can add that too. ￼