# Intake Pull CI — Cross‑Repo Automation

This repo can automatically pull the reviewer bundle produced by the main `fl-bsa` repo and then rebuild the whitepaper.

## Triggers (three options)

1. repository_dispatch (preferred)
- In `fl-bsa` CI, dispatch an event to this repo after a successful run that uploads the reviewer-bundle artifact.
- Example curl (run in fl‑bsa CI with a repo token):
```
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${GH_TOKEN}" \
  https://api.github.com/repos/<owner>/<whitepaper-repo>/dispatches \
  -d '{
        "event_type":"wp-intake-ready",
        "client_payload":{
          "producer_repo":"equilens-labs/fl-bsa",
          "workflow_file":"wp-evidence-nightly.yml",
          "branch":"main",
          "artifact_name":"wp-reviewer-pack-v4",
          "producer_run_id":""
        }
      }'
```
- This repo listens for `repository_dispatch` with type `wp-intake-ready` and downloads the bundle artifact.

2. Scheduled pull
- A daily cron (`0 6 * * *`) attempts to pull the latest reviewer bundle from `equilens-labs/fl-bsa` (default workflow/file/branch).

3. Manual pull
- Use the GitHub UI to run the `pull-wp-intake` workflow with custom inputs for producer repo/workflow/branch/artifact.
- For tagged releases and other audit-sensitive rebuilds, set `producer_run_id` to the exact successful producer run. This avoids branch-head drift and makes the whitepaper artifact replayable.

## Authentication (private producers)

If `fl-bsa` is private, add a secret `PRODUCER_TOKEN` in this repo. Prefer a GitHub App installation token, or a fine-grained PAT scoped only to `equilens-labs/fl-bsa` with:

- Actions: read
- Contents: read

The workflow fails fast when `PRODUCER_TOKEN` is missing for a cross-repo private producer. It does not silently fall back to this repo's `GITHUB_TOKEN`, because GitHub masks private cross-repo authorization failures as `404 Not Found`.

Rotate the token on the same cadence as other CI cross-repo credentials, and remove it when the producer repository is no longer private or when this intake path is retired.

## What happens after pull

The workflow downloads `WhitePaper_Reviewer_Pack_v4.zip`, unpacks it, and syncs the relevant contents into this repo:
- `intake/selection_rates.csv`
- `intake/fairness_slices.json` (gender AIR by slice: historical/amplification/intrinsic)
- `intake/metrics_uncertainty.json` (v4 SoT for the PDF)
- `intake/metrics_long.csv` (legacy/annex/back-compat)
- `intake/group_confusion.csv` (if present)
- `intake/certificates/*.json`
- `intake/manifest.json` (from `provenance/manifest.json` in the bundle)
- `config/sap.yaml` (copied from the bundle)

Then it regenerates LaTeX macros and builds the PDF and arXiv source, uploading both as workflow artifacts.

The workflow also stamps `intake/manifest.json` with `whitepaper_consumer`, recording the consumer repository, run ID, run attempt, commit SHA, workflow, event, ingestion timestamp, and producer artifact selectors used for the rebuild.

## Notes

- repository_dispatch does not pass secrets; it only carries a small JSON payload for repo/workflow selection. The actual download uses this repo’s token/secret.
- If the producer artifact cannot be downloaded (missing token, private repo access), the job fails fast.
