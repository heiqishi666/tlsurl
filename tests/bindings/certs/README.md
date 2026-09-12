# Public test-only certificates

These keys are intentionally public fixtures for local CI servers. They must never be used for production services or added to a machine trust store.

The server certificate covers `localhost` only, so `127.0.0.1` exercises hostname rejection. The client certificate is for mTLS. Fixtures expire on 2040-01-01; the CA signing key is not retained.

Regenerate with `python tests/bindings/generate_certificates.py` in an environment with `cryptography` installed. Tests require only the generated PEM files and Python/Node standard libraries.
