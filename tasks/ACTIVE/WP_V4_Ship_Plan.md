# Whitepaper v4 Ship Plan (Decision-Backed, Implementation-Ready)

**Audience:** Engineering (producer `fl-bsa`) + Docs/Release (consumer `fl-bsa-whitepaper`)  
**Status:** Updated Jan 2026 (implementation applied; see §0.2 for current status + remaining TODOs)  
**Decision owner:** (per latest sign-off in chat)  

---

## 0) Signed-Off Decisions (Do Not Re-litigate in Implementation)

1) **Narrative / showcased run**
- Keep the current **gender AIR violation** and frame the paper as: *“the system evaluates fairness and surfaces violations with quantified uncertainty.”*
- Do **not** claim the showcased run is “fair”.

2) **Calibration (ECE)**
- ECE is **out of scope** for this run and must be explicitly reported as **not evaluated**.
- Add a short “when enabled” note and a TODO in SAP/docs (no fake numbers).

3) **Single source of truth (SoT) for “DI” in the whitepaper**
- The whitepaper SoT is **AIR / disparity ratio** from the deterministic uncertainty surface.
- Keep **AIF360 DI** as a **secondary / annex-only** continuity metric (do not use it in Exec Summary).

4) **Race (multi-class) handling**
- Use **pairwise disparity ratios vs a deterministic reference** (race reference = `white`).
- Main PDF shows **worst-case pair** only; annex shows **all pairs**.
- Apply **Holm–Bonferroni** multiplicity control **to p-values** (CIs unadjusted; clearly label this).

5) **Group orientation determinism**
- Reference/protected mapping must be explicit and deterministic; never rely on `unique()` ordering.
- Mapping must be visible in both **producer manifest** and **whitepaper preamble**.

6) **Uncertainty methods (SoT for PDF)**
- **Selection rates:** Wilson intervals.
- **AIR (ratio):** delta method on log-ratio CI (deterministic; no bootstrap).
- **p-values:** two-proportion z-test for large-n; Fisher exact for small-n.
- **No bootstraps in the main whitepaper PDF** (bootstraps may exist only as “non-SoT annex artifacts”).

7) **Metric naming in PDF**
- Use “**Disparity ratio (AIR-equivalent)**” and “**approval-rate gap**” (SRG).
- Do not label anything “EO/EOpp” unless true labels + predicted scores are genuinely in scope.

8) **Visibility thresholds in PDF**
- Gender always visible.
- Race visible in main PDF **only if** each race group meets: `n ≥ 300` and `pct ≥ 5%`; otherwise annex-only with a notice.

9) **Synthetic quality (SQ) threshold**
- SQ threshold `0.8` is **advisory** in v4; if the showcased run does not meet it, the PDF must say so explicitly.
- The evidence bundle must include the synthetic quality certificate fields:
  - `quality_threshold_used` and `quality_threshold_met`.

---

## 0.1) Repo Reality Check (Jan 2026) — What We’re Actually Holding

### Active repos (use these)
- **Producer runtime/gate:** `/home/daimakaimura/fl-bsa`
- **Consumer LaTeX/PDF:** `/home/daimakaimura/fl-bsa-whitepaper`

### Stale repo (do not base new work here)
- **Legacy worktree:** `/home/daimakaimura/fl-bsa-wp-gate`
  - It is **~110 commits behind** `origin/main` (diverged) and should not be the base for v4 changes.
  - It contains **historical prototype work**; v4 changes should live in `/home/daimakaimura/fl-bsa` (producer) and `/home/daimakaimura/fl-bsa-whitepaper` (consumer).

### Branch/remote sync notes (informational)
- `fl-bsa` is on `fix/gate-wp-timeout` at `6aa6212` with **local uncommitted changes** for v4 (fairness uncertainty + bundling).
- `fl-bsa-whitepaper` `main` matches `origin/main` (`d54bba8`) with **local uncommitted changes** (intake + paper sources + generated figures).

---

## 0.2) Current Status (This Worktree)

### Producer (`/home/daimakaimura/fl-bsa`)
- Deterministic AIR uncertainty updated to **Wilson + delta(log AIR)**; race pairs now include **Holm–Bonferroni** adjusted p-values.
- Reviewer ZIP bundling logic updated to include `intake/metrics_uncertainty.json`, `config/fairness_config.yaml`, and **all** `certificates/*.json` (not just model certs).

### Consumer (`/home/daimakaimura/fl-bsa-whitepaper`)
- Paper now uses deterministic **`intake/metrics_uncertainty.json` as SoT** (no bootstrap numbers in main body).
- EO/EOpp wording removed; replaced with **approval-rate gap (SRG)**; race is **gated** out of main body for this run.
- PDF builds successfully to: `/home/daimakaimura/fl-bsa-whitepaper/dist/whitepaper.pdf`.

### Updated reviewer bundle (ready to hand to reviewers)
- `/home/daimakaimura/fl-bsa/artifacts/WhitePaper_Reviewer_Pack_v4.zip` now includes v4-required SoT + configs + certificate set.

### Remaining high-impact TODOs
- Align `config/sap.yaml` wording with v4 deterministic SoT (currently still describes bootstrap/BH; paper does not).
- Fix cross-repo CI intake automation (`pull-wp-intake.yml`) to pull the reviewer ZIP that is actually produced.

---

## 1) Current Baseline (As-Is, Already Produced)

### Evidence bundle (producer output)
- Bundle path: `/home/daimakaimura/fl-bsa/artifacts/WhitePaper_Reviewer_Pack_v4.zip`
- Run ID: `7d94fa9a-1ef3-43d3-a095-58bc2ed78d70`
- Producer commit: `f3cad9686c7ef3f889ebb90a8b73b9e2439a51a1`

**What is inside the current ZIP (25 files)**
- Intake (core): `intake/selection_rates.csv`, `intake/group_confusion.csv`, `intake/regulatory_matrix.csv`
- Intake (tables): `intake/metrics_uncertainty.json` (SoT), `intake/metrics_long.csv` (annex/back-compat)
- Intake (templating): `intake/air_status.json`, `intake/ece_status.json`, `intake/eo_status.json`, `intake/run_summary.json`
- Provenance: `provenance/manifest.json` (includes `fairness_reference_groups`, `fairness_protected_groups`, `fairness_policy`)
- Config: `config/sap.yaml`, `config/fairness_config.yaml`
- Certificates: full set under `certificates/*.json` (includes `synthetic_quality_certificate.json`)
- Metadata: `metadata/tuning_*.json`, `metadata/generator_*meta.json`

### Consumer import + PDF
- Imported into `fl-bsa-whitepaper/intake/…`
- PDF builds to: `fl-bsa-whitepaper/dist/whitepaper.pdf`

### Critical fact (for narrative)
- Gender AIR violates 0.80 threshold (female vs male); race passes but must be treated carefully (multi-class + gating).

---

## 1.1) Gap Summary (What Was Blocking v4, Now Resolved Here)

### Producer → consumer contract gaps
- The reviewer ZIP now includes deterministic SoT (`intake/metrics_uncertainty.json`) and the fairness orientation policy (`config/fairness_config.yaml`), so the consumer no longer needs to depend on bootstrap artifacts for the main body.

### Whitepaper content gaps (LaTeX)
The paper sources were updated to match v4 decisions:
- No EO/EOpp claims; SRG is used instead.
- Deterministic Wilson/delta uncertainty is described; ECE explicitly marked “not evaluated”.
- Race is data-gated out of the main PDF for this run (annex-only).

---

## 2) Producer (`fl-bsa`) Work Summary (v4)

### 2.1 Make deterministic fairness uncertainty the whitepaper SoT

**What already exists (good news):**
- Deterministic uncertainty surface module: `fl-bsa/flbsa/metrics/fairness_uncertainty.py`
- Deterministic orientation policy + race visibility thresholds: `fl-bsa/config/fairness_config.yaml`
- Pipeline already computes `metrics_manifest["fairness_uncertainty"]` using `fairness_config.yaml`:
  - Implementation: `fl-bsa/flbsa/orchestrator/tasks/audit.py`
- Pipeline already writes a validator artifact:
  - `output/<run_id>/validation/metrics_uncertainty.json`

**Status (Jan 2026): Implemented in this worktree**
- Reviewer bundle now includes deterministic SoT: `/home/daimakaimura/fl-bsa/artifacts/WhitePaper_Reviewer_Pack_v4.zip` → `intake/metrics_uncertainty.json`.
- Reviewer bundle now includes fairness policy: `/home/daimakaimura/fl-bsa/artifacts/WhitePaper_Reviewer_Pack_v4.zip` → `config/fairness_config.yaml`.
- Provenance fairness mapping/policy is present in `/home/daimakaimura/fl-bsa/artifacts/WhitePaper_Reviewer_Pack_v4.zip` → `provenance/manifest.json`.
- Producer packager (`fl-bsa/tools/wp/run_wp_evidence.py`) was updated to emit these fields; run one full Gate‑WP evidence run to confirm end-to-end packaging.

**Action**
1) Include deterministic uncertainty artifacts in the reviewer bundle:
   - Add `validation/metrics_uncertainty.json` into the ZIP (recommended location inside ZIP: `intake/metrics_uncertainty.json` to match consumer intake convention).
   - Also include the fairness orientation policy:
     - `config/fairness_config.yaml` into ZIP as `config/fairness_config.yaml`.
2) Ensure `provenance/manifest.json` embeds the resolved mapping (explicit in manifest, not implied):
   - `fairness_reference_groups`: `{gender: male, race: white}`
   - `fairness_protected_groups`: `{gender: [female], race: [black, asian, hispanic, other]}`
   - `display_policy`: `{min_group_n: 300, min_group_pct: 0.05}`

**Where**
- Bundle packaging: `fl-bsa/tools/wp/run_wp_evidence.py` (`_package_bundle`)
- Provenance patching (best-effort is fine for v4): `fl-bsa/tools/wp/run_wp_evidence.py` (after the pipeline completes, when it already patches `provenance/manifest.json`)
  - Reference implementation exists in the stale worktree: `fl-bsa-wp-gate/tools/wp/run_wp_evidence.py`

**Acceptance**
- `zipinfo -1 WhitePaper_Reviewer_Pack_v4.zip` lists:
  - `intake/metrics_uncertainty.json`
  - `config/fairness_config.yaml`
- Whitepaper can be built using only deterministic SoT artifacts (no bootstrap required).

---

### 2.1b Include synthetic quality evidence (SQ) in the reviewer bundle

**Status (Jan 2026): Implemented in this worktree**
- Reviewer bundle includes the full certificate set under `certificates/*.json` (including `synthetic_quality_certificate.json`).

**Action**
- Include at least these certificates in the reviewer ZIP under `certificates/`:
  - `synthetic_quality_certificate.json`
  - `synthetic_validation_certificate.json`
  - `regulatory_alignment_certificate.json`
  - (keep existing) `model_certificate_amplification.json`, `model_certificate_intrinsic.json`

**Where**
- `fl-bsa/tools/wp/run_wp_evidence.py` (`_package_bundle`: include more `certificates/*.json`)
  - Reference implementation exists in the stale worktree: `fl-bsa-wp-gate/tools/wp/run_wp_evidence.py`

**Acceptance**
- Reviewer ZIP contains `certificates/synthetic_quality_certificate.json`.
- Whitepaper can point to concrete SQ evidence inside the bundle.

---

### 2.2 Update AIR CI method to delta-log-ratio (SoT)

**Status (Jan 2026): Implemented in `fl-bsa`**
- AIR CI now uses delta-method CI on `log(AIR)` (stored as `method: wilson+delta`); selection-rate CIs remain Wilson.

**Action**
- Implement delta-method CI on `log(AIR)` and store it as the SoT AIR CI:
  - `log(AIR) = log(p_prot) − log(p_ref)`
  - `Var(log(p)) ≈ (1 − p) / (p · n)` (binomial MLE approximation)
  - `CI = exp(log(AIR) ± z · SE)`
- Preserve Wilson CIs for each group selection rate (still useful and deterministic).

**Where**
- `fl-bsa/flbsa/metrics/fairness_uncertainty.py`

**Acceptance**
- For the current bundle counts (female 2127/4822, male 2966/5178), AIR CI is approximately `[0.741, 0.799]` (close to the prior bootstrap CI).
- AIR CI remains deterministic across runs and independent of bootstrap replicates.

---

### 2.3 Race multiplicity control (Holm–Bonferroni)

**Status (Jan 2026): Implemented in `fl-bsa`**
- Race pairs include Holm–Bonferroni adjusted p-values (`p_value_adjusted`, `p_value_adjustment: holm_bonferroni`).

**Action**
- Compute and store Holm–Bonferroni adjusted p-values for race pairs vs reference:
  - Add `p_value_adjusted` and `adjustment_method: holm_bonferroni` to each pair.
- Main PDF uses adjusted p-values; annex shows both (raw + adjusted).

**Where**
- `fl-bsa/flbsa/metrics/fairness_uncertainty.py` (new helper: `holm_adjust_p_values()`)
- `fl-bsa/flbsa/orchestrator/tasks/audit.py` (if it assembles race “pairs” structure, ensure adjusted fields propagate)

**Acceptance**
- Adjusted p-values are monotone and `p_adj ≥ p_raw` for each pair.
- Worst-case pair selection is by AIR point (or by minimum lower CI—choose and document).

---

### 2.4 Keep bootstrap artifacts (optional annex-only)

**Decision**
- Bootstraps are allowed only as “additional analysis” and must not be SoT for the PDF.

**Action**
- If keeping bootstrap outputs, relocate/label them clearly under an annex path in the bundle, e.g.:
  - `intake/annex/metrics_long_bootstrap.csv`
  - `intake/annex/plots/*`
- Ensure the deterministic SoT files remain primary.

**Where**
- `fl-bsa/tools/wp/run_wp_evidence.py` (bundle layout)
- Potentially `fl-bsa/flbsa/metrics/wp_intake.py` (if you keep generating bootstrap metrics_long.csv for annex)

**Acceptance**
- Main PDF builds without reading any bootstrap artifact.
- Annex is clearly marked “non-SoT”.

---

### 2.5 Align SAP with v4 SoT (recommended)

**Why**
- Today the producer SAP (`fl-bsa/config/sap.yaml`) still encodes bootstrap + BH multiplicity, while v4 sign-off requires deterministic Wilson/delta + Holm for race p-values (and “ECE not evaluated” for this scenario).

**Action**
- Update the producer SAP to reflect what the paper will claim and what the SoT artifact will contain:
  - AIR: Wilson + delta-log-ratio CI (deterministic SoT)
  - Race multiplicity: Holm–Bonferroni on p-values (explicitly scoped to race pairs)
  - ECE: explicitly marked “not evaluated” for this scenario, with “when enabled” requirements
  - Bootstrap: optional annex-only (if retained at all)

**Where**
- `fl-bsa/config/sap.yaml` (producer contract shipped in the reviewer ZIP)

**Acceptance**
- The reviewer ZIP’s `config/sap.yaml` matches the Methods section and the numbers printed in the main body.

---

## 3) Consumer (`fl-bsa-whitepaper`) Work Summary (v4)

### 3.1 Switch paper SoT to deterministic uncertainty artifacts

**Status (Jan 2026): Implemented in this worktree**

**Action**
1) Update intake expectations:
   - Add required: `intake/metrics_uncertainty.json` (deterministic SoT).
   - Treat `intake/metrics_long.csv` as annex-only (or optional).
2) Update macro/table generation:
   - Build Exec Summary + key tables from deterministic SoT.
   - Keep selection-rate plots (Wilson) driven from `intake/selection_rates.csv`.

**Where**
- Macro generators:
  - `fl-bsa-whitepaper/scripts/gen_tex_macros_from_metrics.py` (refactor or add new script that reads `metrics_uncertainty.json`)
  - `fl-bsa-whitepaper/scripts/gen_tex_preamble_from_manifest.py` (already reads manifest; extend to read fairness mapping if added)
- LaTeX:
  - `fl-bsa-whitepaper/sections/01_executive_summary.tex`
  - `fl-bsa-whitepaper/sections/02_problem_estimands.tex`
  - `fl-bsa-whitepaper/sections/03_methods.tex`
  - `fl-bsa-whitepaper/sections/06_results.tex`

**Acceptance**
- The PDF’s headline numbers (AIR + approval-rate gap) come from `metrics_uncertainty.json` only.
- The language matches the “evaluate fairness / surface violations” narrative.

---

### 3.2 Replace EO/EOpp sections with approval-rate gap (SRG)

**Status (Jan 2026): Implemented in this worktree**

**Action**
- Remove “Equalised Odds” terminology unless true labels/predictions are actually in scope.
- Add SRG (approval-rate gap) tables and definitions.

**Where**
- `fl-bsa-whitepaper/sections/02_problem_estimands.tex` (remove EO equations; add SRG definition)
- `fl-bsa-whitepaper/sections/06_results.tex` (replace EO table with SRG table)
- `fl-bsa-whitepaper/sections/appendix_b_metrics_defs.tex` (update quick-reference terms)

**Acceptance**
- No “EO / EOpp / TPR / FPR” claims remain in the whitepaper unless backed by genuine labels/predictions.

---

### 3.3 Enforce race visibility policy in PDF

**Status (Jan 2026): Implemented in this worktree**

**Action**
- Implement gating:
  - If `metrics_uncertainty.json` says `display_in_main_pdf=false`, hide race in main body and show annex-only with notice.
  - Otherwise show worst-case pair in main.

**Where**
- Table generator script(s) and LaTeX conditionals (prefer data-driven macro like `\\ShowRaceMain{0|1}`).

**Acceptance**
- For current run, race is annex-only (because `other` is below thresholds).

---

### 3.3b Apply race gating to plots (not just tables)

**Status (Jan 2026): Implemented in this worktree**

**Why**
- The current figure generator (`scripts/gen_plots_from_intake.py`) always plots race when present, which violates the v4 “race annex-only when small-n” policy.

**Action**
- Drive plotting from the same policy signal used by the tables:
  - Preferred: read `intake/metrics_uncertainty.json` and use `fairness_uncertainty.race.display_in_main_pdf`
  - Alternative (fallback): compute `min_group_n`/`min_group_pct` directly from `intake/selection_rates.csv`

**Where**
- `fl-bsa-whitepaper/scripts/gen_plots_from_intake.py`

**Acceptance**
- For the current run, the published figures include **gender only** in the main PDF; race figures move to annex or are omitted.

---

### 3.3c SAP unification (producer SAP is the SoT)

**Current state**
- `fl-bsa-whitepaper/config/sap.yaml` is a local copy with a different shape and bootstrap settings than `fl-bsa/config/sap.yaml` (the file that actually ships in the reviewer ZIP).

**Action**
- Make the whitepaper build consume the *run’s SAP from the bundle* (or a copied-in exact replica), not a repo-local fork.
  - Option A: on intake import, overwrite/refresh `fl-bsa-whitepaper/config/sap.yaml` from the ZIP.
  - Option B: keep `fl-bsa-whitepaper/config/sap.yaml` but regenerate it at build time from `intake/` (discouraged unless versioned).
  - Option C: point macro scripts to `intake/sap.yaml` and stop using `config/sap.yaml` for run-specific parameters.

**Acceptance**
- The paper’s thresholds, methods, and “not evaluated” claims match the exact `config/sap.yaml` shipped with the evidence ZIP used for that PDF build.

---

### 3.4 Update docs/specs to match the actual producer contract

**Action**
- Bring these in sync with the producer validator and actual bundle contents:
  - `fl-bsa-whitepaper/ops/Bundle_Spec_v4.md`
  - `fl-bsa-whitepaper/tasks/Intake.md`
  - `fl-bsa-whitepaper/docs/data_pipeline_spec.md`
  - `fl-bsa-whitepaper/docs/ci_intake.md` and `.github/workflows/pull-wp-intake.yml` (see 3.5)

**Acceptance**
- All docs reference the correct producer validator: `fl-bsa/tools/ci/validate_wp_intake.py`.
- Docs no longer claim `metrics.json` is required in the reviewer ZIP (unless you add it).
- Required/optional file lists match `zipinfo` output.

---

### 3.4b Add SQ advisory statement (threshold not met)

**Status (Jan 2026): Implemented in this worktree**

**Action**
- Add a short, explicit statement in Methods or Limitations:
  - “Synthetic quality threshold used is 0.8; this run did not meet the threshold; treat SQ as advisory for v4.”
- Drive it from the certificate values in the evidence bundle; do not hard-code.

**Where**
- LaTeX (recommended):
  - `fl-bsa-whitepaper/sections/03_methods.tex` or `fl-bsa-whitepaper/sections/10_limitations_monitoring.tex`
- Table/macro generator: add macros like `\\SqThresholdUsed`, `\\SqThresholdMet`.

**Acceptance**
- If `quality_threshold_met=false` in the bundle, the PDF shows the advisory line.

---

### 3.5 Fix cross-repo automation (optional for v4 ship; required for long-term)

**Current state**
- `fl-bsa-whitepaper/.github/workflows/pull-wp-intake.yml` has an `if:` that prevents `schedule` and `repository_dispatch` from running.
- It expects a `wp-intake` artifact + `index.json`, but the producer workflow publishes a reviewer ZIP.

**Action**
- Update automation to download and import the actual reviewer ZIP produced by `fl-bsa`:
  - Producer: `fl-bsa/.github/workflows/wp-evidence-nightly.yml` uploads `WhitePaper_Reviewer_Pack_v4.zip`.
  - Consumer should download that ZIP (from artifacts or from a release) and unpack into `intake/`.

**Acceptance**
- Scheduled pull updates intake and rebuilds PDF without manual steps.

---

### 3.6 Release packaging: attach the exact evidence ZIP used

**Action**
- Modify `fl-bsa-whitepaper/.github/workflows/latex.yml` to attach:
  - `dist/whitepaper.pdf`
  - `dist/whitepaper_arxiv_source.zip`
  - the exact `WhitePaper_Reviewer_Pack_v4.zip` used for that release (either committed under `artifacts/archive/` or fetched in CI).

**Acceptance**
- A release is a one-stop download: PDF + source + evidence ZIP.

---

## 4) Validation / Acceptance Checklist (End-to-End)

1) **Determinism**
- Rebuild PDF 3× → identical AIR values, labels, and tables.
- Shuffle CSV row order → identical reference/protected mapping and identical results.

2) **Math spot-check**
- Hand-check gender AIR and delta CI matches counts from `selection_rates.csv`.

3) **Small-n policy**
- Force a tiny cell in a test fixture (or a synthetic scenario) → Fisher exact is used and surfaced.

4) **Multiplicity**
- Race annex shows Holm-adjusted p-values.

5) **Visibility gating**
- Gender always visible.
- Race main-body visibility matches `display_in_main_pdf` policy.

6) **Spec conformance**
- Producer-side validator passes on the output root for the WP run.
- Consumer-side docs/spec match producer artifacts.

7) **SQ evidence**
- Evidence ZIP contains `certificates/synthetic_quality_certificate.json`.
- PDF statement matches `quality_threshold_used` and `quality_threshold_met`.

---

## 5) Open Items (Must Be Explicitly Scoped)

1) **ECE**
- Explicitly “not evaluated” for v4.
- Any mention of ECE thresholds must be framed as “SAP threshold defined; not evaluated in this scenario”.

2) **Drift uncertainty (PSI/KS CIs)**
- Out of scope for v4; must not be implied as computed.

3) **Dataset hash formatting**
- Current manifests use raw hex (no `sha256:` prefix). Decide the contract and make docs consistent.
