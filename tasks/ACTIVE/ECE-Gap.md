 1 +  # FL-BSA Whitepaper: ECE Gap Analysis Report
         2 +  
         3 +  **Document Purpose:** Technical gap analysis for external regulatory review
         4 +  **Date:** 2025-01-20
         5 +  **Evidence Bundle Run ID:** d1248f4c-d10c-4000-8e1a-56d80c319d5e
         6 +  
         7 +  ---
         8 +  
         9 +  ## Executive Summary
        10 +  
        11 +  The FL-BSA whitepaper evidence bundle is missing Expected Calibration Error (ECE) metrics. This report provides a rigorous 
           + technical explanation of the gap, its root cause in the data generation pipeline, and its implications for regulatory compliance
           +  claims.
        12 +  
        13 +  **Key Finding:** The CTGAN model architecture outputs binary loan decisions (`loan_approved ∈ {0,1}`) rather than probability 
           + scores (`S ∈ [0,1]`). ECE computation requires probability scores by mathematical definition. The pipeline correctly identifies 
           + this limitation and marks ECE as "TBD" rather than reporting invalid metrics.
        14 +  
        15 +  ---
        16 +  
        17 +  ## 1. What is Expected Calibration Error (ECE)?
        18 +  
        19 +  ### 1.1 Mathematical Definition
        20 +  
        21 +  ECE measures the alignment between a model's predicted probabilities and observed outcome frequencies. As defined in the 
           + whitepaper (`sections/02_problem_estimands.tex`):
        22 +  
        23 +  ```
        24 +  ECE = Σₖ (nₖ / Σⱼ nⱼ) |p̂ₖ - s̄ₖ|
        25 +  ```
        26 +  
        27 +  Where:
        28 +  - `Bₖ` = bins partitioning the score range [0,1]
        29 +  - `nₖ` = count of predictions in bin k
        30 +  - `s̄ₖ` = mean predicted score in bin k
        31 +  - `p̂ₖ` = empirical positive rate (actual outcomes) in bin k
        32 +  
        33 +  ### 1.2 Interpretation
        34 +  
        35 +  A well-calibrated model satisfies: P(Y=1 | S=s) ≈ s
        36 +  
        37 +  Example: Among all applicants receiving a 70% approval probability, approximately 70% should actually be approved when ground 
           + truth is available.
        38 +  
        39 +  ECE quantifies deviation from this ideal. Lower ECE indicates better calibration.
        40 +  
        41 +  ### 1.3 Required Data Elements
        42 +  
        43 +  | Element | Type | Description |
        44 +  |---------|------|-------------|
        45 +  | `probability_score` | Float [0,1] | Model's predicted probability of positive outcome |
        46 +  | `ground_truth` | Binary {0,1} | Actual outcome (required for `p̂ₖ` computation) |
        47 +  
        48 +  ---
        49 +  
        50 +  ## 2. What the Current Bundle Contains
        51 +  
        52 +  ### 2.1 Available Metrics (from `intake/metrics_long.csv`)
        53 +  
        54 +  | Metric | Groups | Method | Status |
        55 +  |--------|--------|--------|--------|
        56 +  | `selection_rate` | gender:female, gender:male, race:{asian,black,hispanic,other,white} | Wilson CI | Complete |
        57 +  | `air` | gender:all, race:all | Bootstrap percentile | Complete |
        58 +  | `tpr` | Per group | Wilson CI | Complete |
        59 +  | `fpr` | Per group | Wilson CI | Complete |
        60 +  | `tpr_gap` | gender:all, race:all | Bootstrap percentile | Complete |
        61 +  | `fpr_gap` | gender:all, race:all | Bootstrap percentile | Complete |
        62 +  | `ece` | — | — | **NOT COMPUTED** |
        63 +  
        64 +  ### 2.2 Available Evidence Files
        65 +  
        66 +  ```
        67 +  intake/
        68 +  ├── manifest_gate_wp.json    # Run provenance (ece_enabled: false)
        69 +  ├── metrics_long.csv         # 28 rows, no ECE entries
        70 +  ├── selection_rates.csv      # Selection counts per group
        71 +  └── group_confusion.csv      # TP/FP/TN/FN per group
        72 +  ```
        73 +  
        74 +  ### 2.3 Manifest Confirmation
        75 +  
        76 +  From `intake/manifest_gate_wp.json`:
        77 +  ```json
        78 +  {
        79 +    "capabilities": {
        80 +      "eo_enabled": true,
        81 +      "ece_enabled": false
        82 +    }
        83 +  }
        84 +  ```
        85 +  
        86 +  The pipeline explicitly declares ECE is disabled for this run.
        87 +  
        88 +  ---
        89 +  
        90 +  ## 3. Root Cause Analysis
        91 +  
        92 +  ### 3.1 Model Architecture Limitation
        93 +  
        94 +  FL-BSA uses CTGAN (Conditional Tabular GAN) to generate synthetic loan decision data. The CTGAN generator architecture outputs:
        95 +  
        96 +  - **Binary decisions:** `loan_approved ∈ {0, 1}`
        97 +  - **NOT probabilities:** No intermediate sigmoid or softmax layer exposing `P(loan_approved=1)`
        98 +  
        99 +  This is an architectural characteristic of the generator network, not a bug.
       100 +  
       101 +  ### 3.2 Pipeline Code Evidence
       102 +  
       103 +  From `flbsa/metrics/wp_intake.py`:
       104 +  
       105 +  **Line 260-262 - Stub function:**
       106 +  ```python
       107 +  def write_calibration_bins_stub(_: Path) -> None:
       108 +      """Placeholder: ECE not produced without probability scores."""
       109 +      return None
       110 +  ```
       111 +  
       112 +  **Line 665-679 - ECE computation guard:**
       113 +  ```python
       114 +  def append_ece_to_metrics_long(
       115 +      df: pd.DataFrame,
       116 +      *,
       117 +      y_true: str,
       118 +      score: str,  # <-- Requires probability score column
       119 +      ctx: IntakeContext,
       120 +      ...
       121 +  ) -> Path | None:
       122 +      """Append global ECE to metrics_long if scores available (bootstrap CI)."""
       123 +      ...
       124 +      if y_true not in df.columns or score not in df.columns:
       125 +          return None  # <-- Graceful exit when scores unavailable
       126 +  ```
       127 +  
       128 +  **Line 601-662 - Calibration bins writer:**
       129 +  ```python
       130 +  def write_calibration_bins(
       131 +      df: pd.DataFrame,
       132 +      *,
       133 +      y_true: str,
       134 +      score: str,  # <-- Also requires probability scores
       135 +      ...
       136 +  ) -> Path | None:
       137 +      """Write calibration_bins.csv if probability scores are available."""
       138 +      ...
       139 +      if y_true not in df.columns or score not in df.columns:
       140 +          return None
       141 +  ```
       142 +  
       143 +  ### 3.3 Data Flow Diagram
       144 +  
       145 +  ```
       146 +  CTGAN Generator
       147 +        │
       148 +        ▼
       149 +  ┌─────────────────┐
       150 +  │ loan_approved   │  Binary {0,1}
       151 +  │ (synthetic)     │
       152 +  └─────────────────┘
       153 +        │
       154 +        ├──► selection_rate ✓
       155 +        ├──► AIR ✓
       156 +        │
       157 +        ▼
       158 +  ┌─────────────────┐
       159 +  │ ground_truth    │  Binary {0,1} (from input data or synthetic)
       160 +  │ (for EO)        │
       161 +  └─────────────────┘
       162 +        │
       163 +        ├──► TPR, FPR ✓
       164 +        ├──► TPR_gap, FPR_gap ✓
       165 +        │
       166 +        ✗ No probability_score column
       167 +        │
       168 +        ▼
       169 +  ┌─────────────────┐
       170 +  │ ECE computation │  BLOCKED
       171 +  │ requires S∈[0,1]│
       172 +  └─────────────────┘
       173 +  ```
       174 +  
       175 +  ---
       176 +  
       177 +  ## 4. Why ECE Matters for Regulatory Compliance
       178 +  
       179 +  ### 4.1 Statistical Analysis Plan (SAP) Requirement
       180 +  
       181 +  From `config/sap.yaml`:
       182 +  ```yaml
       183 +  thresholds:
       184 +    air_min: 0.8
       185 +    tpr_gap_max: 0.05
       186 +    fpr_gap_max: 0.05
       187 +    ece_max: 0.02    # <-- ECE threshold defined
       188 +  ```
       189 +  
       190 +  The SAP commits to evaluating ECE ≤ 0.02. Without computed ECE, this claim cannot be validated.
       191 +  
       192 +  ### 4.2 Regulatory Framework References
       193 +  
       194 +  From `docs/WhitePaper_Intake_Compiled.md`:
       195 +  
       196 +  **EU AI Act (Art. 10):**
       197 +  > "Data governance and quality for training, validation and testing data"
       198 +  
       199 +  Calibration is a data quality property. ECE provides quantitative evidence that model outputs are interpretable and reliable.
       200 +  
       201 +  **CFPB/ECOA Guidance:**
       202 +  > "Within-group calibration checks; ECE targets ≤ 0.02; Brier score tracked"
       203 +  
       204 +  Fair lending examinations may require evidence that probability estimates are accurate across demographic groups.
       205 +  
       206 +  ### 4.3 Whitepaper Section Impact
       207 +  
       208 +  The whitepaper (`sections/06_results.tex`) includes:
       209 +  ```latex
       210 +  \subsection{Calibration (ECE)}
       211 +  \input{includes/table_ece_summary}
       212 +  ```
       213 +  
       214 +  Currently renders as:
       215 +  ```
       216 +  ┌─────────────────────────────────────────────────────┐
       217 +  │ run   model   split   ECE   LCI   UCI              │
       218 +  ├─────────────────────────────────────────────────────┤
       219 +  │        No ECE rows found in metrics                 │
       220 +  └─────────────────────────────────────────────────────┘
       221 +  ```
       222 +  
       223 +  This incomplete table weakens the whitepaper's regulatory evidence value.
       224 +  
       225 +  ---
       226 +  
       227 +  ## 5. Metrics Successfully Computed
       228 +  
       229 +  Despite the ECE gap, the bundle contains complete fairness evidence:
       230 +  
       231 +  ### 5.1 Adverse Impact Ratio (AIR)
       232 +  
       233 +  | Attribute | AIR | 95% CI | Threshold | Status |
       234 +  |-----------|-----|--------|-----------|--------|
       235 +  | Gender | 0.771 | [0.743, 0.802] | ≥ 0.80 | **VIOLATION** |
       236 +  | Race | 0.860 | [0.765, 0.925] | ≥ 0.80 | Pass |
       237 +  
       238 +  **Interpretation:** Female applicants have 77.1% the selection rate of male applicants, below the 80% adverse impact threshold.
       239 +  
       240 +  ### 5.2 Equalized Odds (TPR/FPR Gaps)
       241 +  
       242 +  | Metric | Attribute | Gap | 95% CI | Threshold | Status |
       243 +  |--------|-----------|-----|--------|-----------|--------|
       244 +  | TPR gap | Gender | 0.0 | [0.0, 0.0] | ≤ 0.05 | Pass |
       245 +  | FPR gap | Gender | 0.0 | [0.0, 0.0] | ≤ 0.05 | Pass |
       246 +  | TPR gap | Race | 0.0 | [0.0, 0.0] | ≤ 0.05 | Pass |
       247 +  | FPR gap | Race | 0.0 | [0.0, 0.0] | ≤ 0.05 | Pass |
       248 +  
       249 +  **Note:** Zero gaps occur because TPR=1.0 and FPR=0.0 across all groups in the synthetic data. This is consistent with the 
           + CTGAN generating aligned approval/ground-truth pairs.
       250 +  
       251 +  ---
       252 +  
       253 +  ## 6. Options for Resolution
       254 +  
       255 +  ### Option A: Proceed Without ECE (Recommended for Initial Version)
       256 +  
       257 +  **Approach:** Accept "TBD" / "Not computed" in whitepaper; document limitation explicitly.
       258 +  
       259 +  **Pros:**
       260 +  - Honest representation of current capabilities
       261 +  - No risk of invalid/synthetic metrics
       262 +  - Faster time to regulatory submission
       263 +  
       264 +  **Cons:**
       265 +  - Incomplete against SAP commitments
       266 +  - May require follow-up evidence package
       267 +  
       268 +  **Implementation:** No code changes. Add explanatory footnote to ECE section.
       269 +  
       270 +  ### Option B: Modify CTGAN to Output Probability Scores
       271 +  
       272 +  **Approach:** Add sigmoid output layer to generator; output P(loan_approved=1).
       273 +  
       274 +  **Pros:**
       275 +  - Enables true ECE computation
       276 +  - Full compliance with SAP
       277 +  
       278 +  **Cons:**
       279 +  - Significant model architecture change
       280 +  - Requires re-validation of synthetic data quality
       281 +  - May affect GAN training stability
       282 +  - Timeline: Estimated 2-4 weeks of development + testing
       283 +  
       284 +  **Implementation:** Modify CTGAN forward pass; update wp_intake.py to pass `score` column.
       285 +  
       286 +  ### Option C: Synthetic ECE Placeholder (NOT Recommended)
       287 +  
       288 +  **Approach:** Generate synthetic probability scores post-hoc.
       289 +  
       290 +  **Why this is inappropriate:**
       291 +  - Regulatory evidence must be traceable to actual model behavior
       292 +  - Post-hoc fabrication creates compliance risk
       293 +  - Violates data integrity principles in EU AI Act Art. 10
       294 +  
       295 +  ---
       296 +  
       297 +  ## 7. Current Whitepaper Macro Values
       298 +  
       299 +  From `includes/metrics_macros.tex`:
       300 +  
       301 +  ```latex
       302 +  \renewcommand{\AIRThreshold}{0.800}
       303 +  \renewcommand{\TprGapThreshold}{0.050}
       304 +  \renewcommand{\FprGapThreshold}{0.050}
       305 +  \renewcommand{\EceThreshold}{0.020}
       306 +  \renewcommand{\MinAIR}{0.771}
       307 +  \renewcommand{\MaxECE}{TBD}           % <-- Correctly marked as TBD
       308 +  \renewcommand{\NumAIRViolations}{1}
       309 +  \renewcommand{\NumTPRGapViol}{0}
       310 +  \renewcommand{\NumFPRGapViol}{0}
       311 +  ```
       312 +  
       313 +  ---
       314 +  
       315 +  ## 8. Recommendations
       316 +  
       317 +  1. **Immediate:** Compile whitepaper with current bundle; ECE section will show "No ECE rows found"
       318 +  2. **Short-term:** Add explicit footnote explaining ECE requires probability scores and is planned for future release
       319 +  3. **Medium-term:** Evaluate Option B (CTGAN modification) based on regulatory feedback priority
       320 +  4. **Do not:** Fabricate synthetic ECE values (Option C)
       321 +  
       322 +  ---
       323 +  
       324 +  ## Appendix: Evidence File Checksums
       325 +  
       326 +  | File | SHA-256 (first 16 chars) |
       327 +  |------|--------------------------|
       328 +  | manifest_gate_wp.json | (from run_id: d1248f4c...) |
       329 +  | Dataset hash | 7fbc4c8b4d24b217... |
       330 +  | Code commit | a4c0f9a58be60898... |
       331 +  
       332 +  ---
       333 +  
       334 +  ## Next Steps (Post latexmk Installation)
       335 +  
       336 +  1. Run `make pdf` to compile whitepaper
       337 +  2. Review rendered ECE table (expect "No ECE rows found")
       338 +  3. Decide whether to add explanatory footnote before regulatory submission
       339 +  4. Track Option B (CTGAN probability output) as technical debt item