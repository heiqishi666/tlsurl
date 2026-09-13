# tlsurl

Rust-powered HTTP client with custom TLS fingerprints, one-step randomized JA3/JA4 configuration, HTTP/2, browser profiles, streaming and WebSocket support.

Development preview (0.1.0).

Prebuilt wheels target CPython 3.10–3.14 on Linux x64/ARM64, Windows x64 and macOS Intel/Apple Silicon. Supported installations do not need Rust or a C/C++ compiler.

Install a published wheel without compiling Rust:

```shell
python -m pip install --only-binary=:all: tlsurl
```

```python
from tlsurl import Client

with Client() as client:
    response = client.get("https://example.com")
    response.raise_for_status()
    print(response.text())
```

Use `AsyncClient` with `async with` for asyncio.

Enable randomized TLS configuration with one option:

```python
with Client(random_tls=True) as client:
    print(client.get("https://example.com").status)
```

Use `random_tls_seed=42` alongside `random_tls=True` to reproduce a configuration in the same library version. A client generates its configuration once; create a new client to generate another. Random mode uses TLS 1.2/1.3 and is mutually exclusive with `tls`, `profile` and `platform`. JA3/JA4 describe the actual ClientHello; this API does not accept arbitrary target hashes or guarantee unique fingerprints.

For manual control, pass `tls={"curves_list": "X25519:P-256", "grease": True}` and configure cipher suites, signature algorithms and ALPN as needed. Browser presets such as `profile="chrome_149"` can also be customized with explicit `tls` and `http2` fields.

Clients reuse connections; close clients and streaming responses when finished. TLS verification is enabled by default and proxies require explicit configuration.

See the [API documentation](https://github.com/heiqishi666/tlsurl/blob/main/docs/native-bindings.md), [platform requirements](https://github.com/heiqishi666/tlsurl/blob/main/docs/platform-support.md) and [validation scope](https://github.com/heiqishi666/tlsurl/blob/main/docs/validation.md).

Based on the Apache-2.0 licensed wreq project. Original notices and licenses are retained in the source repository.
