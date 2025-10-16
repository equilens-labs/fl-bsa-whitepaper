# Bundle Spec v4 — **fl-bsa-whitepaper** (separate repo)

> **Repo root**: `/data/projects/fl-bsa-whitepaper` (this repo is **independent** from the main `fl-bsa` repo).  
> **Assumption**: You have already unzipped the two scaffolds into this repo (resync scaffold + gate pack).

---

## 1) Overview (what this produces)
A reviewer‑ready zip **`out/WhitePaper_Reviewer_Pack_v4.zip`** that contains:
- **`intake/metrics_long.csv`** — global metrics (**AIR**, **tpr_gap**, **fpr_gap**, **ece**) each with **95% CIs** and `n`; per‑group **selection_rate**, **tpr**, **fpr** with CIs and `n`.
- **`provenance/manifest.json`** — **non‑placeholder** container digest, dataset hash, code commit, RNG seed, hardware, timestamps.
- **`intake/regulatory_matrix.csv`** — no TBDs for in‑scope controls.
- **`privacy/tests/`** — `privacy_evidence_membership.json`, `privacy_evidence_attribute.json`, `dp_accounting.json`.
- **`config/sap.yaml`** — thresholds and bootstrap settings.

_Optional but recommended_: `intake/group_summary_*.csv`, `intake/feature_missingness_*.csv`, `traceability_matrix.csv`, and the refreshed draft (`docs/WhitePaper_Intake_Compiled.md` or PDF).

---

## 2) Directory mappings (after unzipping the two scaffolds)
- `scripts/` — `compute_metrics.py`, `check_acceptance.py`, `verify_reviewer_bundle.py`, `build_reviewer_bundle.py`
- `config/` — `sap.yaml` (central thresholds: **AIR ≥ 0.80**, **EO gaps ≤ 0.05**, **ECE ≤ 0.02**; bootstrap B, seed)
- `provenance/` — `capture_provenance.sh` (emits `manifest.json`)
- `schemas/` — JSON Schemas for `metrics_long` and `manifest`
- `privacy/tests/` — privacy evidence JSONs (replace stubs with real results)
- `.github/workflows/` — `acceptance_strict.yml` (CI gate)
- `docs/` — reviewer bundle spec, DoD, draft content
- **`intake/`** — **this repo’s canonical location** for aggregated inputs and generated metrics:  
  - Inputs: `selection_rates.csv`, `group_confusion.csv`, `calibration_bins.csv`, `regulatory_matrix.csv`  
  - Outputs: `metrics_long.csv`
- `out/` — packaged reviewer bundles

> **Separation from `../fl-bsa`:** this repo is self‑contained. If you need a container digest from the main repo’s pipeline, fetch the digest from your registry and pass it to `capture_provenance.sh` via `CONTAINER_REF` (no direct code coupling).

---

## 3) Required bundle contents (validation rules)
**Must include:**
1. `intake/metrics_long.csv`  
   - Global metrics: `AIR`, `tpr_gap`, `fpr_gap`, `ece` — each with columns: `run_id,split,model_id,metric,group,value,lower_ci,upper_ci,n`.  
   - Per‑group metrics: `selection_rate`, `tpr`, `fpr` for each `attr:value` with **Wilson 95% CIs** and `n`.  
   - **Conventions**:  
     - `metric` names lowercase; `group` formatted as `attr:value` (e.g., `gender:female`, `race:asian`).  
     - `split` ∈ {`train`,`validation`,`test`,`synthetic`} (yours may differ; keep consistent).  
     - **Stable** `run_id` across drops (set via `--run-id` or env `RUN_ID`).

2. `provenance/manifest.json`  
   - Required keys: `run_id`, `dataset_hash` (`sha256:...`), `code_commit`, `container_digest` (`repo@sha256:...`), `rng_seed`, `hardware`, `start_ts`, `end_ts`.  
   - **No placeholders** for `container_digest`. Get a real digest: e.g., `docker inspect --format='{{index .RepoDigests 0}}' <image:tag>` or `skopeo inspect docker://…`.

3. `intake/regulatory_matrix.csv`  
   - Columns: `framework, citation, requirement_text, control_assurance, evidence_artifact, owner, status, notes`.  
   - `status` ∈ {`in-place`,`validated`,`planned`} (no `TBD` for in‑scope items).

4. `privacy/tests/`  
   - `privacy_evidence_membership.json` (keys: `mi_auc`, `method`, `notes`).  
   - `privacy_evidence_attribute.json` (keys: `ai_auc`, `method`, `notes`).  
   - `dp_accounting.json` (keys: `epsilon`, `delta`, `accountant`, `notes` if DP not claimed).

5. `config/sap.yaml`  
   - `thresholds`: `air_min: 0.80`, `tpr_gap_max: 0.05`, `fpr_gap_max: 0.05`, `ece_max: 0.02`.  
   - `bootstrap`: `B: 2000`, `seed: 42`, `method: percentile`.

**CI blocks merges** if any required file is missing, any threshold is violated, schemas break, privacy JSONs are absent, or `container_digest` is a placeholder.

---

## 4) Generation flow (aligned to this repo layout)
1. **Compute metrics** (AIR/EO/ECE with 95% CIs):  
   ```bash
   python3 scripts/compute_metrics.py      --inputs intake      --sap config/sap.yaml      --out intake/metrics_long.csv      --run-id "$(date +%Y%m%d-%H%M%S)"      --model-id generator_both.pkl      --split synthetic
   ```

2. **Capture provenance** (align `RUN_ID` with step 1):  
   ```bash
   export RUN_ID="$(date +%Y%m%d-%H%M%S)"   # use the same value as above
   bash provenance/capture_provenance.sh      CONTAINER_REF=registry.example.com/fl-bsa/generator@sha256:…      DATASET_PATH=intake/selection_rates.csv      RNG_SEED=42
   ```

3. **Validate thresholds & schemas**:  
   ```bash
   python3 scripts/check_acceptance.py      --metrics intake/metrics_long.csv      --manifests provenance/manifest.json      --sap config/sap.yaml
   ```

4. **Verify reviewer bundle completeness**:  
   ```bash
   python3 scripts/verify_reviewer_bundle.py      --metrics intake/metrics_long.csv      --manifest provenance/manifest.json      --regulatory intake/regulatory_matrix.csv      --privacy privacy/tests      --sap config/sap.yaml
   ```

5. **Package** (creates `out/WhitePaper_Reviewer_Pack_v4.zip`):  
   ```bash
   python3 scripts/build_reviewer_bundle.py --out-dir out --zip-name WhitePaper_Reviewer_Pack_v4.zip
   # Convenience:
   make verify && make bundle
   ```

---

## 5) CI enforcement (separate whitepaper repo)
The strict workflow **must** reference the **intake/** path. Ensure your `.github/workflows/acceptance_strict.yml` uses:
```yaml
- run: python scripts/verify_reviewer_bundle.py         --metrics intake/metrics_long.csv         --manifest provenance/manifest.json         --regulatory intake/regulatory_matrix.csv         --privacy privacy/tests         --sap config/sap.yaml
```
PRs use `.github/PULL_REQUEST_TEMPLATE.md` and DoD (`docs/WP-DoD.md`) to confirm the bundle is reviewer‑ready.

---

## 6) Style & consistency guidelines
- **Paths:** use `intake/…` for all inputs/metrics; `provenance/…` for manifests; `out/…` for packs; `docs/…` for narrative.  
- **Names:** lowercase `snake_case` for files; metrics lowercase (`air`,`tpr_gap`,`fpr_gap`,`ece`,`selection_rate`,`tpr`,`fpr`).  
- **Groups:** `attr:value` everywhere (e.g., `gender:female`), stable across runs.  
- **Dates/IDs:** ISO timestamps; stable `run_id` aligned between metrics and manifest.  
- **CIs:** include `lower_ci`/`upper_ci` and `n` for every metric row that represents a proportion or global composite.  
- **Traceability:** regenerate `traceability_matrix.csv` whenever metrics or claims change.

---

## 7) Troubleshooting
- **CI fails on `container_digest`** → pass a real digest via `CONTAINER_REF`; avoid `not_available`.  
- **Missing EO/ECE** → ensure `intake/group_confusion.csv` (tp/fp/tn/fn by attr/value) and `intake/calibration_bins.csv` (bin counts, positives, mean_pred) are present.  
- **Schema errors** → check required columns in `metrics_long.csv`: `run_id,split,model_id,metric,group,value,lower_ci,upper_ci,n`.  
- **Regulatory TBDs** → replace `TBD` with `planned` (or stronger) for in‑scope rows.

---

## 8) Independence from `../fl-bsa`
- This repo does **not** depend on the main `fl-bsa` codebase.  
- Optional linkage: fetch **container digests** published by `../fl-bsa` CI/CD to your registry and pass them here via `CONTAINER_REF`.  
- Keep whitepaper artifacts, metrics, and evidence **inside this repo**; never read raw customer data.

---

**Done right**, running `make verify && make bundle` yields a reviewer‑ready `out/WhitePaper_Reviewer_Pack_v4.zip` with strict checks enforced in CI.
