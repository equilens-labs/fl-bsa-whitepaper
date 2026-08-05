# Stable-v5.0.1 Whitepaper Candidate Path

## Current state

The current stable-v5 characterization anchor is the exact FL-BSA product tag `v5.0.1`, not the
older v5.0.0 evidence line. The source identities are:

- annotated product tag object `3a0ea6e4faea9d61aabcedebab2a838624fb587d`;
- peeled product commit `cc32b3a8d13cb75419b0dec1d4b9bdf5a3eb90c2`;
- release-evidence workflow run `30765888408`, attempt `1`;
- primary Actions artifact `wp-intake-bundle-v4-1`, artifact ID `8838967644`;
- primary artifact API digest
  `sha256:7241da6013653e96337c540d3670bed69c04454002f3e7d315a95e9c8e197615`;
- inner `WhitePaper_Intake_Bundle_v4.zip` SHA-256
  `f6a0bd9390565f7bd852b451e11b7384b1628c24caba02865b1ec94c1e263026`;
- product-to-whitepaper contract SHA-256
  `71da7127165e227c17d854e523f45cecf82f758da95cdcc63b6eaee591a9a214`.

The consumer anchor is `baselines/stable-v5-characterization.json`. It pins intake commit
`4e3071112c6deee1d29239007bfa65c67b6b5a64`, intake tree
`b95cd1e8950820236f6e12a737dc87aa9aac5375`, configuration tree
`98223995a8c3614254d6a99988644d1615591ff8`, and selected-input projection SHA-256
`4ba53f9727cfd80c40f42770edea1d0f61332d58a9ec934d4811df29d764e8ca`.

The deterministic compatibility export has SHA-256
`a60911bf4f720ac046580ea22aad2a182151b10c3ed3dd6cdca5e1035af51468`. It is a Git reconstruction
of the pinned intake/config projection. It is not the original attested producer ZIP; both
identities remain explicit.

This repository state is a review candidate only. It creates no tag, release, merge, public URL,
website update, arXiv submission, customer-evidence authorization, or publication approval.

## Local reviewed candidate

From a clean checkout of the candidate commit:

```bash
python3 -m unittest discover -s tests
make candidate
make arxiv
python3 scripts/intake_anchor.py export \
  --anchor baselines/stable-v5-characterization.json \
  --repo-root . \
  --output dist/stable-v5-intake-compatibility.zip
python3 scripts/validate_public_intake.py \
  --bundle-root /path/to/extracted/stable-v5-intake \
  --schema-root .
```

Review these files as one candidate set:

- `dist/fl-bsa-v5.0.1-characterization-candidate.pdf`;
- `dist/fl-bsa-v5.0.1-companion-evidence.zip`;
- `dist/whitepaper_arxiv_source.zip`; and
- `dist/stable-v5-intake-compatibility.zip`.

The PDF embeds the exact whitepaper commit and companion digest. The arXiv archive includes the
validated generated identity include, so it rebuilds the same source-bound candidate. The companion
contains a standard-library offline verifier; run it before relying on any evidence bytes.

## Optional draft-release staging after owner approval

The workflow has a narrowly scoped, manual path that can attach byte-verified assets to an already
existing unpublished draft release. It does not create a tag or release and does not publish the
draft. Do not invoke it for an unapproved pull request.

Only after the designated owner has reviewed and approved the exact candidate commit, created the
exact whitepaper tag and an unpublished draft release, the authorized operator may dispatch:

```bash
gh workflow run latex.yml --ref v5.0.1 -f draft_release_tag=v5.0.1
```

The dispatch ref, draft tag, and built commit must agree. The workflow refuses duplicate or
byte-different assets, never uses `--clobber`, and records a receipt only after remote bytes are
downloaded and verified. Publishing the draft and submitting to arXiv remain separate human
actions.

## Remaining publication blockers

Public distribution remains blocked until all of the following are resolved or explicitly accepted
by the authorized owners:

1. owner review and approval of the exact PDF, companion, hashes, legal wording, and distribution
   route;
2. a durable public location that co-distributes the PDF and companion;
3. a trusted external digest channel or verifiable release signature;
4. product-side convergence or explicit versioning of the configured-reference and highest-rate
   race policies;
5. confirmation that `customer_evidence_eligible=false`,
   `promotion_evidence_eligible=false`, and `characterization_only` remain appropriate; and
6. additional evidence before making production-utility, near-duplicate privacy, calibration,
   customer-portfolio, deployment-security, or legal-compliance claims.
