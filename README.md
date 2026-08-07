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
fails unless the checkout is clean, selects the reviewed demo/evaluation profile, clears LaTeX
auxiliary state, and then embeds the exact whitepaper commit.

```bash
make publication-candidate-repeatability
sha256sum dist/fl-bsa-v5.0.1-characterization-candidate.pdf \
  dist/fl-bsa-v5.0.1-companion-evidence.zip \
  dist/whitepaper_arxiv_source.zip \
  dist/stable-v5-intake-compatibility.zip \
  dist/publication-manifest.json
```

The candidate target copies the reviewed profile from
`profiles/publication_profile.candidate.tex` to the ignored local override, enabling the visible and
machine-readable `DEMO / EVALUATION ONLY` safety marker used by candidate CI and the
publication-manifest gate. The aggregate target rebuilds the PDF, companion, arXiv source,
compatibility export, and hash-bound publication manifest as one sequential handoff set. It also
runs the official veraPDF CLI from a pinned container digest under the explicit UA-1 profile. The
candidate intentionally withholds PDF/UA identification metadata: the preflight accepts exactly
that declaration failure and rejects every substantive UA-1 rule failure. This automated check is
not a substitute for PAC and human assistive-technology review.

## Offline companion verification

The companion contains the exact producer ZIP and release intake, all 21 certificate files (18
distinct canonical-content hash nodes plus three legacy-name aliases), the 40-run Gold robustness
aggregate, the generated utility fixture and ten-seed TSTR result, current regulatory overlay,
interpretation ledger, file manifest, and a standard-library verifier.

```bash
sha256sum dist/fl-bsa-v5.0.1-companion-evidence.zip
mkdir /tmp/flbsa-wp-companion
python3 -m zipfile -e dist/fl-bsa-v5.0.1-companion-evidence.zip \
  /tmp/flbsa-wp-companion
python3 /tmp/flbsa-wp-companion/verify_companion_bundle.py \
  --expected-utility-sha256 \
  2b05a4a2b7ce2d798b9156ed5f837efe890ee87e4f5e914497724802636e4595 \
  --expected-gold-manifest-sha256 \
  353cd77907a5b5b0f64534ce6e5b00defeb872f5a8585aec43006ec24f96e073 \
  --expected-gold-index-sha256 \
  9ffb2c04a95f428f068d471732c7d9ed1e27a16d553749c2ec828907fbe9166c \
  --expected-gold-summary-sha256 \
  15bee5d51c6816e4bd8bffdde3bcb657e5a25932f9742f17496c7a53884858ce \
  dist/fl-bsa-v5.0.1-companion-evidence.zip
```

First compare the whole companion ZIP with the companion digest on the PDF cover; that external
comparison authenticates the bundled verifier and its inputs relative to the PDF. Then copy the
separate utility and three Gold digests from the PDF into the four `--expected-*` arguments. The
verifier consumes those caller-supplied values; it does not read the PDF. It checks every member
hash and size, source identities, bounded claim flags, corrected SRG method, race reference policy,
certificate hashes and predecessor links, and exact robustness completeness and aggregates. The
Gold manifest, index, and merged summary bytes must match their supplied digests before those
aggregates are consumed. For utility, the paper-owned summary bytes must match its supplied digest
before the verifier validates the ten-row structure and recomputes aggregates and skill retention.
The headline characterization must be an exact projection of those anchored layers. The verifier
does not regenerate utility model outputs or independently authenticate the remaining surfaces of a
coherently rewritten ZIP. Certificate signature fields are checked for complete encoding only
because the public verification key is not bundled; the companion therefore claims integrity
linkage, not independent authentication.

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

The exact v5.0.1 lock pins `cryptography` 49.0.0, which is in the affected range for
[CVE-2026-69247](https://github.com/advisories/GHSA-g6cj-pr64-35w5); the fix starts at 50.0.0.
v5.0.1 is therefore security-superseded and must remain unpublished as a current release. The
annotated candidate tag `v5.0.2` (tag object `3d27f7d17c2c853753d40cb883858617ead21677`,
peeled commit `b246e39a23be938397a6d28612c776bedd8b42e2`) is bound to successful release-evidence
run `31087235319` and pins `cryptography` 50.0.0. Its full Release workflow run `31089912581`
nevertheless failed on that same commit, and no v5.0.2 GitHub Release had published as of 6 August
2026. This candidate does not characterize v5.0.2. Publication requires an owner decision either
to preserve this strictly as an archival v5.0.1 characterization or to retire it. Any
current-release paper must wait for, and then be rebuilt against, the exact product tag and evidence
whose full release workflow succeeds and whose release actually publishes; a successor version
must not be guessed while drafting. This paper must never be relabelled or presented as
current-release evidence.

The PDF and companion must be reviewed and distributed together. This candidate has no public
companion URL and is not signed. Public publication requires explicit owner approval, current legal
review, a durable co-distribution route, and a trusted digest or signature channel. The workflows
must not be used to merge a pull request or publish a release without the designated owner's own
review and approval.
