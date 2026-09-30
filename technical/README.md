# FL-BSA v5.0.8 public technical whitepaper

This source produces the comprehensive public technical paper for FL-BSA v5.0.8. It is aimed at
technical evaluators, model-risk teams, fair-outcomes specialists, security reviewers, and
procurement engineers. The paper covers the selected native generation backend, branch semantics,
statistical estimands, single-run evidence, the predeclared 40-run robustness plan, advisory utility,
evidence integrity, deployment and privacy boundaries, governance interpretation, reproducibility,
limitations, and evaluator checks.

The paper is a `public_technical_characterization` of synthetic/demo evidence. Its evidence
disposition remains `characterization_only` and `customer_evidence_eligible=false`. It does not
establish production utility, legal or compliance certification, regulator approval, Marketplace/GA
authorization, or improved real-world lending outcomes.

## Evidence binding

[`releases/v5.0.8.source-lock.json`](releases/v5.0.8.source-lock.json) fixes:

- product tag, annotated-tag object, and peeled commit;
- release-evidence run, retained source attempt, current successful attempt, and chronology;
- exact producer job IDs and timestamps;
- exact intake and robustness Actions artifact IDs, names, digests, sizes, and expiry;
- reviewed inner intake and robustness-file digests; and
- signed release manifest, attestation, and trust-root record digests.

The product repository owns the separately reviewed source-selection and metadata-correction record.
The official workflow checks that record out at its exact commit and validates its file hash before
using it. It does not search for a latest run or artifact.

## Official build and review set

`.github/workflows/build-public-technical-whitepaper.yml` is manual, restricted to `main` and the
fixed `v5.0.8` selector, and has read-only repository permissions. Cross-repository reads use the
existing `PRODUCER_TOKEN`; the workflow performs no publication or repository write.

After source validation it uploads one review artifact containing:

- `whitepaper.pdf`
- `fl-bsa-v5.0.8-technical-companion.zip`
- `whitepaper_release.json`
- `SHA256SUMS.txt`

The companion contains the exact retained intake, a sanitized 40-run projection, the reviewed source
record and correction, checksums, and a standard-library offline verifier. Raw robustness files and
private runner paths are excluded.

An authorized reviewer can verify a downloaded set without network access:

```bash
sha256sum --check SHA256SUMS.txt
python3 verify_public_technical_companion.py \
  fl-bsa-v5.0.8-technical-companion.zip
```

The verifier is also embedded in the companion. Compare the whole companion digest with the PDF and
sidecar before trusting the embedded copy.

## Local rendering

The official workflow owns source retrieval. After an operator has reproduced its validated
`build/technical/v5.0.8/` directory and companion locally, run:

```bash
make technical-pdf
make technical-verify
```

Local rendering is useful for review. Publication must use the exact official workflow bytes after
the independent content, statistical, visual, accessibility, claim-boundary, and artifact-set
reviews are complete and recorded.
