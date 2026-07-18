# Stable-v5 Whitepaper Publication Path

## Current recorded state

As checked on 2026-07-18, `equilens-labs/fl-bsa-whitepaper` had no GitHub Releases. The producer
repository's `v5.0.0` release and release-evidence run prove the source of the stable-v5 intake;
they do not prove that a whitepaper PDF or arXiv source archive was published from this
repository. This durability repair creates no release or tag in the whitepaper repository and no
arXiv submission or public upload. It did create the separately described private producer-side
archival prerelease solely to retain the original intake bytes.

The producer run `28884829824` did create `wp-intake-bundle-v4`; GitHub still reported that
Actions artifact as non-expired on 2026-07-18, with expiry scheduled for 2026-10-05. It is not
among the assets attached to the producer's immutable `v5.0.0` product Release. The exact original
ZIP is now retained separately in the private producer repository by immutable prerelease
`private-artifact-archive-v5.0.0-whitepaper-intake-20260718` (release `356061977`, asset
`481325251`). Its 85,356-byte asset has SHA-256
`f33b55d32a5bb60b63a53fde583463ac5015d59b0d086f89ac972de45cece063` and is bound to producer
commit `09f6ca91dc9cf92c143559046e4517eb9576182c`. The anchor in this repository therefore no
longer depends on the transient Actions copy for preservation of the original bytes.

That archival prerelease is private retention only. It is not a product release, whitepaper PDF
or arXiv publication, customer delivery or customer-evidence authorization, certification,
Marketplace/go-live approval, or authorization to publish or distribute the asset. The existing
`v5.0.0` product Release remains the producer repository's latest release.

A separate public-assets repository does have a v5-era release:
`equilens-labs/fl-bsa-pub@v5.0.0-rc9-public-fix-2724455`. Its audited asset inventory includes
`whitepaper.pdf` with SHA-256
`2cfc8096d73769185bb0724d0c080408d292651a1bcf94d9b3d9d51863c69c20` and an intake ZIP with
SHA-256 `406679efcc66bab25d03f64baec5634e9f147992c5b122c42338566e1ba346f6`.
That release maps to RC9 evidence commit `272445518e369d99bc350e66d3ab85f4b84121a0`, not the
stable-v5 producer commit `09f6ca91dc9cf92c143559046e4517eb9576182c`, and its inventory does
not contain the arXiv source ZIP. It is evidence of a public RC9 whitepaper, not proof that the
exact stable-v5 PDF/arXiv pair was published.

## Candidate build

The `latex-build` workflow creates ordinary PDF and arXiv artifacts on pushes and pull requests.
When run with `workflow_dispatch`, it additionally writes
`dist/publication-manifest.json` and the reconstructed
`dist/stable-v5-intake-compatibility.zip`, then uploads both as
`stable-v5-publication-candidate-<run_attempt>`. All intermediate Actions artifact names are
attempt-qualified; manual draft staging records their exact artifact IDs and digests in the
receipt. The manifest records:

- the exact whitepaper source commit and source-tree Git object ID;
- the source commit's whole `intake` and `config` tree object IDs for traceability;
- the exact descriptor-selected stable-v5 publication-input projection digest;
- the stable-v5 producer commit, release-evidence run and original bundle digest;
- SHA-256 and byte size for `whitepaper.pdf`, `whitepaper_arxiv_source.zip`, and the compatibility
  intake ZIP; the frozen exporter path/hash and both original/reconstructed ZIP hashes; and
- the `DEMO / EVALUATION ONLY`, characterization-only claim boundary.

The historical evidence anchor remains intake commit
`a451eae4284c4c592783f108e206e5ba1c0e5747` and its exact whole-tree OIDs. Publication binding is
narrower: the descriptor selects the current evidence/config files that feed or substantiate
the stable-v5 paper—including the repository-owned model-hyperparameter input—and hashes their
Git object projection. `intake/archive/` is explicitly
excluded. The archival cleanup merged as PR #26 therefore records a different whole intake-tree
OID but retains the same selected-input digest. Manifest creation still compares the current
manifest bytes with the pinned hash, and any selected input change fails closed.

For a local candidate build:

```bash
printf '\\drafttrue\n' > includes/publication_profile.local.tex
make pdf
make arxiv
python3 scripts/intake_anchor.py export \
  --anchor baselines/stable-v5-characterization.json \
  --repo-root . \
  --output dist/stable-v5-intake-compatibility.zip
python3 scripts/build_publication_manifest.py \
  --whitepaper-commit "$(git rev-parse HEAD)" \
  --publication-status candidate_not_published \
  --compatibility-intake dist/stable-v5-intake-compatibility.zip
```

`build_publication_manifest.py` invokes `pdftotext` and fails unless the rendered PDF contains
the required marker. It also requires `--whitepaper-commit` to equal the checked-out `HEAD` and
fails on tracked or non-ignored untracked checkout changes. The arXiv packager admits tracked Git
members plus only the exact reviewed generated watermark profile and bibliography bytes; a stray
suffix-allowed file cannot enter the archive. Remove the ignored local profile file after the
candidate review if an unmarked local development build is desired.

Review `dist/whitepaper.pdf`, `dist/whitepaper_arxiv_source.zip`,
`dist/stable-v5-intake-compatibility.zip`, and `dist/publication-manifest.json` together. The
manifest is a hash-bound candidate record, not a publication receipt. The compatibility ZIP at
`42bcdcc72043a9ddd70f1821cf88b2c9963d34bd8f4444ee3b4093ed34276060` is a deterministic Git
projection, not the original attested producer ZIP at
`f33b55d32a5bb60b63a53fde583463ac5015d59b0d086f89ac972de45cece063`.

## Authorized GitHub release path

If an authorized operator separately decides to prepare a whitepaper GitHub Release tagged
`v5.0.0`, they first create the exact tag and save the release as a draft. They then manually run
`gh workflow run latex.yml --ref v5.0.0 -f draft_release_tag=v5.0.0`. Both the dispatch ref and
the input must name the exact tag; a dispatch from `main` is rejected so the recorded Actions
head SHA and the built/tagged commit cannot diverge. The workflow checks that exactly one release with
that tag exists, remains a mutable unpublished draft, and resolves to the exact commit it built.
It stages the PDF, arXiv source, and distinctly named compatibility intake ZIP. Release-asset
enumeration is paginated; duplicate names fail, existing same-named assets must be byte-identical,
and the workflow never overwrites a mismatch. Only after all three remote assets are downloaded
and hash-verified does it stage `stable-v5-publication-receipt.json` with
`publication_status=github_draft_release_assets_staged_characterization_only`.

If staging fails, the operator must use **Re-run all jobs** or create a new dispatch from the exact
tag. **Re-run failed jobs** is deliberately rejected because it can reuse artifacts from an older
run attempt while the release job runs under a newer attempt. A preserved receipt is API-bound to
the exact successful `build` job and its unexpired artifacts, so a later failure in the staging job
does not invalidate build provenance.

Creating the tag/release and publishing the verified draft are deliberately separate operator
actions outside this workflow and outside this repair. This draft-first sequence remains
compatible with GitHub release immutability because no assets are attached after publication.

The build job is read-only. A separate manual draft-staging job downloads the already-built
candidates and alone receives `contents: write`; every action in that path is pinned to a full
commit SHA. Per-tag concurrency serializes staging attempts.

An arXiv submission remains a separate human publication action. The generated source ZIP and
manifest do not assert an arXiv identifier, submission, acceptance, endorsement, legal or
compliance certification, regulator approval, customer-evidence eligibility, or production
readiness.

## Decision gate

Before any publication action, the operator must choose and record the exact whitepaper commit,
review the rendered artifact and claim boundary, and verify all artifact hashes. Exact-stable
publication also remains blocked until the SRG interval-method disposition tracked by product issue
`#1535` is resolved or explicitly waived by the authorized claims/release owners. If the
source commit does not carry the pinned stable-v5 publication-input projection, create a new
explicitly named baseline rather than weakening or repointing this one. A whole-tree difference
confined to `intake/archive/` is traceability metadata and does not require a new evidence
baseline.
