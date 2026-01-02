# FL-BSA Evidence Pipeline — Data Flow Specification

This document describes how evidence artifacts flow from the FL-BSA runtime (`fl-bsa`) to this whitepaper publication repository.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  fl-bsa (Producer)                                          │
│                                                             │
│  make gate-wp                                               │
│    ├─ Starts services (API, Worker, Redis)                  │
│    ├─ Generates seeded synthetic dataset                    │
│    ├─ Runs full bias analysis pipeline                      │
│    ├─ Computes fairness metrics (AIR, EO, ECE)              │
│    ├─ Captures provenance (hashes, digests, seeds)          │
│    ├─ Validates intake artifacts                            │
│    └─ Packages: WhitePaper_Reviewer_Pack_v4.zip             │
│                                                             │
│  Key tools:                                                 │
│    - tools/wp/run_wp_evidence.py (orchestrator)             │
│    - tools/ci/validate_wp_intake.py (validation; schema contract) │
│    - flbsa/metrics/wp_intake.py (metrics computation)       │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ WhitePaper_Reviewer_Pack_v4.zip
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  fl-bsa-whitepaper (Consumer / This Repo)                   │
│                                                             │
│  intake/                                                    │
│    ├─ metrics_uncertainty.json (v4 SoT)                     │
│    ├─ metrics_long.csv (legacy/annex)                       │
│    ├─ selection_rates.csv                                   │
│    ├─ manifest.json                                         │
│    ├─ certificates/*.json                                   │
│    └─ (other supporting CSVs)                               │
│                                                             │
│  make pdf                                                   │
│    ├─ Generates TeX macros from metrics                     │
│    └─ Compiles LaTeX → dist/whitepaper.pdf                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Producer: fl-bsa

### Gate-WP Process

The `make gate-wp` target orchestrates deterministic evidence generation:

1. **Service Startup**: Starts API, Worker, and Redis containers with fixed port offsets
2. **Dataset Generation**: Calls `/gen-synth-data` API with seeded parameters
3. **Pipeline Submission**: POSTs dataset to `/api/v1/pipeline`
4. **Completion Polling**: Monitors pipeline status until complete
5. **Artifact Harvesting**: Collects intake CSVs from `output/<pipeline_id>/intake/`
6. **Validation**: Runs strict schema and bounds checking
7. **Provenance Repair**: Fills in real dataset hashes and container digests
8. **Bundling**: Packages everything into `WhitePaper_Reviewer_Pack_v4.zip`

### Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `WP_SEED` | 42 | RNG seed for reproducibility |
| `WP_N_SAMPLES` | 3000 | Synthetic dataset size |
| `WP_TIMEOUT` | 1800 | Pipeline timeout (seconds) |
| `WP_ENABLE_EO` | 1 | Enable Equalized Odds metrics |
| `WP_SAP` | config/sap.yaml | Statistical Analysis Plan |

### Output Artifacts

```
output/<pipeline_id>/
├── intake/
│   ├── selection_rates.csv      # Per-group selection rates
│   ├── metrics_long.csv         # All fairness metrics with CIs
│   ├── group_confusion.csv      # Confusion matrices (EO)
│   ├── calibration_bins.csv     # Calibration analysis (when score/probabilities available)
│   └── regulatory_matrix.csv    # Compliance mapping
│   ├── air_status.json          # WP summary JSON (per-attribute AIR status)
│   ├── eo_status.json           # WP summary JSON (per-attribute EO status)
│   ├── ece_status.json          # WP summary JSON (ECE status; may be not evaluated)
│   └── run_summary.json         # WP summary JSON (unified compliance payload)
├── validation/
│   └── metrics_uncertainty.json # v4 deterministic SoT (fairness uncertainty surface)
├── provenance/
│   └── manifest.json            # Full provenance
└── (other pipeline outputs)
```

---

## Metrics Computation

### Fairness Metrics (in fl-bsa)

| Metric | Description | CI Method |
|--------|-------------|-----------|
| `selection_rate` | Per-group approval rate | Wilson 95% |
| `air` (v4 SoT) | Disparity ratio (AIR-equivalent) | Delta-method CI on log(AIR) (`wilson+delta`) |
| `tpr`, `fpr` | Per-group true/false positive rates | Wilson 95% |
| `tpr_gap`, `fpr_gap` | Max gaps in TPR/FPR | Bootstrap (BCa or percentile) |
| `ece` | Expected Calibration Error | Bootstrap (BCa or percentile; only when score/probabilities exist) |

### SAP Thresholds

Defined in `config/sap.yaml`:
- AIR ≥ 0.80 (four-fifths rule)
- TPR gap ≤ 0.05
- FPR gap ≤ 0.05
- ECE ≤ 0.02

### Bootstrap Configuration
- Bootstrap replicates, alpha, and method are pinned by `config/sap.yaml` and recorded in `provenance/manifest.json` under `inference{...}`.
- Gate-WP can run `bootstrap_bca` or `bootstrap_percentile` depending on configuration.

---

## Consumer: fl-bsa-whitepaper

### Import Process

```bash
# 1. Get bundle from producer
# (either download from CI or copy from local run)

# 2. Extract to intake/
unzip WhitePaper_Reviewer_Pack_v4.zip -d /tmp/bundle
cp /tmp/bundle/intake/*.csv intake/
cp /tmp/bundle/intake/*.json intake/
cp /tmp/bundle/provenance/manifest.json intake/manifest.json
mkdir -p intake/certificates && cp /tmp/bundle/certificates/*.json intake/certificates/
cp /tmp/bundle/config/sap.yaml config/sap.yaml
cp /tmp/bundle/config/fairness_config.yaml config/fairness_config.yaml

# 3. Generate TeX macros
make macros

# 4. Build PDF
make pdf
```

### Macro Generation

`scripts/gen_tex_macros_from_metrics.py` reads:
- `intake/metrics_uncertainty.json` (preferred SoT for v4)
- `intake/metrics_long.csv` (legacy fallback for ECE tables / back-compat)
- `config/sap.yaml`

And generates:
- `includes/metrics_macros.tex` — threshold values, summary statistics
- `includes/table_air_summary.tex` — AIR table
- `includes/table_srg_summary.tex` — approval-rate gap (SRG) table
- `includes/table_ece_summary.tex` — ECE table

---

## CSV Schemas

### metrics_uncertainty.json (v4 SoT)

- **Format:** JSON (schema version `fairness_uncertainty.v1`)
- **Meaning:** Deterministic fairness uncertainty surface (AIR + approval-rate gap) with race pairwise vs reference, p-values, and visibility gating signals.

### metrics_long.csv

```
run_id,split,model_id,metric,group,value,lower_ci,upper_ci,n,method,ci_degenerate
```

| Column | Type | Description |
|--------|------|-------------|
| run_id | string | Unique pipeline run identifier |
| split | string | Data split (test, synthetic, etc.) |
| model_id | string | Model identifier |
| metric | string | Metric name (air, selection_rate, tpr_gap, etc.) |
| group | string | Group identifier (attr:value or "all") |
| value | float | Metric value |
| lower_ci | float | Lower 95% CI bound |
| upper_ci | float | Upper 95% CI bound |
| n | int | Sample size |
| method | string | CI method (wilson, bootstrap_bca, bootstrap_percentile) |
| ci_degenerate | bool | Whether the CI is effectively zero-width |

### selection_rates.csv

```
run_id,split,model_id,attribute,group,selected,n
```

| Column | Type | Description |
|--------|------|-------------|
| attribute | string | Protected attribute (gender, race, etc.) |
| group | string | Group value (female, male, etc.) |
| selected | int | Count of positive outcomes |
| n | int | Total count in group |

### manifest.json

```json
{
  "schema_version": "wp-intake.v1",
  "run_id": "20251127-123456",
  "created": "2025-11-27T12:34:56Z",
  "dataset_hash": "sha256:abc123...",
  "commit_sha": "def456...",
  "container_digests": {
    "api_image_digest": "sha256:...",
    "worker_image_digest": "sha256:..."
  },
  "seeds": {"rng_seed": 42, "bootstrap_seed": 42},
  "capabilities": {
    "eo_enabled": true,
    "ece_enabled": false
  },
  "fairness_reference_groups": {"gender": "male", "race": "white"},
  "fairness_protected_groups": {"gender": ["female"], "race": ["black", "asian", "hispanic", "other"]},
  "fairness_policy": {"display_race_in_main_pdf": {"min_group_n": 300, "min_group_pct": 0.05}},
  "inference": {"method": "bca", "replicates": 2000, "alpha": 0.05, "seed": 42, "smoothing": 1e-6}
}
```

---

## CI Integration

The `.github/workflows/pull-wp-intake.yml` workflow can:
1. Trigger on producer CI completion (`repository_dispatch`)
2. Download the reviewer bundle artifact from producer (`wp-reviewer-pack-v4` from `wp-evidence-nightly.yml`)
3. Copy to `intake/`
4. Regenerate macros and build PDF
5. Upload PDF artifact

This workflow is intended to keep the PDF build reproducible and up to date with the producer’s latest evidence run.

---

## Validation

### Producer-Side (fl-bsa)

`tools/ci/validate_wp_intake.py` checks:
- Required CSV columns present
- CI bounds are sensible (lower ≤ value ≤ upper)
- All values in valid ranges (e.g., rates in [0,1])
- Provenance manifest has real values (no placeholders in CI mode)
- Required protected attributes covered (gender, race)

### Consumer-Side (this repo)

The LaTeX build process will:
- Show "TBD" placeholders if metrics are missing
- Generate tables from whatever data is available
- Fail gracefully on missing optional files

---

## Reproducibility

Every bundle includes full provenance:
- **Dataset hash**: SHA256 of input data
- **Code commit**: Git SHA of producer code
- **Container digests**: Exact image versions used
- **RNG seeds**: All random number generator seeds
- **Timestamps**: Start and end times

This enables any run to be reproduced exactly.
