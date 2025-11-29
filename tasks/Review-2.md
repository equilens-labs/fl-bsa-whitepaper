Good, I see both things:
	•	WhitePaper_Reviewer_Pack_v4.zip (intake bundle + certificates + SAP).
	•	whitepaper.pdf (compiled article).  ￼

I’ve loaded the bundle, recomputed the key metrics, and cross-checked against the PDF.

⸻

1. Run summary (from the intake bundle)

From intake/selection_rates.csv:
	•	Gender
	•	Female: 2127 / 4822 ⇒ selection rate ≈ 0.4411
	•	Male: 2965 / 5178 ⇒ selection rate ≈ 0.5726
	•	AIR (gender) = min / max = 0.7703
BCa 95% CI (from metrics_long.csv): [0.7392, 0.8011]
⇒ violates AIR ≥ 0.80.
	•	Race
	•	Asian: 275 / 598 ⇒ 0.4599
	•	Black: 679 / 1302 ⇒ 0.5215
	•	Hispanic: 926 / 1726 ⇒ 0.5365
	•	Other: 145 / 283 ⇒ 0.5124
	•	White: 3067 / 6091 ⇒ 0.5035
	•	AIR (race) = 0.8572
BCa 95% CI: [0.7867, 0.9416]
⇒ passes AIR ≥ 0.80.

From intake/group_confusion.csv:
	•	For all groups (gender & race):
	•	TP > 0, FN = 0 ⇒ TPR = 1.0
	•	FP = 0, TN > 0 ⇒ FPR = 0.0
	•	So EO gaps:
	•	TPR_gap = 0, FPR_gap = 0
	•	BCa 95% CIs are zero-width (0, 0) because all groups have identical rates.

From the bundle contents:
	•	No intake/calibration_bins.csv and no ece rows in metrics_long.csv.
⇒ ECE is not evaluated; calibration compliance is unknown for this run, by design.

From provenance/manifest.json + config/sap.yaml:
	•	schema_version: wp-intake.v1
	•	run_id: 427d4729-775d-441b-9bbd-463b3c6d48f9
	•	Seeds: rng_seed = 42, bootstrap_seed = 42
	•	Inference: method bca, replicates = 2000, alpha = 0.05, smoothing = 1e-6
	•	Thresholds (SAP): AIR ≥ 0.80, EO gaps ≤ 0.05, ECE ≤ 0.02, BH at q = 0.10.

Status under the SAP:
	•	AIR: 1 violation (gender), race OK.
	•	EO: no violations (TPR_gap = 0, FPR_gap = 0).
	•	ECE: not evaluated (no bins/scores).

⸻

2. Consistency check: bundle ↔ metrics_long ↔ PDF

2.1 Selection rates & AIR
	•	Recomputing Wilson 95% CIs for the group selection rates from selection_rates.csv reproduces the selection_rate rows in metrics_long.csv to ~1e-5.
	•	Recomputing AIR from selection rates gives:
	•	gender AIR ≈ 0.7703, race AIR ≈ 0.8572, exactly the values in the air rows of metrics_long.csv (rounded).
	•	Table 1 in the PDF shows:
	•	gender: AIR 0.770, LCI 0.739, UCI 0.801
	•	race: AIR 0.857, LCI 0.787, UCI 0.942  ￼
which matches the BCa CIs from metrics_long.csv at 3 decimal places.
	•	Figure 1 on page 4 plots AIR for gender and race with CIs and a dashed line at 0.80; visually this is consistent with Table 1 (gender just below the line, race clearly above).  ￼

2.2 Equalized Odds
	•	From group_confusion.csv, all groups have:
	•	TPR = 1, FPR = 0; Wilson CIs match the tpr/fpr rows in metrics_long.csv.
	•	metrics_long.csv stores tpr_gap and fpr_gap as 0 with zero-width BCa CIs and ci_degenerate = True — exactly what you’d expect with identical rates across groups.
	•	Table 2 in the PDF gives 0 / 0 / 0 for all EO gaps, matching metrics_long.csv.  ￼
	•	The note in §6.2 explicitly explains the zero-width CIs in terms of aggregate bootstrap + 0/1 rates, which lines up with the ci_degenerate flag in the bundle.  ￼

2.3 Calibration (ECE)
	•	There is no calibration bins file in the bundle and no ece metric in metrics_long.csv.
	•	§6.3 Calibration (ECE) in the PDF says:
“Calibration (ECE) was not evaluated in this scenario; calibration compliance is therefore unknown in this whitepaper.”  ￼
	•	Table 3 is an ECE summary table that explicitly says no ECE rows were found and reiterates that ECE is not evaluated.  ￼
	•	This is all consistent with the intake bundle.

Only minor glitch:
	•	In the “Snapshot (Populates from Evidence)” subsection, the text currently reads:
“… the minimum AIR observed is 0.770; the ECE (maximum across splits) is TBD; and the EO gap violations are TPR: 0, FPR: 0.”  ￼

So the ECE macro is still at its placeholder “TBD”, even though the rest of the document correctly reports “not evaluated / compliance unknown”. That’s a Gate-WP → LaTeX macro wiring issue, not a stats issue.

2.4 Provenance & regulatory mapping
	•	Table 5 (Run Manifest) in the PDF matches provenance/manifest.json exactly for:
	•	seeds, commit, dataset hash, container digests, schema_version, run_id, config_hash, EO/ECE flags, and inference parameters.  ￼
	•	intake/regulatory_matrix.csv rows (EU AI Act Art.10(3), CFPB/ECOA 12 CFR 1002, etc.) align with the wording and structure of Table 4 (Regulatory mapping) in the PDF — same frameworks, citations, and evidence artefacts, with the prose version slightly more narrative.  ￼

Overall: metrics_long, the intake CSVs, the manifest, and the PDF are numerically consistent.

⸻

3. Concrete issues / action items for Gate-WP + whitepaper repo

From this pass, my best “fix-list” for you / Gate-WP is:
	1.	Snapshot ECE placeholder
	•	Fix the macro that populates the ECE line in the Snapshot block so that:
	•	When there are no ece rows in metrics_long or ece_enabled = False in the manifest:
	•	It renders something like:
“the ECE was not evaluated (no probability scores/bins were available; compliance unknown)”
	•	rather than “TBD”.
	•	This is the only obvious inconsistency between the bundle and the compiled PDF.
	2.	Snapshot wording for AIR
	•	Current text: “we observe AIR violations 1 …” is slightly awkward.
	•	Given the data, a clearer auto-summary would be:
	•	“One AIR violation (gender) under the 0.80 threshold; race satisfies the SAP threshold.”
	•	That can come straight from counting how many AIR rows in metrics_long have value < air_min from sap.yaml.
	3.	Explicitly tie Exec Summary to SAP fields
	•	The thresholds in §1.2 and §1.3 already match sap.yaml (AIR ≥ 0.800, EO gaps ≤ 0.050, ECE ≤ 0.020).  ￼
	•	Gate-WP should keep using config/sap.yaml as the single source for those numbers so the text can’t drift.
	4.	Optional: ECE macros for future runs
	•	For future runs where ece_enabled = True and bins exist:
	•	Snapshot should show:
	•	max ECE across splits + CI (from metrics_long).
	•	“ECE threshold met / violated” based on sap.yaml.ece_max.
	•	For this run, the correct behaviour remains: “not evaluated; compliance unknown.”
	5.	Acceptance checklist status (for this bundle)
	•	All reported metrics trace back to selection_rates.csv and group_confusion.csv.
	•	AIR table and AIR plot are aligned.
	•	EO gaps are reported and are only computed because group_confusion.csv exists.
	•	ECE is only discussed as “not evaluated”; no bogus value is introduced.
	•	Wilson/BCa intervals use seeds and B as specified in the manifest/SAP.
	•	Provenance table mirrors key manifest fields.
	•	Security/Privacy and Reproducibility sections are present and aligned with the bundle’s contents.
	•	One small presentational defect: Snapshot’s ECE macro still shows “TBD”.

