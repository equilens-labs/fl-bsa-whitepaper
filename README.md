# FL-BSA Whitepaper Evidence Repository

This repository houses the evidence, reviewer packs, and publication assets for the FL-BSA (Fair-Lending Bias-Simulation Appliance) regulatory whitepaper.

---

## Quick Start

### Build PDF from Existing Metrics
```bash
# Generate LaTeX macros from current intake data
make macros

# Build the whitepaper PDF
make pdf
# Output: dist/whitepaper.pdf

# Package for arXiv submission
make arxiv
# Output: dist/whitepaper_arxiv_source.zip
```

### Update Evidence from fl-bsa
```bash
# 1. In fl-bsa repo, generate fresh evidence bundle
cd /path/to/fl-bsa
make gate-wp
# Produces: artifacts/WhitePaper_Reviewer_Pack_v4.zip

# 2. In this repo, import the bundle
unzip /path/to/WhitePaper_Reviewer_Pack_v4.zip -d /tmp/bundle
cp /tmp/bundle/intake/*.csv intake/
cp /tmp/bundle/provenance/manifest.json intake/manifest.json

# 3. Rebuild PDF with updated metrics
make pdf
```

---

## Repository Structure

```
fl-bsa-whitepaper/
├── main.tex                    # LaTeX entry point
├── sections/                   # Document sections (12 files)
├── includes/                   # Macros and auto-generated tables
├── bib/                        # Bibliography (references.bib)
├── intake/                     # Evidence data (CSVs, manifests)
├── config/                     # SAP thresholds (sap.yaml)
├── scripts/                    # Build helpers
├── docs/                       # Detailed specifications
├── ops/                        # Bundle spec
├── tasks/                      # Task documentation
├── artifacts/                  # Reviewer bundles (current + archive)
├── templates/                  # Intake templates for future cycles
├── Makefile                    # Build targets
└── .github/workflows/          # CI (LaTeX build, intake pull)
```

---

## Workflow

### Evidence Generation (Producer: fl-bsa)

The `fl-bsa` repository contains the FL-BSA runtime and the `gate-wp` target that generates deterministic evidence bundles:

```bash
make gate-wp
```

This:
1. Starts FL-BSA services (API, Worker, Redis)
2. Generates a seeded synthetic dataset
3. Runs full bias analysis pipeline
4. Computes fairness metrics (AIR, EO, ECE) with 95% CIs
5. Captures provenance (dataset hash, container digests, seeds)
6. Validates and packages: `WhitePaper_Reviewer_Pack_v4.zip`

### Publication (This Repo)

1. Import bundle to `intake/`
2. Run `make pdf` to compile LaTeX with updated metrics
3. CI automatically builds on push/PR

---

## Key Files

| Location | Description |
|----------|-------------|
| `intake/metrics_long.csv` | Fairness metrics with confidence intervals |
| `intake/manifest.json` | Provenance (hashes, commits, seeds) |
| `config/sap.yaml` | Statistical Analysis Plan thresholds |
| `includes/metrics_macros.tex` | Auto-generated LaTeX macros |
| `dist/whitepaper.pdf` | Compiled whitepaper |

---

## SAP Thresholds

Defined in `config/sap.yaml`:
- **AIR** ≥ 0.80 (four-fifths rule)
- **TPR gap** ≤ 0.05 (equalized odds)
- **FPR gap** ≤ 0.05 (equalized odds)
- **ECE** ≤ 0.02 (calibration error)

---

## CI/CD

### GitHub Actions Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `latex.yml` | push, PR, release | Build PDF and arXiv bundle |
| `pull-wp-intake.yml` | dispatch, schedule | (Future) Pull intake from producer |

On release, the CI attaches `whitepaper.pdf` and `whitepaper_arxiv_source.zip` to the GitHub release.

---

## Documentation

| Document | Description |
|----------|-------------|
| `docs/data_pipeline_spec.md` | Evidence pipeline architecture |
| `docs/SAP.md` | Statistical Analysis Plan narrative |
| `ops/Bundle_Spec_v4.md` | Reviewer bundle format spec |
| `tasks/Intake.md` | Bundle consumption instructions |
| `tasks/LaTeX-Structure.md` | LaTeX project structure |

---

## Provenance

Evidence bundles include full reproducibility metadata:
- **Dataset hash**: SHA256 of input data
- **Code commit**: Git SHA of producer code
- **Container digests**: Exact image versions
- **RNG seeds**: All random number generator seeds
- **Timestamps**: Start and end times

This ensures any evidence can be reproduced exactly.
