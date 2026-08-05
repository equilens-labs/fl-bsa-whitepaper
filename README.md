# FL-BSA v5.0.1 Characterization Whitepaper

This repository builds the review candidate, figures, and standalone companion evidence for the
FL-BSA v5.0.1 characterization paper. The candidate is bound to:

- annotated product tag `v5.0.1` (`3a0ea6e4faea9d61aabcedebab2a838624fb587d`);
- peeled product commit `cc32b3a8d13cb75419b0dec1d4b9bdf5a3eb90c2`;
- release-evidence workflow run `30765888408`, attempt `1`; and
- primary intake ZIP SHA-256
  `f6a0bd9390565f7bd852b451e11b7384b1628c24caba02865b1ec94c1e263026`.

Its status is `candidate_not_published` and `characterization_only`. Nothing in the build creates,
publishes, or merges a release.

## Build

Install the locked Python dependencies and a TeX Live distribution that provides `latexmk`, then:

```bash
python3 -m unittest discover -s tests
make pdf
```

Outputs:

- `dist/fl-bsa-v5.0.1-characterization-candidate.pdf`
- `dist/fl-bsa-v5.0.1-companion-evidence.zip`
- compatibility alias `dist/whitepaper.pdf`

`make pdf` regenerates strict intake macros, plots, characterization assets, the deterministic
companion ZIP, and an untracked self-identity include before compiling. Development builds record a
dirty source state. After all tracked generated files are reviewed and committed, `make candidate`
fails unless the checkout is clean and then embeds the exact whitepaper commit.

```bash
printf '\\drafttrue\n' > includes/publication_profile.local.tex
make candidate
sha256sum dist/fl-bsa-v5.0.1-characterization-candidate.pdf \
  dist/fl-bsa-v5.0.1-companion-evidence.zip
```

The ignored publication profile enables the visible and machine-readable
`DEMO / EVALUATION ONLY` safety marker used by candidate CI and the publication-manifest gate.

## Offline companion verification

The companion contains the exact producer ZIP and release intake, all 21 certificate files (18
distinct canonical-content hash nodes plus three legacy-name aliases), the 40-run Gold robustness
aggregate, the generated utility fixture and ten-seed TSTR result, current regulatory overlay,
interpretation ledger, file manifest, and a standard-library verifier.

```bash
mkdir /tmp/flbsa-wp-companion
python3 -m zipfile -e dist/fl-bsa-v5.0.1-companion-evidence.zip \
  /tmp/flbsa-wp-companion
python3 /tmp/flbsa-wp-companion/verify_companion_bundle.py \
  dist/fl-bsa-v5.0.1-companion-evidence.zip
```

The verifier checks every member hash and size, source identities, bounded claim flags, corrected
SRG method, race reference policy, certificate hashes and predecessor links, robustness
completeness, and utility seed completeness. Certificate signature fields are checked for complete
encoding only because the public verification key is not bundled; the companion therefore claims
integrity linkage, not independent authentication.

## Evidence layers

- `intake/`: exact producer-managed v5.0.1 whitepaper intake plus deterministic consumer stamp.
- `evidence/v5.0.1/robustness/`: exact release Gold aggregate and index.
- `evidence/v5.0.1/utility/`: generated fixture, source identity, reproducible TSTR script output.
- `evidence/v5.0.1/publication/`: paper-owned current interpretation, identities, and derived
  characterization. These files do not rewrite producer metrics.
- `companion/`: offline handoff instructions.

The 0.80 AIR line is an internally selected fairness-screening heuristic, not an ECOA or Regulation
B compliance test. ECE is unevaluated, EO is non-informative, and the intrinsic parity result is a
mechanical post-label control rather than a causal conclusion.

## Publication boundary

The PDF and companion must be reviewed and distributed together. This candidate has no public
companion URL and is not signed. Public publication requires explicit owner approval, current legal
review, a durable co-distribution route, and a trusted digest or signature channel. The workflows
must not be used to merge a pull request or publish a release without the designated owner's own
review and approval.
