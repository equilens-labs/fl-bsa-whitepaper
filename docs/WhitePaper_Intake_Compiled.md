# White Paper Intake — Completed Compilation (FL‑BSA)

Last updated: 2025‑10‑07

Status Notice — Pre‑Production
- This whitepaper intake and attached run evidence are produced from a pre‑production (gold‑gate) environment. Outputs may contain issues and are subject to change.
- Not for external distribution without final review and sign‑off. Results are provided for evaluation/validation only and do not constitute legal or regulatory advice.

This document consolidates all requested inputs from the White Paper Intake (RFI + templates) using authoritative sources in this repository. It is regulator‑ready and links to concrete evidence, code locations, and processes. Dataset‑dependent artifacts (aggregated CSVs) are specified with schemas and generation commands but require client data to populate.

---

## 0) Quick‑Start Checklist (Status)
- [x] Scope & Audience (Section 1)
- [x] Regulatory Mapping (Section 2)
- [ ] Aggregated data artifacts (Section 3) — requires client data
- [x] SAP filled (Section 4)
- [x] Modeling & Algorithms (Section 5)
- [x] Evaluation Design & Metrics (Section 6)
- [x] Compliance Evidence & Governance (Section 7)
- [x] Security/Privacy/Operations (Section 8)
- [x] Reproducibility bundle spec (Section 9)
- [x] Legal/IP & licensing inventory plan (Section 10)
- [x] Packaging & Contacts (Section 11)

References used: `docs/_INDEX.md`, `docs/_CURRENT_STATE.md`, `SSoT.md`, `docs/gold/*`, `flbsa/*` modules (metrics, certification, hyperparameters, synthetic, validation), Makefile gates.

---

## 1) Scope & Audience

1. Primary audience
   - Banking regulators and supervisors (ECOA/Reg B, EU AI Act reviewers)
   - Bank Model Risk Management (SR 11‑7), Compliance/Legal, Internal Audit
   - Data Science Leads, Risk Analytics, Executive sponsors

2. Decisions to support
   - Procurement and due diligence; model validation sign‑off; compliance attestations
   - Evidence packaging for supervisory examinations; ongoing monitoring approvals

3. Top claims to substantiate
   - Dual‑branch method quantifies historical bias vs achievable fairness with auditable evidence
   - Disparate Impact/AIR and EO gaps measured with validated statistics and CIs
   - Synthetic borrowers preserve key dependencies; QC thresholds enforced and certified
   - No‑Data‑Leaves: zero external egress; cryptographic chain of evidence and signed outputs
   - Performance SLAs: 10k < 15s; 100k < 2m; 1M < 15m; PDF < 30s

4. Context constraints
   - Deployment: customer VPC/on‑prem; optional air‑gapped
   - Network: deny‑by‑default egress; optional Prometheus `/metrics` for local monitoring
   - Telemetry: none by default; all monitoring local (customer‑managed)

5. Reader prerequisites
   - Math/stats: probability, CIs, bootstrap; fairness metrics (AIR/DI, EO)
   - Regulatory: ECOA/Reg B basics, EU AI Act Art. 10, SR 11‑7 concepts

6. Document tone
   - Proof‑oriented and empirical audit; executive summary with technical appendices

---

## 2) Regulatory & Policy Mapping

Applicable frameworks (deployment‑dependent):
- US: ECOA/Reg B, CFPB fair‑lending guidance; EEOC four‑fifths (for AIR/DI reference)
- UK: FCA Consumer Duty; PRA/FCA model governance
- EU: EU AI Act (Art. 10 data/records, bias testing), EBA ICT/Security
- Global: SR 11‑7 (model risk), NIST AI RMF, ISO/IEC 23894

Controls and evidence (how we comply):
- Bias testing: dual‑branch analysis; metrics and CIs; signed reports and manifests
- Documentation: regulator templates (ECOA/EU/FCA) via LaTeX → PDF; evidence bundling
- Governance: segregation of duties for sign‑off; monitoring triggers and thresholds
- Privacy/Security: no external egress; SBOM; signed images; vuln scanning; key management

Evidence references
- Certificates and hashing: docs/crypto/CERT_HASHING.md, `flbsa/certification/*`
- Metrics/math: docs/gold/mathematical-framework/BIAS-METRICS-AND-STATISTICS.md; `flbsa/metrics/*`
- Gates: Makefile targets `gate-e-certificates`, `gate-f-determinism`, `gate-h-perf`

Questions (filled)
1) Frameworks for this deployment: ECOA/Reg B, CFPB, FCA Consumer Duty, EU AI Act, SR 11‑7, NIST AI RMF, ISO/IEC 23894 (confirm with client regulator/jurisdiction)
2) Client fairness policy thresholds (defaults; confirm client policy):
   - AIR/DI ≥ 0.80; SPD ≤ 0.10; EO (TPR/FPR) gaps ≤ 0.05; within‑group calibration ECE ≤ 0.02
3) Explainability expectations: ECOA adverse‑action reason‑codes CSV supported; transparency appendix in PDF

Note: A full `regulatory_matrix.csv` (citation → control → evidence → owner → status → notes) can be produced from this mapping; owners set per deployment.

---

## 3) Data Room (Aggregated — no row‑level data)

Provide aggregated exports (client‑generated) with schemas below. No PII/row‑level data is required.

### 3.1 Schema & Provenance
- Data dictionary: field, type, units, allowed range, protected flags, proxy risk
- Time & geography coverage; inclusion/exclusion rules; sampling frame
- Label definition: e.g., `loan_approved` (performance horizon/charge‑off definition if applicable)

### 3.2 Dataset Summaries (per split)
CSV schema: `dataset_summary.csv`
`dataset_id, split, n, positive_rate, timeframe_start, timeframe_end, geography, notes`

### 3.3 Group/Slice Summaries
CSV schema: `group_summary.csv`
`dataset_id, split, group, n, positive_rate, mean_score, fpr, fnr`
Include protected classes and intersectional slices.

### 3.4 Missingness by Feature
CSV schema: `feature_missingness.csv`
`feature, split, frac_missing`

### 3.5 Shift Diagnostics (optional)
Population/sample shift across time/banks (e.g., PSI/Jensen–Shannon) with brief table/figure.

Command stubs: see `tasks/FUTURE/Whitepaper/WhitePaper_RFI.md` §3 templates (SQL provided).

Status: Pending client data. Repo includes complete methodology and validation, but not bank data.

---

## 4) Statistical Analysis Plan (SAP) & Estimands

Primary endpoints (formal; confirm thresholds per policy)
- AIR (Adverse Impact Ratio): min group approval ratio vs best group; target ≥ 0.80
- Equalized Odds gaps: max |TPR_g−TPR_{g′}| and |FPR_g−FPR_{g′}| ≤ 0.05
- Calibration (ECE): overall and within groups ≤ 0.02 at chosen binning

Estimands (notation A protected, Y label, Ŷ decision at threshold t, S score)
- AIR: argmin_g Pr(Ŷ=1|A=g) / Pr(Ŷ=1|A=g⋆)
- EO gaps: max_{g,g′} |TPR_g−TPR_{g′}|, max_{g,g′} |FPR_g−FPR_{g′}|
- Calibration within groups: reliability of S within bins by A
- Predictive parity: PPV parity across groups

Hypotheses and α
- H0: Metrics meet policy thresholds (e.g., AIR ≥ 0.80; EO gaps ≤ 0.05)
- H1: At least one endpoint violates the policy threshold
- Significance: α = 0.05 (two‑sided for differences; one‑sided where appropriate)

Multiplicity control
- Benjamini–Hochberg (FDR q=0.10) across multiple slices/metrics; family definition documented per run

Uncertainty quantification
- Bootstrap CIs (BCa) with ≥2,000 resamples; see `flbsa/metrics/statistical_significance.py`
- Seeds recorded per run; determinism gate validates stability; Wilson intervals for proportions where applicable

Power & sample‑size
- Target ≥80–90% power for detecting material disparities
- Two‑proportion tests for EO/SPD deltas; sample size via analytic approximation (`calculate_sample_size`) and/or simulation
- Minimum per‑group n=30 for validity (code constant `MIN_GROUP_SIZE`)

Sensitivity/robustness
- Threshold perturbations; subgroup reweighting; permutation/placebo; jackknife/influence functions; TS(TR/RS) for generators

Decision rules
- Go: all primary endpoints meet thresholds with 95% CIs consistent
- No‑Go: primary endpoint failure; mitigation required (threshold policy, feature review, reweighting) and re‑test

Sources: `docs/gold/mathematical-framework/BIAS-METRICS-AND-STATISTICS.md`, `flbsa/metrics/*`.

---

## 5) Modeling & Algorithms (formal spec)

Objective (CTGAN; conditional GAN with PAC)
Minimax objective with conditional inputs and PacGAN discriminator packing:
min_G max_D E_x[log D(x|c)] + E_z[log(1 − D(G(z|c)))] + λ·GP (gradient penalty as configured by library). Packing (PAC) > 1 improves mode collapse resistance; batch/PAC normalized per `.ai/critical_paths/PAC_NORMALIZATION.md` and `flbsa/utils/ctgan_wrapper.py`.

Architecture & hyperparameters (ranges; branch‑specific defaults)
- Model family: CTGAN (`ctgan` package) wrapped by `CTGANWithHistory`
- Amplification branch (bias‑preserving):
  - `generator_dim`: (128,128) or (256,256); `embedding_dim`: 64–256
  - `epochs`: 50–200; `batch_size`: 256–1024 (normalized to dataset)
  - `pac`: 5–10 (auto‑reduced if dataset small)
  - LRs: 1e‑4–1e‑3; steps: 1; decay 1e‑6–1e‑5
- Intrinsic branch (fair baseline):
  - `generator_dim`: (64,64) or (64,128,64); `embedding_dim`: 32–128
  - `epochs`: 100–300 (smaller networks, more epochs)
  - Other ranges as above; conservative learning rates
- See tuner: `flbsa/hyperparameters/tuner.py` (Optuna TPE; branch‑aware search)

Training protocol
- Per‑branch hyperparameter optimization → train with `CTGANWithHistory`
- Batch/PAC normalization: always use effective PAC after normalization
- Determinism: seeded (`FLBSA_TUNING_SEED`); training history captured each epoch
- Validation: `ModelValidator` + BVH contracts; corruption and PAC fallbacks handled

Baselines/ablations
- CTGAN branch comparison; ablate PAC, embedding, dims, epochs; with/without fairness post‑processing; optional DP mode (future)

Privacy
- No external egress; signed artifacts; privacy AUC improvements observed (<0.89 in P2.5 remediation); membership/attribute inference tests to be executed per‑client if required

Fairness interventions
- Amplification: strict bias preservation sampler (`bias_preserving_sampler_v2`)
- Intrinsic: per‑group fair labeling to minimize group disparities; threshold policy documented

Pseudocode (end‑to‑end)
1) Profile data → detect categorical → tune (branch A,B)
2) Train CTGAN(A,B) with normalized batch/PAC
3) Generate synthetic A (bias‑preserved) and B (fair)
4) Label/correct outcomes (branch policies)
5) Validate QC + compute metrics + bootstrap CIs
6) Produce PDF + signed certificates + manifests

Complexity: tuning O(T·C·fit), generation O(N), metrics O(N) per run; parallelizable across branches and resamples

Key sources: `flbsa/utils/ctgan_wrapper.py`, `flbsa/hyperparameters/tuner.py`, `flbsa/synthetic/*`, `docs/gold/p2-bulletproof-ctgan/IMPLEMENTATION-SUMMARY.md`.

---

## 6) Evaluation Design & Metrics

Splits
- Time‑based or k‑fold; bank‑holdout or cross‑bank generalization as applicable

Threshold selection & calibration
- Global threshold with within‑group calibration checks; ECE targets ≤ 0.02; Brier score tracked

Metric set
- AIR/DI, SPD, EO/EOpp (TPR/FPR parity), calibration within groups, predictive parity, ROC‑AUC, PR‑AUC, KS, cost curves

Error budget & uncertainty
- Bootstrap propagation (synthesis → training → assessment); CI coverage validated; report CI alongside point estimates

Robustness
- Covariate shift tests (PSI/JSD), label noise sensitivity, counterfactual stress, TSTR/TSRS

Audit logs (per run)
- `run_id, dataset_hash, code_commit, container_digest, start_ts, end_ts, rng_seeds, hardware`
- See templates: `whitepaper_intake_templates/runs.json`, `repro_manifest_example.json`

Artifacts
- `metrics_long.csv`: `run_id, split, model_id, metric, group, value, lower_ci, upper_ci, n`
- `runs.json`: per‑run manifests; determinism validated by `gate-f-determinism`

---

## 7) Compliance Evidence & Governance

Artifacts
- Quality Certificates (bias detection, synthetic quality, convergence, stability) under `flbsa/certification/*` with canonical hashes
- Example adverse‑action reason‑codes CSV (when applicable)
- Evidence bundle endpoint (manifest + PDF + SBOM); optional at‑rest encryption; see docs/gold/p3 implementation summary

Monitoring plan & triggers
- Control limits: AIR ≥ 0.80; EO gaps ≤ 0.05; ECE ≤ 0.02; drift/shift thresholds (PSI/JSD) as agreed
- Triggers: any primary endpoint breach; significant drift; performance SLO breach

Sign‑off (segregation of duties)
- Owners: Model Risk lead (validation), Compliance officer (policy), Data Science lead (implementation); reviewers recorded in manifest

---

## 8) Security, Privacy & Operations

Network & egress policy
- Deny‑by‑default egress; allow loopback/bridge as needed; DOCKER‑USER egress firewall supported; no external calls in library code (gate: `make validate-no-external`)

Key management
- Customer KMS/Secrets Manager; KMS rotation guide provided; keys referenced in evidence manifests

SBOM & vulnerability management
- Containers signed (Cosign); SBOM in CI; daily CVE scanning with break‑the‑build gating; NOTICE maintained
- Wheel SBOM/provenance planned per `tasks/FUTURE/ProductionPlan.md`

Performance & capacity (SLOs)
- 10k < 15s; 100k < 2m; 1M < 15m; PDF < 30s; validated benchmarks in `SSoT.md`

DR/backup & recovery
- Evidence bundle zip (manifest + PDF + SBOM); optional encryption; stateless runtime; RPO/RTO set per customer ops; health checks `/health/*`

Monitoring
- Prometheus `/metrics`; optional Grafana dashboard JSON; structured logs with correlation IDs

Failure modes & recovery
- CTGAN training failure (PAC/batch mismatch) → auto‑normalize & retry; GPU unavailability → CPU fallback; degraded mode documented

References: `docs/architecture/system-overview.md`, `docs/SECURITY-CHECKLIST.md`, `docs/gold/p3-implementation-summary.md`, `SSoT.md`.

---

## 9) Reproducibility Bundle

Provide `manifest.json` per run including:
- Dataset hash (SHA‑256), RNG seeds, software versions, container digests, config snapshot
- Start/end timestamps; hardware details; determinism notes (non‑deterministic kernels flagged)
- All certificate hashes in a chain (previous_certificate_hash)

Seeding & signing
- Seeds parameterized (`FLBSA_TUNING_SEED`, training seeds); recorded in `runs.json` and manifest; artifacts signed

Determinism constraints
- GPU kernels may introduce nondeterminism; CI determinism gate; CPU fallback available

Templates: `whitepaper_intake_templates/runs.json`, `repro_manifest_example.json`

---

## 10) Legal/IP & Licensing

Project license
- MIT (see `LICENSE`); NOTICE maintained for Apache‑2.0 components

Third‑party inventory
- Generate offline attributions from `poetry.lock`: `make lexpro-licenses` → `artifacts/licenses/*`
- Produce `licenses_inventory.csv` with: `component, version, license, use, notes`
- Typical core components (subject to `poetry.lock`): ctgan, aif360, fairlearn, numpy, pandas, optuna, pydantic, fastapi, celery, redis‑py, cryptography

Marketplace & IP
- AWS Marketplace terms; containers signed; SBOM and provenance retained; patents: none blocking disclosure (confirm legal review)

---

## 11) Packaging & Contacts

Packaging & redaction
- Deliverable: PDF (executive + technical + regulatory appendices) + JSON manifests; evidence zip; redact any client identifiers
- Filename convention: `FLBSA_Whitepaper_<Client>_<YYYYMMDD>_vX.Y.pdf` with aligned manifest names

Contacts (owner/reviewer)
- Model Risk Lead — Owner (validation)
- Compliance Officer — Owner (policy mapping)
- DS Lead — Owner (implementation; metrics)
- Security Lead — Reviewer (SBOM, vuln, egress)
- Legal — Reviewer (licensing/IP)

---

## Claims to Substantiate (Summary)
- Dual‑branch method quantifies bias amplification vs intrinsic fairness; evidence tables and figures included
- AIR ≥ 0.80 for balanced and evidence_tamper scenarios; gender_bias fails by design; security shows race AIR ≈ 0.78 (fails 0.80 rule) and is flagged for remediation (policy‑dependent)
- Distribution/QC fidelity: range, correlation, and privacy checks; contracts enforced via BVH
- No‑Data‑Leaves Promise: zero external egress; cryptographic certificate chain; signed outputs
- Performance SLAs met at 10k/100k/1M; generator reuse for monitoring runs

---

## Privacy & Security Audit Checklist (Filled)
- [x] Data egress policy documented — deny‑by‑default; validate via `make validate-no-external`; DOCKER‑USER firewall
- [x] Key management documented — customer KMS/Secrets Manager; rotation guide; key IDs in manifests
- [x] SBOM available for containers — generated in CI; signed images (Cosign)
- [x] Vulnerability scans — daily CVE scanning; break‑the‑build gates; Trivy/GitHub security
- [x] Patching policy & cadence — weekly patching; dependency review; gated in CI
- [~] Membership inference test results — privacy AUC improvements observed; formal MI/AI test battery per‑client on request
- [~] Attribute inference test results — available as part of privacy test battery (optional)
- [~] Differential privacy accounting — optional DP mode (roadmap); default non‑DP
- [x] DR/backup & recovery objectives — evidence bundle; stateless services; RPO/RTO per client ops
- [x] Monitoring & SLOs — Prometheus metrics; SLOs documented and tracked

Legend: [x]=Yes, [~]=Partial/Optional, [ ]=No

---

## Appendix — Pointers to Source of Truth
- Docs index: `docs/_INDEX.md`
- Current state: `docs/_CURRENT_STATE.md`
- SSOT: `SSoT.md`
- Math & metrics: `docs/gold/mathematical-framework/BIAS-METRICS-AND-STATISTICS.md`, `flbsa/metrics/*`
- Dual‑branch CTGAN: `docs/gold/p2-bulletproof-ctgan/IMPLEMENTATION-SUMMARY.md`, `flbsa/synthetic/*`, `flbsa/hyperparameters/tuner.py`
- Certificates & hashing: `docs/crypto/CERT_HASHING.md`, `flbsa/certification/*`
- Security checklist: `docs/SECURITY-CHECKLIST.md`, `docs/architecture/system-overview.md`
- Gates & baselines: Makefile (`gate-*`), `ci/baselines/*`

---

## Evidence Map — Docs & Source Code (Rigorous)

This section ties each claim/control to exact documentation and implementation points (source modules, key functions/classes) plus representative tests.

- Bias metrics (AIR/DI, SPD, EO)
  - Docs: `docs/gold/mathematical-framework/BIAS-METRICS-AND-STATISTICS.md`
  - Code: `flbsa/metrics/mathematical_definitions.py` (e.g., `adverse_impact_ratio`, `statistical_parity_difference`, `equal_opportunity_difference`)
  - Stats engine: `flbsa/metrics/statistical_significance.py` (two‑proportion z‑test, bootstrap BCa, power)
  - Tests: `tests/test_statistical_significance.py`, `tests/test_mathematical_definitions.py`, `tests/test_mathematical_consolidated.py`

- Dual‑branch CTGAN training and generation
  - Docs: `docs/gold/p2-bulletproof-ctgan/IMPLEMENTATION-SUMMARY.md`, `docs/user-guide/bias-metrics.md`
  - Code: `flbsa/synthetic/dual_branch_generator.py` (class `DualBranchCTGANGenerator`);
    `flbsa/utils/ctgan_wrapper.py` (`CTGANWithHistory`, `normalize_batch_size_for_data`)
  - Tuning: `flbsa/hyperparameters/tuner.py` (Optuna TPE, branch‑aware ranges, PAC retry)
  - Tests: `tests/test_ctgan_bias_correction.py`, `tests/test_bias_preserving_sampler.py`, `tests/test_ground_truth_generator.py`

- PAC normalization and small‑dataset safety
  - Docs: `.ai/critical_paths/PAC_NORMALIZATION.md`
  - Code: `flbsa/utils/ctgan_wrapper.py` (`normalize_batch_size_for_data`, `normalize_batch_size`)
  - Usage: enforced in `flbsa/hyperparameters/tuner.py` and `flbsa/synthetic/dual_branch_generator.py`

- Bias preservation (amplification branch) and fair labeling (intrinsic)
  - Docs: `docs/gold/dual-branch-ctgan/AMPLIFICATION-VS-INTRINSIC.md`
  - Code: `flbsa/synthetic/bias_preserving_sampler_v2.py` (strict preservation); `flbsa/bvh/contracts.py` (`calculate_bias_metrics`); `flbsa/analysis/dual_branch_compare.py`
  - Tests: `tests/test_bias_preserving_sampler.py`, `tests/test_eu_ai_act_metrics.py`

- BVH contracts (P2) and quality remediation (P2.5)
  - Docs: `docs/gold/p2-bulletproof-ctgan/IMPLEMENTATION-SUMMARY.md`, `docs/gold/p2.5-bvh-quality-remediation/IMPLEMENTATION-SUMMARY.md`
  - Code: `flbsa/bvh/contracts.py`; `flbsa/synthetic/postprocess.py`; `flbsa/synthetic/transformers.py`; `flbsa/synthetic/fe_joint.py`
  - Tests: see P2.5 summary test lists; `tests/bvh/*`, `tests/synthetic/*`

- Certificates, hashing, chain validation
  - Docs: `docs/crypto/CERT_HASHING.md`
  - Code: `flbsa/certification/io.py` (`canonical_payload`, `compute_certificate_hash`, `canonicalize_obj`, `write_certificate_json`, `validate_certificate_chain`)
  - Orchestration: `flbsa/orchestrator/tasks/synthetic_validation.py` (writes `SyntheticValidationCertificate`)
  - Tests: `tests/test_certificate_canonical_hashing.py`, `tests/test_certificate_organization.py`, `tools/ci/validate_certificates.py`

- Security and privacy (no egress, logging, exceptions)
  - Docs: `docs/SECURITY-CHECKLIST.md`, `docs/architecture/system-overview.md`
  - Gates: `make validate-no-external` (no `requests|urllib|httpx|aiohttp` in lib code), `make validate-errpipe-lib`, `make validate-exceptions`
  - Enforcement: Makefile target `validate-no-external` greps lib code; tests enforce privacy and exception policies

- Performance SLAs and monitoring
  - Docs: `SSoT.md` performance benchmarks; `docs/_CURRENT_STATE.md` gates and perf baselines; `docs/grafana/flbsa-dashboard.json`
  - Code: metrics collection under `flbsa/monitoring/*`; Prometheus endpoint via API layer; perf tests in `tests/performance/`

- Schema constants and protected attributes
  - Code: `flbsa/schema/constants.py` (e.g., `TARGET_COLUMN`, `PROTECTED_ATTRIBUTES`), validator in `flbsa/schema/data_validation.py`
  - Tests: `tests/test_schema_compliance_audit.py`, `tests/test_p1_functional_validation.py`

- Reproducibility and determinism
  - Docs: `docs/gold/code-freeze-infrastructure/`, `docs/_CURRENT_STATE.md` (gates E/F)
  - Gates: `make gate-f-determinism`; evidence bundling in `docs/gold/p3-implementation-summary.md`
- Code: seeded tuning (`FLBSA_TUNING_SEED`), seeds recorded in manifests/templates under `whitepaper_intake_templates/`

---

## Run Evidence — Gold Gate 20251007T101329Z

Summary
- Scenarios (status; DI/AOD/EOD):
  - balanced: PASS; DI 0.9929; AOD 0.0040; EOD 0.0040
  - gender_bias: FAIL; DI 0.6908; AOD 0.1724; EOD 0.1724
  - outliers: PASS; DI 1.0028; AOD −0.0015; EOD −0.0015
  - security: PASS; DI 1.0089; AOD −0.0050; EOD −0.0050
  - evidence_tamper: PASS; DI 1.0088; AOD −0.0050; EOD −0.0050
- Source: `/data/projects/fl-bsa/artifacts/gold/20251007T101329Z/summary.json`

Key artifacts (gender_bias example)
- Report PDF: `/data/projects/fl-bsa/artifacts/gold/20251007T101329Z/02_gender_bias/report.pdf`
- Metrics (API shape): `/data/projects/fl-bsa/artifacts/gold/20251007T101329Z/02_gender_bias/metrics_api.json`
- Certificates (chain valid): hyperparameter tuning (both), model (both), generation process, synthetic validation, synthetic quality, training convergence
  - Example: `/data/projects/fl-bsa/artifacts/gold/20251007T101329Z/02_gender_bias/synthetic_validation_certificate.json`
- Evidence bundle (encrypted/plain): `/data/projects/fl-bsa/artifacts/gold/20251007T101329Z/02_gender_bias/downloads/evidence.zip(.enc)`

Section 3 Aggregated CSVs (generated from this run)
- Dataset summaries: `tasks/FUTURE/Whitepaper/dataset_summary_20251007T101329Z.csv`
  - Columns: dataset_id, split, n, positive_rate, timeframe_start, timeframe_end, geography, notes
  - n uses synthetic_rows from metrics_api.json; notes capture DI and PASS/FAIL per scenario
- Group summaries: `tasks/FUTURE/Whitepaper/group_summary_20251007T101329Z.csv`
  - Groups: gender:{male,female}, race:{white,black,hispanic,asian,other}; positive_rate from selection rates; fpr/fnr left blank (no labels available). n is intentionally left blank to avoid mixing input coverage counts with synthetic population counts.
- Feature missingness: `tasks/FUTURE/Whitepaper/feature_missingness_20251007T101329Z.csv`
  - Computed directly from each scenario’s `dataset.csv`; split column encodes scenario name; this is row‑level‑free (only aggregate missingness fractions)

Chain and signing evidence
- Certificate algorithm: ECDSA‑P256‑SHA256; canonical hashing verified; chain PASS in summary report
- Implementation: `flbsa/certification/io.py` (canonical_payload, compute_certificate_hash, write_certificate_json)

Notes
- Positive rates per scenario come from `fairlearn_metrics.overall_selection_rate` (or computed from dataset when needed)
- Group counts from `dataset_quality.coverage` in metrics_api.json
 - Security scenario race AIR computed from per‑group selection rates (asian vs best group) ≈ 0.78 (< 0.80) — claim updated accordingly

Artifacts Provided (Reviewer Pack)
- `tasks/FUTURE/Whitepaper/metrics_long.csv` — per-metric values with 95% CIs and n by run/split/group (selection rates; SPD/DI for gender)
- `tasks/FUTURE/Whitepaper/runs.json` — run manifests with dataset hash, code commit, timestamps, software version
- `tasks/FUTURE/Whitepaper/manifest.json` — reproducibility bundle index (per-run)
- `tasks/FUTURE/Whitepaper/model_hyperparams.yaml` — chosen hyperparameters per branch + search ranges
- `tasks/FUTURE/Whitepaper/SAP.md` — filled from template with thresholds, CI method (BCa/Wilson), replicates (2,000)
- `tasks/FUTURE/Whitepaper/governance_contacts.csv` — roles for MRM, Compliance, Security, Legal (placeholders)
- `tasks/FUTURE/Whitepaper/privacy_audit_checklist.md` — filled checklist with SBOM/CVE references
- `tasks/FUTURE/Whitepaper/licenses_inventory.csv` — third‑party components (from poetry.lock)
- `tasks/FUTURE/Whitepaper/regulatory_matrix.csv` — framework→requirement→control→evidence mapping with owners/status
- `tasks/FUTURE/Whitepaper/claims_to_substantiate.md` — final claims list
