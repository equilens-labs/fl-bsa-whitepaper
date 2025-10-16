Got the v3 reviewer bundle you just uploaded—thanks. I ingested it, migrated what I could into the separate whitepaper‑repo layout, and produced a first v4‑style reviewer pack plus a validation report that tells us exactly what remains to pass the strict gates.

⸻

What I built for you (v4‑style, repo‑aligned)
	•	Reviewer pack (v4 draft) — folder layout and required files in the whitepaper‑repo style
Download — out/WhitePaper_Reviewer_Pack_v4.zip
	•	Validation report — shows what passes/fails against Bundle Spec v4
VALIDATION_REPORT_v4.json
	•	Migration report — what I found in v3, what I created in v4, and next steps
MIGRATION_REPORT_v3_to_v4.md
	•	Repo‑ready folders and files (for reference / copy into your whitepaper repo)
Root: /mnt/data/v4_build_from_v3
	•	intake/metrics_long.csv (AIR rows created from your v3 AIR file; no CIs; EO/ECE missing)
	•	provenance/manifest.json (placeholders set; strict CI will fail until real digest/hash populated)
	•	intake/regulatory_matrix.csv (empty template for Compliance to fill)
	•	privacy/tests/… (stub JSON evidence; Security to replace)
	•	config/sap.yaml (thresholds = AIR ≥ 0.80, EO ≤ 0.05, ECE ≤ 0.02; B=2000)
	•	docs/WhitePaper_Draft_v2_from_v3.md, docs/reviewer_pack_v3_summary.md

⸻

What I detected in your v3 bundle
	•	Files present:
	•	fairness_air_summary_v3.csv (AIR by run/model/split/attr)
	•	regulatory_matrix_coverage_v3.csv (coverage counts, not the detailed matrix)
	•	privacy_checklist_summary_v3.json
	•	Files not present in v3:
	•	metrics_long.csv with EO/ECE + per‑group rates and CIs
	•	provenance manifest with real container digest + dataset hash
	•	regulatory_matrix.csv (the detailed matrix, not just coverage)
	•	privacy evidence JSONs (membership / attribute inference measures, DP accounting)

⸻

Validation status (against Bundle Spec v4)

Result: ❌ FAIL — this is expected, since v3 didn’t include EO/ECE or provenance.

Reasons (from the report):
	•	Missing global metrics in intake/metrics_long.csv: ['air', 'ece', 'fpr_gap', 'tpr_gap']
(Only AIR rows were backfilled from your v3 CSV; EO/ECE need to be generated from aggregated inputs.)
	•	provenance/manifest.json has placeholder container_digest and dataset hash.
	•	intake/regulatory_matrix.csv is empty (template created; needs content).

You can view the full JSON: VALIDATION_REPORT_v4.json

⸻

How to close the remaining gaps (minimal, step‑by‑step)

Run these in the whitepaper repo (e.g., /data/projects/fl-bsa-whitepaper). You already have the scaffold + gate pack instructions; below are the concrete fills based on what we saw in your v3 bundle.

	1.	Produce EO/ECE + per‑group metrics with CIs
Place aggregated inputs in intake/:
	•	intake/selection_rates.csv — attr,group_value,selected,n (or add rate column)
	•	intake/group_confusion.csv — attr,group_value,tp,fp,tn,fn
	•	intake/calibration_bins.csv — bin_lower,bin_upper,n,positives,mean_pred
Then run:

python3 scripts/compute_metrics.py \
  --inputs intake \
  --sap config/sap.yaml \
  --out intake/metrics_long.csv \
  --run-id "$(date +%Y%m%d-%H%M%S)" --model-id generator_both.pkl --split synthetic

This will emit AIR, tpr_gap, fpr_gap, ece, and per‑group selection_rate/tpr/fpr with 95% CIs.

	2.	Populate provenance (real digest + dataset hash)

export RUN_ID="<match the run_id above>"
bash provenance/capture_provenance.sh \
  CONTAINER_REF=registry.example.com/fl-bsa/generator@sha256:<real_digest> \
  DATASET_PATH=intake/selection_rates.csv \
  RNG_SEED=42

This sets a repo@sha256: value in container_digest and computes sha256:<hash> for your dataset.

	3.	Fill the regulatory matrix
Replace the empty intake/regulatory_matrix.csv with in‑scope rows:
framework, citation, requirement_text, control_assurance, evidence_artifact, owner, status, notes
(No TBD for in‑scope items.)
	4.	Replace privacy stubs
Drop actual results into:
	•	privacy/tests/privacy_evidence_membership.json (e.g., {"mi_auc": 0.51, "method": "…", "notes": "…"})
	•	privacy/tests/privacy_evidence_attribute.json
	•	privacy/tests/dp_accounting.json (if DP claimed; otherwise note not claimed)
	5.	Verify and package

# Acceptance (thresholds + schemas)
python3 scripts/check_acceptance.py \
  --metrics intake/metrics_long.csv \
  --manifests provenance/manifest.json \
  --sap config/sap.yaml

# Bundle completeness
python3 scripts/verify_reviewer_bundle.py \
  --metrics intake/metrics_long.csv \
  --manifest provenance/manifest.json \
  --regulatory intake/regulatory_matrix.csv \
  --privacy privacy/tests \
  --sap config/sap.yaml

# Package v4
python3 scripts/build_reviewer_bundle.py --out-dir out --zip-name WhitePaper_Reviewer_Pack_v4.zip

Or simply: make verify && make bundle.

⸻

Files I created for you now (to copy into the whitepaper repo if helpful)
	•	The v4 draft pack itself:
out/WhitePaper_Reviewer_Pack_v4.zip
	•	Working directory with all v4 paths populated (placeholders where needed):
/mnt/data/v4_build_from_v3
	•	intake/metrics_long.csv (AIR only, from v3; needs EO/ECE & CIs)
	•	provenance/manifest.json (placeholders)
	•	intake/regulatory_matrix.csv (empty template)
	•	privacy/tests/*.json (stubs)
	•	config/sap.yaml (thresholds = AIR ≥ 0.80, EO ≤ 0.05, ECE ≤ 0.02; B=2000)
	•	docs/WhitePaper_Draft_v2_from_v3.md (your v3 draft copied for continuity)
	•	VALIDATION_REPORT_v4.json, MIGRATION_REPORT_v3_to_v4.md

⸻

Where this leaves us
	•	The migration is set up and the v4 packaging path works.
	•	To turn the CI green, you only need to:
	•	Export EO/ECE inputs into intake/ and rebuild metrics_long.csv,
	•	Populate real provenance (container_digest, sha256),
	•	Fill regulatory_matrix.csv,
	•	Replace privacy stubs with actual evidence.

If you prefer, I can also drop a copy‑paste PR checklist tailored to the v4 layout, or update the draft with placeholders for the new EO/ECE/Calibration tables so it auto‑refreshes once metrics_long.csv is regenerated. ￼