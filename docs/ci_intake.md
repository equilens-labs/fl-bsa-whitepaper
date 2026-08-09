# Intake Pull CI — Cross-Repo Automation

This repository consumes the whitepaper intake bundle produced by
`equilens-labs/fl-bsa`. The daily schedule validates the bundle and emits a JSON receipt only. An
exact `release-evidence.yml` dispatch additionally builds a separate version-bound release paper
and manifest; it never recompiles or rewrites the fixed archival v5.0.1 paper. Public Git
persistence is a separate, explicit publication mutation and remains disabled for both reviewed
product producers. When that mutation is approved, the workflow can preserve the exact source
state under the bounded branch contracts below. Transient Actions artifacts are review outputs,
not durable publication.

## Persistence contract

The workflow writes a `flbsa.whitepaper_intake_snapshot.v3` record to
`intake/whitepaper_snapshot.json` before it persists a source tree. The record binds the producer
repository, workflow, branch, run ID/attempt, artifact name/ID/API digest, product commit,
bundle filename and SHA-256 to the whitepaper base commit. It also fixes the public claim
boundary to:

- `customer_evidence_eligible=false`
- `customer_evidence_disposition=characterization_only`
- `publication_status=candidate_not_published`

All intake persistence runs share the `pull-wp-intake-persistence` concurrency group and do
not cancel an in-progress predecessor. This serializes reads and writes to the rolling branch.

The current producer contract requires `persist_intake_pr=false`, so neither reviewed product
workflow can write a public intake branch. The rolling-history implementation remains fail-closed
behind that contract for a separately reviewed future publishing route.

The dormant release persistence implementation uses workflow-write-once branches named
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
          "producer_contract_sha256":"<exact-shared-contract-sha256>",
          "persist_intake_pr":"false"
        }
      }'
```

The accepted producers are deliberately narrow:

- repository: `equilens-labs/fl-bsa`
- workflows: `wp-evidence-nightly.yml` or `release-evidence.yml`
- artifacts: on-demand dispatch requires the attempt-qualified, attested
  `wp-intake-bundle-v4-<run-attempt>`; scheduled transition compatibility may accept the historical
  unqualified first-attempt artifact, but never silently falls back to the reviewer pack

`contracts/whitepaper-intake-producer-contract.v1.json` is copied byte-for-byte into both
repositories. Both producer workflows build their payload through the matching contract helper,
and this consumer validates the same fields and contract SHA-256 before it queries or downloads
anything. A missing field, extra field, stale event, stale release branch, contract mismatch, or
anything other than literal `persist_intake_pr=false` fails. Changing this boundary requires a
reviewed contract change in both repositories.

Every on-demand producer dispatch must provide the run ID, run attempt, artifact ID, and API
digest. The consumer rejects an incomplete dispatch instead of searching for a recent successful
run. It independently resolves all four values, verifies the outer Actions ZIP against the API
digest/size, and records them in the snapshot.

### Scheduled pull

The daily `0 6 * * *` schedule resolves the current `equilens-labs/fl-bsa@main` commit and the
newest `wp-evidence-nightly.yml` run on `main` without filtering by run status. The newest run must
be for that exact current commit. The consumer then waits only on that run: queued or in-progress
authority is polled, while a failed, cancelled, timed-out, stale-head, or otherwise unsuccessful
authority fails the pull. It never searches backward for an older successful run.

After the selected run succeeds, the consumer reads the producer contract from that exact immutable
product commit, hashes its raw bytes, and requires equality with the reviewed contract in this
repository. A missing file, inaccessible commit, oversized file, or byte drift fails before any
artifact is selected or downloaded. The receipt therefore records a contract hash proven on both
sides of the scheduled handoff.

Immediately before downloading artifact bytes, the consumer re-resolves `fl-bsa@main`, the newest
matching producer run, and the selected run attempt/status. Any branch, run, attempt, or conclusion
drift fails closed so a run that became stale during the bounded wait cannot be consumed. Once the
authority remains exact, the workflow derives `wp-intake-bundle-v4-<run-attempt>` and applies the
same validation with public persistence disabled.

For transition compatibility only, an attempt-1 run with no qualified artifact may select one
unique attested `wp-intake-bundle-v4`. There is no scheduled fallback for later attempts or to
the unattested reviewer pack.

The consuming workflow has no `workflow_dispatch` input for arbitrary producer artifacts. Exact
on-demand rebuilds use the contract-bound `wp-intake-ready` dispatch instead.

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
token is absent. In GitHub Actions, persistence also requires the exact canonical HTTPS origin for
`equilens-labs/fl-bsa-whitepaper`: exactly one effective fetch URL and one effective push URL,
allowing only the optional `.git` suffix. A different repository, an SSH origin, a separate or
multiple `pushurl`, or a Git URL rewrite is rejected.

Rotate both credentials on the normal CI credential cadence. Never put a token or its contents
in a dispatch payload, artifact, snapshot record, or tracked file.

## Consumption and validation

The workflow downloads `WhitePaper_Intake_Bundle_v4.zip` and verifies its GitHub artifact
attestation against `equilens-labs/fl-bsa`. Current scheduled and contract-bound dispatches can
select only the attested primary bundle; the historical reviewer-pack compatibility code is
dormant, and there is no automatic fallback. Duplicate same-named artifacts fail as ambiguous.
It validates the `wp-intake.v1`
provenance schema and `fairness_uncertainty.v1` metrics schema. Before download, every selected
run ID (discovered or dispatched) is resolved through the Actions API and must be numeric and match
the exact workflow path, approved event, source repository, branch, SHA, and attempt policy.
Scheduled and nightly intake requires the whole producer workflow to reach `completed/success`
within the bounded poll. The release-only dispatch instead requires the exact-attempt
`WP Evidence (release-grade)` job to complete successfully and admits only the matching active
producer run while the downstream paper is being built. This narrowly bounded exception avoids a
cycle in which the product waits for the paper while the paper waits for the whole product workflow;
a failed job, failed completed run, wrong attempt, wrong SHA, duplicate job name, or unsupported
pending state fails closed. Both reviewed producer workflows run from `main`:
`wp-evidence-nightly.yml` may use `schedule` or `repository_dispatch`, while
`release-evidence.yml` must use `repository_dispatch`. Scheduled discovery additionally binds the
newest run, regardless of status, to the current `fl-bsa@main` ref and repeats that authority check
immediately before artifact consumption; it never substitutes an older green run.
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
The same validator requires every SRG-bearing uncertainty and slice block to name
`conservative_wilson_endpoint_difference`, requires finite protected/reference selection rates,
recomputes the SRG point as protected minus reference, recomputes its bounds from the protected and
reference Wilson endpoints, and binds that method in the provenance manifest and run summary. A
producer may carry a legacy-label correction history only with the exact reviewed JSON-pointer
contract, `interval_values_changed=false`, and a pointer to a validated current-method SRG block.
Legacy, unknown, arithmetically inconsistent, duplicate, malformed, or unbound corrections fail
closed.
The validator itself carries five narrow reviewed empty-baseline/additive schemas: broken
correlation rows and range-violation rows may reference only column names already disclosed by
the tracked certificate, the SRG correction history may appear only on the two reviewed
SRG-bearing artifacts, and `ci_runtime_provenance` may appear in either manifest only with the
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
The fifth schema permits the product's four public ECDSA certificate-signing fields only at a
certificate document's top level and only as a complete set. The validator requires a 128-character
lowercase-hex signature, a 16-character lowercase-hex public-key fingerprint, the exact
`ECDSA-P256-SHA256` algorithm label, and the product signer's UTC ISO timestamp form. Partial,
nested, malformed, or differently labelled signature metadata fails closed.
This is a disclosure-format and bounded-value check, not cryptographic verification. Signature
authenticity and trust-root membership remain the responsibility of the product's release
verification path.

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

Every live intake run uploads `intake/whitepaper_snapshot.json`. Scheduled nightly intake stops at
that receipt and never builds a PDF or arXiv source. For an exact `release-evidence.yml` dispatch,
the same workflow also validates the release tag, product commit, producer run/attempt and artifact
identity, intake snapshot, generator backend, and non-customer-evidence claim boundary. It then
generates the regulatory appendix from every escaped row and column of the exact
`intake/regulatory_matrix.csv`, compiles `release/main.tex` with the digest-pinned TeX image, and
uploads exactly:

- `whitepaper.pdf`
- `whitepaper_release.json`

The manifest binds the PDF digest and visible product, producer-run, whitepaper-commit/run, and
snapshot identities. The product release workflow downloads that exact downstream run, validates
both files, and re-uploads them as a product-bound signing input before the release can proceed.
The release paper remains a demo/evaluation characterization artifact; it is not customer evidence
or a published paper.

This separation is deliberate: the repository's archival document is fixed to v5.0.1, so compiling
it with arbitrary newer or rolling intake would create a mixed-version artifact. The Git snapshot
remains the long-lived intake reproducibility surface, while each current release paper is generated
only from its own exact release-evidence run.

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

The v5.0.1 evidence anchor is whitepaper commit
`8c44075a0c19149905efe377c148579608cfccab`, with intake tree
`b95cd1e8950820236f6e12a737dc87aa9aac5375` and config tree
`86d51b0ee92662bf6470ca0120d41022161423bd`. It binds product tag `v5.0.1`, annotated tag object
`3a0ea6e4faea9d61aabcedebab2a838624fb587d`, peeled commit
`cc32b3a8d13cb75419b0dec1d4b9bdf5a3eb90c2`, and release-evidence run `30765888408` attempt 1.
A later paper-only commit is checked against `publication_inputs.paths` and the projection digest,
not against whole-tree equality; any change to a selected publication input still fails closed.

Producer-side consumers must fetch the descriptor, `scripts/intake_anchor.py`, and the frozen
exporter named by `export.script` from the same reviewed whitepaper commit. They verify the
frozen exporter hash recorded in the descriptor, fetch enough Git history to resolve
`consumer.intake_commit`, run `validate`, and only then run `export`. A future baseline that
needs different export behavior gets a new exporter path; it must not rewrite the stable-v5
exporter. This replaces any bounded "latest N releases" scan. Private-repository access requires
whitepaper Contents read permission. A moving branch name or an unverified downloaded ZIP is
not an equivalent anchor.

See `docs/stable_v5_publication.md` for the PDF/arXiv candidate and publication boundary.
