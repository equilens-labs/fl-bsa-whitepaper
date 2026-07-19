# Intake Pull CI — Cross-Repo Automation

This repository consumes the whitepaper intake bundle produced by
`equilens-labs/fl-bsa` and rebuilds the paper. Public Git persistence is a separate, explicit
publication mutation: ordinary dispatches and the daily schedule validate and build with
persistence disabled. When that mutation is approved, the workflow can preserve the exact source
state under the bounded branch contracts below. Transient Actions artifacts are review outputs,
not durable publication.

## Persistence contract

The workflow writes a `flbsa.whitepaper_intake_snapshot.v2` record to
`intake/whitepaper_snapshot.json` before it persists a source tree. The record binds the producer
repository, workflow, branch, run ID/attempt, artifact name/ID/API digest, product commit,
bundle filename and SHA-256 to the whitepaper base commit. It also fixes the public claim
boundary to:

- `customer_evidence_eligible=false`
- `customer_evidence_disposition=characterization_only`
- `publication_status=candidate_not_published`

All intake persistence runs share the `pull-wp-intake-persistence` concurrency group and do
not cancel an in-progress predecessor. This serializes reads and writes to the rolling branch.

When a `wp-evidence-nightly.yml` dispatch explicitly sets `persist_intake_pr=true`, it uses one
public branch: `chore/wp-intake-nightly`. Each changed snapshot is committed with both the current
default-branch commit and the previous rolling head as parents. The previous head therefore remains
reachable, while repeated runs with the same snapshot ID and tree are no-ops. It does not create
per-run branches or PRs. The ordinary producer dispatch and scheduled pull keep this setting false.

Approved `release-evidence.yml` persistence inputs use workflow-write-once branches named
`chore/wp-intake-<producer-sha12>-<producer-run-id>`. An exact replay is a no-op. If that branch
already exists with different content, the workflow fails instead of rewriting it. A release
snapshot PR is best-effort reviewer convenience; the write-once branch is the durable workflow
anchor. These branches currently have no branch-protection/ruleset guarantee: a repository
administrator can move or delete them. The snapshot ID, source-tree comparison, and workflow's
no-rewrite rule detect ordinary replay drift but do not turn the branch into an immutable Git
object or policy boundary.
Only the specific GitHub policy error that prevents Actions from creating or approving PRs is
soft-failed and recorded in the job summary plus the `intake-pr-soft-fail` artifact. Other
branch, push, or PR failures remain hard failures.

The workflow never force-pushes a persistence branch. This migration also does not delete or
rewrite historical `chore/wp-intake-*` branches.

## Triggers

### Producer dispatch (preferred)

After uploading an intake artifact, trusted producer automation dispatches the exact producer
run:

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${GH_TOKEN}" \
  https://api.github.com/repos/equilens-labs/fl-bsa-whitepaper/dispatches \
  -d '{
        "event_type":"wp-intake-ready",
        "client_payload":{
          "producer_repo":"equilens-labs/fl-bsa",
          "workflow_file":"wp-evidence-nightly.yml",
          "branch":"main",
          "artifact_name":"wp-intake-bundle-v4-<run-attempt>",
          "producer_run_id":"<exact-run-id>",
          "producer_run_attempt":"<exact-run-attempt>",
          "artifact_id":"<exact-actions-artifact-id>",
          "artifact_digest":"sha256:<exact-actions-artifact-digest>",
          "persist_intake_pr":"false"
        }
      }'
```

The accepted producers are deliberately narrow:

- repository: `equilens-labs/fl-bsa`
- workflows: `wp-evidence-nightly.yml` or `release-evidence.yml`
- artifacts: attempt-qualified, attested `wp-intake-bundle-v4-<run-attempt>`; the historical
  unqualified name is accepted only for first-attempt runs; unattested `wp-reviewer-pack-v4` is
  restricted to explicit first-attempt legacy compatibility (never an automatic fallback)

`persist_intake_pr` is retained as a compatibility payload name. It controls public snapshot
persistence and defaults to `false`. Only literal `true` or `false` (case-normalized) is accepted;
malformed or alternate truthy/falsey values fail before any Git mutation. For an explicitly approved nightly input, `true` means the
rolling history branch and no PR. For an explicitly approved release input, it means the
workflow-write-once branch plus a best-effort PR. Validation, PDF compilation, and Actions-artifact
upload still run when it is false; no public intake branch is created or updated.

Product workflow operators use the typed `persist_public_whitepaper_snapshot` input on
`wp-evidence-nightly.yml`; the producer maps that value to the internal compatibility payload field
shown above. Do not treat `persist_intake_pr` as an independent publication approval.

For release and other audit-sensitive rebuilds, the producer dispatches the run ID, run attempt,
artifact ID, and API digest so the consumer cannot drift to a newer branch-head run or a retained
artifact from another attempt. The consumer independently resolves all four values, verifies the
outer Actions ZIP against the API digest/size, and records them in the snapshot.

### Scheduled pull

The daily `0 6 * * *` schedule resolves the latest successful `wp-evidence-nightly.yml` run on
`main`, reads its API-verified run attempt, derives
`wp-intake-bundle-v4-<run-attempt>`, and applies the same validation with public persistence
disabled.
For transition compatibility only, an attempt-1 run with no qualified artifact may select one
unique attested `wp-intake-bundle-v4`. There is no scheduled fallback for later attempts or to
the unattested reviewer pack.

The consuming workflow intentionally has no `workflow_dispatch` input for arbitrary producer
artifacts. Exact on-demand rebuilds use the trusted `wp-intake-ready` dispatch instead.

## Authentication

For a private producer, configure `PRODUCER_TOKEN` as a GitHub App installation token or
fine-grained PAT scoped only to `equilens-labs/fl-bsa` with Actions read, Contents read, and
Attestations read. The last permission is required to verify the downloaded bundle's GitHub
attestation. The workflow fails if cross-repository authorization is absent; it does not silently
substitute the whitepaper repository's token. Do not grant Packages, administration, or write
access to this read-only producer credential.

`WP_INTAKE_PR_TOKEN` is required only when public persistence is explicitly approved. Scope it to
`equilens-labs/fl-bsa-whitepaper` with Contents write and Pull requests write. Scheduled and
ordinary validation/build runs receive a read-only default Actions token; checkout does not persist
that credential. The write token is exposed only to the guarded persistence step, which configures
the Git credential helper after validating literal `true` and fails before Git mutation when the
token is absent.

Rotate both credentials on the normal CI credential cadence. Never put a token or its contents
in a dispatch payload, artifact, snapshot record, or tracked file.

## Consumption and validation

The workflow downloads `WhitePaper_Intake_Bundle_v4.zip`, verifies its GitHub artifact
attestation against `equilens-labs/fl-bsa`, and accepts the unattested legacy reviewer pack only
when the dispatch explicitly selects it, with a warning and a valid `wp.pack_intent.v1` boundary.
It never falls back from a missing primary artifact. Duplicate same-named artifacts fail as
ambiguous. It validates the `wp-intake.v1`
provenance schema and `fairness_uncertainty.v1` metrics schema. Before download, every selected
run ID (discovered or dispatched) is resolved through the Actions API and must be numeric, match
the exact workflow path, approved event, source repository, and branch policy, and reach
`completed/success` within a bounded 20-minute poll. Nightly intake is restricted to `main`;
release intake is restricted to an exact semantic release branch whose suffix and corresponding
Git tag both resolve to the run head.
After unpacking, the bundle product commit and every recorded commit alias must equal that
API-verified run head SHA.

Before extraction, the consumer rejects duplicate, unsafe, oversized, or unexpected archive
members. Only the reviewed intake CSV/JSON names, reviewed certificate JSON names,
`config/sap.yaml`, optional `config/fairness_config.yaml`, and `provenance/manifest.json` may cross
the private-producer/public-consumer boundary. In particular, `privacy/**`, `metadata/**`, logs,
Markdown, and unreviewed future names fail closed.

After safe extraction, `scripts/validate_public_intake.py` enforces the content half of the
disclosure boundary. JSON/YAML keys and types must be a subset of the reviewed tracked public
files; CSV headers must match their tracked public counterparts exactly. Duplicate structured
keys, new fields/columns, high-confidence credentials, email addresses, user-home paths, private
IP addresses, sensitive identity fields, control characters, and oversized values fail closed.
A legitimate producer schema expansion therefore requires a reviewed public baseline change in
this repository before the corresponding private data can cross the boundary.
The validator itself carries three narrow reviewed empty-baseline/additive schemas: broken
correlation rows and range-violation rows may reference only column names already disclosed by
the tracked certificate, and `ci_runtime_provenance` may appear in either manifest only with the
exact `wp.ci_runtime_provenance.v2` bounded product-CI
run/artifact/runtime-digest/projection shape. Version 2 is the first producer-consumer shape that
persists runtime build-source identity; the incomplete pre-producer version-1 shape is not
accepted. Its `runtime_image` object
also records the full lowercase 40-hex `image_build_sha` from the image configuration's source
label and one exact `build_disposition`:

- `built_for_source` and `reused_exact_sha_tag_matching_projection` require
  `image_build_sha == source_ci.head_sha`;
- `reused_exact_sha_tag_projection_equivalent` requires a distinct image build source,
  `image_build_sha != source_ci.head_sha`; and
- `reused_main_profile_latest_matching_projection` permits either relationship because the
  moving profile alias may already point to the source build or to an input-equivalent build.

Missing, malformed, duplicate, or unknown fields and incoherent SHA/disposition pairs fail
closed. This records which already-verified runtime image was exercised; it does not make an
equivalent-input image the same source build. The CI block must keep `full_ci_proven=false`; it
cannot be used to widen the evidence or publication claim boundary.

The consumer stages a complete replacement for the producer-managed surfaces:

- `intake/*.csv` and `intake/*.json`
- `intake/certificates/*.json`
- `intake/manifest.json` from `provenance/manifest.json`
- `config/sap.yaml` and, when present, `config/fairness_config.yaml`

It removes omitted producer-managed files so they cannot survive from an older bundle. The six
explicit repository-owned top-level intake files (`*_TEMPLATE.csv`, governance contacts, license
inventory, model hyperparameters, and privacy checklist) plus the `intake/archive/` traceability
tree are copied into the stage and are never sourced from the incoming bundle.

The committed `whitepaper_consumer` stamp is deterministic. Actions already retains execution
timestamps and attempts, so those run observations are not copied into the source tree. The
stamp records the whitepaper base commit plus the exact producer selectors and bundle digest.
It also records the API-verified run head SHA, which must equal the bundle product commit. This
prevents timestamp-only Git churn and lets an exact replay compare both snapshot ID and tree.

Strict generators rebuild macros and figures, LaTeX compiles the PDF, and CI verifies the
`DEMO / EVALUATION ONLY` text marker. The workflow uploads generated
`whitepaper-pdf-from-intake` and `arxiv-source-from-intake` candidates, but it never re-uploads the
raw private producer ZIP. The Git snapshot is the long-lived reproducibility surface.

## Stable-v5 compatibility anchor

`baselines/stable-v5-characterization.json` is the repository-owned durable anchor for the
stable-v5 characterization intake. It pins:

- producer release-evidence run, product commit and original attested bundle SHA-256;
- the whitepaper intake commit and exact `intake` / `config` Git tree object IDs;
- the pinned manifest and pack-intent hashes and their non-evidence-grade boundary;
- a descriptor-selected publication-input projection that includes the repository-owned
  `intake/model_hyperparams.yaml` consumed by TeX generation and excludes `intake/archive/`; and
- the deterministic compatibility exporter script and expected export digest.

Validate or export it from a full whitepaper checkout:

```bash
python3 scripts/intake_anchor.py validate \
  --anchor baselines/stable-v5-characterization.json \
  --repo-root .

python3 scripts/intake_anchor.py export \
  --anchor baselines/stable-v5-characterization.json \
  --repo-root . \
  --output dist/WhitePaper_Intake_Bundle_v4.zip
```

The compatibility ZIP is reconstructed from the pinned whitepaper Git objects with stored
(uncompressed) members so its bytes do not depend on a zlib implementation. Its digest is
recorded under `export.expected_sha256`; it is intentionally distinct from the original
producer-attested bundle digest under `producer.bundle_sha256`. The reconstruction is a durable
replay surface, not a claim that the original Actions artifact was republished.

The historical evidence anchor remains whitepaper commit
`a451eae4284c4c592783f108e206e5ba1c0e5747` and its whole `intake` / `config` tree OIDs. A
publication candidate is checked against `publication_inputs.paths` and the projection digest,
not against whole-tree equality. Consequently PR #26's archival move at
`e93a0fef4c88d7cb4c2c38df6f7dd26a11b75837` changes the recorded current intake-tree OID while
retaining the exact stable-v5 publication-input digest. A selected current input change still
fails closed.

Producer-side consumers must fetch the descriptor, `scripts/intake_anchor.py`, and the frozen
exporter named by `export.script` from the same reviewed whitepaper commit. They verify the
frozen exporter hash recorded in the descriptor, fetch enough Git history to resolve
`consumer.intake_commit`, run `validate`, and only then run `export`. A future baseline that
needs different export behavior gets a new exporter path; it must not rewrite the stable-v5
exporter. This replaces any bounded "latest N releases" scan. Private-repository access requires
whitepaper Contents read permission. A moving branch name or an unverified downloaded ZIP is
not an equivalent anchor.

See `docs/stable_v5_publication.md` for the PDF/arXiv candidate and publication boundary.
