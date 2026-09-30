# FL-BSA v5.0.8 technical companion

The publication companion pairs with the public v5.0.8 technical whitepaper. It contains the exact reviewed whitepaper intake ZIP, the reviewed build/correction decision, a consumer source record, a canonical evidence summary, a sanitized 40-row robustness projection, an offline verifier, and a manifest of member sizes and SHA-256 digests.

Run the included verifier with Python 3:

```bash
python3 verify_public_technical_companion.py fl-bsa-v5.0.8-technical-companion.zip
```

The companion contains no customer data, generated row data, private Gold bundle, private runner path, service log, secret, or signing key. Its evidence disposition is `characterization_only`; customer-evidence eligibility and production-utility establishment are false. The verifier checks byte integrity and evidence semantics. It does not independently validate every vendor ECDSA signature.
