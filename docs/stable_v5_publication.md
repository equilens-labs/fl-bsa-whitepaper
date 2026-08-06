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
`8c44075a0c19149905efe377c148579608cfccab`, intake tree
`b95cd1e8950820236f6e12a737dc87aa9aac5375`, configuration tree
`86d51b0ee92662bf6470ca0120d41022161423bd`, and selected-input projection SHA-256
`9b40c0e8c8e6291c51b267f38a72c242705895c3269844b37c4b35d23d9526c9`.

The deterministic compatibility export has SHA-256
`09f0f404512f0e7366b1070c654c17d5511253b9765a91fcd1e4e9fe9294b626`. It is a Git reconstruction
of the pinned intake/config projection. It is not the original attested producer ZIP; both
identities remain explicit.

v5.0.1 is security-superseded: its lock pins `cryptography` 49.0.0 in the affected range for
CVE-2026-69247. Annotated successor tag `v5.0.2` exists at tag object
`3d27f7d17c2c853753d40cb883858617ead21677`, peeled commit
`b246e39a23be938397a6d28612c776bedd8b42e2`, and successful release-evidence run `31087235319`;
its lock pins `cryptography` 50.0.0. The v5.0.1 material is therefore archival-only and must not be
presented or staged as a current release.

This repository state is a review candidate only. It creates no tag, release, merge, public URL,
website update, arXiv submission, customer-evidence authorization, or publication approval.

## Local reviewed candidate

From a clean checkout of the candidate commit:

```bash
make publication-candidate
python3 scripts/validate_public_intake.py \
  --bundle-root /path/to/extracted/stable-v5-intake \
  --schema-root .
```

Review these files as one candidate set:

- `dist/fl-bsa-v5.0.1-characterization-candidate.pdf`;
- `dist/fl-bsa-v5.0.1-companion-evidence.zip`;
- `dist/whitepaper_arxiv_source.zip`;
- `dist/stable-v5-intake-compatibility.zip`; and
- `dist/publication-manifest.json`.

The PDF embeds the exact whitepaper commit and companion digest. The arXiv archive includes the
validated generated identity include, so it rebuilds the same source-bound candidate. The companion
contains a standard-library offline verifier; run it before relying on any evidence bytes. The
aggregate build also performs pinned official veraPDF forced-profile preflight. It permits only the
intentionally absent PDF/UA declaration metadata; human assistive-technology review remains
required before any conformance declaration.

## No v5.0.1 draft-release staging

Do not dispatch the workflow's draft-release path for v5.0.1. The path's existence is not release
authorization, and the security-superseded tag cannot be staged as a current release. Any later
archival distribution requires a new, explicit owner decision and current legal/security review.
A current-release paper must instead be separately rebuilt and reviewed against exact v5.0.2
evidence; this v5.0.1 paper and companion cannot be relabelled or reused for that purpose.

## Remaining publication blockers

Public distribution remains blocked until all of the following are resolved or explicitly accepted
by the authorized owners:

1. owner review and approval of the exact PDF, companion, hashes, legal wording, and distribution
   route;
2. an explicit choice to retain the security-superseded v5.0.1 artifact only as an archival
   characterization or retire it in favour of a separately rebuilt v5.0.2 paper;
3. a durable public location that co-distributes the PDF and companion;
4. a trusted external digest channel or verifiable release signature;
5. product-side convergence or explicit versioning of the configured-reference and highest-rate
   race policies;
6. confirmation that `customer_evidence_eligible=false`,
   `promotion_evidence_eligible=false`, and `characterization_only` remain appropriate; and
7. additional evidence before making production-utility, near-duplicate privacy, calibration,
   customer-portfolio, deployment-security, or legal-compliance claims; and
8. human reading-order and screen-reader review, plus an authorized publication-time accessibility
   decision before any formal PDF/UA declaration.
