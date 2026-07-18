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
# Produces: artifacts/WhitePaper_Intake_Bundle_v4.zip

# 2. In this repo, import the bundle
unzip /path/to/WhitePaper_Intake_Bundle_v4.zip -d /tmp/bundle
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
├── baselines/                  # Reviewed evidence-baseline descriptors
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
6. Validates and packages: `WhitePaper_Intake_Bundle_v4.zip`

### Publication (This Repo)

1. Import bundle to `intake/`, or run `pull-wp-intake.yml` so CI persists an intake snapshot and artifacts
2. Run `make pdf` to compile LaTeX with updated metrics
3. CI automatically builds on push/PR

The stable-v5 characterization intake has a repository-owned durability descriptor at
`baselines/stable-v5-characterization.json`. It pins the original producer release-evidence
identity and the exact historical whitepaper `intake` / `config` Git trees, and can reconstruct a
deterministic compatibility ZIP without relying on expiring Actions artifacts or a bounded
release search. A separate selected-input projection binds publication candidates while allowing
traceability-only `intake/archive/` changes. See `docs/ci_intake.md` for validation/export
commands.

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
| `latex.yml` | push, PR, manual | Build PDF/arXiv candidates; optionally stage assets on an existing draft release |
| `pull-wp-intake.yml` | dispatch, schedule | Pull intake from producer, rebuild, and persist append-only snapshot history/artifacts |

Manual dispatch without `draft_release_tag` produces candidate workflow artifacts with
`publication_status=candidate_not_published`. With an exact existing semantic tag, it requires a
single still-unpublished draft release bound to the built tag commit, then stages and byte-verifies
the PDF/arXiv assets. For an independently authorized `v5.0.0` draft it also stages the explicitly
reconstructed compatibility ZIP and a hash-bound receipt whose status still says draft assets
staged. Draft staging must be dispatched from that tag itself, for example
`gh workflow run latex.yml --ref v5.0.0 -f draft_release_tag=v5.0.0`; dispatching from `main` is
rejected even when the checkout could otherwise resolve the tag. If staging fails, use a full
re-run of all jobs or a new exact-tag dispatch; partial failed-job re-runs are rejected so artifact
and receipt attempts cannot diverge. The workflow never creates a
release/tag, publishes a draft, or submits to arXiv. Only the
draft-staging job has `contents: write`; the build job remains read-only.
Public CI PDF artifacts enable the optional `DEMO / EVALUATION ONLY` text-layer watermark via
`includes/publication_profile.local.tex`; local builds remain unmarked unless that local include
sets `\drafttrue`.

Routine nightly intake uses the single append-only `chore/wp-intake-nightly` branch and creates
no per-run PR. Release-evidence input uses a workflow-write-once per-run branch and a best-effort
PR. The workflow does not rewrite those branches, but repository administrators can move or
delete them because no branch-protection/ruleset guarantee is claimed. Neither path force-pushes
or deletes historical intake branches. Each selected producer run is
API-verified and bounded polling must observe successful completion before stamping. Incoming
bundle members pass explicit filename plus content/schema public-disclosure validation; the raw private-producer ZIP is never
re-uploaded from this public repository. Producer-managed paths are replaced while the explicit
repository-owned intake files and `intake/archive/` tree are preserved.
When product CI supplies the optional bounded runtime-provenance block, the public validator also
requires the image configuration's full source SHA and an exact build/reuse disposition, with the
source-SHA relationship enforced for each disposition. See `docs/ci_intake.md`; this metadata does
not change the bounded evidence or publication claim.

---

## Documentation

| Document | Description |
|----------|-------------|
| `docs/data_pipeline_spec.md` | Evidence pipeline architecture |
| `docs/ci_intake.md` | Durable intake and stable-v5 anchor contract |
| `docs/stable_v5_publication.md` | Stable-v5 PDF/arXiv candidate and publication boundary |
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
