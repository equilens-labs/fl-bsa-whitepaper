# Statistical Analysis Plan (SAP) — Template

## 1. Objectives & Endpoints
- **Primary endpoints**: (e.g., AIR ≥ 0.80; EO gaps ≤ 0.05; ECE ≤ 0.02)
- **Secondary endpoints**: (e.g., ROC‑AUC, PR‑AUC, KS, cost curves)

## 2. Estimands (formal definitions)
Let A denote the protected attribute, Y the true label, \(\hat{Y}\) a binary decision at threshold t, and S a score.
- **AIR**: \(\mathrm{AIR} = \min_g \frac{\Pr(\hat{Y}=1\mid A=g)}{\Pr(\hat{Y}=1\mid A=g^*)}\).
- **Equalized odds gaps**: \(\max_{g,g'} |\mathrm{TPR}_g - \mathrm{TPR}_{g'}|\), \(\max_{g,g'} |\mathrm{FPR}_g - \mathrm{FPR}_{g'}|\).
- **Calibration within groups**: reliability of S within bins, by A.
- **Predictive parity**: PPV parity across groups.

## 3. Hypotheses & Significance
- \(H_0\): [state null]
- \(H_1\): [state alternative]
- Significance level: \(\alpha = 0.05\) (or specify)

## 4. Multiplicity Control
- Procedure (e.g., Benjamini–Hochberg) and FDR/FWER target.

## 5. Uncertainty Quantification
- Interval type: BCa bootstrap / percentile / Wilson / asymptotic.
- Replicates: [e.g., 2000].
- Seed policy: [e.g., fixed per‑run; logged in `runs.json`].

## 6. Power & Sample Size
- Minimal detectable effects (MDE) for disparity metrics; power target (≥ 0.8/0.9).
- Method: analytic approximation or simulation; assumptions documented.

## 7. Sensitivity & Robustness
- Threshold perturbations, subgroup reweighting, permutation tests, placebo features, jackknife/influence functions.

## 8. Decision Rules
- Go/No‑Go thresholds for each endpoint; escalation/mitigation actions.

## 9. Reporting
- Table/figure list, CI presentation rules, rounding/precision, redaction policy.
