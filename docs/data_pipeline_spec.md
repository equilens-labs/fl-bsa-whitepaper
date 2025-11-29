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
│    - tools/wp/validate_wp_intake.py (validation)            │
│    - flbsa/metrics/wp_intake.py (metrics computation)       │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ WhitePaper_Reviewer_Pack_v4.zip
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  fl-bsa-whitepaper (Consumer / This Repo)                   │
│                                                             │
│  intake/                                                    │
│    ├─ metrics_long.csv                                      │
│    ├─ selection_rates.csv                                   │
│    ├─ manifest.json                                         │
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
│   ├── calibration_bins.csv     # Calibration analysis
│   └── regulatory_matrix.csv    # Compliance mapping
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
| `air` | Adverse Impact Ratio (four-fifths rule) | Bootstrap percentile |
| `tpr`, `fpr` | Per-group true/false positive rates | Wilson 95% |
| `tpr_gap`, `fpr_gap` | Max gaps in TPR/FPR | Bootstrap percentile |
| `ece` | Expected Calibration Error | Bootstrap percentile |

### SAP Thresholds

Defined in `config/sap.yaml`:
- AIR ≥ 0.80 (four-fifths rule)
- TPR gap ≤ 0.05
- FPR gap ≤ 0.05
- ECE ≤ 0.02

### Bootstrap Configuration
- Iterations: 2000
- Seed: 42
- Method: percentile

---

## Consumer: fl-bsa-whitepaper

### Import Process

```bash
# 1. Get bundle from producer
# (either download from CI or copy from local run)

# 2. Extract to intake/
unzip WhitePaper_Reviewer_Pack_v4.zip -d /tmp/bundle
cp /tmp/bundle/intake/*.csv intake/
cp /tmp/bundle/provenance/manifest.json intake/manifest.json

# 3. Generate TeX macros
make macros

# 4. Build PDF
make pdf
```

### Macro Generation

`scripts/gen_tex_macros_from_metrics.py` reads:
- `intake/metrics_long.csv`
- `config/sap.yaml`

And generates:
- `includes/metrics_macros.tex` — threshold values, summary statistics
- `includes/table_air_summary.tex` — AIR table
- `includes/table_eo_summary.tex` — EO gaps table
- `includes/table_ece_summary.tex` — ECE table

---

## CSV Schemas

### metrics_long.csv

```
run_id,split,model_id,metric,group,value,lower_ci,upper_ci,n,method
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
| method | string | CI method (wilson, bootstrap_percentile) |

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
    "api": "repo@sha256:...",
    "worker": "repo@sha256:..."
  },
  "seeds": {"rng": 42},
  "capabilities": {
    "eo_enabled": true,
    "ece_enabled": true
  }
}
```

---

## CI Integration (Future)

The `.github/workflows/pull-wp-intake.yml` workflow can:
1. Trigger on producer CI completion (`repository_dispatch`)
2. Download `wp-intake` artifact from producer
3. Copy to `intake/`
4. Regenerate macros and build PDF
5. Upload PDF artifact

Currently manual; will be wired when cross-repo integration is finalized.

---

## Validation

### Producer-Side (fl-bsa)

`tools/wp/validate_wp_intake.py` checks:
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
