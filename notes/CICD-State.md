# FL‑BSA CI/CD Status Report (External Reviewer)

Date: 2025-10-07 (UTC)
Repository: equilens-labs/fl-bsa

This report documents the current CI/CD state observed on GitHub Actions for the FL‑BSA repository. It summarizes the workflow topology, recent failures, root causes with evidence, and recommended remediation paths. No code changes were made as part of this assessment.

---

## Executive Summary

- Multiple PR CI failures have the same primary root causes:
  - Poetry lockfile drift: jobs abort early at dependency installation when `pyproject.toml` changes are not accompanied by a refreshed `poetry.lock`.
  - Prod E2E (Quick) intermittently fails post‑tests due to a strict TLS proxy health gate (nginx 502 to upstream `api:80` for `/healthz`) despite API being healthy.
  - GPU workflow requires a self‑hosted GPU runner; jobs remain queued and will block if marked required.
- Branch protection on `main` currently does not list required status checks; practical blocking occurs because the team avoids merging while CI is red.
- Scheduled security/CVE scans on `main` are failing (lock issues or scanner setup), creating red signals in the repository’s Actions history.

---

## CI/CD Topology (Workflows & Gates)

Active workflows under `.github/workflows`:

- CI (Comprehensive): `.github/workflows/ci-comprehensive.yml`
  - Triggers: PRs to `main`/`release/*`, pushes to `main`, manual, scheduled.
  - Structure: path filter → baseline guard → static validators (Gate A) → runtime image build + push to GHCR → “gates” job executes Makefile gates (B/C/D/E/F/G), gathers coverage, then integration and prod E2E quick.
  - Notable steps:
    - Builds a distroless runtime image (`Dockerfile` target `runtime`) and pushes to GHCR.
    - Uses compose with overlays: `docker-compose.prod.yml` + `docker-compose.ci-alerts.yml` + `docker-compose.ci-tls.yml` + `docker-compose.ci-prebuilt.yml`.
    - Applies an egress firewall via `iptables` in the prod E2E job, allowing loopback/bridge ranges; drops everything else.
    - Validates artifacts against schemas (`tools/ci/schema_validator.py`) and certificates (`tools/ci/validate_certificates.py`), and checks API surface vs baseline (Gate G).

- Benchmark CI: `.github/workflows/benchmark-ci.yml`
  - Triggers: PRs, pushes to `main`, nightly schedule, manual dispatch.
  - Jobs: PR quick suite, nightly “full”, optional baseline update.

- FL‑BSA GPU Performance & ML Tests: `.github/workflows/runson-gpu.yml`
  - Triggers: PRs, pushes to `main`, manual dispatch.
  - Requires a self‑hosted runner with GPU labels; not compatible with GitHub‑hosted runners.

- Security Scanning: `.github/workflows/security.yml` and `cve-scan.yml`
  - Triggers: PRs, pushes to `main`, nightly schedule.
  - Tools: Trivy (container), pip‑audit, Safety, Bandit, Checkov, SBOM (Syft), Grype.

- Performance Validation: `.github/workflows/performance-validation.yml`
  - Triggers: pushes/pull_requests touching performance/synthetic paths, nightly schedule, manual.

Makefile gates (referenced by CI):

- Gate A (Static): lint, style, unsafe call scan, privacy compliance tests, doc/link checks, LexPro privacy markers.
- Gate B/C/D: fast unit tests + multi‑seed flake detection + coverage enforcement.
- Gate E/F/G: schema validation, determinism checks, API surface comparison.
- Integration / Prod E2E (Gate P): service bring‑up via compose, service warm‑up, production‑like flows, evidence bundle, schema checks, TLS proxy health.

---

## Branch Protection & Required Checks (Main)

Pulled via GitHub API on 2025‑10‑07:

- Required status checks: none configured (`checks`: [], `contexts`: []).
- Required PR reviews: 1 approval.
- Enforce admins: disabled.

Implication: merges are not technically blocked by required checks; however, CI red states have practically blocked merges (policy) and affect confidence.

---

## Recent Runs (Representative Evidence)

Time window: 2025‑10‑06 to 2025‑10‑07 UTC. Selected PRs and runs with failing jobs:

1) PR #10 `chore/ci-hardening`

- CI (Comprehensive): failure — job `static-analysis` aborted at dependency install due to Poetry lock drift.
  - Run: https://github.com/equilens-labs/fl-bsa/actions/runs/18292700373
  - Key log excerpt: `pyproject.toml changed significantly since poetry.lock was last generated. Run \
    poetry lock to fix the lock file.`
- Security Scanning: failure — `Python Dependency Vulnerability Scan` aborted at `poetry install` with the same lock drift message.
  - Run: https://github.com/equilens-labs/fl-bsa/actions/runs/18292700354
- Benchmark CI: failure — PR fast job failed at `poetry install` with lock drift.
  - Run: https://github.com/equilens-labs/fl-bsa/actions/runs/18292700348
- GPU tests: queued — no GPU runner available to pick up the job.
  - Run: https://github.com/equilens-labs/fl-bsa/actions/runs/18292700346

2) PR #6 `feature/site-staging`

- CI (Comprehensive): failure — `Prod E2E (Quick)` reported TLS proxy health failure (post‑tests), despite API/worker healthy.
  - Run: https://github.com/equilens-labs/fl-bsa/actions/runs/18292016515
  - Compose status at failure time: `api` healthy; `tlsproxy` unhealthy (nginx:stable).
  - TLS health loop: repeated `curl -fsSk https://127.0.0.1:8443/healthz` → 502 over 60s.
  - `tlsproxy` logs show repeated `connect() failed (111: Connection refused)` to upstream `http://api:80/healthz`.
  - Note: Earlier in the same job, `API /healthz` over plain HTTP passed; tests and schema validation later reported success (`✅ All artifacts conform to schemas (24 files validated)`), but the TLS health step exits 1.
- Other jobs on this PR: `static-analysis`, `runtime-image`, `gates`, and `Integration (Smoke)` — success; Security Scanning — success; Benchmark CI — success.

3) PR #9 `feature/site-staging-min`

- Security Scanning: failure — lock drift at `poetry install`.
  - Run: https://github.com/equilens-labs/fl-bsa/actions/runs/18287969856
- Benchmark CI: failure — lock drift and broad `SyntaxError: invalid escape sequence '\\s'` across many tests during collection on this runner/toolchain.
  - Run: https://github.com/equilens-labs/fl-bsa/actions/runs/18287969857
- GPU tests: queued — no runner available.
  - Run: https://github.com/equilens-labs/fl-bsa/actions/runs/18287969867

Scheduled jobs on `main` (nightly):

- CVE Scanning (nightly): failures recorded (not analyzed in depth; likely scanner setup or dependency export issues; they do not block merges unless marked required).
- Security Scanning (nightly): failures observed; see lock drift notes above.

---

## Root Cause Analysis

1) Poetry lockfile drift (High impact, repeatable)

- Symptom: Jobs fail at `poetry install` with message: `pyproject.toml changed significantly since poetry.lock was last generated. Run 'poetry lock' to fix the lock file.`
- Where observed: CI static analysis, Security Scanning (dependency scan), Benchmark CI.
- Cause: `pyproject.toml` dependency changes or Poetry metadata changes were merged/pushed without regenerating `poetry.lock`; also differing Poetry versions in workflows produce strictness warnings and aborts.
- Impact: Early aborts in multiple workflows, blocking PRs practically.
- Evidence: Runs 18292700373, 18292700354, 18292700348, 18287969857 (PRs: #10 and #9).

2) Prod E2E (Quick) TLS proxy health gate (Moderate impact, intermittent)

- Symptom: TLS proxy health loop fails (`502` from nginx to upstream API `/healthz`) even while `api` and `worker` are healthy.
- Topology: TLS proxy `nginx:stable`, config at `tools/ci/tls/nginx.conf` proxies to `api:80`. `tlsproxy` starts after services; job includes an HTTP health check (passes) and later a TLS readiness check (fails).
- Observed in: PR #6 run 18292016515 — `API healthy` earlier; later, `tlsproxy` logs repeated `connect() failed (111: Connection refused)` to upstream.
- Likely: Timing/race or container connectivity transient during/after long test phases (the failure occurred hours into the job). Given compose ps shows `api` healthy, it may be an ephemeral proxy issue. The gate is strict and fails the job after successful tests and schema checks.
- Impact: CI reports a failure for an otherwise passing E2E job.

3) GPU workflow requires self‑hosted runner (Low impact if not required; blocking if required)

- Symptom: GPU jobs remain `queued` due to lack of eligible self‑hosted GPU runner.
- Observed for multiple PRs. If marked required in branch protections or org rules, this will hard‑block merges.

4) Benchmark CI syntax errors on a runner/toolchain (PR #9)

- Symptom: `SyntaxError: invalid escape sequence '\\s'` during test collection across many modules.
- Likely: test suite literal/regex escape usage or a Python/pytest behavior shift on that runner image; warrants a quick lint fix in tests (use raw strings for regex patterns) or pin plugin versions.

5) Potential (not currently failing observed PRs): GHCR permissions on forks

- Note: The CI pipeline builds and pushes the runtime image to GHCR. For PRs from forks, `GITHUB_TOKEN` generally lacks `packages:write`, which would cause the `runtime-image` job to fail; the current failures examined were from same‑repo PR branches where this was not triggered.

---

## Risk Assessment

- Lockfile drift — High: Affects multiple workflows; easy to trip; produces consistent early failure.
- TLS proxy gate — Medium: Fails post‑tests, undermining signal reliability; logs point to intermittent nginx→api connectivity, not functional regression in the app.
- GPU workflow — Medium (if required), Low otherwise: Queued jobs create noise and delay; set as required would block merges.
- Benchmark CI syntax errors — Medium: Test suite correctness/compatibility; affects only Benchmark job; not a product runtime defect.
- Scheduled security/CVE jobs — Low/Medium: Red history; not blocking merges but raises governance noise. Should be stabilized or scoped.

---

## Observability & Evidence (Artifacts)

- E2E artifacts example (PR #6 run 18292016515): collected compose config, TLS logs, JUnit, and coverage.
  - JUnit gate‑p: shows many E2E tests passed; several Prometheus tests were skipped due to compose availability; total tests executed; overall success before TLS step.
  - Coverage XML for gate‑p present.
  - `output_pre_schema_summary.json`: multiple pipeline directories with `metrics.json`, `report_metadata.json`, certificate artifacts, confirming functional E2E behavior.

---

## Recommendations (No changes applied yet)

1) Enforce lock hygiene

- Process: Require `poetry lock` in PRs that modify `pyproject.toml`; add a lightweight CI gate to check lock consistency (read‑only).
- Align Poetry versions in workflows (pin a single version across workflows) to reduce compatibility warnings.

2) Make heavy jobs manual/self‑hosted only (as per policy)

- GPU workflow: restrict triggers to `workflow_dispatch` and `runs-on: [self-hosted, gpu]` only; or disable by renaming to `.disabled`.
- Benchmark CI: same approach — manual only or disable; remove PR/push/schedule triggers if they must never run on GitHub‑hosted runners.
- Performance validation: move to manual or self‑hosted only if it’s heavy.

3) Stabilize Prod E2E TLS gate

- Convert TLS proxy health step to a soft gate on PRs (report‑only) while keeping hard gate on `main`/nightlies.
- Increase TLS readiness window and log introspection, or re‑order step to occur immediately after services warm‑up (before long test phases), then re‑verify quickly post‑tests with longer retries.
- Double‑check nginx upstream target (`api:80`) and compose network settings; log the resolved upstream IP at failure time.

4) Resolve benchmark test collection errors

- Audit tests using regex escapes; convert to raw strings or escape properly; align pytest/plugins versions to the runner image.

5) (Optional) Guard against GHCR push on forks

- In `runtime-image` job, conditionally skip image push for forked PRs; fall back to local build for compose.

6) Cleanup scheduled scans

- Ensure nightly Security/CVE workflows are stable or make them advisory to avoid persistent red history; consider gating only on `main`, not PRs.

---

## Appendix: Key Files & Commands

- Workflows: `.github/workflows/*.yml`
- Makefile gates: `Makefile` (targets: `gate-a`, `gate-b`, `gate-c`, `gate-d`, `gate-e-*`, `gate-f-*`, `gate-g-*`, `gate-p`)
- Compose: `docker-compose.prod.yml`, `docker-compose.ci-*.yml`
- TLS proxy config: `tools/ci/tls/nginx.conf`
- Schema validator: `tools/ci/schema_validator.py`
- Certificates validator: `tools/ci/validate_certificates.py`

Useful GitHub CLI commands executed during assessment:

```bash
# List latest runs
gh run list -L 30 --json databaseId,workflowName,event,status,conclusion,headBranch,createdAt,url

# View jobs for a run
gh run view <run_id> --json jobs

# Stream job logs
gh run view <run_id> --job <job_id> --log

# Branch protection
gh api "/repos/<owner>/<repo>/branches/main/protection"
```

---

## Closing Note

This report reflects the CI/CD state as of 2025‑10‑07 and should be revisited after the recommended remediations (lock hygiene, heavy‑job policy, TLS gate stabilization) are implemented.

---

## Addendum — Makefile and Development Docs Review

Scope: full pass over `Makefile` and `docs/development/*` to validate gates, selection rules, and expectations against observed CI behavior.

1) Gates and Marker SSOT (Makefile)
- Gate‑B marker expression excludes infra/heavy lanes as intended (`GATEB_MARKER_EXPR`), keeping fast, unit/infra‑free tests in the quick lane. Confirmed in `Makefile`.
- Gate‑B‑Alt, Integration, Celery, E2E, Perf are strictly marker‑driven; each gate sets timeouts and environment clamps. Confirmed in `Makefile` targets `gate-b-alt`, `gate-integration`, `gate-celery`, `gate-e2e`, `gate-h-perf`.
- Determinism and API surface are explicit gates (F/G). `gate-f-determinism` sets BLAS/OMP clamps and runs a deterministic verifier. `gate-g-api` compares against `ci/baselines/api_manifest.json`.
- Schema and certificates validation are wired as Gate‑E steps (`gate-e-schema`, `gate-e-certificates`) and align with `tools/ci/schema_validator.py` and `tools/ci/validate_certificates.py`.

2) E2E/TLS Flow (Makefile vs. Workflow)
- Gate‑P (Prod E2E) itself brings up services, warms up, runs production‑like E2E tests, gathers evidence and logs. Gate‑P, as defined in `Makefile`, does not include the TLS proxy health loop.
- The strict TLS proxy health check (nginx to `api:80/healthz`) is injected in the CI workflow job (`.github/workflows/ci-comprehensive.yml`) after Gate‑P. This is where we saw 502s despite API health. This explains why Gate‑P tests can pass while the job still fails later on TLS health.

3) Coverage & Thresholds (Docs vs. Makefile)
- Makefile: Gate‑D enforces ≥80% coverage (report‑only) using Gate‑B’s coverage data; Gate‑B itself generates coverage but does not enforce a threshold.
- Docs: `docs/development/quality-gates.md` describes Gate‑B features and mentions a “Minimum 8% coverage threshold” under Gate‑B. This does not match the current Makefile behavior (likely a documentation typo or legacy note). Current enforcement is Gate‑D ≥80%.

4) Heavy/Perf Lanes and Policy (Docs)
- The development docs (`ci-cd.md`, `makefile-reference.md`, `quality-gates.md`) consistently separate heavy/perf and full‑stack lanes from Gate‑B. They encourage keeping fast lanes green and running heavy work in dedicated lanes.
- This supports the operational policy that GPU and Benchmark should not run on GitHub‑hosted runners by default. The repository already contains disabled variants for some workflows (e.g., `*.disabled` files), and the Makefile provides local equivalents.

5) Determinism and Stability (Docs)
- Docs reinforce deterministic clamps (OMP/BLAS/thread pools) and strict seed handling across gates. The Makefile implements those clamps broadly via the `CLAMPS` env and specific gates.

6) Baselines and Guardrails (Docs + Workflows)
- Baseline Guard in CI enforces label `baseline:update` for changes under `ci/baselines/*` and `tools/api_manifest.py`. This aligns with the docs’ requirement to review baseline changes intentionally.

7) Summary of Minor Doc–Code Mismatch
- Gate‑B coverage threshold mention (8%) in docs does not reflect current Makefile behavior (no Gate‑B coverage threshold; Gate‑D enforces 80%). Recommendation: update `docs/development/quality-gates.md` to remove/clarify that line and point to Gate‑D for enforcement.

All other reviewed elements (marker SSOT, gate responsibilities, evidence/schema/cert validations, determinism, and API surface gate) are consistent between the Makefile, development docs, and the observed CI configuration.
