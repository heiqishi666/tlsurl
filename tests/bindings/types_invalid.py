"""Each line below must be rejected by the installed Python type declarations."""
from tlsurl import Client

Client(platform="not-a-platform")
Client(tls={"min_version": "9.9"})
Client().get("https://example.org", timeot_ms=1)
Client().post("https://example.org", body_file=123)
Client().post("https://example.org", multipart=[{"name": "missing-source"}])
