# tlsurl

Rust-powered HTTP client with TLS and HTTP/2 configuration, browser profiles, streaming and WebSocket support.

Development preview: official package publication is not yet complete.

Prebuilt wheels target CPython 3.10–3.14 on Linux x64/ARM64, Windows x64 and macOS Intel/Apple Silicon. Supported installations do not need Rust or a C/C++ compiler.

```python
from tlsurl import Client

with Client() as client:
    response = client.get("https://example.com")
    response.raise_for_status()
    print(response.text())
```

Use `AsyncClient` with `async with` for asyncio.

Clients reuse connections; close clients and streaming responses when finished. TLS verification is enabled by default and proxies require explicit configuration.

See the [API documentation](https://github.com/heiqishi666/tlsurl/blob/main/docs/native-bindings.md), [platform requirements](https://github.com/heiqishi666/tlsurl/blob/main/docs/platform-support.md) and [validation scope](https://github.com/heiqishi666/tlsurl/blob/main/docs/validation.md).

Based on the Apache-2.0 licensed wreq project. Original notices and licenses are retained in the source repository.
