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
  fl-bsa-v5.0.1-companion-evidence.zip
```

The verifier checks every bundled file, reconstructs and hashes the original producer ZIP,
recomputes the fairness arithmetic, validates the exact robustness and utility seed structures and
aggregates, cross-checks the paper-owned characterization summary against those source layers,
traverses the complete certificate graph, and enforces the bounded claim flags. Full utility
regeneration still requires the exact product checkout and recorded third-party runtime.

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

The paper and this ZIP must be distributed together after an authorized publication decision.
This candidate has no public companion URL. Verify the ZIP SHA-256 printed in the PDF against the
delivered file before relying on its contents.
