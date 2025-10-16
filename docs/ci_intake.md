# Intake Pull CI — Cross‑Repo Automation

This repo can automatically pull the `wp-intake` artifact produced by the main `fl-bsa` repo and then rebuild the whitepaper.

## Triggers (three options)

1. repository_dispatch (preferred)
- In `fl-bsa` CI, call the GitHub API to dispatch an event to this repo after a successful run that uploads the `wp-intake` artifact.
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
          "workflow_file":"ci-comprehensive.yml",
          "branch":"main",
          "artifact_name":"wp-intake"
        }
      }'
```
- This repo listens for `repository_dispatch` with type `wp-intake-ready` and downloads the artifact.

2. Scheduled pull
- A daily cron (`0 6 * * *`) attempts to pull the latest `wp-intake` from `equilens-labs/fl-bsa` (default workflow/file/branch).

3. Manual pull
- Use the GitHub UI to run the `pull-wp-intake` workflow with custom inputs for producer repo/workflow/branch/artifact.

## Authentication (private producers)

If `fl-bsa` is private, add a secret `PRODUCER_TOKEN` in this repo with `repo:read` scope. The workflow uses:

```
github_token: ${{ secrets.PRODUCER_TOKEN || github.token }}
```

so it falls back to the default GITHUB_TOKEN for public repos but uses the secret for private ones.

## What happens after pull

The workflow copies the latest pipeline’s files from `wp-intake/<pipeline_id>/` into this repo:
- `intake/selection_rates.csv`
- `intake/metrics_long.csv`
- `intake/group_confusion.csv` (if present)
- `intake/metrics.json`
- `provenance/manifest.json`

Then it regenerates LaTeX macros and builds the PDF and arXiv source, uploading both as workflow artifacts.

## Notes

- repository_dispatch does not pass secrets; it only carries a small JSON payload for repo/workflow selection. The actual download uses this repo’s token/secret.
- If no `wp-intake/index.json` is found, the job will skip copying but still build the LaTeX with placeholders.

