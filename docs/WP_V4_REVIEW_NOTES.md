# Whitepaper v4 — Review Notes, Audit, and TODOs

This document captures the current state of the v4 evidence bundle → PDF pipeline, the key results
in the latest clean rebuild, and the remaining work items to close before external review.

## Latest Clean Rebuild (Producer → Consumer)

Producer (FL‑BSA):
- Bundle: `/home/daimakaimura/fl-bsa/artifacts/WhitePaper_Reviewer_Pack_v4.zip`
- sha256: `2fb146e6ac3d3d9a715375cc12ab42a965dd1128d6a5e15bb0cb1d960acf6845`
- run_id: `485998b9-162d-4a31-b2b9-15507ce4733c`
- commit_sha (per `intake/manifest.json`): `bbac3d71b30b82daef5fca2b055029c3b93aa77d`

Consumer (Whitepaper):
- PDF: `/home/daimakaimura/fl-bsa-whitepaper/dist/whitepaper.pdf`
- sha256: `d30a346527469e655e5e764a07b741fc04498854d11509cc96aba48726581155`

## Bundle Contract (v4 SoT)

The v4 paper is driven by these artifacts (all present in the bundle):
- `intake/manifest.json` — provenance + deterministic group orientation (`fairness_reference_groups`, `fairness_protected_groups`)
- `intake/run_summary.json` — run metadata + headline outcomes, including inference config
- `intake/metrics_uncertainty.json` — deterministic fairness uncertainty SoT (`fairness_uncertainty.v1`)
- `intake/fairness_slices.json` — three-slice narrative guardrail (historical / amplification / intrinsic)

The consumer repo ingests:
- `bundle/intake/*.csv|*.json` → `intake/`
- `bundle/provenance/manifest.json` → `intake/manifest.json`
- `bundle/certificates/*.json` → `intake/certificates/`
- `bundle/config/*.yaml` → `config/`

## Key Fairness Results (Gender AIR by Slice)

From `intake/fairness_slices.json` (reference=`male`, protected=`female`, threshold=0.80):
- Historical AIR: `0.7706` (CI `0.7170–0.8282`) — baseline disparity
- Amplification AIR: `0.7700` (CI `0.7402–0.8011`) — bias preservation (fidelity)
- Intrinsic AIR: `1.0006` (CI `0.9752–1.0266`) — near-parity achievable

Bias preservation and improvement summaries:
- Amplification vs historical absolute AIR delta: `0.00055`
- Intrinsic uplift vs historical relative: `29.8%` (≈`0.2985`)

## Interpreting the Review Flags

### “Certificates unsigned”
Certificates in the bundle are signed; the signature material is stored in:
- `certificate_signature` (hex)
- `signature_algorithm` (e.g., `ECDSA-P256-SHA256`)
- `public_key_fingerprint`

If an external checker expects a field named `signature`, treat that as a checker/schema mismatch.
Do **not** add a top-level `signature` field without careful review: in FL‑BSA legacy handling,
`signature` has been used as a *hash* field in older chain logic.

### “Model certificates invalid” (`validation_results.valid=false`)
In this run, `model_certificate_*` report `validation_results.valid=false`. This reflects failed
validation sub-checks (commonly distribution-preservation strictness) and is intended as evidence:
it is **not** a cryptographic validity failure (the certificate is still signed).

If we require “valid=true” for the whitepaper narrative, we need a policy decision:
- either relax validation thresholds (risk: weakens guardrails), or
- keep `valid=false` and explicitly frame it as an advisory/quality limitation (recommended unless
policy changes are approved).

### `p_value_adjusted = null` (gender)
Gender is a single binary comparison, so multiplicity adjustment is not required. If downstream
consumers want a non-null field, the producer emits:
- `p_value_adjustment="none"`
- `p_value_adjusted = p_value`

### `race.display_in_main_pdf=false`
Race is gated for main-text display based on `config/fairness_config.yaml` display policy:
- current thresholds: `min_group_n=300`, `min_group_pct=0.05`
- observed in this run: `other` group `n=283` (~2.83%)

This is working as designed: race is computed and available, but not shown in the main tables when
small-group thresholds are not met.

## TODOs Before External Review

Paper / narrative:
- Ensure the Executive Summary always labels AIRs by slice (Historical / Amplification / Intrinsic).
- Keep wording aligned: this run demonstrates baseline disparity detection + bias-preserving fidelity + intrinsic improvement.

Evidence / schema:
- Decide whether external reviewers require `validation_results.valid=true` for model certificates; if so, specify which checks/thresholds can be relaxed (or generate a higher-quality scenario).
- Decide whether to lower race display thresholds (or adjust the scenario demographics) to surface race in the main PDF, or keep race in annex with a clear notice.

Automation:
- Keep the intake pull workflow pinned to schema versions (`wp-intake.v1`, `fairness_uncertainty.v1`) so producer changes fail loudly.
