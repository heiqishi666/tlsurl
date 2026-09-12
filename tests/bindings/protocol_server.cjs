// Loopback-only fixture; all keys are intentionally public test data.
const http2 = require('node:http2')
const fs = require('node:fs')
const path = require('node:path')
const certs = path.join(__dirname, 'certs')
const material = {
  key: fs.readFileSync(path.join(certs, 'server-key.pem')),
  cert: fs.readFileSync(path.join(certs, 'server.pem')),
  ca: fs.readFileSync(path.join(certs, 'ca.pem')),
  allowHTTP1: true,
}

function serve(options) {
  return new Promise(resolve => {
    const server = http2.createSecureServer({ ...material, ...options })
    server.on('tlsClientError', () => {})
    server.on('sessionError', () => {})
    server.on('request', (req, res) => {
      req.resume()
      const body = JSON.stringify({
        tlsVersion: req.socket.getProtocol(), alpn: req.socket.alpnProtocol,
        authorized: req.socket.authorized, httpVersion: req.httpVersion,
        cipher: req.socket.getCipher().name, headers: Object.keys(req.headers),
        userAgent: req.headers['user-agent'],
        settings: req.stream?.session.remoteSettings,
      })
      res.writeHead(200, { 'content-type': 'application/json', 'content-length': Buffer.byteLength(body) })
      res.end(body)
    })
    server.listen(0, '127.0.0.1', () => resolve(server.address().port))
  })
}

Promise.all([
  serve({}), serve({ requestCert: true, rejectUnauthorized: true }),
  serve({ minVersion: 'TLSv1.2', maxVersion: 'TLSv1.2' }),
]).then(([normal, mtls, tls12]) => console.log(JSON.stringify({ normal, mtls, tls12 })))
