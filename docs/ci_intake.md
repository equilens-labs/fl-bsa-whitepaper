# Intake Pull CI — Cross-Repo Automation

This repository consumes one release-bound whitepaper intake bundle from
`equilens-labs/fl-bsa`. The product's `release-evidence.yml` workflow is the sole reviewed
producer, and `wp-intake-ready` repository dispatch is the sole trigger. There is no daily timer,
latest-run search, arbitrary manual selector, compatibility artifact fallback, or Git/PR persistence
path.

The consumer uploads an exact JSON receipt and builds the version-bound release paper. It never
rewrites the fixed archival v5.0.1 paper, publishes a paper, or widens the
`customer_evidence_eligible=false` claim boundary.

## Trigger and authority

After uploading and attesting its attempt-qualified intake artifact, Release Evidence sends this
shape:

```json
{
  "event_type": "wp-intake-ready",
  "client_payload": {
    "producer_repo": "equilens-labs/fl-bsa",
    "workflow_file": "release-evidence.yml",
    "branch": "main",
    "artifact_name": "wp-intake-bundle-v4-<run-attempt>",
    "producer_run_id": "<exact-run-id>",
    "producer_run_attempt": "<exact-run-attempt>",
    "artifact_id": "<exact-actions-artifact-id>",
    "artifact_digest": "sha256:<exact-actions-artifact-digest>",
    "producer_contract_sha256": "<exact-shared-contract-sha256>",
    "persist_intake_pr": "false"
  }
}
```

`contracts/whitepaper-intake-producer-contract.v1.json` is copied byte-for-byte into both
repositories. Both sides require the exact repository, `release-evidence.yml`, `main`,
`repository_dispatch`, payload fields, attempt-qualified artifact name, contract digest, and
literal `persist_intake_pr=false`. A missing or extra field, retired workflow, timer event, branch
drift, malformed identity, or contract mismatch fails before the consumer queries producer state.

The consumer does not search workflow history. It resolves only the dispatched run ID and attempt,
checks the exact workflow path/repository/branch/head/event through the Actions API, and polls only
the exact-attempt `WP Evidence (release-grade)` job. That job must complete successfully. This
bounded active-run rule breaks the product/whitepaper dependency cycle without treating the whole
still-running Release Evidence workflow as successful. A failed completed run or job, duplicate job,
wrong attempt, unsupported pending state, or timeout fails closed.

## Authentication

`PRODUCER_TOKEN` must be a GitHub App installation token or fine-grained PAT scoped to
`equilens-labs/fl-bsa` with Actions read, Contents read, and Attestations read. The consumer fails
when cross-repository authorization is absent; it does not substitute the whitepaper repository's
token. Do not grant Packages, administration, or write access, and never put a token in a dispatch
payload, artifact, receipt, or tracked file.

## Consumption and validation

The workflow downloads `WhitePaper_Intake_Bundle_v4.zip` and verifies its GitHub artifact
attestation against `equilens-labs/fl-bsa`. Only the exact attempt-qualified primary bundle is
accepted; duplicate or missing artifacts fail closed. It validates the `wp-intake.v1` provenance
schema and current-release `fairness_uncertainty.v2` metrics schema; the checked-in v1 intake
remains a historical baseline. Before download, the dispatched run ID is
resolved through the Actions API and must match the exact workflow path, approved event, source
repository, branch, SHA, and attempt policy. The exact-attempt `WP Evidence (release-grade)` job
must complete successfully; a failed job, failed completed run, wrong attempt, wrong SHA, duplicate
job name, or unsupported pending state fails closed.

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
A legitimate producer schema expansion therefore requires either a reviewed public baseline
change or a narrow explicit extension schema in this repository before the corresponding private
data can cross the boundary.
The same validator requires every SRG-bearing uncertainty and slice block to name
`conservative_wilson_endpoint_difference`, requires finite protected/reference selection rates,
recomputes the SRG point as protected minus reference, recomputes its bounds from the protected and
reference Wilson endpoints, and binds that method in the provenance manifest and run summary. A
producer may carry a legacy-label correction history only with the exact reviewed JSON-pointer
contract, `interval_values_changed=false`, and a pointer to a validated current-method SRG block.
Legacy, unknown, arithmetically inconsistent, duplicate, malformed, or unbound corrections fail
closed.
The validator itself carries narrow reviewed empty-baseline/additive schemas: broken
correlation rows and range-violation rows may reference only column names already disclosed by
the tracked certificate, the SRG correction history may appear only on the two reviewed
SRG-bearing artifacts, and the count-derived race fields `configured_protected_groups`,
`unknown_treatment`, `suppressed_groups`, `verdict_scope`, and `status_caveat` may appear only at
their reviewed metrics, AIR-status, and run-summary AIR paths with their exact structural shapes.
The product-side race evidence contract remains the semantic and source-binding authority for
those fields.
`ci_runtime_provenance` may appear in either manifest only with the exact
`wp.ci_runtime_provenance.v2` bounded product-CI
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
A separate reviewed schema permits the product's four public ECDSA certificate-signing fields only
at a certificate document's top level and only as a complete set. The validator requires a
128-character lowercase-hex signature, a 16-character lowercase-hex public-key fingerprint, the
exact `ECDSA-P256-SHA256` algorithm label, and the product signer's UTC ISO timestamp form. Partial,
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

Every intake run uploads `intake/whitepaper_snapshot.json` and validates the release tag, product
commit, producer run/attempt and artifact
identity, intake snapshot, generator backend, and non-customer-evidence claim boundary. It then
generates the regulatory appendix from every escaped row and column of the exact
`intake/regulatory_matrix.csv`, compiles `release/main.tex` with the digest-pinned TeX image, and
rejects material horizontal overflow from the completed TeX log. The post-compile validator also
requires the full visible eligibility, disposition, and publication-status tokens in the PDF text
layer, tolerating only extractor whitespace introduced at visible line wraps. It then uploads
exactly:

- `whitepaper.pdf`
- `whitepaper_release.json`

The bundle is rejected before staging unless `metrics_long.csv`, `selection_rates.csv`, and
`regulatory_matrix.csv` are present alongside the other required intake members. Regulatory cells
must be non-empty ASCII text: the release path uses reviewed pdfLaTeX/T1 rendering, so unsupported
Unicode fails at intake rendering instead of failing later in the release cut. The ordinary
pull-request/push `latex-build` workflow also generates deterministic smoke identity inputs and
compiles `release/main.tex`, applies the same layout and visible-claim checks, and does not upload
that smoke PDF as release evidence.

The manifest binds the PDF digest and visible product, producer-run, whitepaper-commit/run, and
snapshot identities. The product release workflow downloads that exact downstream run, validates
both files, and re-uploads them as a product-bound signing input before the release can proceed.
The release paper remains a demo/evaluation characterization artifact; it is not customer evidence
or a published paper.

This separation is deliberate: the repository's archival document is fixed to v5.0.1, so compiling
it with arbitrary newer intake would create a mixed-version artifact. Each current release paper is
generated only from its own exact Release Evidence run and retained as an Actions artifact.

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
