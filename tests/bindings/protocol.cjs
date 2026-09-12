const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { Client } = require(process.argv[2])
const ports = JSON.parse(process.argv[3])
const read = name => fs.readFileSync(path.join(__dirname, 'certs', name), 'utf8')
const caPem = read('ca.pem')

async function main() {
  const normal = `https://localhost:${ports.normal}`
  const client = new Client({ caPem })
  let response = await client.get(normal)
  assert.equal(response.httpVersion, '2')
  assert.equal(response.json().alpn, 'h2')
  await assert.rejects(new Client(2000).get(normal))
  await assert.rejects(client.get(`https://127.0.0.1:${ports.normal}`))
  response = await new Client({ caPem, tls: { alpn: ['http/1.1'], minVersion: '1.2', maxVersion: '1.2',
    cipherList: 'ECDHE-RSA-AES128-GCM-SHA256', curvesList: 'P-256' } }).get(normal)
  assert.equal(response.httpVersion, '1.1')
  assert.equal(response.json().tlsVersion, 'TLSv1.2')
  assert.equal(response.json().cipher, 'ECDHE-RSA-AES128-GCM-SHA256')
  await assert.rejects(new Client({ timeoutMs: 2000, caPem, tls: { minVersion: '1.3' } }).get(`https://localhost:${ports.tls12}`))
  assert.throws(() => new Client({ tls: { minVersion: '1.3', maxVersion: '1.2' } }), /INVALID_CONFIG/)
  assert.throws(() => new Client({ http2: { maxFrameSize: 1 } }), /INVALID_CONFIG/)
  assert.throws(() => new Client({ tls: { alpn: ['h3'] } }), /INVALID_CONFIG/)
  const order = ['method', 'path', 'authority', 'scheme']
  const details = (await new Client({ caPem, http2: { initialWindowSize: 777777, headerTableSize: 1234,
    enablePush: false, pseudoOrder: order } }).get(normal)).json()
  assert.equal(details.settings.initialWindowSize, 777777)
  assert.equal(details.settings.headerTableSize, 1234)
  assert.equal(details.settings.enablePush, false)
  assert.deepEqual(details.headers.filter(h => h.startsWith(':')), order.map(h => ':' + h))
  const mtls = `https://localhost:${ports.mtls}`
  await assert.rejects(new Client({ timeoutMs: 2000, caPem }).get(mtls))
  assert.equal((await new Client({ caPem, identity: { certificatePem: read('client.pem'),
    privateKeyPem: read('client-key.pem') } }).get(mtls)).json().authorized, true)
  console.log('Node TLS trust, hostname, version, ALPN, cipher, mTLS and HTTP/2 wire checks passed')
}
main().catch(error => { console.error(error); process.exitCode = 1 })
