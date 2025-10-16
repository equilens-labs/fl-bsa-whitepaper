# FL-BSA Fairness & Calibration Evidence Pipeline

This document specifies the engineering work required in the **main `fl-bsa` repository** to generate the evidence artifacts consumed by the independent `fl-bsa-whitepaper` repo. Once complete, the whitepaper team will be able to produce reviewer bundles and the LaTeX publication directly from the outputs of the product pipeline.

The scope below stitches together what Block‑2/3 planned (audit scoring, EO/ECE metrics, provenance capture) with the whitepaper bundle contracts (AIR/EO/ECE with CIs, privacy evidence). Treat this as the implementation blueprint for the missing pieces.

---

## 1. Target Artifacts (to produce per pipeline run)

| Path (in `fl-bsa-whitepaper`) | Generated from | Notes |
| --- | --- | --- |
| `intake/selection_rates.csv` | selection rate aggregates per attribute/value | Required for AIR computation with CIs |
| `intake/group_confusion.csv` | group-wise TP/FP/TN/FN counts | Enables EO gaps + Wilson CIs |
| `intake/calibration_bins.csv` | calibration bins with scores + outcomes | Feeds ECE + bootstrap |
| `intake/metrics_long.csv` | derived from the three CSVs above | Must contain `AIR`, `tpr_gap`, `fpr_gap`, `ece`, and per-group `selection_rate`, `tpr`, `fpr` with 95% CIs |
| `provenance/manifest.json` | orchestration metadata | Needs real dataset hash, container digest, code commit, run_id, RNG seed |
| `privacy/tests/*.json` | privacy harness results | Membership, attribute inference, DP accounting |

The first three CSVs must be emitted by the `fl-bsa` pipeline. `fl-bsa-whitepaper` then reads them via `scripts/compute_metrics.py` to produce `metrics_long.csv`. The provenance manifest and privacy outputs can originate in `fl-bsa` and be copied across unmodified.

---

## 2. High-Level Flow (within `fl-bsa`)

```
┌────────────────────────────┐
│  Audit Scoring Component   │  (fit/eval logistic model with fixed seeds)
└────────────┬───────────────┘
             │ confusion counts + calibration bins + selection rates
┌────────────▼───────────────┐
│  Metrics Writer Layer      │  (write CSVs → metrics_long rows)
└────────────┬───────────────┘
             │ manifest data
┌────────────▼───────────────┐
│  Provenance Capture        │  (dataset hash, container digest, seeds, hardware)
└────────────┬───────────────┘
             │ privacy harness outputs
┌────────────▼───────────────┐
│  Evidence Bundler          │  (optional: zip + schemas)
└────────────┬───────────────┘
             │ copy/drop into `fl-bsa-whitepaper`
┌────────────▼───────────────┐
│  Whitepaper repo tooling   │  (compute metrics_long, verify, bundle, LaTeX)
└────────────────────────────┘
```

---

## 3. Detailed Requirements

### 3.1 Audit Scoring Component (ASC)

**Goal**: deterministically produce predictions (`ŷ`, `ŝ`) and group confusion matrices for fairness metrics.

- **Module**: `flbsa/analysis/audit_scoring.py`
- **Entrypoints**:
  - `fit_audit_model(X, y, seed, calibrate: bool) -> AuditModel`
  - `evaluate_by_group(model, X, y, group_map, thresholds, bins) -> {selection_rates, confusion_df, calibration_df}`
- **Implementation notes**:
  - Model: logistic regression with L2 regularisation (scikit-learn), seed all RNGs.
  - Optional calibration: isotonic or Platt scaling (seeded).
  - Split policy: use validation/test splits from pipeline metadata (fall back to synthetic/test) – record `split` used.
  - Output CSVs **per run**:
    - `selection_rates.csv`: columns `attr,group_value,selected,n` (with deterministic ordering).
    - `group_confusion.csv`: `attr,group_value,tp,fp,tn,fn` per split.
    - `calibration_bins.csv`: `bin_lower,bin_upper,n,positives,mean_pred` plus optional `attr,group_value` for group calibration.
  - Write CSVs under pipeline run directory (e.g., `OUTPUT_DIR/<pipeline_id>/audit/`).
  - Return summary dict for metrics layer (see below).

### 3.2 Metrics Computation Layer

**Goal**: convert ASC outputs into `metrics_long.csv` rows with CIs.

- **Module**: `flbsa/metrics/fairness_groupwise.py`
- **Functions**:
  - `compute_air(selection_rates, threshold=0.80) -> list[MetricRow]`
  - `compute_equalized_odds(confusion_df, alpha=0.05) -> list[MetricRow]`
  - `compute_calibration(calibration_df, B=2000, seed=42) -> list[MetricRow]`
- **Metric row schema** (match whitepaper repo):
  ```python
  MetricRow = dict(
      run_id=str,
      split=str,
      model_id=str,
      metric=str,          # air, tpr_gap, fpr_gap, ece, selection_rate, tpr, fpr
      group=str,           # attr:value or "all"
      value=float,
      lower_ci=float,
      upper_ci=float,
      n=int,
  )
  ```
- **Key calculations**:
  - **AIR**: highest selection_rate per attribute is the denominator; compute ratio + bootstrap CIs (binomial resample of counts).
  - **Equalized odds**: derive TPR/FPR per group → compute gaps to reference; Wilson CIs for rates, bootstrap for gaps if needed.
  - **ECE**: Weighted average of |mean_pred - empirical positive rate| per bin; B=2000 bootstrap on bin contributions.
  - Include per-group selection_rate/tpr/fpr rows with their own Wilson CIs and sample counts (`n`).
  - Align `run_id`, `split`, `model_id` with pipeline metadata (store once upstream).
- **Writers**: extend `metrics_long.csv` (append or overwrite) and update JSON metrics manifest (if present).

### 3.3 Provenance Capture

- Extend existing manifests in `flbsa/orchestrator/tasks/synthetic_validation.py`:
  - Capture `dataset_hash` (sha256 of ingested dataset or metadata-supplied hash).
  - Record `code_commit` (git SHA), `container_digest` (from environment `FLBSA_WORKER_IMAGE_DIGEST` etc.), `rng_seed`, `hardware`, `start_ts`, `end_ts`.
  - Ensure manifests are serialised to `manifest_<run_id>.json` and main `manifest.json`.
- Provide CLI hook to export a whitepaper-ready manifest (JSON schema match to v4).

### 3.4 Privacy Evidence Harness

- Stabilise the privacy attack scripts in `flbsa/security/privacy_attacks.py`:
  - Membership inference (MI) → produce `privacy_evidence_membership.json` with AUC/advantage and params.
  - Attribute inference (AI) → same schema.
  - DP accounting (if DP claimed) → `dp_accounting.json` with ε, δ, accountant description. If not using DP, record `claimed: false` message.
- Ensure outputs write to predictable path (e.g., `OUTPUT_DIR/<pipeline_id>/privacy/`).

### 3.5 Evidence Bundler Integration (optional but recommended)

- The existing evidence bundler (Block‑3 tasks) should include the new CSVs and privacy outputs.
- Ensure bundler manifest references `metrics_long.csv`, confusion/calibration CSVs, privacy JSONs, generator manifest, certificates, etc.

---

## 4. File Layout (within `fl-bsa`)

```
flbsa/
  analysis/
    audit_scoring.py         # new ASC module
  metrics/
    fairness_groupwise.py    # new fairness computations
    aggregate_writer.py      # helper to append metrics_long rows
  orchestrator/tasks/
    synthetic_validation.py  # integrate ASC + metrics + provenance
    audit.py                  # call ASC; write CSVs
  security/
    privacy_attacks.py       # emit privacy evidence JSONs

configs/
  sap.yaml (optional mirror of thresholds)

OUTPUT_DIR/<pipeline_id>/
  audit/
    selection_rates.csv
    group_confusion.csv
    calibration_bins.csv
  metrics/
    metrics_long.csv
  provenance/
    manifest.json
  privacy/
    privacy_evidence_membership.json
    privacy_evidence_attribute.json
    dp_accounting.json
  evidence.zip (optional bundler)
```

---

## 5. CLI / Developer Workflow (in `fl-bsa`)

1. Run the calibration + synthesis pipeline (existing flow):
   ```bash
   make gate-p  # or the relevant E2E orchestration target
   ```
2. Ensure the pipeline writes the three aggregate CSVs and privacy evidence to `OUTPUT_DIR/<pipeline_id>/...` as laid out above.
3. Optional: run a new helper script to copy artefacts into `fl-bsa-whitepaper/intake/` (can be a simple rsync script once outputs exist).
4. Once copied, the whitepaper repo runbook (`ops/runbook_bundle_v4.sh`) can compute metrics_long, validate, and package.

---

## 6. Testing Strategy

### 6.1 Unit Tests
- `tests/analysis/test_audit_scoring.py`
  - Determinism checks (same seed → same coefficients).
  - Group confusion counts on toy data.
- `tests/metrics/test_fairness_groupwise.py`
  - AIR ratios vs known values, bootstrap CIs vs reference.
  - Wilson interval correctness for TPR/FPR (compare to statsmodels or manual calculations).
  - ECE bootstrap replicability with fixed seed.
- `tests/security/test_privacy_attacks.py`
  - JSON schema and key presence.

### 6.2 Integration Tests
- `tests/integration/test_metrics_pipeline.py`
  - Run ASC → metrics layer end-to-end on a synthetic dataset; assert the three CSVs and metrics_long rows exist with expected counts/values.
- `tests/integration/test_provenance_manifest.py`
  - Set env digests + dataset paths; assert manifest fields match; fail if placeholder.
- `tests/integration/test_privacy_artifacts.py`
  - Run attacks on sample dataset; verify JSONs are created and parse correctly.

### 6.3 E2E / Gate Tests
- Extend the Gate‑P suite to check that `metrics_long.csv` contains AIR/EO/ECE, that CIs exist, and that provenance digest isn’t `not_available`.
- Add a nightly job for full bootstrap (B=2000) to keep CI runtime low (Gate‑P can use B=200 with documented approximation).

---

## 7. Acceptance Criteria

- **CSV Outputs**: `selection_rates.csv`, `group_confusion.csv`, `calibration_bins.csv` produced per run with stable schema.
- **metrics_long.csv**: contains AIR, tpr_gap, fpr_gap, ece rows with 95% CIs and per-group selection_rate/tpr/fpr entries.
- **Provenance**: manifest JSON includes real container digest, dataset hash, code commit, RNG seed, start/end timestamps.
- **Privacy Evidence**: membership and attribute inference JSONs plus DP accounting present for each run.
- **Tests**: unit + integration tests passing; new CI gates prevent regressions.
- **Documentation**: developer README or wiki page explaining how to run the new pipeline and where files land.

---

## 8. Handoff to Whitepaper Repo

Once the above exists:

1. Copy CSVs & JSONs from `fl-bsa` run directory into `fl-bsa-whitepaper/intake/` and `.../privacy/tests/`.
2. Run `python3 scripts/compute_metrics.py --inputs intake --sap config/sap.yaml --out intake/metrics_long.csv --run-id <run> ...` inside the whitepaper repo.
3. Execute `make verify && make bundle` to validate thresholds and produce `out/WhitePaper_Reviewer_Pack_v4.zip`.
4. `make pdf` / `make arxiv` to refresh the LaTeX output, then tag a release (CI posts PDF + arXiv bundle automatically).

---

## 9. Open Questions / Decisions

- **Where to store ASC CSVs**: Suggested `OUTPUT_DIR/<pipeline_id>/audit/`; confirm with infra.
- **Bootstrap compute budget**: Gate‑P vs nightly B parameter (200 vs 2000) to balance runtime vs accuracy.
- **Privacy harness runtime**: ensure tests are fast enough for Gate‑P; maybe nightly runs heavier parameter sweeps.
- **Manifest schema versioning**: align with whitepaper repo expectation (e.g., `schema_version: reviewer.v4`).
- **Automation for copying to whitepaper repo**: optional script once pipeline path is stable.

---

Deliverables here unlock the final reviewer bundle and whitepaper automation. Implementing this spec in `fl-bsa` should be treated as priority work for Block‑2/3 catch-up so the whitepaper team can operate independently.
