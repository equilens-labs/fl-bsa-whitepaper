# FL-BSA Whitepaper Evidence Repository

This repository houses the evidence, reviewer packs, and publication assets that back the FL-BSA whitepaper.

## Repo Map

- `artifacts/WhitePaper_Reviewer_Pack_v4/` — working copy of the latest reviewer bundle (metrics, provenance, privacy evidence).
- `artifacts/archive/` — historical bundles and reference zips.
- `intake/` — source evidence from the most recent reviewer drop (datasets, manifests, checklists).
- `config/sap.yaml` — statistical analysis plan thresholds shared by tooling and LaTeX macros.
- `docs/` — narrative docs (SAP, RFI, compiled intake summary) plus task notes.
- `templates/` — starter templates for future intake refresh cycles.
- `scripts/` — LaTeX helper scripts (metric macro generation, arXiv packaging).
- `sections/`, `includes/`, `main.tex`, `Makefile`, `.latexmkrc`, `bib/` — publication-ready LaTeX project.
- `ops/` — operational runbooks (bundle spec, strict-acceptance patch, bundling helper script).
- `tasks/` — task blocks and resync notes delivered with reviewer packs.

## Updating Evidence & Bundles

1. Generate fresh aggregated metrics and manifests from the main `fl-bsa` repo.
2. Drop the results into `intake/` (metrics, manifests, regulatory matrix, privacy evidence).
3. Run the bundling helper (`ops/runbook_bundle_v4.sh`) or `python3 scripts/compute_metrics.py ...` once the metric pipeline lands to rebuild `artifacts/WhitePaper_Reviewer_Pack_v4/`.
4. Ensure provenance (`provenance/manifest.json`) carries real dataset hashes and container digests.
5. Run `make verify` (once the acceptance tooling is present) followed by `make bundle` to emit `out/WhitePaper_Reviewer_Pack_v4.zip`.

## Publishing the Whitepaper

- Generate LaTeX macros from the latest metrics: `python3 scripts/gen_tex_macros_from_metrics.py --metrics intake/metrics_long.csv --sap config/sap.yaml --outdir includes`.
- Build the PDF locally: `make pdf` (outputs `dist/whitepaper.pdf`).
- Package an arXiv-ready source bundle: `make arxiv` (produces `dist/whitepaper_arxiv_source.zip`).
- GitHub Actions (`.github/workflows/latex.yml`) mirrors these steps on every push/PR and attaches both the PDF and arXiv bundle to published releases.

## Provenance

The assets in this repo originated from `chore/ci-stabilize-pr-path` (`local-uncommitted-whitepaper`) and were separated from the runtime `fl-bsa` repository to keep operational evidence and publication materials independent.
