# White Paper Intake — All Questions & Command Templates (v1.0, 2025‑10‑07)

This document lists **everything we need** to produce a mathematically and statistically rigorous white paper.
You can complete it directly in Markdown or use the attached CSV/JSON/YAML templates in the `whitepaper_intake_templates/` folder.

---

## 0) Quick-start checklist
- [ ] Confirm **scope & audience** (Section 1)
- [ ] Fill the **Regulatory Matrix** (`regulatory_matrix.csv`) (Section 2)
- [ ] Export **aggregated data artifacts** (no row-level data) — see `dataset_summary.csv`, `group_summary.csv`, `feature_missingness.csv` (Section 3)
- [ ] Provide **Statistical Analysis Plan (SAP)** (`sap_template.md`) or fill this section (Section 4)
- [ ] Supply **Model & Algorithm** specifics (`model_hyperparams.yaml`, pseudocode, privacy notes) (Section 5)
- [ ] Define **Evaluation Design** and provide **metrics exports** (`metrics_long.csv`, `runs.json`) (Section 6)
- [ ] Attach **Compliance evidence** and governance contacts (`governance_contacts.csv`) (Section 7)
- [ ] Provide **Security/Privacy/Operations** details (Section 8)
- [ ] Provide **Reproducibility** manifest and a worked synthetic example (Section 9)
- [ ] Provide **Legal/IP & licensing** inventory (`licenses_inventory.csv`) (Section 10)

---

## 1) Scope & Audience
**Please answer succinctly.**

1. **Primary audience**: (e.g., regulators, bank model‑risk, execs, DS leads).
2. **Decisions to support**: (e.g., procurement, validation, sign‑off, compliance attestation).
3. **Top claims to substantiate** (bullet list):
   - _Example_: “Synthetic borrowers preserve pairwise & higher‑order dependencies within ±δ for features S.”
   - _Example_: “Fairness metric **AIR** ≥ 0.80 with 95% CI across protected classes.”
4. **Context constraints**: (no‑data‑leaves, on‑prem, air‑gapped, allowable telemetry).
5. **Reader prerequisites**: (math level, statistics level, regulatory familiarity).
6. **Document tone**: (proof‑oriented, empirical‑audit, executive‑readable appendices).

---

## 2) Regulatory & Policy Mapping
**Provide or fill `whitepaper_intake_templates/regulatory_matrix.csv`.**

For each framework (e.g., ECOA/Reg B, CFPB guidance, FCA Consumer Duty, EU AI Act, SR 11‑7, NIST AI RMF, ISO/IEC 23894):
- Citation / requirement text
- Control / assurance (what you do)
- Evidence we can include (artifact/file/ref)
- Responsible owner
- Status (planned / in‑place / validated)
- Notes

**Questions**
1. Which frameworks apply to this deployment?
2. Client‑specific **fairness policy** (thresholds, e.g., 80% rule / AIR ≥ 0.8; EO gaps ≤ X).
3. **Explainability expectations** (ECOA adverse‑action reason codes taxonomy; transparency obligations).

---

## 3) Data Room (Aggregated — no row‑level data)
Use the CSV templates under `whitepaper_intake_templates/` or equivalent exports from your platform.

### 3.1 Schema & Provenance
- Data dictionary (field, type, unit, allowed range, protected attribute flags, proxy risk).
- Time & geography coverage, sampling frame, inclusion/exclusion rules.
- Label definition (e.g., performance horizon; charge‑off definition).

### 3.2 Dataset Summaries (per split: train/valid/test)
- Provide `dataset_summary.csv` with columns:
  `dataset_id, split, n, positive_rate, timeframe_start, timeframe_end, geography, notes`

### 3.3 Group/Slice Summaries
- Provide `group_summary.csv` with columns:
  `dataset_id, split, group, n, positive_rate, mean_score, fpr, fnr`
  *Notes*: `group` should include protected classes and intersectional slices if available.

### 3.4 Missingness by Feature
- Provide `feature_missingness.csv` with columns:
  `feature, split, frac_missing`

### 3.5 Shift Diagnostics (optional but valuable)
- Provide population/sample shift across time/banks (e.g., PSI/JSD) as a short table or figure.

**Command Templates (optional)**
```sql
-- dataset_summary.sql
SELECT
  '<dataset_id>' AS dataset_id,
  split,
  COUNT(*) AS n,
  AVG(CASE WHEN label = 1 THEN 1 ELSE 0 END) AS positive_rate,
  MIN(event_time) AS timeframe_start,
  MAX(event_time) AS timeframe_end,
  '<geography>' AS geography,
  '' AS notes
FROM your_table
GROUP BY split;

-- group_summary.sql (example with protected attribute A and score/yhat)
WITH base AS (
  SELECT split,
         CASE
           WHEN A IS NULL THEN 'A:missing'
           ELSE CONCAT('A:', CAST(A AS STRING))
         END AS group,
         label, score, yhat
  FROM your_scored_table
)
SELECT
  '<dataset_id>' AS dataset_id,
  split,
  group,
  COUNT(*) AS n,
  AVG(CASE WHEN label=1 THEN 1 ELSE 0 END) AS positive_rate,
  AVG(score) AS mean_score,
  SUM(CASE WHEN label=0 AND yhat=1 THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN label=0 THEN 1 ELSE 0 END),0) AS fpr,
  SUM(CASE WHEN label=1 AND yhat=0 THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN label=1 THEN 1 ELSE 0 END),0) AS fnr
FROM base
GROUP BY split, group;

-- feature_missingness.sql
SELECT
  '<feature>' AS feature,
  split,
  AVG(CASE WHEN <feature> IS NULL THEN 1 ELSE 0 END) AS frac_missing
FROM your_table
GROUP BY split;
```

---

## 4) Statistical Analysis Plan (SAP) & Estimands
You can fill `whitepaper_intake_templates/sap_template.md` or answer here.

1. **Primary endpoints** (formal definitions with estimands):
   - **AIR (Adverse Impact Ratio)**: \( \displaystyle \text{AIR} = \min_g \frac{\Pr(\hat{Y}=1 \mid A=g)}{\Pr(\hat{Y}=1 \mid A=g^\star)} \) with \(g^\star\) the highest‑selected group.
   - **EO gaps**: TPR/FPR gaps across groups.
   - **Calibration**: ECE / calibration‑within‑groups.
2. **Hypotheses**: state \(H_0\), \(H_1\), significance level \(\alpha\).
3. **Multiplicity control** (e.g., Benjamini–Hochberg at q=0.10 for many slices/metrics).
4. **Uncertainty quantification** per metric (bootstrap BCa vs. asymptotic; replicates; seed policy).
5. **Power & sample‑size** targets (detectable effect sizes on disparities at ≥ 80–90% power).
6. **Sensitivity/robustness**: permutation tests, placebo features, threshold perturbations, subgroup reweighting, influence functions/jackknife.

**Questions**
- Which metrics are *go/no‑go* vs *monitoring only*?
- What CI method and replicates do you prefer (e.g., 2,000 bootstrap resamples, BCa)?
- What delta thresholds define *material* disparity or performance changes?

---

## 5) Modeling & Algorithms (formal spec, not marketing)
Provide: model family, loss, constraints; architecture/hyperparams; privacy; fairness post‑processing; pseudocode.

**Questions**
1. **Objective**: formal loss and constraints (write the exact optimization problem).
2. **Architecture/Hyperparameters**: fill `model_hyperparams.yaml`. Include ranges and chosen values.
3. **Training protocol**: schedule, early stopping, regularization, RNG seeds.
4. **Baselines/Ablations**: which comparisons to include (e.g., CTGAN vs TVAE, with/without DP).
5. **Privacy guarantees** (ε, δ; accountant method); results of membership/attribute inference tests.
6. **Fairness interventions** (pre/in/post‑processing) with formal statements/lemmas if applicable.
7. **Pseudocode** for the full pipeline (calibrate → synthesize → model → assess), with per‑stage complexity \(O(\cdot)\).

---

## 6) Evaluation Design & Metrics
Provide: data splits, threshold policy, metrics, error budget, robustness checks, audit logs.

**Artifacts**
- `metrics_long.csv`: `run_id, split, model_id, metric, group, value, lower_ci, upper_ci, n`
- `runs.json`: list of run manifests (`run_id, dataset_hash, code_commit, container_digest, start_ts, end_ts`).

**Questions**
1. **Splits**: time‑based or k‑fold; bank‑holdout or cross‑bank generalization.
2. **Threshold selection**: global vs group‑wise; calibration method; Brier/ECE targets.
3. **Metric set**: AIR/DI, EO/EOpp, TPR/FPR gaps, calibration within groups, predictive parity, ROC‑AUC, PR‑AUC, KS, cost curves.
4. **Error budget**: how uncertainty propagates (synthesis → training → assessment).
5. **Robustness**: covariate shift tests, label noise, counterfactual stress, TSTR/TSRS.
6. **Audit logs**: per‑run seeds, hashes, container digests, git SHAs, hardware.

---

## 7) Compliance Evidence & Governance
Provide: regulator‑ready artifacts, SR 11‑7 bundle, monitoring plan, human oversight.

**Artifacts**
- Attach your “Quality Certificates”, example adverse‑action reason‑codes, validation notes.
- `governance_contacts.csv`: `role, name, org, email, responsibility`

**Questions**
- What are the monitoring control limits and retraining triggers?
- Who signs off (segregation of duties)?

---

## 8) Security, Privacy & Operations
Provide: architecture & data‑flow diagrams, SBOM & vuln management, performance/capacity, SLOs, DR/backup, monitoring.

**Questions**
- Network egress policy & key management?
- Patch cadence and vulnerability scan evidence?
- Failure modes and recovery times?

---

## 9) Reproducibility Bundle
Provide:
- `manifest.json` (dataset hash, RNG seeds, software versions, config).
- Container image digests, lockfiles, determinism notes (non‑deterministic kernels).
- A *worked synthetic example* reproducing ≥ 1 figure/table end‑to‑end.

**Questions**
- How should we parameterize seeds and tie them to signed manifests?
- Any determinism constraints from client infra (e.g., GPU kernels)?

---

## 10) Legal/IP & Licensing
Provide: third‑party components, licenses, marketplace terms, trademark usage, patents that constrain disclosure.

**Artifacts**
- `licenses_inventory.csv`: `component, version, license, use, notes`

---

## 11) Packaging & Contacts
- Preferred filename conventions, redaction rules.
- Contacts for each section (owner, reviewer).
- Delivery format expectations (PDF + appendices; JSON manifests).

---

### Appendix A — Metric Definitions (reference)
- **Adverse Impact Ratio (AIR)**: see §4.
- **Equalized Odds / Opportunity**: TPR/FPR gaps; EOpp uses TPR only.
- **Calibration**: ECE; calibration within groups.
- **Predictive Parity**: PPV parity across groups.

### Appendix B — Optional SQL/Notebook Stubs
See command templates in §3, and populate `metrics_long.csv` and `runs.json` from your evaluation pipeline.
