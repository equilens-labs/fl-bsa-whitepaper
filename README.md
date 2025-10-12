# FL-BSA Whitepaper Evidence Repository

This repository houses the regulatory and evidence artifacts required to support the FL-BSA whitepaper.

## Contents

- `docs/` — narrative documents (SAP, RFI, compiled intake summary).
- `intake/` — structured evidence backing every claim (manifests, CSV exports, checklists, hyperparameter configs).
- `templates/` — intake templates for future refresh cycles.
- `artifacts/` — delivered reviewer packs and compiled intake bundle.
- `notes/` — CI/CD status snapshot and gold review observations from 2025-10-07.

## Usage

1. Generate fresh evidence from the FL-BSA main repo (`make gate-p`, Gold suite, etc.).
2. Copy the new outputs into the matching directories here (manifests, CSVs, reviewer packs).
3. Update the manifest/checklist metadata to reflect the new run IDs and timestamps.
4. Commit and push to keep the whitepaper collateral in sync with the product release cadence.

## Provenance

These assets were recovered from the `chore/ci-stabilize-pr-path` stash (`local-uncommitted-whitepaper`) and moved out of the main `fl-bsa` repository to keep the runtime repo lean.

