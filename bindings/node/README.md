# tlsurl

Rust-powered HTTP client with TLS and HTTP/2 configuration, browser profiles, streaming and WebSocket support.

Development preview: 0.1.0.

Install from the npm registry:

```sh
npm install tlsurl
```

Prebuilt native packages target Node.js 22/24 on Linux x64/ARM64, Windows x64 and macOS Intel/Apple Silicon. Supported installations do not need Rust or a C/C++ compiler.

```javascript
import { Client } from 'tlsurl'

const client = new Client()
try {
  const response = await client.get('https://example.com')
  response.raiseForStatus()
  console.log(response.text())
} finally {
  client.close()
}
```

Requests return Promises. CommonJS and ES modules are supported. Keep optional dependencies enabled so npm can install the matching native package.

Clients reuse connections; close clients and streaming responses when finished. TLS verification is enabled by default and proxies require explicit configuration.

See the [API documentation](https://github.com/knight-bili/tlsurl/blob/main/docs/native-bindings.md), [platform requirements](https://github.com/knight-bili/tlsurl/blob/main/docs/platform-support.md) and [validation scope](https://github.com/knight-bili/tlsurl/blob/main/docs/validation.md).

Based on the Apache-2.0 licensed wreq project. Original notices and licenses are retained in the source repository.
