Title: Whitepaper Intake Bundle — Consumption Instructions

Audience: Whitepaper workstream (data/analysis/docs)
Status: Ready to use (bundle exported by Gate‑P)

Overview
- Producer repo (fl-bsa) exports a compact bundle after Gate‑P with all per‑pipeline intake artifacts:
  - Required: `selection_rates.csv`, `metrics_long.csv`, `provenance/manifest.json`, `metrics.json`
  - Optional (EO): `group_confusion.csv` (when ground_truth is available)
- Bundle locations:
  - Local (after a run): `artifacts/wp-intake/<pipeline_id>/...`
  - CI artifact name: `wp-intake` (downloadable by the Whitepaper repo)
- Discovery: `artifacts/wp-intake/index.json` lists pipelines and flags to find files.

Pull via CI (Recommended)
- Trigger a workflow in the Whitepaper repo on the producer’s CI completion or on demand.
- Use an artifact‑download action to fetch the `wp-intake` bundle from the producer repo.

Example workflow (Whitepaper repo)
```
name: Pull WP Intake
on:
  workflow_run:
    workflows: ["CI (Comprehensive)"]
    types: [completed]
  workflow_dispatch: {}
jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Download wp-intake bundle from producer
        uses: dawidd6/action-download-artifact@v6
        with:
          repo: <org-or-user>/fl-bsa
          workflow: ci-comprehensive.yml
          workflow_conclusion: success
          name: wp-intake
          path: wp-intake
          if_no_artifact_found: warn
      - name: List bundle
        run: ls -al wp-intake && cat wp-intake/index.json
```

Local Pull (Developer)
- From the producer repo:
  - Build bundle: `poetry run python tools/ci/export_wp_intake.py --root output --dest artifacts/wp-intake`
  - Copy `artifacts/wp-intake/` into the Whitepaper repo (e.g., `data/wp-intake/`) or mount it.

Bundle Layout
- `wp-intake/index.json`: top-level manifest with one entry per pipeline:
  - `pipeline_id`, `created_at`
  - `has_selection_rates`, `has_metrics_long`, `has_group_confusion`, `has_provenance`, `has_metrics_manifest`
  - `commit_sha`, `dataset_hash`, `api_image_digest`, `worker_image_digest`
- Per pipeline: `wp-intake/<pipeline_id>/`
  - `selection_rates.csv`
  - `metrics_long.csv`
  - `group_confusion.csv` (optional; EO only)
  - `metrics.json`
  - `provenance/manifest.json`

CSV Schemas
- selection_rates.csv
  - Header: `run_id,split,model_id,attribute,group,selected,n`
  - Meaning: per `(split, attribute, group)`; `selected` is count of `loan_approved=1`; `n` is group size (0 ≤ selected ≤ n).
- metrics_long.csv
  - Header: `run_id,split,model_id,metric,group,value,lower_ci,upper_ci,n,method`
  - Rows:
    - `selection_rate` for each `attribute:group` (95% CI, `method=wilson`)
    - `air` for each `attribute:all` (adverse impact ratio, 95% CI, `method=bootstrap_percentile`)
- group_confusion.csv (if present)
  - Header: `run_id,split,model_id,attribute,group,TP,FP,TN,FN`
  - Computed with `y_true=ground_truth`, `y_pred=loan_approved`.

Programmatic Loader (Whitepaper)
```
from pathlib import Path
import json
import pandas as pd

def load_wp_bundle(bundle_root: str = "wp-intake"):
    root = Path(bundle_root)
    index = json.loads((root/"index.json").read_text())
    rows_sel, rows_long, rows_eo, prov = [], [], [], []
    for p in index["pipelines"]:
        pid = p["pipeline_id"]
        pdir = root / pid
        if p.get("has_selection_rates"):
            rows_sel.append(pd.read_csv(pdir/"selection_rates.csv").assign(pipeline_id=pid))
        if p.get("has_metrics_long"):
            rows_long.append(pd.read_csv(pdir/"metrics_long.csv").assign(pipeline_id=pid))
        if p.get("has_group_confusion"):
            rows_eo.append(pd.read_csv(pdir/"group_confusion.csv").assign(pipeline_id=pid))
        if p.get("has_provenance"):
            prov.append(json.loads((pdir/"provenance/manifest.json").read_text()))
    sel = pd.concat(rows_sel, ignore_index=True) if rows_sel else pd.DataFrame()
    mlong = pd.concat(rows_long, ignore_index=True) if rows_long else pd.DataFrame()
    eo = pd.concat(rows_eo, ignore_index=True) if rows_eo else pd.DataFrame()
    return {"selection_rates": sel, "metrics_long": mlong, "group_confusion": eo, "provenance": prov, "index": index}
```

Provenance Handling
- File: `provenance/manifest.json`
  - Keys: `schema_version`, `run_id`, `created`, `dataset_hash`, `commit_sha`, `container_digests`, `seeds`, `config_hash`, `capabilities`
- Usage:
  - Cite `commit_sha` in the paper as the build reference.
  - Use `dataset_hash` for reproducibility. Locally it may be `not_available`; in CI it is strict.
  - If EO is required, check `has_group_confusion` in `index.json` and/or `capabilities.eo_enabled`.

EO Notes
- EO is optional and only present when ground_truth is available.
- For EO-required analyses, filter to pipelines with `has_group_confusion: true`.

Integrity Checks (Optional)
- Validate shapes/values before consumption:
  - Headers exactly match for both CSVs.
  - `selection_rate`: 0 ≤ value ≤ 1 and `lower_ci ≤ value ≤ upper_ci`.
  - `selection_rate` equals `selected/n` within tolerance.
  - `air` recomputed from selection rates matches within tolerance.
- You can vendor the producer’s validator for identical rules:
  - `poetry run python tools/ci/validate_wp_intake.py --root wp-intake`

Operational Tips
- Keep only the last N pipelines (use `index.json` ordering) to limit workspace size.
- Cache `wp-intake/` path across jobs if your build is multi‑stage.
- Surface provenance (commit, dataset hash, seeds) in footnotes/appendix for reproducibility.

Common Pitfalls
- No bundle downloaded: ensure the artifact name is `wp-intake` and the path is correct.
- Placeholder provenance fields: expected locally; CI fills commit/digests/hash before upload.
- Missing EO: not all pipelines have ground_truth; guard EO sections with `has_group_confusion`.

