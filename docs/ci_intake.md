# Intake Pull CI — Cross‑Repo Automation

This repo can automatically pull the whitepaper intake bundle produced by the main `fl-bsa` repo, rebuild the whitepaper, and open a PR that preserves the exact intake snapshot in git history.

## Triggers (three options)

1. repository_dispatch (preferred)
- In `fl-bsa` CI, dispatch an event to this repo after a successful run that uploads the intake-bundle artifact.
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
          "artifact_name":"wp-intake-bundle-v4",
          "producer_run_id":"",
          "persist_intake_pr":"true"
        }
      }'
```
- This repo listens for `repository_dispatch` with type `wp-intake-ready` and downloads the bundle artifact.

2. Scheduled pull
- A daily cron (`0 6 * * *`) attempts to pull the latest intake bundle from `equilens-labs/fl-bsa` (default workflow/file/branch).

3. Manual pull
- Use the GitHub UI to run the `pull-wp-intake` workflow with custom inputs for producer repo/workflow/branch/artifact.
- For tagged releases and other audit-sensitive rebuilds, set `producer_run_id` to the exact successful producer run. This avoids branch-head drift and makes the whitepaper artifact replayable.
- Leave `persist_intake_pr=true` for release evidence. Set it to `false` only for local/debug rebuilds where a transient PDF artifact is intentionally enough.

## Authentication (private producers)

If `fl-bsa` is private, add a secret `PRODUCER_TOKEN` in this repo. Prefer a GitHub App installation token, or a fine-grained PAT scoped only to `equilens-labs/fl-bsa` with:

- Actions: read
- Contents: read

The workflow fails fast when `PRODUCER_TOKEN` is missing for a cross-repo private producer. It does not silently fall back to this repo's `GITHUB_TOKEN`, because GitHub masks private cross-repo authorization failures as `404 Not Found`.

Rotate the token on the same cadence as other CI cross-repo credentials, and remove it when the producer repository is no longer private or when this intake path is retired.

## What happens after pull

The workflow downloads `WhitePaper_Intake_Bundle_v4.zip`, unpacks it, and syncs the relevant contents into this repo. For pre-rename producer runs, it falls back to `WhitePaper_Reviewer_Pack_v4.zip` / `wp-reviewer-pack-v4` so older evidence can still be replayed.
- `intake/selection_rates.csv`
- `intake/fairness_slices.json` (gender AIR by slice: historical/amplification/intrinsic)
- `intake/metrics_uncertainty.json` (v4 SoT for the PDF)
- `intake/metrics_long.csv` (legacy/annex/back-compat)
- `intake/group_confusion.csv` (if present)
- `intake/certificates/*.json`
- `intake/manifest.json` (from `provenance/manifest.json` in the bundle)
- `config/sap.yaml` (copied from the bundle)

Then it regenerates LaTeX macros and figures, builds the PDF and arXiv source, and uploads them as workflow artifacts.

The workflow also stamps `intake/manifest.json` with `whitepaper_consumer`, recording the consumer repository, run ID, run attempt, commit SHA, workflow, event, ingestion timestamp, and producer artifact selectors used for the rebuild.

When `persist_intake_pr=true`, the workflow opens or updates a branch named `chore/wp-intake-<producer-sha>-<producer-run-id>` with the synced `intake/`, `config/`, generated `includes/`, and generated `figures/` changes. This PR is the reproducibility anchor for the PDF source snapshot; the transient `whitepaper-pdf-from-intake` artifact is not the only copy of the evidence state.

## Notes

- repository_dispatch does not pass secrets; it only carries a small JSON payload for repo/workflow selection. The actual download uses this repo’s token/secret.
- If the producer artifact cannot be downloaded (missing token, private repo access, or neither new nor legacy artifact name exists), the job fails fast.
