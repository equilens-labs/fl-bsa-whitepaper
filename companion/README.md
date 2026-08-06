# FL-BSA v5.0.1 whitepaper companion evidence

This companion is the offline verification surface for the candidate FL-BSA v5.0.1
characterization whitepaper. It is not customer evidence, a product release authorization,
a legal opinion, or a publication event.

The bundle contains the original producer ZIP byte-for-byte at
`producer/WhitePaper_Intake_Bundle_v4.zip`, a consumer-stamped projection in `intake/`, and the
exact release Gold robustness aggregates in `evidence/v5.0.1/robustness/`. Paper-owned
interpretation corrections, the current-as-of regulatory mapping, and the synthetic-fixture
utility study are separate under `evidence/v5.0.1/publication/` and
`evidence/v5.0.1/utility/`; they do not rewrite producer bytes.

From a directory containing the delivered ZIP, first compare its SHA-256 with the digest printed
in the PDF. Only after that check, extract the bundled verifier and run it against the original
ZIP:

```text
sha256sum fl-bsa-v5.0.1-companion-evidence.zip
mkdir fl-bsa-v5.0.1-companion-evidence
python3 -m zipfile -e fl-bsa-v5.0.1-companion-evidence.zip \
  fl-bsa-v5.0.1-companion-evidence
python3 fl-bsa-v5.0.1-companion-evidence/verify_companion_bundle.py \
  --expected-utility-sha256 \
  2b05a4a2b7ce2d798b9156ed5f837efe890ee87e4f5e914497724802636e4595 \
  --expected-gold-manifest-sha256 \
  353cd77907a5b5b0f64534ce6e5b00defeb872f5a8585aec43006ec24f96e073 \
  --expected-gold-index-sha256 \
  9ffb2c04a95f428f068d471732c7d9ed1e27a16d553749c2ec828907fbe9166c \
  --expected-gold-summary-sha256 \
  15bee5d51c6816e4bd8bffdde3bcb657e5a25932f9742f17496c7a53884858ce \
  fl-bsa-v5.0.1-companion-evidence.zip
```

The verifier checks every bundled file, reconstructs and hashes the original producer ZIP,
recomputes the fairness arithmetic, validates the exact robustness seed structure and aggregates,
traverses the complete certificate graph, and enforces the bounded claim flags. Before consuming
Gold, it requires the exact evidence manifest, robustness index, and merged summary bytes to match
the three SHA-256 values supplied on the command line. For utility, it
requires the exact `utility_summary.json` bytes to match its supplied SHA-256, then validates the
ten-row structure and recomputes aggregates and skill retention from those rows. Copy all four
values from the trusted
PDF; the verifier does not read the PDF. It cross-checks the paper-owned characterization summary
against those anchored layers. It does not regenerate generator outputs or model predictions, and
it cannot independently authenticate the remaining surfaces of a coherently rewritten ZIP; the
preceding whole-ZIP digest comparison is the bundle-wide external trust step. Full utility
regeneration requires the exact product checkout and recorded third-party runtime.

The `customer_evidence_eligible=false` publication boundary is in
`intake/archive/v5.0.1-release-30765888408.json` and independently in
`evidence/v5.0.1/robustness/robustness_gate_disposition.json`; it is not a field in
`intake/pack_intent.json`.

The verifier requires only Python 3.11 or newer. To reproduce the optional utility study, use an
exact checkout of product tag `v5.0.1` and an environment containing the product dependencies plus
scikit-learn, then run:

```text
python3 scripts/evaluate_fixture_utility.py \
  --product-root /path/to/exact-v5.0.1-checkout \
  --fixture evidence/v5.0.1/utility/balanced_fixture.csv.gz \
  --output /tmp/utility_summary.json
```

This companion remains an archival candidate, not a current release: exact v5.0.1 pins
`cryptography` 49.0.0 in the affected range for
[CVE-2026-69247](https://github.com/advisories/GHSA-g6cj-pr64-35w5). It must remain unpublished
unless the owner expressly approves archival characterization. The annotated candidate tag
`v5.0.2` (tag object `3d27f7d17c2c853753d40cb883858617ead21677`, peeled commit
`b246e39a23be938397a6d28612c776bedd8b42e2`) is bound to successful release-evidence run
`31087235319` and pins `cryptography` 50.0.0, but full Release workflow run `31089912581` failed on
that same commit and no v5.0.2 GitHub Release had published as of 6 August 2026. This companion does
not contain or characterize v5.0.2 evidence and must never be relabelled as v5.0.2. Any
current-release replacement must be separately rebuilt against whichever exact product tag both
completes the full release workflow and actually publishes, not a successor named in advance.

The paper and this ZIP must be distributed together after an authorized publication decision.
This candidate has no public companion URL. Verify the ZIP SHA-256 printed in the PDF against the
delivered file before relying on its contents.
