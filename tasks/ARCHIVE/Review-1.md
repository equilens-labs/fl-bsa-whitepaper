Absolutely—here’s the clean split you can hand to each team.

⸻

A) FL‑BSA repo (gate‑wp + worker/pipeline)

Owner: Product Eng / Stats
Goal: Compute the metrics & CIs (incl. BCa) inside the pipeline, stamp method metadata into the bundle, and keep the whitepaper repo “renderer‑only”.

1) Context & Goal
	•	Role: Generate the WP intake bundle (data, metrics, CIs, manifest, certificates).
	•	Change: Add a configurable inference surface (BCa vs percentile) used by the worker; have gate‑wp propagate the choice; emit method metadata in the manifest and per‑metric rows.

2) Current State & SSoT
	•	gate-wp already generates a seeded dataset, submits the pipeline, validates intake, and packages WhitePaper_Reviewer_Pack_v4.zip.
	•	Intake contains selection_rates.csv, metrics_long.csv, group_confusion.csv, optional calibration_bins.csv, provenance/manifest.json.
	•	EO enable/repair is handled already; provenance gets commit/image digests when available.

3) Proposed Approach (impact · lanes · rollback)
	1.	Inference config surface (SAP + env overrides) → High · Eng/Stats · rollback: default to existing percentile.
	2.	Worker CI dispatcher (BCa + smoothing, row‑level preferred) → High · Eng/Stats · rollback: call percentile only.
	3.	Emit method & params into provenance/manifest.json and metrics_long.csv → Med · Eng/Ops · rollback: omit fields.
	4.	gate‑wp exports CI knobs and stamps them into the manifest → Med · Ops/Eng · rollback: remove env/patch lines.

4) Change‑Set Preview (file‑scoped diffs/snippets)

4.1 SAP (config/sap.yaml)

inference:
  method: bca          # "bca" | "percentile"
  replicates: 2000     # B
  alpha: 0.05          # 95% CI
  seed: ${FLBSA_TEST_SEED}
  smoothing: 1e-6      # clip for boundary probs; set 0 to disable

4.2 Makefile (gate‑wp block — add the four CI_… exports)

- @WP_ENABLE_EO=1 FLBSA_ADD_GROUND_TRUTH=1 $(MAKE) services-up
+ @WP_ENABLE_EO=1 FLBSA_ADD_GROUND_TRUTH=1 \
+   CI_METHOD=bca CI_REPLICATES=2000 CI_ALPHA=0.05 CI_SMOOTH=1e-6 \
+   $(MAKE) services-up

4.3 Worker dispatcher (e.g., flbsa/metrics/inference.py)

# New module or extend an existing one
from .bca import bootstrap_bca_ci        # canonical non-parametric BCa
from .percentile import pct_boot_ci      # existing percentile CI

def ci_dispatch(values, *, method, alpha, B, seed, smoothing=0.0):
    import numpy as np
    v = np.asarray(values, dtype=float)
    if smoothing:
        v = np.clip(v, smoothing, 1.0 - smoothing)  # avoid 0/1 degeneracy
    if method == "bca":
        return bootstrap_bca_ci(v, alpha=alpha, B=B, seed=seed)
    return pct_boot_ci(v, alpha=alpha, B=B, seed=seed)

4.4 Read config/env in worker (where metrics are computed)

cfg = sap.get("inference", {})  # loaded SAP dict
method = (cfg.get("method") or os.getenv("CI_METHOD") or "percentile").lower()
B      = int(cfg.get("replicates") or os.getenv("CI_REPLICATES") or 2000)
alpha  = float(cfg.get("alpha") or os.getenv("CI_ALPHA") or 0.05)
seed   = int(cfg.get("seed") or os.getenv("FLBSA_TEST_SEED") or 42)
smooth = float(cfg.get("smoothing") or os.getenv("CI_SMOOTH") or 0.0)

# When building CIs for AIR/EO/ECE:
ci_low, ci_high = ci_dispatch(series, method=method, alpha=alpha, B=B, seed=seed, smoothing=smooth)
row["ci_low"], row["ci_high"], row["ci_method"] = ci_low, ci_high, method
row["ci_degenerate"] = (ci_high == ci_low)

4.5 Stamp inference block in manifest (tools/wp/run_wp_evidence.py)

Add inside your provenance patch section (you already open/modify JSON):

inf = {
  "method": os.getenv("CI_METHOD", "percentile"),
  "replicates": int(os.getenv("CI_REPLICATES", "2000")),
  "alpha": float(os.getenv("CI_ALPHA", "0.05")),
  "seed": int(os.getenv("FLBSA_TEST_SEED", "42")),
  "smoothing": float(os.getenv("CI_SMOOTH", "0.0"))
}
data["inference"] = { **inf, **(data.get("inference") or {}) }

4.6 metrics_long.csv schema delta

Add columns: ci_method, ci_low, ci_high, ci_degenerate.
(No breaking changes; CSV gains columns on the right.)

5) Verification Plan (commands & artifacts)

# Baseline run (percentile)
CI_METHOD=percentile CI_REPLICATES=2000 CI_ALPHA=0.05 CI_SMOOTH=0 \
  make gate-wp WP_SAP=config/sap.yaml WP_OUT=artifacts/wp_pct.zip

# BCa run
CI_METHOD=bca CI_REPLICATES=2000 CI_ALPHA=0.05 CI_SMOOTH=1e-6 \
  make gate-wp WP_SAP=config/sap.yaml WP_OUT=artifacts/wp_bca.zip

# Inspect metadata
unzip -p artifacts/wp_bca.zip provenance/manifest.json | jq .inference
# -> should show method "bca", B=2000, alpha=0.05, smoothing=1e-6

# Inspect CIs
unzip -p artifacts/wp_bca.zip intake/metrics_long.csv | head -n 3
# -> columns include ci_method/ci_low/ci_high/ci_degenerate

Artifacts: artifacts/wp_bca.zip contains intake + inference metadata; fewer zero‑width CIs for EO/AIR expected.

6) Risks & Rollback
	•	BCa perf: ~B× computation; if slow, reduce replicates (1000) or set method=percentile.
	•	Smoothing bias: tiny ε; set smoothing: 0 to disable.

7) Follow‑ups
	•	Prefer row‑level bootstrap over aggregate where feasible.
	•	Ensure container_digests populate in provenance for production runs.

8) Assumptions & Unknowns
	•	File locations for metrics code may differ; adjust module paths accordingly.
	•	ECE rows might be absent; that’s fine—whitepaper will state “ECE not evaluated”.

⸻

B) Whitepaper repo (renderer)

Owner: Docs/Reg Eng / LexPro review
Goal: Render the PDF only; never compute metrics. Pull method/params from the bundle and introduce scope/rigor text.

1) Context & Goal
	•	Input is WhitePaper_Reviewer_Pack_v4.zip from A).
	•	Add small template hooks for scope, status, and inference metadata display.

2) Current State & SSoT
	•	You compile via Tectonic/LaTeX (or similar); intake provides CSVs + provenance/manifest.json.
	•	The document currently hints at manifest/provenance but needs explicit scope/method language.

3) Proposed Approach (impact · lanes · rollback)
	1.	Expose inference metadata from manifest → Med · Docs/Eng · rollback: hide section.
	2.	Add scope statement + thresholds in Exec Summary → High · Docs/LexPro · rollback: remove paragraph.
	3.	Conditionals: print “ECE not evaluated” when calibration rows are missing → Low · Docs · rollback: hide line.
	4.	Degeneracy note: if any ci_degenerate=true, show one‑liner caution → Low · Docs · rollback: hide line.

4) Change‑Set Preview

4.1 Pre‑processor (reads bundle & emits TeX macros or a JSON for LaTeX)

tools/wp/render_preamble.py (example):

import json, zipfile, sys
bundle = sys.argv[1]
with zipfile.ZipFile(bundle) as z:
    inf = json.loads(z.read("provenance/manifest.json"))
    inf = (inf or {}).get("inference") or {}
method = inf.get("method","percentile").upper()
B = inf.get("replicates", 2000); alpha = inf.get("alpha", 0.05)
print(rf"\newcommand{{\InferenceMethod}}{{{method}}}")
print(rf"\newcommand{{\InferenceReplicates}}{{{B}}}")
print(rf"\newcommand{{\InferenceAlpha}}{{{alpha}}}")

Call this in your build script and \input{generated/preamble.tex} in LaTeX.

4.2 Exec Summary (paste)

Scope and positioning. This whitepaper documents FL‑BSA’s behavior on a synthetic audit scenario and the
evidence artifacts generated (report, metrics manifest, certificate links). It provides metrics and documentation
building blocks aligned with ECOA/Reg B’s four‑fifths rule, EU AI Act Article 10 evidence, and related frameworks.
It is not a legal opinion and does not constitute a complete compliance submission for any specific deployment.

Run status. Under configured thresholds (AIR ≥ 0.80; EO gaps ≤ 0.05; ECE ≤ 0.02), this run shows one AIR
violation for gender (AIR = 0.771) [VERIFY]. Calibration (ECE) was not evaluated because no calibration rows
were present in the intake bundle.

4.3 Methods block (show method from manifest)

Uncertainty estimates. Confidence intervals in this document are produced by \InferenceMethod{}
bootstrap with B=\InferenceReplicates{} replicates (α=\InferenceAlpha{}). In scenarios with boundary
probabilities (e.g., TPR=1.0 or FPR=0.0), aggregate percentile bootstrap can yield zero‑width intervals;
FL‑BSA supports non‑parametric BCa at row‑level in compliance reports to mitigate this.

4.4 Conditional notes
	•	If calibration_bins.csv missing → print “Calibration (ECE) not evaluated in this scenario.”
	•	If any metric row has ci_degenerate=true → print “Some intervals are zero‑width due to boundary rates; interpret with caution.”

5) Verification Plan

# Generate bundle (from A)
make gate-wp WP_OUT=artifacts/wp_bca.zip

# Preamble (emit macros)
python tools/wp/render_preamble.py artifacts/wp_bca.zip > build/generated/preamble.tex

# Compile PDF
tectonic -X compile whitepaper.tex

Artifacts: dist/whitepaper.pdf shows \InferenceMethod = BCA, thresholds in Exec Summary, and the calibration/degeneracy notes when applicable.

6) Risks & Rollback
	•	No math in renderer; minimal risk. If reviewers dislike the added lines, remove the blocks or hide behind a build flag.

7) Follow‑ups
	•	Decide permanent tone: template (reused across customers) vs one‑off; keep the scope paragraph either way.
	•	Link section references to your canonical docs index for AIR/EO/ECE definitions if desired.

8) Assumptions & Unknowns
	•	Exact LaTeX/Markdown file names in the repo. Use your current build chain; the pre‑processor only prints a few macros.

⸻

“Who does what” hand‑off (put this in the tracking ticket)

Item	Team	Repo	Deliverable
Add SAP inference block + env overrides	Eng/Stats	fl‑bsa	YAML + worker config load
Implement ci_dispatch (BCa/percentile + smoothing)	Eng/Stats	fl‑bsa	Code + unit tests
Emit CI metadata in manifest + metrics_long.csv	Eng/Ops	fl‑bsa	Manifest fields + CSV cols
Export CI_* envs in gate-wp and stamp manifest	Ops	fl‑bsa	Makefile diff + manifest patch
Keep EO repair & provenance patching	Ops	fl‑bsa	No change (already present)
Read manifest in renderer & print method/params	Docs/Reg Eng	whitepaper repo	Pre‑processor + TeX macros
Add scope/status/degeneracy/ECE notes	Docs/Reg Eng + LexPro	whitepaper repo	Text blocks
Build & QA PDF	Docs	whitepaper repo	dist/whitepaper.pdf


⸻

TL;DR
	•	(a) fl‑bsa repo = compute CIs (BCa vs percentile), write method metadata into the bundle.
	•	(b) whitepaper repo = render only, show method & scope language, never compute stats.

If you want, I can turn this into two PR descriptions (one per repo) with the above diffs and checklists pre‑filled.