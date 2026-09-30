Thanks—here are precise answers for each follow‑up, split between the two repos so you can brief each team cleanly. I’ll also flag the impact/lanes/rollback for every decision.

Note: The whitepaper/data bundles you uploaded earlier have expired in my environment. If you want me to extract live numbers/verbatim tables, please re‑upload the ZIP/PDF and I’ll parse them directly.

⸻

0) One canonical rule up front (to keep both teams aligned)
	•	Canonical CI fields going forward:
ci_method, ci_low, ci_high, ci_degenerate (plus the run‑level inference{ method, replicates, alpha, seed, smoothing } in provenance/manifest.json).
Legacy compatibility only: lower_ci, upper_ci.

Impact: High · Lanes: Eng/Stats, Docs · Rollback: Keep rendering lower_ci/upper_ci only.

⸻

1) Inference metadata & CIs

Q: Should the whitepaper use only ci_low/ci_high or keep lower_ci/upper_ci in sync?
	•	(A) fl‑bsa repo (pipeline) — action
	•	Always write both: set lower_ci = ci_low, upper_ci = ci_high in metrics_long.csv. That keeps old consumers working and makes the new pair authoritative.
	•	Keep ci_method column populated per row (e.g., bca or percentile), and set ci_degenerate=true|false.
Impact: High · Lanes: Eng/Stats · Rollback: stop mirroring legacy columns.
	•	(B) whitepaper repo (renderer) — action
	•	Read order: prefer ci_low/ci_high. If missing, fall back to lower_ci/upper_ci.
	•	Table templates: render Point and 95% CI from the chosen pair; print a small footnote with \InferenceMethod{} once per table.
Impact: Med · Lanes: Docs/Templating · Rollback: render legacy only.

⸻

Q: Expose smoothing ε in the preamble?
	•	Recommendation: Yes, conditionally. Define \InferenceSmoothing only when smoothing>0 in manifest; otherwise do not mention it. This keeps the Methods section explicit when a clip was applied but avoids noise.
	•	(B) renderer macro policy
	•	Emit: \newcommand{\InferenceSmoothing}{1e-6} only if smoothing>0; otherwise emit \newcommand{\InferenceSmoothing}{}% and guard the text with \ifx\InferenceSmoothing\empty ... \else ... \fi.
Impact: Low · Lanes: Docs · Rollback: drop smoothing mention.

⸻

2) Calibration (ECE) handling

Q: When calibration_bins.csv is present, always show ECE+CI+method, or gate it by a flag?
	•	Detection precedence (to avoid drift):
	1.	If provenance/manifest.json exposes capabilities.calibration_enabled=true or metrics_long.csv has metric_id in {ece, ece_max, ece_w}, then show ECE (with CI and ci_method).
	2.	Else, do not show and render a one‑liner explaining it wasn’t evaluated.
	•	(A) pipeline
	•	Populate capabilities.calibration_enabled consistently when ECE was computed (true/false). (You already do similar for EO via the repair helper.)
	•	(B) renderer
	•	If capability true (or ECE rows detected), include the ECE card/table; otherwise include the “not evaluated” line.
Impact: Med · Lanes: Eng/Stats, Docs · Rollback: rely on file presence only.

Q: Wording when ECE is missing—strong vs soft?
	•	Default (recommended for regulator‑grade):
Strong — “Calibration (ECE) was not evaluated in this scenario; calibration compliance is therefore unknown in this whitepaper.”
	•	Optional (marketing‑friendlier):
Soft — “Calibration (ECE) was not evaluated for this scenario and will be included in the accompanying compliance test pack when enabled.”

Add a build flag WP_TONE=strict|soft in the renderer to switch the sentence.

Impact: Content only · Lanes: Docs/LexPro · Rollback: pick one line and stick to it.

⸻

3) Scope and tone

Q: Scope paragraph: hard‑code “synthetic audit” or parameterize?
	•	Parameterize via a new manifest field:

"scenario": {
  "type": "synthetic_audit",   // "customer_run", "pilot_plus", etc.
  "label": "Gender-bias stress"
}

	•	(A) pipeline: write scenario.type and scenario.label into provenance/manifest.json.
	•	(B) renderer:
	•	If type="synthetic_audit", print: “This whitepaper documents a synthetic audit scenario … not a legal opinion …”
	•	If type="customer_run", print: “This whitepaper documents a customer deployment run … metrics/evidence building blocks … not a legal opinion …”
Impact: Med · Lanes: Eng/Ops (manifest), Docs · Rollback: hard‑code current sentence.

Q: Exec Summary “Run status”: show the count of threshold violations across AIR/EO/ECE up top?
	•	Recommendation: Yes—one compact line helps regulators triage; details remain in Results.
	•	(A) pipeline: include thresholds in manifest:

"thresholds": { "air_min": 0.80, "eo_gap_max": 0.05, "ece_max": 0.02 }


	•	(B) renderer: compute:
	•	viol_air = count(AIR < air_min)
	•	viol_eogap = count(ΔTPR>eo_gap_max or ΔFPR>eo_gap_max)
	•	viol_ece = 1 if ECE>ece_max else 0 (when present)
Then render:
“Status: AIR violations X, EO‑gap violations Y, ECE violations Z.”
Impact: Med · Lanes: Eng (thresholds), Docs · Rollback: put counts in Results only.

⸻

4) Degenerate intervals (0‑width CIs)

Q: Keep the terse note or expand for lay readers?
	•	Recommended text (regulator‑friendly, clear):
“Some groups in this synthetic scenario have rates at 0% or 100%. With aggregate bootstrap this can yield zero‑width confidence intervals, even though real‑world uncertainty would be larger. FL‑BSA’s compliance reports use row‑level BCa bootstrap to mitigate this effect.”

Show this note only if any row has ci_degenerate=true.

Impact: Low · Lanes: Docs · Rollback: keep the terse version: “Some intervals are zero‑width due to boundary rates; interpret with caution.”

⸻

5) Linking to canonical docs

Q: OK to reference canonical docs and modules?
	•	Yes, with commit pinning from the manifest for reproducibility. Add an “Implementation Reference” appendix:

AIR, EO, ECE definitions are implemented in:
  • flbsa.metrics.mathematical_definitions
  • flbsa.metrics.statistical_significance
  • Commit: \CodeCommit (from manifest)
For conceptual background: /docs/technical/bias-metrics-and-statistics.md

	•	(A) pipeline: ensure code_commit (or commit_sha) is populated in the manifest (you already patch it).
	•	(B) renderer: expose \CodeCommit from manifest.

Impact: Low · Lanes: Docs · Rollback: remove the appendix.

⸻

6) Concrete snippets for the renderer (drop‑in)

Preamble generation (Python)

# tools/wp/preamble.py
import json, zipfile, sys
z = zipfile.ZipFile(sys.argv[1])
m = json.loads(z.read("provenance/manifest.json"))
inf = m.get("inference", {})
thr = m.get("thresholds", {"air_min":0.80,"eo_gap_max":0.05,"ece_max":0.02})
sc  = m.get("scenario", {"type":"synthetic_audit","label":"Synthetic audit"})

def macro(k, v): print(rf"\newcommand{{\{k}}}{{{v}}}")
macro("InferenceMethod", (inf.get("method","percentile")).upper())
macro("InferenceReplicates", inf.get("replicates",2000))
macro("InferenceAlpha", inf.get("alpha",0.05))
macro("CodeCommit", m.get("code_commit", m.get("commit_sha","not\_available")))
if float(inf.get("smoothing",0))>0: macro("InferenceSmoothing", inf["smoothing"])
macro("ScenarioType", sc.get("type","synthetic_audit"))
macro("ScenarioLabel", sc.get("label","Synthetic audit"))
macro("AirMin", thr["air_min"]); macro("EoGapMax", thr["eo_gap_max"]); macro("EceMax", thr["ece_max"])

LaTeX Exec‑Summary fragments

\textbf{Scope and positioning.}
\ifthenelse{\equal{\ScenarioType}{synthetic_audit}}{%
  This whitepaper documents a \textit{synthetic audit scenario} and the evidence artifacts generated.
}{%
  This whitepaper documents a \textit{customer deployment run} and the evidence artifacts generated.
}
It provides metrics/evidence building blocks aligned with ECOA/Reg B, EU AI Act Art. 10, and related frameworks.
It is not a legal opinion or a complete compliance submission.

\medskip
\textbf{Run status.} Thresholds: AIR $\ge$ \AirMin, EO gaps $\le$ \EoGapMax, ECE $\le$ \EceMax. 
\RunStatusLine  % (macro you fill from a small script that tallies violations)

Degeneracy note (conditional)

\IfBooleanTF{\HasDegenerateCIs}{%
  \footnotesize\emph{Note.} Some groups in this \ScenarioType{} have rates at 0\% or 100\%.
  With aggregate bootstrap this can yield zero-width confidence intervals; FL-BSA compliance reports use row-level BCa bootstrap.
}{}

(Set \HasDegenerateCIs true in your preprocessor if any ci_degenerate=true in the CSV.)

⸻

7) Minimal changes checklist (by repo)

(A) fl‑bsa repo
	•	Write ci_method, ci_low, ci_high, ci_degenerate per metric row. (High)
	•	Mirror lower_ci/upper_ci = ci_low/ci_high for back‑compat. (Med)
	•	Manifest: add inference{...}, thresholds{...}, scenario{type,label}. (Med)
	•	Keep EO/ECE capability flags consistent (capabilities.calibration_enabled, capabilities.eo_enabled). (Med)

Rollback: Remove new fields; keep legacy columns; scope hard‑coded in PDF.

(B) whitepaper repo
	•	Prefer ci_low/ci_high; fall back to legacy. (Med)
	•	Preamble macros: \InferenceMethod, \InferenceReplicates, \InferenceAlpha, optional \InferenceSmoothing, \ScenarioType, \ScenarioLabel, thresholds. (Med)
	•	Exec Summary: scope paragraph (parameterized), status line with violation counts. (Med)
	•	ECE display rules per capabilities/file presence; strong default wording when absent. (Low)
	•	Degeneracy note when any ci_degenerate=true. (Low)
	•	Implementation Reference appendix with module names + \CodeCommit. (Low)

⸻

8) Why this setup avoids confusion
	•	Single source of truth for intervals = ci_low/ci_high (+ ci_method).
	•	Legacy columns mirrored = old readers don’t break.
	•	Renderer never computes stats = no drift between PDF and bundle.
	•	Scenario/thresholds parameterized = reusable document for synthetic demos and customer runs.
	•	Smoothing disclosed only when used = transparent, not noisy.

If you’d like, I can turn this into two short PR descriptions (one per repo) with the exact file diffs and checkboxes copied from the checklists above.